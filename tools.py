"""
tools.py — utility functions for file I/O and store scraping.

These are plain Python helpers used by nodes, not LangGraph tools
(i.e., not functions callable by the LLM).
"""
import csv
import json
import re
import urllib.request
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse


# ── File I/O ──────────────────────────────────────────────────────────────────

def load_reviews_from_file(file_path: str) -> list[dict]:
    """
    Load reviews from a local CSV or JSON file.

    Expected CSV columns (minimum): rating, text
    Optional columns: version, date, author

    Expected JSON: a list of objects with the same keys.
    """
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    if path.suffix == ".json":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else [data]

    elif path.suffix == ".csv":
        reviews = []
        with open(path, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                reviews.append(dict(row))
        return reviews

    else:
        raise ValueError(
            f"Unsupported format: '{path.suffix}'. Use .csv or .json"
        )


def write_report_to_file(
    report: str, output_dir: str = "reports", prefix: str = "report"
) -> str:
    """
    Save a markdown report to reports/ with a timestamp in the filename.
    prefix: 'report' for Phase 1, 'release' for Phase 2.
    Returns the path of the created file.
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = Path(output_dir) / f"{prefix}_{timestamp}.md"

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report)

    return str(output_path)


def write_html_to_file(html: str, output_dir: str = "reports", prefix: str = "dashboard") -> str:
    """
    Save the HTML dashboard to reports/ with a timestamp in the filename.
    Returns the path of the created file.
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = Path(output_dir) / f"{prefix}_{timestamp}.html"

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    return str(output_path)


# ── Store scraping ────────────────────────────────────────────────────────────

def parse_store_url(url: str) -> tuple[str, str]:
    """
    Extract store type and app ID from a store URL.
    Returns: ('appstore', '123456789') or ('playstore', 'com.example.app')
    """
    if "apps.apple.com" in url:
        match = re.search(r'/id(\d+)', url)
        if not match:
            raise ValueError(
                "App ID not found in App Store URL. Expected format: .../id123456789"
            )
        return "appstore", match.group(1)

    elif "play.google.com" in url:
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        app_id = params.get("id", [None])[0]
        if not app_id:
            raise ValueError(
                "App ID not found in Google Play URL. Expected format: ...?id=com.example.app"
            )
        return "playstore", app_id

    else:
        raise ValueError(
            "Unrecognized URL. Use an App Store (apps.apple.com) "
            "or Google Play (play.google.com) link."
        )


def fetch_appstore_reviews(app_id: str, country: str = "us", max_reviews: int = 500) -> list[dict]:
    """
    Fetch reviews from the App Store via the iTunes RSS API (public, no auth required).
    50 reviews per page, up to 10 pages (500 reviews max — hard API limit).
    """
    reviews = []
    max_pages = min(10, -(-max_reviews // 50))  # ceil division, capped at 10

    for page in range(1, max_pages + 1):
        url = (
            f"https://itunes.apple.com/rss/customerreviews/"
            f"page={page}/id={app_id}/sortBy=mostRecent/json"
        )
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "vox-populi/1.0"})
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read())
        except Exception as e:
            print(f"  ⚠️  Error fetching page {page}: {e}")
            break

        entries = data.get("feed", {}).get("entry", [])
        if not entries:
            break

        # First entry on page 1 is app metadata, not a review
        items = entries[1:] if page == 1 else entries

        for entry in items:
            reviews.append({
                "rating":  entry.get("im:rating",  {}).get("label", ""),
                "text":    entry.get("content",    {}).get("label", ""),
                "version": entry.get("im:version", {}).get("label", ""),
                "author":  entry.get("author", {}).get("name", {}).get("label", ""),
            })
            if len(reviews) >= max_reviews:
                return reviews

    return reviews


def fetch_playstore_reviews(app_id: str, count: int = 500) -> list[dict]:
    """
    Fetch reviews from Google Play using google-play-scraper.
    Requires: pip install google-play-scraper
    """
    try:
        from google_play_scraper import Sort, reviews as gps_reviews
    except ImportError:
        raise ImportError(
            "google-play-scraper is not installed. Run: pip install google-play-scraper"
        )

    result, _ = gps_reviews(
        app_id,
        lang="en",
        country="us",
        sort=Sort.NEWEST,
        count=count,
    )

    return [
        {
            "rating":  str(r["score"]),
            "text":    r.get("content", ""),
            "version": r.get("appVersion", ""),
            "author":  r.get("userName", ""),
        }
        for r in result
    ]


def load_reviews_from_store(url: str, max_reviews: int = 500) -> list[dict]:
    """
    Entry point for store scraping.
    Auto-detects App Store or Google Play from the URL.
    """
    store, app_id = parse_store_url(url)

    if store == "appstore":
        print(f"  🍎 App Store — app ID: {app_id} (max {max_reviews} reviews)")
        return fetch_appstore_reviews(app_id, max_reviews=max_reviews)
    else:
        print(f"  🤖 Google Play — package: {app_id} (max {max_reviews} reviews)")
        return fetch_playstore_reviews(app_id, count=max_reviews)
