#!/usr/bin/env python3
"""Fill airport coordinates, countries, time zones and UTC offsets in a Flight Atlas ledger.

Stdlib only; no network. Uses the bundled airport table (assets/airports.csv) and the
system IANA time-zone database via zoneinfo (Windows: `pip install tzdata`).

For each leg it:
  * upper-cases IATA codes;
  * fills missing origin/destination lat, lon and country, and adds origin_tz / destination_tz;
  * turns `departure_local` / `arrival_local` (wall-clock time printed on the ticket, no offset)
    into offset-aware `departure_scheduled` / `arrival_scheduled`, handling DST;
  * checks values that are already present (coordinates, country, offsets) against the reference
    and warns on disagreement instead of silently trusting either side.

Existing values are kept unless --overwrite is given. Review every warning before analyzing.
"""
import argparse
import copy
import datetime as dt
import json
import math
import re
from pathlib import Path

from airports import lookup, normalize

try:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
except ImportError:  # pragma: no cover - Python < 3.9 is unsupported anyway
    raise SystemExit('Python 3.10+ with zoneinfo is required')

COORD_TOLERANCE_DEG = 0.25


def zone(name):
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return None


def parse_local(value):
    """Parse a wall-clock timestamp with no offset. Returns (datetime, error)."""
    if not isinstance(value, str) or not value.strip():
        return None, 'empty local time'
    if not re.match(r'^\d{4}-\d{2}-\d{2}[T ]\d{1,2}:\d{2}', value.strip()):
        return None, f'local time {value!r} has no clock time (use YYYY-MM-DDTHH:MM); missing times stay unknown'
    try:
        parsed = dt.datetime.fromisoformat(value.strip().replace(' ', 'T', 1))
    except ValueError:
        return None, f'unreadable local time {value!r} (use YYYY-MM-DDTHH:MM)'
    if parsed.tzinfo is not None:
        return None, f'local time {value!r} already has an offset; put it in *_scheduled instead'
    return parsed, None


def localize(naive, tz):
    """Attach a zone, refusing DST gaps and ambiguous fall-back times. Returns (aware, error)."""
    early = naive.replace(tzinfo=tz, fold=0)
    late = naive.replace(tzinfo=tz, fold=1)
    roundtrip = early.astimezone(dt.timezone.utc).astimezone(tz).replace(tzinfo=None)
    if roundtrip != naive:
        return None, f'{naive.isoformat()} does not exist in {tz.key} (DST gap)'
    if early.utcoffset() != late.utcoffset():
        return None, f'{naive.isoformat()} is ambiguous in {tz.key} (DST fall-back); obtain the offset from the source'
    return early, None


def iso(aware):
    text = aware.isoformat(timespec='seconds')
    return text


def parse_aware(value):
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except ValueError:
        return None
    return parsed if parsed.utcoffset() is not None else None


def enrich(data, overwrite=False):
    """Return (enriched copy, warnings, counts). Never mutates the input."""
    data = copy.deepcopy(data)
    warnings = []
    counts = {'codes_normalized': 0, 'coordinates_filled': 0, 'countries_filled': 0,
              'time_zones_added': 0, 'timestamps_filled': 0, 'dates_filled': 0}
    for leg in data.get('legs', []):
        ident = leg.get('id', '?')
        zones = {}
        for side in ('origin', 'destination'):
            raw = leg.get(side)
            code = normalize(raw)
            if raw is not None and code is None:
                warnings.append(f'{ident}: {side} {raw!r} is not a three-letter IATA code; not enriched')
                continue
            if code is None:
                continue
            if code != raw:
                leg[side] = code
                counts['codes_normalized'] += 1
            ref = lookup(code)
            if ref is None:
                warnings.append(f'{ident}: {side} {code} not in bundled airport table; supply verified coordinates, country and offsets manually')
                continue
            lat_key, lon_key, country_key, tz_key = (f'{side}_lat', f'{side}_lon', f'{side}_country', f'{side}_tz')
            lat, lon = leg.get(lat_key), leg.get(lon_key)
            have_coords = all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in (lat, lon))
            if not have_coords or overwrite:
                if have_coords and (abs(lat - ref['lat']) > COORD_TOLERANCE_DEG or abs(lon - ref['lon']) > COORD_TOLERANCE_DEG):
                    warnings.append(f'{ident}: {side} {code} coordinates replaced with reference values')
                leg[lat_key], leg[lon_key] = ref['lat'], ref['lon']
                counts['coordinates_filled'] += 1
            elif abs(lat - ref['lat']) > COORD_TOLERANCE_DEG or abs(lon - ref['lon']) > COORD_TOLERANCE_DEG:
                warnings.append(f'{ident}: {side} {code} coordinates ({lat}, {lon}) differ from reference ({ref["lat"]}, {ref["lon"]}); verify or re-run with --overwrite')
            if not leg.get(country_key) or overwrite:
                if leg.get(country_key) != ref['country']:
                    counts['countries_filled'] += 1
                leg[country_key] = ref['country']
            elif leg[country_key] != ref['country']:
                warnings.append(f'{ident}: {side} {code} country {leg[country_key]!r} differs from reference {ref["country"]!r}')
            tz = zone(ref['tz'])
            if tz is None:
                warnings.append(f'{ident}: time zone {ref["tz"]} unavailable on this system (install tzdata); offsets not computed for {code}')
                continue
            if leg.get(tz_key) != ref['tz']:
                leg[tz_key] = ref['tz']
                counts['time_zones_added'] += 1
            zones[side] = tz
        for side, key in (('origin', 'departure'), ('destination', 'arrival')):
            local_key, sched_key = f'{key}_local', f'{key}_scheduled'
            tz = zones.get(side)
            existing = parse_aware(leg[sched_key]) if leg.get(sched_key) else None
            if leg.get(sched_key) and existing is None:
                warnings.append(f'{ident}: {sched_key} {leg[sched_key]!r} lacks a UTC offset')
            if leg.get(local_key):
                naive, error = parse_local(leg[local_key])
                if error:
                    warnings.append(f'{ident}: {local_key}: {error}')
                    continue
                if key == 'departure':
                    # The calendar date is known even when the UTC offset cannot be resolved.
                    day = naive.date().isoformat()
                    if not leg.get('departure_date'):
                        leg['departure_date'] = day
                        counts['dates_filled'] += 1
                    elif leg['departure_date'] != day:
                        warnings.append(f'{ident}: departure_date {leg["departure_date"]} differs from departure_local date {day}')
                if tz is None:
                    continue
                aware, error = localize(naive, tz)
                if error:
                    warnings.append(f'{ident}: {local_key}: {error}')
                    continue
                if existing is not None and existing != aware and not overwrite:
                    warnings.append(f'{ident}: {sched_key} {leg[sched_key]} disagrees with {local_key} in {tz.key} ({iso(aware)}); kept existing, verify')
                    continue
                if existing is None or overwrite or existing.utcoffset() != aware.utcoffset():
                    # Same instant written in another zone is rewritten in the airport's own zone,
                    # so its date matches the local departure date the analyzer checks.
                    leg[sched_key] = iso(aware)
                    counts['timestamps_filled'] += 1
            elif existing is not None and tz is not None:
                wall = existing.replace(tzinfo=None)
                roundtrip = wall.replace(tzinfo=tz).astimezone(dt.timezone.utc).astimezone(tz).replace(tzinfo=None)
                if roundtrip != wall:
                    warnings.append(f'{ident}: {sched_key} {leg[sched_key]} is a clock time that does not exist in {tz.key} (DST gap); check the source')
                    continue
                expected = wall.replace(tzinfo=tz, fold=0).utcoffset()
                expected_late = wall.replace(tzinfo=tz, fold=1).utcoffset()
                if existing.utcoffset() not in (expected, expected_late):
                    hours = existing.utcoffset().total_seconds() / 3600
                    want = expected.total_seconds() / 3600
                    warnings.append(f'{ident}: {sched_key} offset {hours:+g}h does not match {tz.key} on that date ({want:+g}h); check DST')
    return data, warnings, counts


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('input')
    parser.add_argument('--out', required=True)
    parser.add_argument('--overwrite', action='store_true', help='replace existing values with reference/local-time results')
    args = parser.parse_args()
    try:
        data = json.loads(Path(args.input).read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit(f'Could not read ledger: {error}')
    if not isinstance(data, dict) or not isinstance(data.get('legs'), list):
        raise SystemExit('Ledger must be a JSON object with a "legs" list')
    result, warnings, counts = enrich(data, args.overwrite)
    Path(args.out).write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps({'filled': counts, 'warnings': warnings}, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
