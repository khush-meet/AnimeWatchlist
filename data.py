"""Title catalogue.

TITLES = hand-curated rows (below) + titles loaded from scraped_titles.json.
Curated rows always win: a scraped title that matches a curated one is skipped.
Run `python scrape.py` to refresh scraped_titles.json.
Run `python fetch_images.py` to refresh images.json (posters).

tier: essential | recommended | optional
src: 'dubsite' (listed on animedubhindi.link) or 'classic' (famous anime)
"""
import json
import re
from pathlib import Path

SCRAPED_FILE = Path(__file__).parent / "scraped_titles.json"
IMAGES_FILE = Path(__file__).parent / "images.json"


def t(title, kind, year, eps, mins, genres, hindi, tier, src, note=""):
    return dict(title=title, kind=kind, year=year, eps=eps, mins=mins,
                genres=genres, hindi=hindi, tier=tier, src=src, note=note)


CURATED = [
    # ---- listed on animedubhindi.link (home page) ----
    t("Blue Box Season 2", "Series", 2025, 12, 24, ["Romance", "Sports", "Drama"], True, "recommended", "dubsite", "Watch season 1 first."),
    t("Mushoku Tensei: Jobless Reincarnation Season 3", "Series", 2026, 12, 24, ["Isekai", "Fantasy", "Drama"], True, "recommended", "dubsite", "Seasons 1 and 2 first."),
    t("That Time I Got Reincarnated as a Slime Season 4", "Series", 2026, 24, 24, ["Isekai", "Fantasy", "Action"], True, "recommended", "dubsite", "Seasons 1 to 3 first."),
    t("The Exiled Heavy Knight Knows How to Game the System", "Series", 2026, 12, 24, ["Isekai", "Fantasy"], True, "optional", "dubsite"),
    t("Chainsmoker Cat", "Series", 2026, 12, 24, ["Comedy"], True, "optional", "dubsite"),
    t("The Ramparts of Ice Season 2", "Series", 2026, 12, 24, ["Fantasy"], True, "optional", "dubsite", "Season 1 first."),
    t("JoJo's Bizarre Adventure: Golden Wind (Season 4)", "Series", 2018, 39, 23, ["Action", "Supernatural"], True, "recommended", "dubsite", "Standalone story, but parts 1 to 3 add context."),
    t("The Frontier Lord Begins with Zero Subjects", "Series", 2026, 12, 24, ["Fantasy", "Isekai"], True, "optional", "dubsite"),
    t("Tomb Raider King", "Series", 2024, 12, 24, ["Action", "Fantasy"], True, "optional", "dubsite"),
    t("Re:Zero - Starting Life in Another World Season 4", "Series", 2026, 18, 24, ["Isekai", "Thriller", "Drama"], True, "recommended", "dubsite", "Seasons 1 to 3 first."),
    t("The Laid-Off Cheat-Granting Mage Enjoys a Second Lease on Life", "Series", 2026, 12, 24, ["Isekai", "Fantasy"], True, "optional", "dubsite"),
    t("Liar Game", "Series", 2026, 12, 24, ["Thriller", "Mystery"], True, "optional", "dubsite"),
    t("Grand Blue Dreaming Season 3", "Series", 2026, 12, 24, ["Comedy", "Slice of Life"], True, "optional", "dubsite", "Seasons 1 and 2 first."),
    t("As a Reincarnated Aristocrat, I'll Use My Appraisal Skill Season 3", "Series", 2026, 12, 24, ["Isekai", "Fantasy"], True, "optional", "dubsite"),
    t("Overgeared", "Series", 2026, 12, 24, ["Fantasy", "Action"], True, "optional", "dubsite"),

    # ---- famous anime ----
    t("Naruto", "Series", 2002, 220, 23, ["Shounen", "Action", "Adventure"], True, "essential", "classic"),
    t("Naruto Shippuden", "Series", 2007, 500, 23, ["Shounen", "Action", "Adventure"], True, "essential", "classic", "Long. Some filler arcs can be skipped."),
    t("One Piece", "Series", 1999, 1150, 24, ["Shounen", "Adventure", "Action"], True, "essential", "classic", "Still running. Hours are approximate."),
    t("Dragon Ball Z", "Series", 1989, 291, 24, ["Shounen", "Action"], True, "essential", "classic"),
    t("Death Note", "Series", 2006, 37, 23, ["Mystery", "Thriller", "Supernatural"], True, "essential", "classic"),
    t("Fullmetal Alchemist: Brotherhood", "Series", 2009, 64, 24, ["Shounen", "Fantasy", "Adventure"], True, "essential", "classic"),
    t("Attack on Titan", "Series", 2013, 87, 24, ["Action", "Drama", "Thriller"], True, "essential", "classic", "All four seasons."),
    t("Hunter x Hunter (2011)", "Series", 2011, 148, 23, ["Shounen", "Adventure", "Fantasy"], True, "essential", "classic"),
    t("Demon Slayer: Kimetsu no Yaiba", "Series", 2019, 26, 24, ["Shounen", "Action", "Supernatural"], True, "essential", "classic", "Season 1."),
    t("Jujutsu Kaisen", "Series", 2020, 24, 24, ["Shounen", "Action", "Supernatural"], True, "essential", "classic", "Season 1."),
    t("My Hero Academia", "Series", 2016, 13, 24, ["Shounen", "Action", "School"], True, "recommended", "classic", "Season 1."),
    t("One Punch Man", "Series", 2015, 12, 24, ["Action", "Comedy", "Sci-Fi"], True, "recommended", "classic", "Season 1."),
    t("Bleach", "Series", 2004, 366, 24, ["Shounen", "Action", "Supernatural"], True, "recommended", "classic"),
    t("Black Clover", "Series", 2017, 170, 24, ["Shounen", "Magic", "Fantasy"], True, "recommended", "classic"),
    t("Solo Leveling", "Series", 2024, 12, 24, ["Action", "Fantasy"], True, "recommended", "classic", "Season 1."),
    t("Spy x Family", "Series", 2022, 25, 24, ["Comedy", "Action", "Slice of Life"], True, "recommended", "classic", "Season 1."),
    t("Chainsaw Man", "Series", 2022, 12, 24, ["Action", "Horror", "Supernatural"], True, "recommended", "classic"),
    t("Haikyu!!", "Series", 2014, 25, 24, ["Sports", "Shounen", "School"], True, "recommended", "classic", "Season 1."),
    t("Steins;Gate", "Series", 2011, 24, 24, ["Sci-Fi", "Thriller", "Drama"], False, "recommended", "classic"),
    t("Code Geass: Lelouch of the Rebellion", "Series", 2006, 25, 24, ["Sci-Fi", "Thriller", "Drama"], False, "recommended", "classic", "Season 1."),
    t("Cowboy Bebop", "Series", 1998, 26, 24, ["Sci-Fi", "Action"], False, "recommended", "classic"),
    t("Vinland Saga", "Series", 2019, 24, 24, ["Action", "Drama", "Adventure"], False, "recommended", "classic", "Season 1."),
    t("Frieren: Beyond Journey's End", "Series", 2023, 28, 24, ["Fantasy", "Adventure", "Drama"], False, "recommended", "classic"),
    t("Dr. Stone", "Series", 2019, 24, 24, ["Shounen", "Sci-Fi", "Adventure"], True, "optional", "classic", "Season 1."),
    t("Sword Art Online", "Series", 2012, 25, 24, ["Isekai", "Action", "Romance"], True, "optional", "classic", "Season 1."),
    t("Tokyo Ghoul", "Series", 2014, 12, 24, ["Horror", "Action", "Supernatural"], True, "optional", "classic", "Season 1."),
    t("Fairy Tail", "Series", 2009, 175, 24, ["Shounen", "Magic", "Fantasy"], True, "optional", "classic"),
    t("Your Name.", "Movie", 2016, 1, 107, ["Romance", "Drama", "Supernatural"], False, "essential", "classic"),
    t("Spirited Away", "Movie", 2001, 1, 125, ["Fantasy", "Adventure"], False, "essential", "classic"),
]


def _key(title):
    """Normalise a title so 'Re:Zero - Season 4' and 're zero season 4' match."""
    return re.sub(r"[^a-z0-9]+", "", title.lower())


def load_scraped():
    """Read scraped_titles.json -> list of dicts in the same shape as t()."""
    if not SCRAPED_FILE.exists():
        return []
    try:
        raw = json.loads(SCRAPED_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(f"Could not read {SCRAPED_FILE.name}: {e}")
        return []

    rows = []
    for item in raw:
        title = (item.get("title") or "").strip()
        if not title:
            continue
        movie = bool(item.get("movie"))
        rows.append(t(
            title,
            "Movie" if movie else "Series",
            None,                   # year unknown from scrape
            1 if movie else None,   # eps unknown for series
            None,                   # minutes unknown
            ["Unsorted"],
            bool(item.get("hindi")),
            "optional",
            "dubsite",
        ))
    return rows


def load_images():
    """images.json maps uid -> poster url (made by fetch_images.py)."""
    if not IMAGES_FILE.exists():
        return {}
    try:
        return json.loads(IMAGES_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def build_titles():
    seen = {_key(x["title"]) for x in CURATED}
    merged = list(CURATED)
    for row in load_scraped():
        k = _key(row["title"])
        if k and k not in seen:
            seen.add(k)
            merged.append(row)

    images = load_images()
    for i, x in enumerate(merged):
        x["id"] = i
        x["uid"] = _key(x["title"])          # stable id: used for ticks + images
        x["image"] = images.get(x["uid"], "")
    return merged


TITLES = build_titles()