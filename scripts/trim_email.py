#!/usr/bin/env python3
"""Cut an airline/agency email down to its itinerary lines before reading it closely.

Stdlib only. Accepts .eml, .html/.htm or plain-text files (or stdin with "-").
Removes links, tracking URLs, markup and marketing boilerplate, then keeps only lines
that look like itinerary evidence (flight numbers, airport codes, dates, times, durations,
status words) with one line of context. Prints the trimmed text and a size note on stderr.

This is a reading aid, not a parser: it never decides what was flown. If the trimmed text
lacks a segment the source mentions, read the original message or its attachment.
"""
import argparse
import email
import email.policy
import html
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

URL = re.compile(r'<?https?://\S+>?|\bwww\.\S+|\[\]\([^)]*\)|\]\([^)]*\)')
MONTH = r'(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*'
SIGNALS = [
    re.compile(r'\b\d{1,2}:\d{2}\b'),                                        # clock times
    re.compile(rf'\b\d{{1,2}}\s+{MONTH}\b|\b{MONTH}\s+\d{{1,2}}\b', re.I),     # 3 Mar / March 3
    re.compile(r'\b\d{4}-\d{2}-\d{2}\b'),                                    # ISO dates
    re.compile(r'\b(?:[A-Z]{2}|[A-Z]\d|\d[A-Z])\s?\d{1,4}[A-Z]?\b'),         # ZZ401, UL 190, 6E1234
    re.compile(r'\b\d{1,2}\s*(?:h|hr|hrs|hours?)\s*\d{0,2}\s*(?:m|min|mins|minutes?)?\b', re.I),
    re.compile(r'\b(?:depart\w*|arriv\w*|duration|flight|itinerary|outbound|inbound|return|'
               r'operated by|terminal|non-stop|nonstop|stops?|status|confirmed|cancel\w*|'
               r'chang\w*|reschedul\w*|refund\w*|passenger\w*|traveller|traveler|'
               r'booking (?:ref\w*|no\.?|number)|e-?ticket|class|cabin|fare|'
               r'boarding|check-?in|seat|aircraft|layover|connection)\b', re.I),
]
BOILERPLATE = re.compile(r'unsubscribe|privacy policy|terms and conditions|all rights reserved|'
                         r'follow (?:us|emirates)|download (?:our|the) app|safe senders|'
                         r'do not reply|view (?:this|in) (?:email|browser)|copyright|©', re.I)
AIRPORT = re.compile(r'\b[A-Z]{3}\b')
# Reservation-system (GDS/PNR) segment lines, as travel agents paste them:
#   "2 ZZ 512 U 14FEB 6 LHRJFK HK3 0925 1340"   "ZZ 271 K 08FEB JFKLHR HK3 1615 0455+1"
GDS = re.compile(r'\b([A-Z0-9]{2})\s?(\d{1,4})\s+([A-Z])\s+(\d{2})(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)(\d{2})?'
                 r'\s+(?:\d\s+)?([A-Z]{3})\s?([A-Z]{3})\*?\s+([A-Z]{2})(\d{1,2})\s+(\d{4})\s+(\d{4})(\+\d)?\b')
GDS_STATUS = {'HK': 'confirmed', 'KK': 'confirmed', 'RR': 'reconfirmed', 'TK': 'schedule changed', 'UN': 'flight cancelled',
              'UC': 'not confirmed', 'HX': 'cancelled', 'XX': 'cancelled', 'HL': 'waitlisted', 'NO': 'no action'}


def gds_segments(text):
    """Decode reservation-system segment lines into readable segments (carrier, number, day, route, times, status).

    The year is not in the line; the caller takes it from the message date. Times are local, as printed.
    """
    out = []
    for m in GDS.finditer(text):
        carrier, number, cls, dd, mon, yy, a, b, status, pax, dep, arr, plus = m.groups()
        out.append({'flight': f'{carrier}{int(number)}', 'class': cls, 'day': f'{dd}{mon}' + (yy or ''),
                    'origin': a, 'destination': b, 'departure': f'{dep[:2]}:{dep[2:]}', 'arrival': f'{arr[:2]}:{arr[2:]}',
                    'arrival_day_offset': int(plus[1:]) if plus else 0, 'status': GDS_STATUS.get(status, status), 'seats': int(pax)})
    return out


def describe_gds(seg):
    plus = f' (+{seg["arrival_day_offset"]} day)' if seg['arrival_day_offset'] else ''
    return (f'[GDS segment] {seg["flight"]} {seg["day"]} {seg["origin"]}→{seg["destination"]} '
            f'dep {seg["departure"]} arr {seg["arrival"]}{plus}, {seg["status"]}, {seg["seats"]} seat(s)')


class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'head'):
            self.skip += 1
        if tag in ('br', 'p', 'div', 'tr', 'li', 'h1', 'h2', 'h3', 'table'):
            self.parts.append('\n')

    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'head') and self.skip:
            self.skip -= 1
        if tag in ('td', 'th'):
            self.parts.append(' | ')

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def html_to_text(markup):
    parser = _Text()
    parser.feed(markup)
    return html.unescape(''.join(parser.parts))


def load(path):
    data = sys.stdin.buffer.read() if path == '-' else Path(path).read_bytes()
    header = []
    head = data.lstrip()[:20].lower()
    if (path != '-' and path.lower().endswith('.eml')) or head.startswith((b'received:', b'return-path:', b'mime-version:', b'from:')):
        # Parse bytes so the declared MIME charset decodes the body correctly.
        message = email.message_from_bytes(data, policy=email.policy.default)
        header = [f'{k}: {message[k]}' for k in ('Subject', 'Date', 'From') if message[k]]
        body = message.get_body(preferencelist=('plain', 'html'))
        raw = body.get_content() if body else ''
        if body is not None and body.get_content_type() == 'text/html':
            raw = html_to_text(raw)
        return header, raw
    raw = data.decode('utf-8', errors='replace')
    if '<html' in raw[:2000].lower() or '<table' in raw[:5000].lower():
        raw = html_to_text(raw)
    return header, raw


def _pieces(line, limit=300):
    """Split very long lines (flattened HTML tables) so itinerary parts survive on their own."""
    if len(line) <= limit:
        return [line]
    parts = [p for p in re.split(r'\s+\|\s+|\s\*\s|(?<=[.!?])\s+|\s{3,}', line) if p and p.strip()]
    out = []
    for part in parts:
        while len(part) > limit:
            cut = part.rfind(' ', 0, limit)
            cut = cut if cut > limit // 2 else limit
            out.append(part[:cut])
            part = part[cut:]
        out.append(part)
    return out


def trim(text, context=1):
    """Return the itinerary-looking lines of an email body."""
    text = URL.sub(' ', text)
    lines = []
    for raw in text.splitlines():
        for line in _pieces(raw):
            line = re.sub(r'[|*_=]{1,}', ' ', line)
            line = re.sub(r'\s+', ' ', line).strip(' -•:')
            if line and not BOILERPLATE.search(line):
                lines.append(line)
    keep = set()
    for i, line in enumerate(lines):
        score = sum(bool(p.search(line)) for p in SIGNALS) + bool(AIRPORT.search(line))
        if score:
            keep.update(range(max(0, i - context), min(len(lines), i + context + 1)))
    out, previous = [], None
    for i in sorted(keep):
        if lines[i] != previous:
            out.append(lines[i])
            # Spell out agent-pasted reservation lines; "HK8" (8 seats) also warns that the booking covers others.
            out.extend(describe_gds(seg) for seg in gds_segments(lines[i]))
        previous = lines[i]
    return '\n'.join(out)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('inputs', nargs='+', help='.eml, .html or .txt files, or - for stdin')
    parser.add_argument('--context', type=int, default=1, help='lines of context around each match')
    args = parser.parse_args()
    for path in args.inputs:
        header, body = load(path)
        trimmed = trim(body, args.context)
        if len(args.inputs) > 1:
            print(f'===== {path}')
        print('\n'.join(header + [trimmed]))
        print(f'[{path}: {len(body):,} chars -> {len(trimmed):,}]', file=sys.stderr)


if __name__ == '__main__':
    main()
