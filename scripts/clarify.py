#!/usr/bin/env python3
"""Word the open questions in a Flight Atlas summary as one short chat message.

  python3 clarify.py summary.json            # the message to send
  python3 clarify.py summary.json --json     # the same questions as data

Each question names the exact flight it is about and offers the same simple answers:
send the ticket, boarding pass or a screenshot; say it was another way (train, car, bus, ferry);
say it fell outside the report dates; or leave it as a gap. Nothing is added to the ledger
until the person answers. Stdlib only.
"""
import argparse
import datetime as dt
import json
import sys
from pathlib import Path

from airports import lookup

MAX_QUESTIONS = 5


def place(code):
    ref = lookup(code)
    city = (ref or {}).get('city') or ''
    return f'{city} ({code})' if city else str(code)


def city(code):
    ref = lookup(code)
    return (ref or {}).get('city') or str(code)


def day(value, with_year=False):
    try:
        d = dt.date.fromisoformat(str(value)[:10])
    except ValueError:
        return str(value)
    return f'{d.day} {d.strftime("%b")}' + (f' {d.year}' if with_year else '')


def flight(leg, with_year=False):
    return f'{leg["origin"]} → {leg["destination"]}, {day(leg["date"], with_year)}'


def on(leg, with_year=False):
    """'on 3 Mar (LIS → ORD)'"""
    return f'on {day(leg["date"], with_year)} ({leg["origin"]} → {leg["destination"]})'


def word(question, with_year=False):
    """One numbered question, in plain words, with its answer options."""
    kind = question['kind']
    if kind == 'confirm_home':
        names = ' and '.join(place(c) for c in question['airports'])
        return (f'**Home:** I treated {names} as home, so a trip starts when you leave it. '
                'Is that right? If you have more than one home base, name them all.', None)
    if kind == 'missing_outbound':
        leg = question['leg']
        return (f'**{city(question["place"])}:** I found your flight from {city(question["place"])} {on(leg, with_year)} '
                f'but nothing that took you there. How did you get to {city(question["place"])}?', 'trip')
    if kind == 'missing_return':
        leg = question['leg']
        return (f'**{city(question["place"])}:** I found your flight to {city(question["place"])} {on(leg, with_year)} '
                f'but no flight onwards or back. How did you leave {city(question["place"])}?', 'trip')
    if kind == 'missing_transfer':
        a, b = question['after'], question['before']
        here, there = city(a['destination']), city(b['origin'])
        if here == there:
            # Two airports in one city: name the airports, not the city twice.
            here, there = a['destination'], b['origin']
            title, prep = city(a['destination']), 'at'
        else:
            title, prep = f'{here} to {there}', 'in'
        # The date shown is when that flight left, not when it landed (an overnight flight lands a day later).
        into = 'your flight into' if prep == 'in' else 'your flight to'
        return (f'**{title}:** after {into} {here} {on(a, with_year)}, your next flight left from {there} {on(b, with_year)}. '
                f'How did you get from {here} to {there}?', 'trip')
    if kind == 'unknown_duration':
        legs = question['legs']
        shown = ', '.join(flight(l, with_year) for l in legs[:4]) + (f' and {len(legs) - 4} more' if len(legs) > 4 else '')
        n = len(legs)
        return (f'**Flight times:** {n} flight{"s have" if n != 1 else " has"} no scheduled time on record ({shown}). '
                'If you have the e-tickets or a screenshot of the booking, send them and I\'ll add the hours.', None)
    return (f'**Check:** {kind}', None)


OPTIONS = {
    'trip': 'For each, reply **flew** (send the e-ticket, boarding pass or a screenshot, or just tell me the flight and date), '
            '**another way** (train, car, bus, ferry), **outside the dates** (before or after this report), or **not sure** (I\'ll keep it marked as a gap).',
}


def message(summary, limit=MAX_QUESTIONS):
    questions = summary.get('clarifications') or []
    if not questions:
        return ''
    dates = [str(t.get('start_date', ''))[:4] for t in summary.get('trips', [])]
    with_year = len(set(dates)) > 1
    lines, kinds = [], []
    for i, q in enumerate(questions[:limit], 1):
        text, kind = word(q, with_year)
        if q.get('hint'):
            text += f' I found: {q["hint"]}'
        lines.append(f'{i}. {text}')
        if kind and kind not in kinds:
            kinds.append(kind)
    head = (f'A few things would make your flight record complete. '
            f'I won\'t add any flight you haven\'t confirmed or sent a document for.')
    body = '\n'.join(lines)
    extra = len(questions) - limit
    tail = [OPTIONS[k] for k in kinds]
    if extra > 0:
        tail.append(f'There {"are" if extra != 1 else "is"} {extra} more open item{"s" if extra != 1 else ""} after these; I\'ll ask once these are settled.')
    tail.append('You can answer in any order, just numbers and a word or two is fine, and documents can be PDFs, photos or screenshots.')
    return head + '\n\n' + body + '\n\n' + '\n\n'.join(tail)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('summary', type=Path)
    parser.add_argument('--json', action='store_true', help='print the questions as data')
    parser.add_argument('--limit', type=int, default=MAX_QUESTIONS)
    args = parser.parse_args()
    try:
        summary = json.loads(args.summary.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as error:
        sys.exit(f'Could not read summary: {error}')
    if args.json:
        print(json.dumps(summary.get('clarifications', []), indent=2, ensure_ascii=False))
        return
    print(message(summary, args.limit) or 'No open questions: every trip is closed, explained or has its return booked, and every flight has a time.')


if __name__ == '__main__':
    main()
