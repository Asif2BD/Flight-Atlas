#!/usr/bin/env python3
"""Turn saved mail-search results into a one-line-per-message travel index.

Stdlib only. Reads one or more JSON files saved from a mail search tool (Gmail-style
``{"threads": [{"messages": [...]}]}``, a plain list of messages, or ``{"messages": [...]}``)
and prints, oldest first, one short line per distinct message:

    2025-05-13  boarding   example-air.test  AAA-BBB 14 May 2025  "Boarding pass for Jordan Lee ZZ0450..."

Each line carries a kind (booking, change, cancel, checkin, boarding, loyalty, ground,
hotel, noise, other) and any route or date the subject already gives, so a long period can be
triaged from metadata before a single message is opened. With ``--traveler "First Last"``
it also flags messages addressed to a different passenger (``other:<name>``), which is how
bookings made for family and colleagues stay out of the traveler's ledger.

This is a triage aid, not a parser: it never decides what was flown, and a kind is a guess
from the subject and preview. Open the message before recording a flight.
"""
import argparse
import html
import json
import re
import sys
from pathlib import Path

MONTHS = 'jan feb mar apr may jun jul aug sep oct nov dec'.split()
MONTH = r'(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*'

# Order matters: the first matching kind wins.
KINDS = [
    ('noise', re.compile(r'how was your (?:check-?in|stay|trip)|rate your|newsletter|webinar|'
                         r'meeting|invitation:|reminder: your meeting|sale\b|deals?\b|% off|'
                         r'save up to|offer|mentors|survey|review your|quiz|travel tip|free nights|'
                         r'is protected|stowaway|pre-arrival|nytimes|medium\.com|substack|newsletter', re.I)),
    ('cancel', re.compile(r'cancel|refund|void', re.I)),
    ('change', re.compile(r'schedule change|flight change|time change|rebook|reschedul|'
                          r'updated itinerary|itinerary (?:change|update)|has changed|disruption', re.I)),
    ('boarding', re.compile(r'boarding pass|carte d.embarquement|check-?in confirmation|'
                            r"you(?:'re| are) checked in", re.I)),
    ('checkin', re.compile(r'check[- ]?in (?:online|now|is open|open)|check in online|'
                           r'time to check in|can now check in|online check-?in|check-?in starts', re.I)),
    ('loyalty', re.compile(r'miles? (?:credited|posted|added)|skywards|statement|points (?:credited|posted)|'
                           r'thank(?:s| you) for flying', re.I)),
    ('ground', re.compile(r'flix|bus\b|train|rail|ferry|coach|uber|gojek|grab\b|careem|taxi', re.I)),
    ('hotel', re.compile(r'hotel|stay at|reservation at|room|resort|check-?in rezervace|pre-arrival|'
                         r'car rental|rental confirmation|budget\.com|hertz|avis\.|sixt|enterprise\.com', re.I)),
    ('booking', re.compile(r'itinerary|e-?ticket|ticket receipt|booking confirm|flight confirm|'
                           r'flight purchase|flight booking|your flight|your trip to|reservation|'
                           r'booking (?:no|#|ref)|pnr', re.I)),
]
FLIGHT_SUBJECT = re.compile(r'flight|air|e-?ticket|boarding|itinerary', re.I)

ROUTE = re.compile(r'\b([A-Z]{3})\s*(?:-|–|→|✈|to)\s*([A-Z]{3})\b')
CITY_ROUTE = re.compile(r'\b([A-Z][a-z]+(?: [A-Z][a-z]+)?)\s*(?:✈|→)\s*([A-Z][a-z]+(?: [A-Z][a-z]+)?)')
TO_CITY = re.compile(r'(?:flight|trip|flying) to ([A-Z][A-Za-z .\'-]{1,30}?)(?: on| - |,|\(|$)')
DAY_MONTH = re.compile(rf'\b(\d{{1,2}})[ -]({MONTH})(?:[ -](\d{{2,4}}))?\b', re.I)
MONTH_DAY = re.compile(rf'\b({MONTH})\.? (\d{{1,2}})\b(?:,? (\d{{4}}))?', re.I)

# Salutations and "for <NAME>" phrases that name the passenger.
PASSENGER = [
    re.compile(r'\b(?i:hello|dear|hi)\s+(?:(?i:mr|mrs|ms|miss|mstr|dr)\.?\s+)?([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,3})'),
    re.compile(r'\bfor\s+(?:MR|MRS|MS|MISS|MSTR|DR)\.?\s+([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,3})'),
    re.compile(r'\b(?i:passenger):?\s+(?:(?i:mr|mrs|ms|miss|mstr|dr)\.?\s+)?([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,3})'),
]
TITLES = {'mr', 'mrs', 'ms', 'miss', 'mstr', 'dr', 'passenger', 'customer', 'traveller', 'traveler', 'guest'}
# Greetings that name nobody.
NOT_A_NAME = {'sir', 'madam', 'user', 'customer', 'valued', 'member', 'concern', 'details', 'all', 'there',
              'traveller', 'traveler', 'guest', 'friend', 'team', 'passenger', 'colleague', 'partner'}
STOP = {'thank', 'thanks', 'your', 'you', 'we', 'the', 'and', 'this', 'there', 'team', 'online', 'check',
        'booking', 'flight', 'below', 'please', 'at', 'is', 'has', 'been', 'issued', 'our', 'for',
        'itinerary', 'confirmation', 'e', 'ticket', 'reservation', 'receipt', 'welcome', 'with'}


def tokens(name):
    out = []
    for t in re.findall(r'[a-z]+', name.lower()):
        if t in TITLES:
            continue
        # Airline style "RAHMAN/ASIFMR" glues the title onto the given name.
        for title in ('mrs', 'mstr', 'miss', 'mr', 'ms'):
            if t.endswith(title) and len(t) > len(title) + 1:
                t = t[:-len(title)]
                break
        out.append(t)
    return out


def passenger_names(text):
    found = []
    for pattern in PASSENGER:
        for m in pattern.finditer(text):
            words = []
            shouting = m.group(1).split()[0].isupper()
            for w in m.group(1).split():
                # "SAM LEE Itinerary": an upper-case name ends at the first ordinary word.
                if w.lower() in STOP or (shouting and not w.isupper()):
                    break
                words.append(w)
            if words and words[0].lower() not in NOT_A_NAME:
                found.append(' '.join(words))
    return found


def same_person(name, traveler):
    """True when every name the traveler goes by is present (order-free, initials allowed).

    "LEE JORDAN" and "M Jordan Lee" match "Jordan Lee"; "Sam Lee" does not.
    A single given name ("Hello Jordan") matches when it is one of the traveler's names.
    """
    have, want = tokens(name), tokens(traveler)
    if not have or not want:
        return True
    if len(have) == 1:
        return have[0] in want
    full = [t for t in have if len(t) > 1]
    return all(w in full for w in want) or (len(full) == 1 and full[0] in want and len(want) == 1)


def classify(subject, snippet, sender):
    text = subject + ' ' + snippet[:80]
    for kind, pattern in KINDS:
        if pattern.search(subject) or (kind in ('noise', 'ground', 'hotel') and pattern.search(sender)):
            if kind in ('cancel', 'change') and not FLIGHT_SUBJECT.search(text + ' ' + sender):
                continue
            return kind
    # Previews are noisy ("free cancellation", "change your seat"): only the calmer kinds count there.
    for kind, pattern in KINDS:
        if kind in ('noise', 'cancel', 'change'):
            continue
        if pattern.search(snippet[:160]):
            return kind
    return 'other'


def date_hint(subject):
    m = DAY_MONTH.search(subject)
    if m:
        year = m.group(3)
        year = ('20' + year) if year and len(year) == 2 else year
        return f"{int(m.group(1))} {m.group(2)[:3].title()}" + (f' {year}' if year else '')
    m = MONTH_DAY.search(subject)
    if m:
        return f"{int(m.group(2))} {m.group(1)[:3].title()}" + (f' {m.group(3)}' if m.group(3) else '')
    return ''


def route_hint(subject):
    m = ROUTE.search(subject)
    if m and m.group(1) != m.group(2):
        return f'{m.group(1)}-{m.group(2)}'
    m = CITY_ROUTE.search(subject)
    if m:
        return f'{m.group(1)}-{m.group(2)}'
    m = TO_CITY.search(subject)
    if m:
        return 'to ' + m.group(1).strip()
    return ''


def messages(data):
    """Yield message dicts from the shapes mail tools return."""
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and isinstance(item.get('text'), str):
                try:
                    yield from messages(json.loads(item['text']))
                    continue
                except json.JSONDecodeError:
                    pass
            if isinstance(item, dict):
                yield from messages(item) if ('threads' in item or 'messages' in item) else [item]
        return
    if not isinstance(data, dict):
        return
    for thread in data.get('threads', []) or []:
        for message in thread.get('messages', []) or []:
            yield message
    for message in data.get('messages', []) or []:
        yield message
    for message in data.get('value', []) or []:  # Microsoft Graph style
        yield message


def field(m, *names):
    for n in names:
        v = m.get(n)
        if isinstance(v, dict):
            v = v.get('emailAddress', v).get('address') if isinstance(v.get('emailAddress', v), dict) else None
        if v:
            return html.unescape(str(v))
    return ''


def index(paths_or_data, traveler=None):
    rows, seen = [], set()
    for data in paths_or_data:
        for m in messages(data):
            ident = field(m, 'id', 'messageId')
            if not ident or ident in seen:
                continue
            seen.add(ident)
            subject = field(m, 'subject')
            snippet = re.sub(r'\s+', ' ', field(m, 'snippet', 'bodyPreview'))
            sender = field(m, 'sender', 'from')
            day = field(m, 'date', 'receivedDateTime')[:10]
            kind = classify(subject, snippet, sender)
            flags = []
            if traveler and kind not in ('noise', 'hotel'):
                others = sorted({n for n in passenger_names(subject + ' ' + snippet) if not same_person(n, traveler)})
                if others:
                    flags.append('other:' + '/'.join(others))
            if re.search(r'^(?:fwd?|fw):', subject, re.I):
                flags.append('forwarded')
            rows.append({'received': day, 'id': ident, 'thread_id': field(m, 'threadId', 'conversationId'),
                         'kind': kind, 'sender': sender, 'route': route_hint(subject), 'date_hint': date_hint(subject),
                         'flags': flags, 'subject': subject[:120]})
    rows.sort(key=lambda r: (r['received'], r['id']))
    return rows


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('files', nargs='+', help='saved search results (JSON); "-" reads stdin')
    p.add_argument('--traveler', help='the passenger whose flights you are reconstructing, e.g. "Jordan Lee"')
    p.add_argument('--keep-noise', action='store_true', help='also print messages classed as noise or hotel')
    p.add_argument('--json', action='store_true', help='print JSON rows instead of text lines')
    a = p.parse_args()
    loaded = []
    for f in a.files:
        try:
            text = sys.stdin.read() if f == '-' else Path(f).read_text(encoding='utf-8')
            loaded.append(json.loads(text))
        except (OSError, json.JSONDecodeError) as e:
            sys.exit(f'Could not read {f}: {e}')
    rows = index(loaded, a.traveler)
    shown = [r for r in rows if a.keep_noise or r['kind'] not in ('noise', 'hotel')]
    if a.json:
        print(json.dumps(shown, indent=1, ensure_ascii=False))
    else:
        for r in shown:
            hint = ' '.join(x for x in (r['route'], r['date_hint']) if x)
            flags = (' [' + ', '.join(r['flags']) + ']') if r['flags'] else ''
            print(f"{r['received']}  {r['kind']:<8} {r['id']}  {r['sender'][:30]:<30} {hint:<28}{flags}  {r['subject'][:80]}")
    counts = {}
    for r in rows:
        counts[r['kind']] = counts.get(r['kind'], 0) + 1
    print(f'# {len(rows)} messages; ' + ', '.join(f'{k} {v}' for k, v in sorted(counts.items())) +
          f'; {len(rows) - len(shown)} noise/hotel hidden', file=sys.stderr)


if __name__ == '__main__':
    main()
