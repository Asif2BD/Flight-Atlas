#!/usr/bin/env python3
"""Work out which cities and countries a traveler stayed in, from the order of their flights.

Stdlib only. Used by analyze.py. A flight record proves where a plane landed, not where a person
went, so this keeps two lists apart:

- **visited**: places they stayed. An airport counts when the next flight leaves from somewhere
  else (they moved on by road, rail or an unknown way), when there is no next flight, when the next
  flight leaves at least STAY_HOURS later, or when the next flight takes them straight back where
  they came from (a day trip).
- **transit**: airports they only changed planes at: the next flight left the same airport within
  STAY_HOURS and went on somewhere new (or the times are unknown and it left the same or next day).
  A country seen only this way is a transit country, never a visited one.

Home airports are visited by definition and are marked as home. Nothing here adds a flight or a
visit; a person who left the airport on a short connection still shows as transit, so the visited
count is a floor, not a ceiling.
"""
import csv
import datetime as dt
from pathlib import Path

try:
    from airports import lookup
except ImportError:  # used on its own
    lookup = None

STAY_HOURS = 16
TIMING = ('arrival_local', 'departure_local', 'scheduled_minutes')
ASSETS = Path(__file__).resolve().parent.parent / 'assets'
_NAMES = None


def country_name(code):
    global _NAMES
    if _NAMES is None:
        try:
            with open(ASSETS / 'countries.csv', encoding='utf-8') as fh:
                _NAMES = {r['iso_a2']: r['name'] for r in csv.DictReader(fh)}
        except OSError:
            _NAMES = {}
    return _NAMES.get(code) or code


def _instant(value):
    try:
        t = dt.datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except ValueError:
        return None
    return t if t.utcoffset() is not None else None


# The latest a flight can land, in calendar days after its departure date, when nothing else says
# (the longest flights plus crossing the date line).
MAX_ARRIVAL_DAYS = 2
MAX_OFFSET_SHIFT_HOURS = 26


def _day(value):
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _latest_arrival_date(leg):
    """Calendar date the leg landed on, or the latest it could have been when only the departure is known."""
    for field in ('arrival_local', 'arrival_scheduled'):
        if leg.get(field):
            day = _day(leg[field])
            if day:
                return day
    start = _day(leg.get('departure_local') or leg.get('departure_date') or '')
    if start is None:
        return None
    minutes = leg.get('scheduled_minutes')
    if leg.get('departure_local') and isinstance(minutes, (int, float)):
        # Local departure plus flight time plus the widest gap between two offsets (UTC-12 to UTC+14: 26h).
        try:
            t = dt.datetime.fromisoformat(str(leg['departure_local'])[:16])
            return (t + dt.timedelta(minutes=minutes, hours=MAX_OFFSET_SHIFT_HOURS)).date()
        except ValueError:
            pass
    return start + dt.timedelta(days=MAX_ARRIVAL_DAYS)


def _hours_between(arrival_leg, departure_leg):
    """Hours on the ground between two legs: exact from offset-aware times, else a floor from dates.

    Without times, only a whole calendar day between landing and the next departure proves a stay
    (24h or more); anything closer is unknown and returned as None.
    """
    a, b = _instant(arrival_leg.get('arrival_scheduled')), _instant(departure_leg.get('departure_scheduled'))
    if a and b:
        return (b - a).total_seconds() / 3600
    landed, leaves = _latest_arrival_date(arrival_leg), _day(departure_leg.get('departure_local') or departure_leg.get('departure_date') or '')
    if landed is None or leaves is None:
        return None
    days = (leaves - landed).days
    return days * 24 if days >= 2 else None


def _city(code, leg, side):
    ref = lookup(code) if lookup else None
    return ((ref or {}).get('city') or code), (leg.get(side + '_country') or (ref or {}).get('country') or '')


def places(legs, homes=(), timing=None, ground=(), before=None, after=None):
    """`legs` are included legs in time order (dicts with origin, destination, departure_date, countries).

    `timing` maps leg id -> the full ledger row (for arrival_scheduled / departure_scheduled), when the
    legs themselves carry only display fields. `ground` holds confirmed or documented ground segments;
    the places listed in their `via` (city, ISO country, optional lat/lon) were stops on the way and
    count as visited. `before` and `after` are the traveler's nearest flights just outside the report
    period; they are never counted, but they decide whether the first and last airports were a stay or
    only a connection. Returns cities, countries, transit airports and counts.
    """
    timing = timing or {}
    homes = set(homes)
    stayed, passed = {}, {}

    def full(leg):
        # Display legs may drop timing fields; take them back from the ledger row (landing date, local times).
        extra = {k: v for k, v in timing.get(leg.get('id'), {}).items()
                 if (k.endswith('_scheduled') or k in TIMING) and v not in (None, '') and leg.get(k) in (None, '')}
        return {**leg, **{k: v for k, v in extra.items() if k.endswith('_scheduled')}, **{k: v for k, v in extra.items() if k in TIMING}}

    def mark(table, code, leg, side, date):
        city, country = _city(code, leg, side)
        entry = table.setdefault(code, {'airport': code, 'city': city, 'country': country, 'times': 0, 'first_date': date})
        entry['times'] += 1
        entry['first_date'] = min(entry['first_date'], date)

    def connection(arrive, depart):
        # Changed planes: same airport, onward to somewhere new, within STAY_HOURS (unknown counts as a connection).
        if depart['origin'] != arrive['destination'] or arrive['destination'] in homes or depart['destination'] == arrive['origin']:
            return False
        hours = _hours_between(full(arrive), full(depart))
        return hours is None or hours < STAY_HOURS

    if legs:
        first = legs[0]
        if before and connection(before, first):
            mark(passed, first['origin'], first, 'origin', first['departure_date'])
        else:
            mark(stayed, first['origin'], first, 'origin', first['departure_date'])
    for i, leg in enumerate(legs):
        code = leg['destination']
        nxt = legs[i + 1] if i + 1 < len(legs) else after
        if nxt is after and after is not None and nxt['origin'] != code:
            nxt = None  # the next flight outside the period left from elsewhere: it says nothing about this airport
        if nxt is not None and nxt['origin'] != code:
            # They left from another airport: they were on the ground here, and reached the next one somehow.
            mark(stayed, code, leg, 'destination', leg['departure_date'])
            mark(stayed, nxt['origin'], nxt, 'origin', nxt['departure_date'])
            continue
        if nxt is None or code in homes:
            mark(stayed, code, leg, 'destination', leg['departure_date'])
            continue
        # Unknown timing counts as a connection, so the visited list never claims more than the record shows.
        mark(passed if connection(leg, nxt) else stayed, code, leg, 'destination', leg['departure_date'])

    cities = {}
    byid = {l.get('id'): l for l in legs}
    for g in ground:
        for stop in g.get('via') or []:
            if not isinstance(stop, dict) or not stop.get('city'):
                continue
            after = byid.get(g.get('after_id')) or {}
            day = str(stop.get('date') or g.get('date') or after.get('departure_date') or '')[:10]
            key = (stop['city'], str(stop.get('country') or '').upper())
            c = cities.setdefault(key, {'city': stop['city'], 'country': key[1], 'airports': [], 'first_date': day, 'home': False})
            c['first_date'] = min(c['first_date'], day) if c['first_date'] else day
            for k in ('lat', 'lon'):
                if isinstance(stop.get(k), (int, float)):
                    c[k] = stop[k]
    for entry in stayed.values():
        key = (entry['city'], entry['country'])
        c = cities.setdefault(key, {'city': entry['city'], 'country': entry['country'], 'airports': [], 'first_date': entry['first_date'],
                                    'home': False})
        c['airports'].append(entry['airport'])
        c['first_date'] = min(c['first_date'], entry['first_date'])
        c['home'] = c['home'] or entry['airport'] in homes
    countries = {}
    for c in cities.values():
        if not c['country']:
            continue
        k = countries.setdefault(c['country'], {'country': c['country'], 'name': country_name(c['country']), 'cities': [],
                                                'first_date': c['first_date'], 'home': False})
        k['cities'].append(c['city'])
        k['first_date'] = min(k['first_date'], c['first_date'])
        k['home'] = k['home'] or c['home']
    transit_only = sorted({e['country'] for e in passed.values() if e['country'] and e['country'] not in countries})
    city_list = sorted(cities.values(), key=lambda c: (c['first_date'], c['city']))
    country_list = sorted(countries.values(), key=lambda c: (c['first_date'], c['name']))
    transit = sorted(({k: e[k] for k in ('airport', 'city', 'country', 'times')} for code, e in passed.items() if code not in stayed),
                     key=lambda e: e['airport'])
    return {'cities': city_list, 'countries': country_list, 'transit_airports': transit,
            'transit_only_countries': [{'country': c, 'name': country_name(c)} for c in transit_only],
            'stay_hours': STAY_HOURS,
            'counts': {'visited_city_count': len(city_list), 'visited_country_count': len(country_list),
                       'transit_only_country_count': len(transit_only)}}
