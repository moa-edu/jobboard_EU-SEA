#!/usr/bin/env python3
"""
Business & Management faculty job scraper.

Pulls current listings from sources that allow automated access (no login,
no aggressive bot-protection), filters to business/management academic
disciplines, tags each listing with a region, and merges the result into
data/jobs.json -- preserving any existing entries whose URL isn't re-seen
in this run (so a source going down for a night doesn't blank the table),
while dropping anything older than STALE_DAYS that no source has re-confirmed.

Run manually:   python3 scraper.py
Run in CI:      see .github/workflows/update-jobs.yml

IMPORTANT -- read before relying on this:
Academic job boards vary widely in how they treat automated requests.
Some (HigherEdJobs, Chronicle of Higher Education) sit behind bot-protection
services (Incapsula/Cloudflare) that block simple scripted requests outright;
scraping those reliably needs a real browser automation tool (e.g. Playwright)
and is more fragile and more likely to violate the site's Terms of Service,
so this script does NOT attempt them. The sources below were chosen because
they're either RSS, a public JSON/API, or plain server-rendered HTML with no
challenge page -- but sites change. If a source starts returning 0 results,
check SOURCES_STATUS printed at the end of a run, and fix or drop that source
in SOURCES below rather than assuming the discipline has gone quiet.
"""

import json
import re
import sys
import time
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime, timezone

try:
    from bs4 import BeautifulSoup
except ImportError:
    print("Missing dependency: pip install beautifulsoup4 lxml requests", file=sys.stderr)
    raise

DATA_FILE = Path(__file__).parent / "data" / "jobs.json"
STALE_DAYS = 120  # drop a listing if no source has re-confirmed it in this long
USER_AGENT = (
    "Mozilla/5.0 (compatible; BusinessMgmtJobsBot/1.0; "
    "+https://github.com/; academic-jobs dashboard, contact via repo issues)"
)

DISCIPLINE_KEYWORDS = [
    "management", "marketing", "finance", "strategy", "strategic",
    "organizational behavior", "organisational behaviour", "human resources",
    "entrepreneurship", "business analytics", "operations management",
    "supply chain", "accounting", "business administration",
]

REGION_HINTS = {
    "Europe": [
        "UK", "United Kingdom", "England", "London", "Spain", "France",
        "Germany", "Sweden", "Netherlands", "Switzerland", "Italy",
        "Portugal", "Ireland", "Cyprus", "Belgium", "Denmark", "Norway",
        "Finland", "Poland", "Austria",
    ],
    "Asia": [
        "Singapore", "China", "Hong Kong", "Japan", "Korea", "India",
        "Malaysia", "Shanghai", "Shenzhen", "Taiwan", "Thailand",
        "Philippines", "Indonesia", "Vietnam",
    ],
    "Australia": ["Australia", "Sydney", "Melbourne", "Canberra", "Brisbane", "Perth", "NSW", "VIC"],
}


def guess_region(location: str) -> str:
    for region, hints in REGION_HINTS.items():
        for h in hints:
            if h.lower() in location.lower():
                return region
    # crude default: US state abbreviations / "USA" fall through to North America
    return "North America"


def matches_discipline(text: str) -> bool:
    t = text.lower()
    return any(k in t for k in DISCIPLINE_KEYWORDS)


def fetch(url: str, timeout: int = 20) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


# ---------------------------------------------------------------------------
# Source adapters. Each returns a list of dicts:
#   employer, position, sub, location, type, posted (YYYY-MM), url
# Wrap network/parsing errors so one broken source never kills the run.
# ---------------------------------------------------------------------------

def source_econjobmarket():
    """EconJobMarket: public listings, includes business-school finance/
    management/marketing postings. No login required."""
    out = []
    url = "https://econjobmarket.org/rss"
    raw = fetch(url)
    root = ET.fromstring(raw)
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        desc = (item.findtext("description") or "").strip()
        if not matches_discipline(title + " " + desc):
            continue
        out.append({
            "employer": "", "position": title, "sub": "Finance / Economics",
            "location": "", "type": "Tenure-track",
            "posted": datetime.now(timezone.utc).strftime("%Y-%m"),
            "url": link or url,
        })
    return out


def source_theunijobs():
    """Times Higher Education unijobs: Business & Management listings,
    plain server-rendered HTML, no login wall."""
    out = []
    url = "https://www.timeshighereducation.com/unijobs/listings/business-and-management/academic-posts/"
    raw = fetch(url)
    soup = BeautifulSoup(raw, "lxml")
    for card in soup.select("[class*=job-result], article, li"):
        title_el = card.find(["h2", "h3", "a"])
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        if not title or not matches_discipline(title):
            continue
        link_el = card.find("a", href=True)
        link = link_el["href"] if link_el else url
        if link.startswith("/"):
            link = "https://www.timeshighereducation.com" + link
        employer_el = card.find(class_=re.compile("institution|employer|company", re.I))
        employer = employer_el.get_text(strip=True) if employer_el else "See listing"
        loc_el = card.find(class_=re.compile("location", re.I))
        location = loc_el.get_text(strip=True) if loc_el else "Europe"
        out.append({
            "employer": employer, "position": title, "sub": "Management",
            "location": location, "type": "Tenure-track",
            "posted": datetime.now(timezone.utc).strftime("%Y-%m"),
            "url": link,
        })
    return out


def source_academickeys():
    """AcademicKeys business/management job search feed."""
    out = []
    url = "https://business.academickeys.com/seeker_search_results.php?sources=1"
    raw = fetch(url)
    soup = BeautifulSoup(raw, "lxml")
    for a in soup.find_all("a", href=re.compile(r"seeker_job_display")):
        title = a.get_text(strip=True)
        if not title or not matches_discipline(title):
            continue
        link = a["href"]
        if link.startswith("/"):
            link = "https://business.academickeys.com" + link
        out.append({
            "employer": "See listing", "position": title, "sub": "Business",
            "location": "", "type": "Tenure-track",
            "posted": datetime.now(timezone.utc).strftime("%Y-%m"),
            "url": link,
        })
    return out


SOURCES = {
    "econjobmarket": source_econjobmarket,
    "theunijobs": source_theunijobs,
    "academickeys": source_academickeys,
}


def load_existing():
    if DATA_FILE.exists():
        payload = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        return payload.get("jobs", []), payload.get("seen_at", {})
    return [], {}


def main():
    existing_jobs, seen_at = load_existing()
    by_url = {j["url"]: j for j in existing_jobs}

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    status = {}

    for name, fn in SOURCES.items():
        try:
            rows = fn()
            status[name] = f"ok ({len(rows)} matched)"
        except Exception as exc:  # noqa: BLE001 -- one bad source must not kill the run
            status[name] = f"FAILED: {exc!r}"
            rows = []
        for row in rows:
            if not row.get("region"):
                row["region"] = guess_region(row.get("location", ""))
            by_url[row["url"]] = row
            seen_at[row["url"]] = today
        time.sleep(1)  # be polite between sources

    # drop anything stale that no source re-confirmed
    cutoff = datetime.now(timezone.utc)
    fresh = []
    for url, job in by_url.items():
        last_seen = seen_at.get(url)
        if last_seen:
            age_days = (cutoff - datetime.strptime(last_seen, "%Y-%m-%d").replace(tzinfo=timezone.utc)).days
            if age_days > STALE_DAYS:
                continue
        fresh.append(job)

    fresh.sort(key=lambda j: j.get("posted", ""), reverse=True)

    payload = {
        "last_updated": cutoff.isoformat(timespec="seconds"),
        "source_status": status,
        "seen_at": seen_at,
        "jobs": fresh,
    }
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Wrote {len(fresh)} jobs to {DATA_FILE}")
    for name, s in status.items():
        print(f"  {name}: {s}")


if __name__ == "__main__":
    main()
