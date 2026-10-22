# eBay Scraper

`ebay-dl.py` is a command-line program that downloads the first 10 pages of eBay search results for a search term, uses Beautiful Soup to extract every listing, and saves the listings as a JSON file named after the search term (for example, `garden tools.json`).

Each listing is saved as a dictionary with these keys:

| Key | Type | Meaning |
|---|---|---|
| `name` | string | the item's title |
| `price` | integer | price in cents (the lower price if a range is listed) |
| `status` | string | the item's condition, e.g. `Brand New`, `Pre-Owned`, `Refurbished` |
| `shipping` | integer | shipping cost in cents (`0` for free shipping) |
| `free_returns` | boolean | whether the item has free returns |
| `items_sold` | integer | number of items sold |

If a listing is missing a field, the key is kept and its value is `null`.

## Setup

```
python -m pip install requests beautifulsoup4
```

## Generating the files in this repo

The three JSON files in this repo were generated from the artificial listings in the course's `practice-pages` folder, because eBay blocks automated requests. The practice listings are the same for every search term; only the output filename changes.

```
python ebay-dl.py --search "garden tools" --pages-dir practice-pages
python ebay-dl.py --search "drill press" --pages-dir practice-pages
python ebay-dl.py --search "mechanical keyboard" --pages-dir practice-pages
```

To scrape live eBay results instead, leave off `--pages-dir`:

```
python ebay-dl.py --search "garden tools"
```

## CSV output (extra credit)

Add the `--csv` flag to save a CSV file (e.g. `garden tools.csv`) instead of JSON. The three CSV files in this repo were generated with:

```
python ebay-dl.py --search "garden tools" --pages-dir practice-pages --csv
python ebay-dl.py --search "drill press" --pages-dir practice-pages --csv
python ebay-dl.py --search "mechanical keyboard" --pages-dir practice-pages --csv
```

## Course project

This is Project 2 for CSCI 40: [Project 2: Scraping eBay](https://csci40.rtealwitter.com/projects/02_webscraping/project.html).
