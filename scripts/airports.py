#!/usr/bin/env python3
"""Bundled airport reference lookup (IATA -> coordinates, country, IANA time zone).

Stdlib only. Data: assets/airports.csv, derived from the MIT-licensed mwgg/Airports
dataset (see assets/AIRPORTS-LICENSE.md). Usage: python3 airports.py LIS ord NRT
"""
import argparse
import csv
import functools
import json
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / 'assets' / 'airports.csv'


def normalize(code):
    """Return an upper-case three-letter IATA code, or None if it is not one."""
    if not isinstance(code, str):
        return None
    code = code.strip().upper()
    return code if len(code) == 3 and code.isascii() and code.isalpha() else None


@functools.lru_cache(maxsize=1)
def table():
    with DATA.open(encoding='utf-8', newline='') as handle:
        rows = {}
        for row in csv.DictReader(handle):
            row['lat'] = float(row['lat'])
            row['lon'] = float(row['lon'])
            rows[row['iata']] = row
        return rows


def lookup(code):
    """Reference record for an IATA airport code, or None when unknown."""
    code = normalize(code)
    return table().get(code) if code else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('codes', nargs='+', help='IATA airport codes')
    args = parser.parse_args()
    result = {code.upper(): lookup(code) for code in args.codes}
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if any(v is None for v in result.values()):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
