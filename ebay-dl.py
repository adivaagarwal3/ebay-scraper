"""
ebay-dl.py: scrape the first 10 pages of eBay search results for a search
term and save the listings as JSON (or CSV with --csv).

Usage:
    python ebay-dl.py --search "garden tools"
    python ebay-dl.py --search "garden tools" --pages-dir practice-pages
    python ebay-dl.py --search "garden tools" --csv
"""

import argparse
import csv
import json
import os
import re
import time

import requests
from bs4 import BeautifulSoup

NUM_PAGES = 10
FIELDS = ['name', 'price', 'status', 'shipping', 'free_returns', 'items_sold']

# eBay has used two listing layouts; support both.
ITEM_SELECTORS = ['li.s-item', 'li.s-card', 'div.s-item', 'div.s-card']
TITLE_SELECTORS = ['.s-item__title', '.s-card__title']
PRICE_SELECTORS = ['.s-item__price', '.s-card__price']
STATUS_SELECTORS = ['.SECONDARY_INFO', '.s-item__subtitle', '.s-card__subtitle']
SHIPPING_SELECTORS = ['.s-item__shipping', '.s-item__logisticsCost',
                      '.s-item__freeXDays', '.s-card__shipping']
RETURNS_SELECTORS = ['.s-item__free-returns', '.s-item__freeReturnsNoFee',
                     '.s-card__free-returns']
SOLD_SELECTORS = ['.s-item__quantitySold', '.s-item__hotness',
                  '.s-item__additionalItemHotness', '.s-card__sold']

STATUS_WORDS = [
    'Brand New', 'Pre-Owned', 'Pre-owned', 'Refurbished',
    'Certified - Refurbished', 'Excellent - Refurbished',
    'Very Good - Refurbished', 'Good - Refurbished', 'Seller refurbished',
    'Open Box', 'New (Other)', 'New', 'Used', 'For parts or not working',
]


def parse_cents(text):
    """
    Convert the first dollar amount in text to an integer number of cents.
    Returns None if there is no dollar amount.

    >>> parse_cents('$11.95')
    1195
    >>> parse_cents('$12.50 to $18.00')
    1250
    >>> parse_cents('+$4.25 shipping')
    425
    >>> parse_cents('$1,234.5')
    123450
    >>> parse_cents('$7')
    700
    >>> parse_cents('Free shipping') is None
    True
    """
    match = re.search(r'\$\s*([\d,]+)(?:\.(\d{1,2}))?', text)
    if match is None:
        return None
    dollars = int(match.group(1).replace(',', ''))
    cents_text = (match.group(2) or '0').ljust(2, '0')
    return dollars * 100 + int(cents_text)


def parse_shipping(text):
    """
    Convert a shipping description to cents; free shipping is 0.

    >>> parse_shipping('Free shipping')
    0
    >>> parse_shipping('Free delivery in 2-4 days')
    0
    >>> parse_shipping('+$4.25 shipping')
    425
    >>> parse_shipping('Shipping not specified') is None
    True
    """
    if re.search(r'\bfree\b', text, re.IGNORECASE):
        return 0
    return parse_cents(text)


def parse_items_sold(text):
    """
    Extract the number of items sold from text.

    >>> parse_items_sold('1,203 sold')
    1203
    >>> parse_items_sold('25+ sold')
    25
    >>> parse_items_sold('Almost gone') is None
    True
    """
    match = re.search(r'([\d,]+)\+?\s*sold', text, re.IGNORECASE)
    if match is None:
        return None
    return int(match.group(1).replace(',', ''))


def first_text(item, selectors):
    """Return the stripped text of the first element matching any selector."""
    for selector in selectors:
        tag = item.select_one(selector)
        if tag is not None:
            text = tag.get_text(' ', strip=True)
            if text:
                return text
    return None


def clean_name(text):
    """
    Remove eBay's screen-reader and banner text from a title.

    >>> clean_name('New Listing Garden Trowel Opens in a new window or tab')
    'Garden Trowel'
    """
    text = re.sub(r'^New Listing\s*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\s*Opens in a new window or tab\s*$', '', text,
                  flags=re.IGNORECASE)
    return text.strip()


def find_status(item):
    text = first_text(item, STATUS_SELECTORS)
    if text is None:
        return None
    # The subtitle can hold extra text ("Pre-Owned · Apple"); keep the condition.
    for word in STATUS_WORDS:
        if re.search(r'(?<![\w-])' + re.escape(word) + r'(?![\w-])', text):
            return word if len(text) > 40 or '·' in text else text
    return text


def find_shipping(item):
    text = first_text(item, SHIPPING_SELECTORS)
    if text is not None:
        return parse_shipping(text)
    # Fall back to any text fragment that mentions shipping or delivery.
    for fragment in item.stripped_strings:
        if re.search(r'shipping|delivery|postage', fragment, re.IGNORECASE):
            cents = parse_shipping(fragment)
            if cents is not None:
                return cents
    return None


def find_free_returns(item):
    if first_text(item, RETURNS_SELECTORS) is not None:
        return True
    return 'free returns' in item.get_text(' ', strip=True).lower()


def find_items_sold(item):
    text = first_text(item, SOLD_SELECTORS)
    if text is not None:
        sold = parse_items_sold(text)
        if sold is not None:
            return sold
    return parse_items_sold(item.get_text(' ', strip=True))


def extract_items(html):
    """
    Extract every listing from one page of eBay search results.

    >>> html = '''
    ... <ul>
    ...  <li class="s-item">
    ...   <div class="s-item__title"><span>Shop on eBay</span></div>
    ...   <span class="s-item__price">$20.00</span>
    ...  </li>
    ...  <li class="s-item">
    ...   <div class="s-item__title"><span>Steel Trowel</span></div>
    ...   <span class="SECONDARY_INFO">Brand New</span>
    ...   <span class="s-item__price">$11.95</span>
    ...   <span class="s-item__shipping">Free shipping</span>
    ...   <span class="s-item__free-returns">Free returns</span>
    ...   <span class="s-item__hotness">1,024 sold</span>
    ...  </li>
    ...  <li class="s-item">
    ...   <div class="s-item__title"><span>Mystery Seeds</span></div>
    ...  </li>
    ... </ul>'''
    >>> items = extract_items(html)
    >>> len(items)
    2
    >>> items[0]
    {'name': 'Steel Trowel', 'price': 1195, 'status': 'Brand New', 'shipping': 0, 'free_returns': True, 'items_sold': 1024}
    >>> items[1]
    {'name': 'Mystery Seeds', 'price': None, 'status': None, 'shipping': None, 'free_returns': False, 'items_sold': None}
    """
    soup = BeautifulSoup(html, 'html.parser')

    listings = []
    for selector in ITEM_SELECTORS:
        listings = soup.select(selector)
        if listings:
            break

    items = []
    for listing in listings:
        name = first_text(listing, TITLE_SELECTORS)
        if name is not None:
            name = clean_name(name)
        # eBay inserts a placeholder "Shop on eBay" card at the top of results.
        if not name or name.lower() == 'shop on ebay':
            continue

        price_text = first_text(listing, PRICE_SELECTORS)
        items.append({
            'name': name,
            'price': parse_cents(price_text) if price_text else None,
            'status': find_status(listing),
            'shipping': find_shipping(listing),
            'free_returns': find_free_returns(listing),
            'items_sold': find_items_sold(listing),
        })
    return items


def looks_like_robot_check(html):
    lowered = html.lower()
    return any(phrase in lowered for phrase in [
        'pardon our interruption', 'verify yourself', 'are you a robot',
        'captcha', 'checking your browser',
    ])


def download_page(search, page_number):
    response = requests.get(
        'https://www.ebay.com/sch/i.html',
        params={'_nkw': search, '_pgn': page_number},
        headers={'User-Agent': 'Mozilla/5.0'},
        timeout=10,
    )
    response.raise_for_status()
    return response.text


def read_page(pages_dir, page_number):
    path = os.path.join(pages_dir, f'page-{page_number}.html')
    with open(path, encoding='utf-8') as f:
        return f.read()


def save_json(items, filename):
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(items, f, indent=2)


def save_csv(items, filename):
    with open(filename, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(items)


def main():
    parser = argparse.ArgumentParser(
        description='Download eBay search results and save them as JSON.')
    parser.add_argument('search_term', nargs='?',
                        help='the search term (alternative to --search)')
    parser.add_argument('--search', help='the search term')
    parser.add_argument('--pages-dir',
                        help='read page-1.html ... page-10.html from this '
                             'folder instead of downloading from eBay')
    parser.add_argument('--csv', action='store_true',
                        help='save as CSV instead of JSON')
    args = parser.parse_args()

    search = args.search if args.search is not None else args.search_term
    if not search:
        parser.error('a search term is required, e.g. --search "garden tools"')

    all_items = []
    for page_number in range(1, NUM_PAGES + 1):
        if args.pages_dir is not None:
            html = read_page(args.pages_dir, page_number)
        else:
            if page_number > 1:
                time.sleep(1)  # be polite between requests
            try:
                html = download_page(search, page_number)
            except requests.exceptions.RequestException as error:
                print(f'Stopping at page {page_number}: {error}')
                print('Try again with --pages-dir practice-pages')
                break

        items = extract_items(html)
        if not items and looks_like_robot_check(html):
            print(f'Page {page_number} is a robot check; stopping live requests.')
            print('Try again with --pages-dir practice-pages')
            break
        print(f'page {page_number}: {len(items)} items')
        all_items.extend(items)

    extension = 'csv' if args.csv else 'json'
    filename = f'{search}.{extension}'
    if args.csv:
        save_csv(all_items, filename)
    else:
        save_json(all_items, filename)
    print(f'Saved {len(all_items)} items to {filename}')


if __name__ == '__main__':
    main()
