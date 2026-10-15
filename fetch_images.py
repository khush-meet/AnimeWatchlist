"""Fetch poster URLs -> images.json

Tries AniList first, then Jikan (MyAnimeList). If one is unreachable it
switches to the other automatically.

Usage:
    python fetch_images.py            # only titles not done yet
    python fetch_images.py --retry    # also retry titles that had no result
Resumable: progress is saved as it goes, Ctrl+C is safe.
"""
import json
import re
import sys
import time
from pathlib import Path

import requests

from data import TITLES

OUT = Path(__file__).parent / "images.json"
HEADERS = {"User-Agent": "anitrack student project"}

session = requests.Session()
session.headers.update(HEADERS)


class NetError(Exception):
    """Could not reach the server at all (DNS, firewall, no internet...)."""


def strip_season(title):
    return re.sub(r"\s*\(?season\s*\d+\)?", "", title, flags=re.I).strip()


# ---------------- AniList ----------------
ANILIST = "https://graphql.anilist.co"
ANILIST_Q = """
query ($search: String) {
  Media(search: $search, type: ANIME) {
    coverImage { extraLarge large }
  }
}"""


def anilist(query):
    for attempt in range(3):
        try:
            r = session.post(ANILIST, json={"query": ANILIST_Q, "variables": {"search": query}},
                             timeout=20)
        except requests.RequestException as e:
            raise NetError(f"{type(e).__name__}: {e}")
        if r.status_code == 429:
            time.sleep(int(r.headers.get("Retry-After", 10)))
            continue
        if r.status_code != 200:          # 404 = not found
            return ""
        media = (r.json().get("data") or {}).get("Media") or {}
        cover = media.get("coverImage") or {}
        return cover.get("large") or cover.get("extraLarge") or ""
    return ""


# ---------------- Jikan ----------------
JIKAN = "https://api.jikan.moe/v4/anime"


def jikan(query):
    for attempt in range(3):
        try:
            r = session.get(JIKAN, params={"q": query, "limit": 1, "sfw": "true"}, timeout=20)
        except requests.RequestException as e:
            raise NetError(f"{type(e).__name__}: {e}")
        if r.status_code == 429:
            time.sleep(3 * (attempt + 1))
            continue
        if r.status_code != 200:
            return ""
        data = r.json().get("data") or []
        if not data:
            return ""
        jpg = data[0]["images"]["jpg"]
        return jpg.get("large_image_url") or jpg.get("image_url") or ""
    return ""


PROVIDERS = {"anilist": anilist, "jikan": jikan}
DELAY = {"anilist": 1.0, "jikan": 1.1}


def check_connection():
    """Try each provider once and print the real reason if it fails."""
    alive = []
    for name, fn in PROVIDERS.items():
        try:
            fn("Naruto")
            print(f"  {name}: OK")
            alive.append(name)
        except NetError as e:
            print(f"  {name}: FAILED -> {e}")
    return alive


def lookup(title, name):
    fn = PROVIDERS[name]
    return fn(title) or fn(strip_season(title))


def main():
    retry = "--retry" in sys.argv

    print("Checking connection...")
    alive = check_connection()
    if not alive:
        print("\nCannot reach AniList or Jikan from this network. Try:")
        print("  1. Change DNS to 8.8.8.8 / 1.1.1.1 (or 1.1.1.1 app / WARP)")
        print("  2. Use a mobile hotspot or a VPN")
        print("  3. Check your firewall / antivirus is not blocking Python")
        print("  4. Run:  python -c \"import requests; print(requests.get('https://graphql.anilist.co').status_code)\"")
        sys.exit(1)

    cache = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    todo = [x for x in TITLES
            if x["uid"] not in cache or (retry and not cache[x["uid"]])]
    print(f"\n{len(todo)} titles to fetch ({len(cache)} cached), using: {', '.join(alive)}")

    fails = {name: 0 for name in alive}

    try:
        for n, x in enumerate(todo, 1):
            url = ""
            for name in list(alive):
                try:
                    url = lookup(x["title"], name)
                    fails[name] = 0
                    time.sleep(DELAY[name])
                    if url:
                        break
                except NetError as e:
                    fails[name] += 1
                    print(f"  {name} error: {e}")
                    if fails[name] >= 3:
                        print(f"  -> {name} keeps failing, switching it off")
                        alive.remove(name)
            if not alive:
                print("All providers are down, stopping. Run again later.")
                break

            cache[x["uid"]] = url
            print(f"[{n}/{len(todo)}] {'OK  ' if url else 'MISS'} {x['title']}")
            if n % 10 == 0:
                OUT.write_text(json.dumps(cache, indent=1), encoding="utf-8")
    except KeyboardInterrupt:
        print("\nStopped, saving progress...")

    OUT.write_text(json.dumps(cache, indent=1), encoding="utf-8")
    print(f"Saved {sum(1 for v in cache.values() if v)} images to {OUT.name}")


if __name__ == "__main__":
    main()