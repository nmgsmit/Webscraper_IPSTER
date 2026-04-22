#!/usr/bin/env python3
"""Scrape Stella store and workshop opening times into LLM-friendly JSON."""

from __future__ import annotations

import argparse
import html as html_lib
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


BASE_URL = "https://www.stella.nl"
OVERVIEW_URL = f"{BASE_URL}/fietsenwinkels"
DEFAULT_OUTPUT = Path("data/stella_vestigingen.json")
TIMEZONE = "Europe/Amsterdam"
CUSTOMER_SERVICE_EMAIL = "klantenservice@stellanext.nl"

PROVINCE_OVERRIDES = {
    "Best": "Noord-Brabant",
}

SPECIAL_OPENING_PATTERNS = (
    re.compile(
        r"(?:Let op:\s*)?(?:Wij zijn van\s*)?\d{2}-\d{2}\s*t/m\s*"
        r"\d{2}-\d{2}\s*gesloten",
        re.IGNORECASE,
    ),
    re.compile(r".{0,120}speciale openingstijden.{0,180}", re.IGNORECASE),
    re.compile(r".{0,120}gewijzigde openingstijden.{0,180}", re.IGNORECASE),
    re.compile(r".{0,120}afwijkende openingstijden.{0,180}", re.IGNORECASE),
    re.compile(r".{0,120}feestdagopening.{0,180}", re.IGNORECASE),
    re.compile(
        r".{0,120}openingstijden.{0,80}feestdagen.{0,180}",
        re.IGNORECASE,
    ),
)

SPECIAL_OPENING_AGENT_NOTE = (
    "Gebruik speciale openingstijden alleen als deze in items staan. Als er "
    "geen item voor de gevraagde datum is, noem dan dat reguliere "
    "openingstijden op feestdagen kunnen afwijken en verwijs naar Stella voor "
    "actuele bevestiging."
)

DAY_ORDER = (
    ("Monday", "maandag"),
    ("Tuesday", "dinsdag"),
    ("Wednesday", "woensdag"),
    ("Thursday", "donderdag"),
    ("Friday", "vrijdag"),
    ("Saturday", "zaterdag"),
    ("Sunday", "zondag"),
)

OPENING_TIME_LABELS = {
    "Testcenter": "fietsenwinkel",
    "Store": "fietsenwinkel",
    "Werkplaats": "werkplaats",
    "Workshop": "werkplaats",
}

REQUEST_HEADERS = {
    "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
    "Accept-Language": "nl-NL,nl;q=0.9,en;q=0.6",
    "User-Agent": "Mozilla/5.0 (compatible; IPSTER Stella opening-times scraper)",
}


class ScraperError(RuntimeError):
    """Raised when the Stella source data cannot be fetched or normalized."""


def fetch_text(url: str) -> str:
    request = Request(url, headers=REQUEST_HEADERS)
    try:
        with urlopen(request, timeout=30) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(charset, errors="replace")
    except HTTPError as exc:
        raise ScraperError(f"HTTP {exc.code} while fetching {url}") from exc
    except URLError as exc:
        raise ScraperError(f"Could not fetch {url}: {exc.reason}") from exc


def fetch_json(url: str) -> dict[str, Any]:
    text = fetch_text(url)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ScraperError(f"Stella endpoint did not return JSON: {url}") from exc

    if not isinstance(data, dict):
        raise ScraperError(f"Expected a JSON object from {url}")

    return data


def discover_locations_endpoint(overview_url: str = OVERVIEW_URL) -> str:
    html = fetch_text(overview_url)
    match = re.search(r'data-endpoint="([^"]+)"', html)
    if not match:
        raise ScraperError(
            f"Could not find the locations endpoint on {overview_url}"
        )

    endpoint = html_lib.unescape(match.group(1))
    return urljoin(BASE_URL, endpoint)


def normalize_tags(tags: Any) -> list[str]:
    if not isinstance(tags, list):
        return []

    names: list[str] = []
    for tag in tags:
        if isinstance(tag, dict) and tag.get("name"):
            names.append(str(tag["name"]))
    return names


def normalize_postcode(postcode: Any) -> str | None:
    if postcode is None:
        return None

    compact = re.sub(r"\s+", "", str(postcode).upper())
    if re.fullmatch(r"[1-9][0-9]{3}[A-Z]{2}", compact):
        return f"{compact[:4]} {compact[4:]}"

    return str(postcode).strip() or None


def normalize_province(city: str, province: Any) -> str | None:
    if city in PROVINCE_OVERRIDES:
        return PROVINCE_OVERRIDES[city]

    if province is None:
        return None

    return str(province).strip() or None


def normalize_days(times: dict[str, Any]) -> dict[str, dict[str, Any]]:
    normalized: dict[str, dict[str, Any]] = {}
    for source_day, dutch_day in DAY_ORDER:
        source_value = times.get(source_day, {})
        if not isinstance(source_value, dict):
            source_value = {}

        opens_at = source_value.get("from") or None
        closes_at = source_value.get("till") or None
        is_open = bool(opens_at and closes_at)

        normalized[dutch_day] = {
            "dag": dutch_day,
            "bron_dag": source_day,
            "open": is_open,
            "van": opens_at,
            "tot": closes_at,
            "tekst": f"{opens_at} - {closes_at}" if is_open else "Gesloten",
        }

    return normalized


def normalize_opening_times(raw_opening_times: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(raw_opening_times, dict):
        return {}

    normalized: dict[str, dict[str, Any]] = {}
    for source_label, source_value in raw_opening_times.items():
        section_key = OPENING_TIME_LABELS.get(str(source_label), str(source_label).lower())
        if not isinstance(source_value, dict):
            continue

        times = source_value.get("times", {})
        if not isinstance(times, dict):
            times = {}

        remarks = source_value.get("remarks", [])
        normalized[section_key] = {
            "bron_label": source_label,
            "dagen": normalize_days(times),
            "opmerkingen": remarks if isinstance(remarks, list) else [],
        }

    return normalized


def normalize_marker(marker: dict[str, Any]) -> dict[str, Any]:
    relative_url = marker.get("url") or ""
    page_url = urljoin(BASE_URL, str(relative_url))
    city = marker.get("city") or ""
    province = normalize_province(city, marker.get("region"))

    return {
        "id": marker.get("id"),
        "naam": marker.get("title"),
        "plaats": city,
        "pagina_url": page_url,
        "adres": {
            "straat": marker.get("address"),
            "postcode": normalize_postcode(marker.get("postalCode")),
            "plaats": city,
            "provincie": province,
            "land": marker.get("country"),
            "latitude": marker.get("lat"),
            "longitude": marker.get("lng"),
        },
        "contact": {
            "telefoon": marker.get("phoneNumber"),
            "algemene_klantenservice_email": CUSTOMER_SERVICE_EMAIL,
            "website": marker.get("website") or page_url,
        },
        "labels": normalize_tags(marker.get("tags")),
        "afdelingen_bron": marker.get("departments") or [],
        "speciale_openingstijden": {
            "gevonden": False,
            "items": [],
            "agent_instructie": SPECIAL_OPENING_AGENT_NOTE,
        },
        "openingstijden": normalize_opening_times(marker.get("openingTimes")),
    }


def strip_html(text: str) -> str:
    without_scripts = re.sub(
        r"<(script|style)\b[^>]*>.*?</\1>",
        " ",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    without_tags = re.sub(r"<[^>]+>", " ", without_scripts)
    return re.sub(r"\s+", " ", html_lib.unescape(without_tags)).strip()


def find_special_opening_mentions(text: str) -> list[str]:
    plain_text = strip_html(text)
    mentions: list[str] = []
    seen: set[str] = set()

    for pattern in SPECIAL_OPENING_PATTERNS:
        for match in pattern.finditer(plain_text):
            mention = re.sub(r"\s+", " ", match.group(0)).strip()
            if mention and mention.lower() not in seen:
                seen.add(mention.lower())
                mentions.append(mention)

    return mentions


def normalize_special_opening_item(source: str, mention: str) -> dict[str, Any]:
    item: dict[str, Any] = {
        "bron": source,
        "tekst": mention,
    }

    period_match = re.search(
        r"(\d{2}-\d{2})\s*t/m\s*(\d{2}-\d{2})",
        mention,
        flags=re.IGNORECASE,
    )
    if period_match:
        item["type"] = "sluiting"
        item["periode"] = {
            "van": period_match.group(1),
            "tot_en_met": period_match.group(2),
            "jaar": None,
            "opmerking": (
                "De Stella-bron noemt dag en maand, maar geen jaar. Pas deze "
                "sluiting toe op de eerstvolgende relevante jaarwisseling."
            ),
        }

    return item


def get_opening_time_remarks(store: dict[str, Any]) -> list[str]:
    remarks: list[str] = []
    for section in store.get("openingstijden", {}).values():
        if not isinstance(section, dict):
            continue
        for remark in section.get("opmerkingen", []):
            if remark:
                remarks.append(str(remark))
    return remarks


def scan_special_opening_hours(stores: list[dict[str, Any]]) -> dict[str, Any]:
    checked_sources = [OVERVIEW_URL]
    findings: list[dict[str, Any]] = []
    scan_errors: list[str] = []

    for store in stores:
        url = str(store.get("pagina_url") or "")
        if url:
            checked_sources.append(url)

        store_items = [
            normalize_special_opening_item("Stella locaties endpoint", remark)
            for remark in get_opening_time_remarks(store)
        ]

        if store_items:
            store["speciale_openingstijden"]["gevonden"] = True
            store["speciale_openingstijden"]["items"].extend(store_items)

    for url in checked_sources:
        try:
            mentions = find_special_opening_mentions(fetch_text(url))
        except ScraperError as exc:
            scan_errors.append(str(exc))
            continue

        if not mentions:
            continue

        finding = {
            "url": url,
            "vermeldingen": mentions,
        }
        findings.append(finding)

        affected_stores = (
            stores
            if url == OVERVIEW_URL
            else [store for store in stores if store.get("pagina_url") == url]
        )
        for store in affected_stores:
            store["speciale_openingstijden"]["gevonden"] = True
            store["speciale_openingstijden"]["items"].extend(
                normalize_special_opening_item(url, mention)
                for mention in mentions
            )

    found = bool(findings) or any(
        store["speciale_openingstijden"]["gevonden"] for store in stores
    )

    return {
        "gevonden": found,
        "gecontroleerde_bronnen": checked_sources,
            "zoekpatronen": [
            "Let op: Wij zijn van DD-MM t/m DD-MM gesloten",
            "DD-MM t/m DD-MM gesloten",
            "speciale openingstijden",
            "gewijzigde openingstijden",
            "afwijkende openingstijden",
            "feestdagopening",
            "openingstijden ... feestdagen",
        ],
        "resultaten": findings,
        "scan_fouten": scan_errors,
        "agent_instructie": SPECIAL_OPENING_AGENT_NOTE,
    }


def build_dataset(endpoint_url: str) -> dict[str, Any]:
    data = fetch_json(endpoint_url)
    markers = data.get("markers")
    if not isinstance(markers, list):
        raise ScraperError(f"No markers array found in {endpoint_url}")

    stores = [
        normalize_marker(marker)
        for marker in markers
        if isinstance(marker, dict)
    ]
    stores.sort(key=lambda store: str(store.get("plaats") or ""))
    special_opening_hours = scan_special_opening_hours(stores)

    now = datetime.now(ZoneInfo(TIMEZONE)).isoformat(timespec="seconds")
    return {
        "bron": {
            "naam": "Stella Fietsenwinkels",
            "website": BASE_URL,
            "overzicht_url": OVERVIEW_URL,
            "locaties_endpoint": endpoint_url,
            "gescrapet_op": now,
            "tijdzone": TIMEZONE,
            "aantal_vestigingen": len(stores),
            "toelichting": (
                "Stella publiceert de openingstijden per locatie als "
                "Testcenter en Werkplaats. In deze JSON is Testcenter "
                "genormaliseerd naar fietsenwinkel. Live open/dicht-status "
                "wordt bewust niet opgeslagen, zodat een call-agent geen "
                "verouderde scrape-snapshot als actuele status gebruikt."
            ),
            "contact_toelichting": (
                "De locatiebron bevat noreply-adressen per vestiging. Die "
                "worden niet als klantcontact opgeslagen; de JSON gebruikt "
                "het algemene klantenservice-adres van Stella."
            ),
            "correcties": [
                {
                    "veld": "adres.provincie",
                    "vestiging": "Best",
                    "waarde": "Noord-Brabant",
                    "reden": (
                        "De Stella locatiebron geeft Best als Noord-Holland "
                        "terug, maar Best ligt in Noord-Brabant."
                    ),
                }
            ],
            "speciale_openingstijden": special_opening_hours,
        },
        "vestigingen": stores,
    }


def write_json(dataset: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(dataset, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Scrape Stella.nl store and workshop opening times into structured JSON."
        )
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"JSON output path. Default: {DEFAULT_OUTPUT}",
    )
    parser.add_argument(
        "--endpoint",
        help=(
            "Optional Stella locations endpoint. When omitted, the scraper "
            "discovers it from the fietsenwinkels page."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        endpoint = args.endpoint or discover_locations_endpoint()
        dataset = build_dataset(endpoint)
        write_json(dataset, args.output)
    except ScraperError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    count = dataset["bron"]["aantal_vestigingen"]
    print(f"Saved {count} Stella vestigingen to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
