#!/usr/bin/env python3
"""Scrape a minimal Stella JSON file for low-risk LLM retrieval."""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


BASE_URL = "https://www.stella.nl"
OVERVIEW_URL = f"{BASE_URL}/fietsenwinkels"
CUSTOMER_SERVICE_EMAIL = "klantenservice@stellanext.nl"
DEFAULT_OUTPUT = Path("data/stella_vestigingen_simple.json")

DAY_ORDER = (
    ("Monday", "maandag"),
    ("Tuesday", "dinsdag"),
    ("Wednesday", "woensdag"),
    ("Thursday", "donderdag"),
    ("Friday", "vrijdag"),
    ("Saturday", "zaterdag"),
    ("Sunday", "zondag"),
)

SECTION_LABELS = {
    "Testcenter": "fietsenwinkel",
    "Werkplaats": "werkplaats",
}

REQUEST_HEADERS = {
    "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
    "Accept-Language": "nl-NL,nl;q=0.9,en;q=0.6",
    "User-Agent": "Mozilla/5.0 (compatible; IPSTER simple Stella scraper)",
}


class ScraperError(RuntimeError):
    """Raised when the simple Stella data cannot be fetched."""


def fetch_text(url: str) -> str:
    request = Request(url, headers=REQUEST_HEADERS)
    try:
        with urlopen(request, timeout=30) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(charset, errors="replace")
    except HTTPError as exc:
        raise ScraperError(f"HTTP {exc.code} bij ophalen van {url}") from exc
    except URLError as exc:
        raise ScraperError(f"Kon {url} niet ophalen: {exc.reason}") from exc


def fetch_json(url: str) -> dict[str, Any]:
    try:
        data = json.loads(fetch_text(url))
    except json.JSONDecodeError as exc:
        raise ScraperError(f"Stella gaf geen JSON terug: {url}") from exc

    if not isinstance(data, dict):
        raise ScraperError(f"Verwachtte een JSON-object van {url}")

    return data


def discover_locations_endpoint() -> str:
    page = fetch_text(OVERVIEW_URL)
    match = re.search(r'data-endpoint="([^"]+)"', page)
    if not match:
        raise ScraperError("Kon Stella locatie-endpoint niet vinden.")

    return urljoin(BASE_URL, html.unescape(match.group(1)))


def normalize_postcode(postcode: Any) -> str:
    compact = re.sub(r"\s+", "", str(postcode or "").upper())
    if re.fullmatch(r"[1-9][0-9]{3}[A-Z]{2}", compact):
        return f"{compact[:4]} {compact[4:]}"
    return str(postcode or "").strip()


def format_address(marker: dict[str, Any]) -> str:
    city = marker.get("city") or ""
    postcode_city = " ".join(
        part for part in [normalize_postcode(marker.get("postalCode")), city] if part
    )
    return ", ".join(part for part in [marker.get("address"), postcode_city] if part)


def format_day(day_data: Any) -> str:
    if not isinstance(day_data, dict):
        return "Onbekend"

    opens_at = day_data.get("from")
    closes_at = day_data.get("till")
    if opens_at and closes_at:
        return f"{opens_at} - {closes_at}"
    return "Gesloten"


def simplify_opening_times(raw_opening_times: Any) -> dict[str, dict[str, str]]:
    result = {
        "fietsenwinkel": {},
        "werkplaats": {},
    }

    if not isinstance(raw_opening_times, dict):
        return {
            section: {dutch_day: "Onbekend" for _, dutch_day in DAY_ORDER}
            for section in result
        }

    for source_label, section_name in SECTION_LABELS.items():
        section = raw_opening_times.get(source_label, {})
        days = section.get("times", {}) if isinstance(section, dict) else {}
        if not isinstance(days, dict):
            days = {}

        result[section_name] = {
            dutch_day: format_day(days.get(source_day))
            for source_day, dutch_day in DAY_ORDER
        }

    return result


def find_special_closure_notice() -> list[str]:
    page = re.sub(r"<[^>]+>", " ", fetch_text(OVERVIEW_URL))
    page = re.sub(r"\s+", " ", html.unescape(page))
    pattern = re.compile(
        r"(?:Let op:\s*)?(?:Wij zijn van\s*)?\d{2}-\d{2}\s*t/m\s*"
        r"\d{2}-\d{2}\s*gesloten",
        re.IGNORECASE,
    )

    notices: list[str] = []
    seen: set[str] = set()
    for match in pattern.finditer(page):
        notice = match.group(0).strip()
        lower_notice = notice.lower()
        if lower_notice.startswith("wij zijn van"):
            notice = f"Let op: {notice}"
        elif not lower_notice.startswith("let op:"):
            notice = f"Let op: Wij zijn van {notice}"
        if notice.lower() not in seen:
            seen.add(notice.lower())
            notices.append(notice)

    return notices


def simplify_marker(marker: dict[str, Any], special_notices: list[str]) -> dict[str, Any]:
    return {
        "vestiging": marker.get("title"),
        "plaats": marker.get("city"),
        "adres": format_address(marker),
        "telefoon": marker.get("phoneNumber"),
        "email": CUSTOMER_SERVICE_EMAIL,
        "speciale_openingstijden": special_notices,
        "openingstijden": simplify_opening_times(marker.get("openingTimes")),
    }


def build_dataset() -> dict[str, Any]:
    endpoint = discover_locations_endpoint()
    data = fetch_json(endpoint)
    markers = data.get("markers", [])
    if not isinstance(markers, list):
        raise ScraperError("Stella locatie-endpoint bevat geen markers-lijst.")

    special_notices = find_special_closure_notice()
    stores = [
        simplify_marker(marker, special_notices)
        for marker in markers
        if isinstance(marker, dict)
    ]
    stores.sort(key=lambda store: str(store.get("plaats") or ""))

    return {"vestigingen": stores}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scrape a minimal Stella JSON file for LLM retrieval."
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output JSON path. Default: {DEFAULT_OUTPUT}",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        dataset = build_dataset()
    except ScraperError as exc:
        print(f"Fout: {exc}", file=sys.stderr)
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(dataset, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Saved {len(dataset['vestigingen'])} vestigingen to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
