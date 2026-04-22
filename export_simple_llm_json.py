#!/usr/bin/env python3
"""Create a minimal Stella JSON file for low-risk LLM retrieval."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_INPUT = Path("data/stella_vestigingen.json")
DEFAULT_OUTPUT = Path("data/stella_vestigingen_simple.json")


def format_address(store: dict[str, Any]) -> str:
    address = store.get("adres", {})
    parts = [
        address.get("straat"),
        " ".join(
            part
            for part in [address.get("postcode"), address.get("plaats")]
            if part
        ),
    ]
    return ", ".join(part for part in parts if part)


def simplify_days(days: dict[str, Any]) -> dict[str, str]:
    simplified: dict[str, str] = {}
    for day in (
        "maandag",
        "dinsdag",
        "woensdag",
        "donderdag",
        "vrijdag",
        "zaterdag",
        "zondag",
    ):
        day_data = days.get(day, {})
        simplified[day] = str(day_data.get("tekst") or "Onbekend")
    return simplified


def simplify_opening_times(store: dict[str, Any]) -> dict[str, dict[str, str]]:
    opening_times = store.get("openingstijden", {})
    simplified: dict[str, dict[str, str]] = {}

    for section in ("fietsenwinkel", "werkplaats"):
        section_data = opening_times.get(section, {})
        simplified[section] = simplify_days(section_data.get("dagen", {}))

    return simplified


def simplify_special_opening_times(store: dict[str, Any]) -> list[str]:
    special_opening_times = store.get("speciale_openingstijden", {})
    items = special_opening_times.get("items", [])
    if not isinstance(items, list):
        return []

    return [
        str(item.get("tekst"))
        for item in items
        if isinstance(item, dict) and item.get("tekst")
    ]


def simplify_store(store: dict[str, Any]) -> dict[str, Any]:
    contact = store.get("contact", {})
    return {
        "vestiging": store.get("naam"),
        "plaats": store.get("plaats"),
        "adres": format_address(store),
        "telefoon": contact.get("telefoon"),
        "email": contact.get("algemene_klantenservice_email"),
        "speciale_openingstijden": simplify_special_opening_times(store),
        "openingstijden": simplify_opening_times(store),
    }


def build_simple_dataset(source: dict[str, Any]) -> dict[str, Any]:
    stores = source.get("vestigingen", [])
    if not isinstance(stores, list):
        raise ValueError("Input JSON mist de lijst 'vestigingen'.")

    return {
        "doel": (
            "Minimalistische Stella vestigingsdata voor LLM-retrieval. Bevat "
            "alleen locatie, telefoon, algemeen e-mailadres en openingstijden."
        ),
        "belangrijk": (
            "Gebruik geen live open/dicht-status uit deze data. Bereken die "
            "met de actuele datum en tijd in Europe/Amsterdam."
        ),
        "aantal_vestigingen": len(stores),
        "vestigingen": [simplify_store(store) for store in stores],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export a minimal Stella JSON file for LLM retrieval."
    )
    parser.add_argument(
        "-i",
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help=f"Input JSON path. Default: {DEFAULT_INPUT}",
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
    source = json.loads(args.input.read_text(encoding="utf-8"))
    simple_dataset = build_simple_dataset(source)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(simple_dataset, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Saved {simple_dataset['aantal_vestigingen']} vestigingen to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
