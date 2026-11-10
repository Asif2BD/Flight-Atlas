#!/usr/bin/env python3
"""Combine partial Flight Atlas ledgers (for example one per sub-agent or per half-year) into one draft.

Stdlib only. Each input is a ledger v1 object or any JSON object with a "legs" list (plus optional
"ground_segments" and "manual_gaps"). The output is a single ledger v1 draft ready for enrich.py.

What it does, and nothing more:
- concatenates legs, ground segments and manual gaps;
- renames a clashing leg id (prefixing the input's file name) and updates references to it inside
  the same input (supersedes_id, duplicate_of, ground after_id/before_id, manual gap ids);
- merges copies of the same physical flight that overlapping searches found twice: same traveler,
  departure date, route and operating flight (or, when neither copy has a flight number, the same
  printed departure time). The merged row keeps every evidence id and the strongest status;
  a cancelled, superseded or other-traveler row is never merged into a flown one;
- sets report fields given on the command line (title, dates, as_of, home airports).

It prints what it merged and renamed. It does not decide what was flown or resolve conflicts:
two copies that disagree on times are kept apart and listed for review.
"""
import argparse
import datetime as dt
import json
import sys
from pathlib import Path

def _union(a, b):
    a = a if isinstance(a, list) else [a]
    b = b if isinstance(b, list) else [b]
    return list(dict.fromkeys(a + b))


# How to combine report fields that differ between parts; any other field keeps the first part's value.
WIDEN = {'start_date': lambda a, b: min(str(a), str(b)), 'end_date': lambda a, b: max(str(a), str(b)),
         'as_of': lambda a, b: max(str(a), str(b)), 'home_airports': _union}

BASIS = {'ticket_advertised': 4, 'historical_schedule': 3, 'schedule_calculated': 2, 'estimated': 1}
RANK = {'flown': 5, 'user_confirmed': 4, 'strongly_supported': 3, 'itinerary_only': 2}
REFS = ('supersedes_id', 'duplicate_of')


def flight(value):
    return str(value or '').replace(' ', '').upper()


def norm_flight(value):
    v = flight(value)
    # ZZ0586 and ZZ586 are the same flight: drop leading zeros after the two-character airline code.
    if len(v) > 2:
        head, tail = v[:2], v[2:].lstrip('0')
        return head + tail
    return v


def key(leg):
    f = norm_flight(leg.get('operating_flight'))
    base = (leg.get('traveler_id'), str(leg.get('departure_date', ''))[:10],
            str(leg.get('origin', '')).upper(), str(leg.get('destination', '')).upper())
    if f:
        return base + ('F:' + f,)
    if leg.get('departure_local'):
        return base + ('T:' + str(leg['departure_local'])[:16],)
    return None


def same_value(field, a, b):
    """Offset-aware timestamps are compared as instants (10:00+04:00 equals 06:00Z); other fields as written."""
    if field.endswith('_scheduled'):
        try:
            return instant(a) == instant(b)
        except (ValueError, TypeError, AttributeError):
            return a == b
    return a == b


def instant(value):
    t = dt.datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if t.utcoffset() is None:
        raise ValueError('no offset')
    return t.astimezone(dt.timezone.utc)


def load(path):
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as e:
        sys.exit(f'Could not read {path}: {e}')
    if not isinstance(data, dict) or not isinstance(data.get('legs'), list):
        sys.exit(f'{path}: expected a JSON object with a "legs" list')
    return data


def rename_within(data, mapping):
    """Point references inside one input at renamed legs; `mapping` is old id -> new id, applied once."""
    for leg in data['legs']:
        for ref in REFS:
            if leg.get(ref) in mapping:
                leg[ref] = mapping[leg[ref]]
    for item in data.get('ground_segments', []) + data.get('manual_gaps', []):
        if isinstance(item, dict):
            for ref in ('after_id', 'before_id', 'leg_id'):
                if item.get(ref) in mapping:
                    item[ref] = mapping[item[ref]]


def merge(inputs, names=None):
    """Return (ledger, log). `inputs` are ledger-like dicts; `names` label them for renamed ids."""
    names = names or [f'part{i + 1}' for i in range(len(inputs))]
    legs, ground, gaps, log = [], [], [], []
    used = set()
    report = {}
    copies = [json.loads(json.dumps(data)) for data in inputs]
    # Reserve every id that any input uses before inventing replacements, so a new name never
    # collides with a leg that has not been processed yet.
    reserved = {str(leg.get('id')) for data in copies for leg in data['legs'] if leg.get('id')}
    for data, name in zip(copies, names):
        if isinstance(data.get('report'), dict):
            for k, v in data['report'].items():
                if k not in report:
                    report[k] = v
                elif report[k] != v and k in WIDEN:
                    # Parts cover different periods: the merged report spans all of them.
                    report[k] = WIDEN[k](report[k], v)
                    log.append(f'report.{k}: {name} differs; using {report[k]}')
        mapping = {}
        for leg in data['legs']:
            ident = str(leg.get('id') or '')
            if not ident or ident in used:
                new = f'{name}-{ident or "leg"}'
                n = 2
                while new in used or new in reserved:
                    new = f'{name}-{ident or "leg"}-{n}'
                    n += 1
                log.append(f'renamed {ident or "(missing id)"} from {name} to {new}')
                if ident:
                    mapping.setdefault(ident, new)
                leg['id'] = new
                reserved.add(new)
            used.add(leg['id'])
        # One pass with the whole mapping, so a reference is rewritten at most once.
        if mapping:
            rename_within(data, mapping)
        legs.extend(data['legs'])
        ground.extend(g for g in data.get('ground_segments', []) if isinstance(g, dict))
        gaps.extend(g for g in data.get('manual_gaps', []) if isinstance(g, dict))

    kept, byid, groups = [], {}, {}
    referenced = {leg.get(r) for leg in legs for r in REFS} - {None}
    for leg in legs:
        k = key(leg)
        status = leg.get('status')
        if k is None or status not in RANK or leg['id'] in referenced or leg.get('supersedes_id') or leg.get('duplicate_of'):
            kept.append(leg)
            continue
        first = groups.get(k)
        if first is None:
            groups[k] = leg
            kept.append(leg)
            continue
        clash = [f for f in ('departure_local', 'arrival_local', 'scheduled_minutes', 'departure_scheduled', 'arrival_scheduled')
                 if first.get(f) not in (None, '') and leg.get(f) not in (None, '') and not same_value(f, first[f], leg[f])]
        if clash:
            log.append(f'kept {leg["id"]} apart from {first["id"]}: same flight but different {", ".join(clash)}; review')
            kept.append(leg)
            continue
        ids = list(dict.fromkeys(list(first.get('evidence_ids') or []) + list(leg.get('evidence_ids') or [])))
        if RANK[status] > RANK[first['status']]:
            first['status'] = status
        # Same minutes from a better source (a ticket beats an estimate): keep the better provenance.
        if BASIS.get(leg.get('duration_basis'), 0) > BASIS.get(first.get('duration_basis'), 0) and leg.get('scheduled_minutes') is not None:
            first['duration_basis'] = leg['duration_basis']
        for field, value in leg.items():
            if first.get(field) in (None, '', []) and value not in (None, '', []):
                first[field] = value
        first['evidence_ids'] = ids
        notes = [n for n in (first.get('evidence_note'), leg.get('evidence_note')) if n]
        if len(notes) == 2 and notes[1] not in notes[0]:
            first['evidence_note'] = notes[0] + '; ' + notes[1]
        byid[leg['id']] = first['id']
        log.append(f'merged {leg["id"]} into {first["id"]} ({k[1]} {k[2]}-{k[3]})')
    for item in ground + gaps:
        for ref in ('after_id', 'before_id', 'leg_id'):
            if item.get(ref) in byid:
                item[ref] = byid[item[ref]]
    kept.sort(key=lambda l: (str(l.get('departure_date', '')), str(l.get('departure_local', ''))))
    out = {'schema_version': 1, 'report': report, 'legs': kept}
    if ground:
        out['ground_segments'] = ground
    if gaps:
        out['manual_gaps'] = gaps
    return out, log


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('inputs', nargs='+')
    p.add_argument('--out', required=True)
    p.add_argument('--title')
    p.add_argument('--start')
    p.add_argument('--end')
    p.add_argument('--as-of')
    p.add_argument('--home', help='home airports, comma separated, e.g. DXB,MNL')
    a = p.parse_args()
    data = [load(x) for x in a.inputs]
    ledger, log = merge(data, [Path(x).stem for x in a.inputs])
    r = ledger['report']
    for field, value in (('title', a.title), ('start_date', a.start), ('end_date', a.end), ('as_of', a.as_of)):
        if value:
            r[field] = value
    if a.home:
        r['home_airports'] = [c.strip().upper() for c in a.home.split(',') if c.strip()]
    Path(a.out).write_text(json.dumps(ledger, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    for line in log:
        print(line)
    print(f'{len(ledger["legs"])} legs written to {a.out} from {sum(len(d["legs"]) for d in data)} input rows')


if __name__ == '__main__':
    main()
