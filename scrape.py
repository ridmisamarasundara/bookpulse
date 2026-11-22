import requests, time, json
from bs4 import BeautifulSoup

BASE = "https://books.toscrape.com/catalogue/"

def get_soup(url):
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    r.encoding = "utf-8"          # avoids "Â£" garbage in prices
    return BeautifulSoup(r.text, "html.parser")

def book_links(page):
    soup = get_soup(f"{BASE}page-{page}.html")
    return [BASE + a["href"] for a in soup.select("article.product_pod h3 a")]

def parse_book(url):
    s = get_soup(url)
    desc = s.select_one("#product_description + p")
    return {
        "title": s.h1.text,
        "price": s.select_one("p.price_color").text,
        "rating": s.select_one("p.star-rating")["class"][1],
        "category": s.select("ul.breadcrumb li a")[2].text,
        "stock": s.select_one("p.availability").text.strip(),
        "description": desc.text if desc else None,
        "url": url,
    }

if __name__ == "__main__":
    rows = []
    for page in range(1, 6):
        for link in book_links(page):
            try:
                rows.append(parse_book(link))
            except Exception as e:
                print("failed:", link, e)   # handle errors, don't crash
            time.sleep(0.3)                 # be polite
    json.dump(rows, open("data/raw.json", "w"), indent=2)
    print(len(rows), "books scraped")