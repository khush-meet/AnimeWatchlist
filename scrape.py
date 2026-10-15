import json
import re
import time

import requests
from bs4 import BeautifulSoup

BASE = "https://www.animedubhindi.link/"
HEADERS = {"User-Agent": "Mozilla/5.0 (student project, titles only)"}
LANG = re.compile(
    r"\s+(?:Hindi|Tamil|Telugu|English|Japanese|Korean|Chinese|Bengali|Malayalam|Kannada)\b"
)

def clean(raw):
    """Cut 'Hindi, Tamil ... Episodes Download' off the end of a post title."""
    m = LANG.search(raw)
    return (raw[:m.start()] if m else raw).strip(" -–")

def get_page(n):
    url = BASE if n == 1 else f"{BASE}page/{n}/"
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    found = []
    for a in soup.select("h2 a"):
        raw = a.get_text(" ", strip=True)
        if "Download" not in raw:      # skip headings that aren't posts
            continue
        found.append({"title": clean(raw), "hindi": "Hindi" in raw, "movie": "Movie" in raw})
    return found

def main():
    seen, results = set(), []
    for n in range(1, 56):
        try:
            items = get_page(n)
        except Exception as e:
            print(f"Page {n}: {e}")
            break
        if not items:
            print(f"Page {n}: no titles, stopping")
            break
        for it in items:
            key = it["title"].lower()
            if key not in seen:
                seen.add(key)
                results.append(it)
        print(f"Page {n}: {len(items)} titles ({len(results)} total)")
        time.sleep(1)                  # be polite to the server
    with open("scraped_titles.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"Saved {len(results)} titles to scraped_titles.json")

if __name__ == "__main__":
    main()