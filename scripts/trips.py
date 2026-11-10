#!/usr/bin/env python3
"""Group included flight legs into trips and turn coverage holes into questions for the person.

Stdlib only. Used by analyze.py; `clarify.py` prints the questions as a chat message.

A trip starts when the traveller leaves a home airport and ends when they land at one. The
person can name several homes (report.home_airports); otherwise the busiest departure airport
is assumed and the first question asks them to confirm it. Nothing here adds a flight: a trip
whose outbound or return is missing is marked as such and becomes a question.
"""
import collections
import datetime as dt

try:
    from airports import lookup
except ImportError:  # trips.py used on its own, without the bundled airport table
    lookup = None

# A manual gap answers an open end when it points at that leg and says what happened:
# kind outbound_* / return_* (for example outbound_overland, return_after_period) or boundary_*.
ANSWERED_OUTBOUND = ('outbound_', 'boundary')
ANSWERED_RETURN = ('return_', 'boundary')


def homes_for(report, legs):
    """Home airports and whether they were inferred rather than given."""
    given = report.get('home_airports') or report.get('home_airport')
    if isinstance(given, str):
        given = [given]
    if isinstance(given, list):
        codes = [str(c).strip().upper() for c in given if isinstance(c, str) and len(c.strip()) == 3]
        if codes:
            return codes, False
    if not legs:
        return [], True
    departures = collections.Counter(l['origin'] for l in legs)
    endpoints = collections.Counter(c for l in legs for c in (l['origin'], l['destination']))
    first = legs[0]['origin']
    best = max(departures, key=lambda c: (departures[c], endpoints[c], c == first))
    return [best], True


def build_trips(legs, homes, ground=()):
    """Split chronologically ordered legs into trips. `ground` holds (after_id, before_id) pairs closed by ground travel."""
    homes = set(homes); closed = set(ground); trips = []; current = None

    def start(leg):
        return {'legs': [leg], 'outbound_missing': leg['origin'] not in homes, 'return_missing': False, 'breaks': []}

    for leg in legs:
        if current is None:
            current = start(leg)
        else:
            prev = current['legs'][-1]
            same = prev['destination'] == leg['origin']
            by_ground = not same and (prev['id'], leg['id']) in closed
            joined = same or by_ground
            if by_ground and leg['origin'] in homes:
                # A documented train, car or ferry brought them home: that trip is over.
                trips.append(current); current = start(leg)
            elif not joined and leg['origin'] in homes:
                # Left home again without a recorded way back from the last place.
                current['return_missing'] = True
                trips.append(current); current = start(leg)
            else:
                if not joined:
                    current['breaks'].append((prev, leg))
                current['legs'].append(leg)
        if leg['destination'] in homes:
            trips.append(current); current = None
    if current is not None:
        current['return_missing'] = True
        trips.append(current)
    return [_describe(i + 1, t, homes) for i, t in enumerate(trips)]


def _describe(number, trip, homes):
    legs = trip['legs']
    away = []
    for l in legs:
        for code in (l['origin'], l['destination']):
            if code not in homes and code not in away:
                away.append(code)
    chain = [legs[0]['origin']]
    for l in legs:
        if l['origin'] != chain[-1]:
            chain += ['…', l['origin']]
        chain.append(l['destination'])
    known = [l['scheduled_minutes'] for l in legs if l.get('scheduled_minutes') is not None]
    flags = (['outbound_missing'] if trip['outbound_missing'] else []) + (['return_missing'] if trip['return_missing'] else []) + (['gap'] if trip['breaks'] else [])
    return {'id': f'trip-{number}', 'start_date': legs[0]['departure_date'], 'end_date': legs[-1]['departure_date'],
            'destinations': away or [legs[-1]['destination']], 'route': chain, 'leg_ids': [l['id'] for l in legs],
            'flights': len(legs), 'minutes': sum(known), 'unknown_duration_count': len(legs) - len(known),
            'status': flags[0] if flags else 'between_homes' if _between_homes(legs, homes) else 'complete', 'flags': flags,
            'breaks': [{'after_id': a['id'], 'before_id': b['id'], 'from': a['destination'], 'to': b['origin']} for a, b in trip['breaks']]}


def _between_homes(legs, homes):
    """A flight or same-day-ish connection from one home to another: a move between bases, not a trip away.

    A trip that stays somewhere on the way (more than a day between flights) is a real trip that happened
    to end at the other home; it keeps the status complete.
    """
    if not (legs[0]['origin'] in homes and legs[-1]['destination'] in homes and legs[0]['origin'] != legs[-1]['destination']):
        return False
    days = [str(l['departure_date'])[:10] for l in legs]
    try:
        dates = [dt.date.fromisoformat(d) for d in days]
    except ValueError:
        return False
    return all((b - a).days <= 1 for a, b in zip(dates, dates[1:]))


def _answered(manual_gaps, leg_id, prefixes, side):
    """side is 'before_id' for an outbound (context before the first leg) or 'after_id' for a return."""
    return any(leg_id in (g.get('leg_id'), g.get(side)) and str(g.get('kind', '')).startswith(prefixes)
               and not (g.get('after_id') and g.get('before_id')) for g in manual_gaps)


def clarifications(trips, legs, homes, home_inferred, exclusions=(), manual_gaps=(), ground=()):
    """Questions that would complete the record, most important first. Each is data; clarify.py words them."""
    byid = {l['id']: l for l in legs}
    # A gap of kind "hint" answers nothing: it carries what the search found (an arrival card, a hotel,
    # a taxi from the airport) so the question can show it and be answered in a word.
    hints = [g for g in manual_gaps if g.get('kind') == 'hint' and g.get('note')]
    manual_gaps = [g for g in manual_gaps if g.get('kind') != 'hint']
    home_list, homes = list(homes), set(homes)  # the list goes into questions (JSON); the set is for lookups
    closed = {tuple(pair) for pair in ground}
    # A return that is booked but not yet flown (planned, or after the evidence cutoff) is a note, not a question.
    # Superseded or duplicate bookings never count: their exclusion reason is not the planned/future one.
    future = [x for x in exclusions if str(x.get('reason', '')) == 'status: planned' or str(x.get('reason', '')).startswith('future')]
    # The traveler's own flights just outside the report dates show that a trip began before it or runs past it.
    outside = [x for x in exclusions if str(x.get('reason', '')) == 'outside departure-date window']
    questions = []
    if home_inferred and homes and trips:
        questions.append({'kind': 'confirm_home', 'airports': home_list})
    for index, trip in enumerate(trips):
        first, last = byid[trip['leg_ids'][0]], byid[trip['leg_ids'][-1]]
        # A booking can only be this trip's return if no later trip had already started from home.
        next_start = trips[index + 1]['start_date'] if index + 1 < len(trips) else None
        if index and _home_change(trips[index - 1], trip, byid, homes, closed):
            prev = byid[trips[index - 1]['leg_ids'][-1]]
            trip['home_change'] = {'from': prev['destination'], 'to': first['origin']}
            if not any(g.get('after_id') == prev['id'] and g.get('before_id') == first['id'] for g in manual_gaps):
                # Landed at one home and next left from another: the flight between them is missing.
                questions.append({'kind': 'missing_transfer', 'trip_id': trip['id'], 'home_change': True,
                                  'after': _brief(prev), 'before': _brief(first)})
        earlier = index == 0 and _boundary(outside, first, homes, before=True)
        if 'outbound_missing' in trip['flags'] and earlier:
            trip['flags'] = [f if f != 'outbound_missing' else 'outbound_before_period' for f in trip['flags']]
            _restatus(trip)
        if 'outbound_missing' in trip['flags']:
            if _answered(manual_gaps, first['id'], ANSWERED_OUTBOUND, 'before_id'):
                _explain(trip, 'outbound_missing')
            else:
                questions.append({'kind': 'missing_outbound', 'trip_id': trip['id'], 'leg': _brief(first), 'place': first['origin']})
        if 'return_missing' in trip['flags']:
            later = next((x for x in future if x.get('origin') == last['destination'] and str(x.get('departure_date') or '') >= last['departure_date']
                          and (next_start is None or str(x.get('departure_date') or '') <= next_start)), None)
            beyond = next_start is None and _boundary(outside, last, homes, before=False)
            if later:
                trip['return_booked'] = {'date': later.get('departure_date'), 'origin': later.get('origin'), 'destination': later.get('destination')}
                trip['flags'] = [f if f != 'return_missing' else 'return_after_snapshot' for f in trip['flags']]
                _restatus(trip)
            elif beyond:
                # Their next recorded flight is after the report ends: the trip simply runs past the period.
                trip['continues'] = {'date': beyond.get('departure_date'), 'origin': beyond.get('origin'), 'destination': beyond.get('destination')}
                trip['flags'] = [f if f != 'return_missing' else 'return_after_period' for f in trip['flags']]
                _restatus(trip)
            elif _answered(manual_gaps, last['id'], ANSWERED_RETURN, 'after_id'):
                _explain(trip, 'return_missing')
            else:
                questions.append({'kind': 'missing_return', 'trip_id': trip['id'], 'leg': _brief(last), 'place': last['destination']})
        unanswered = 0
        for br in trip['breaks']:
            if any(g.get('after_id') == br['after_id'] and g.get('before_id') == br['before_id'] for g in manual_gaps):
                continue
            unanswered += 1
            questions.append({'kind': 'missing_transfer', 'trip_id': trip['id'], 'after': _brief(byid[br['after_id']]), 'before': _brief(byid[br['before_id']])})
        if trip['breaks'] and not unanswered:
            _explain(trip, 'gap')
    unknown = [_brief(l) for l in legs if l.get('scheduled_minutes') is None]
    if unknown:
        questions.append({'kind': 'unknown_duration', 'legs': unknown})
    for q in questions:
        ids = {q.get('after', {}).get('id'), q.get('before', {}).get('id'), q.get('leg', {}).get('id')} - {None}
        found = [g['note'] for g in hints if ids & {g.get('after_id'), g.get('before_id'), g.get('leg_id')}
                 and (not (g.get('after_id') and g.get('before_id')) or {g['after_id'], g['before_id']} <= ids)]
        if found:
            q['hint'] = ' '.join(found)
    # Ask first about what most likely hides a whole flight: a hop between homes, an open outbound or return,
    # then a change of city mid-trip; a change of airport within one city (usually a taxi) and missing
    # times come last. The sort is stable, so each group stays in date order.
    return sorted(questions, key=_priority)


def _priority(question):
    kind = question['kind']
    if kind == 'confirm_home':
        return 0
    if question.get('home_change') or kind in ('missing_outbound', 'missing_return'):
        return 1
    if kind == 'missing_transfer':
        a, b = question['after']['destination'], question['before']['origin']
        return 3 if _same_city(a, b) else 2
    return 4


def _same_city(a, b):
    if lookup is None:
        return False
    ca, cb = (lookup(a) or {}).get('city'), (lookup(b) or {}).get('city')
    return bool(ca) and ca == cb


BOUNDARY_DAYS = 60


def _boundary(outside, leg, homes, before):
    """The traveler's own flight just outside the report that shows this trip runs on past it, or None.

    Only the nearest such flight counts, within BOUNDARY_DAYS, and only if it keeps them away from home:
    after the report it must leave from somewhere that is not home (leaving home would be a new trip,
    so the way back is still unknown); before the report it must land somewhere that is not home.
    """
    try:
        anchor = dt.date.fromisoformat(str(leg['departure_date'])[:10])
    except ValueError:
        return None
    near = []
    for x in outside:
        try:
            day = dt.date.fromisoformat(str(x.get('departure_date') or '')[:10])
        except ValueError:
            continue
        gap = (anchor - day).days if before else (day - anchor).days
        if 0 < gap <= BOUNDARY_DAYS or (gap == 0 and before):
            near.append((gap, x))
    if not near:
        return None
    x = min(near, key=lambda pair: pair[0])[1]
    end = x.get('destination') if before else x.get('origin')
    return None if end in homes else x


def _home_change(prev_trip, trip, byid, homes, closed):
    """True when the previous trip ended at one home and this one leaves from a different home."""
    last, first = byid[prev_trip['leg_ids'][-1]], byid[trip['leg_ids'][0]]
    return (last['destination'] in homes and first['origin'] in homes and last['destination'] != first['origin']
            and (last['id'], first['id']) not in closed)


NOTES = ('return_after_snapshot', 'return_after_period', 'outbound_before_period')


def _explain(trip, flag):
    """The person (or a reviewed note) already explained this open end: keep it visible, stop asking."""
    trip['flags'] = [f if f != flag else flag + '_explained' for f in trip['flags']]
    _restatus(trip)


def _restatus(trip):
    """Status shows the most pressing thing: an open end, then a booked return, then an explained one."""
    flags = trip['flags']
    open_flags = [f for f in flags if not f.endswith('_explained') and f not in NOTES]
    notes = [f for f in flags if f in NOTES]
    trip['status'] = open_flags[0] if open_flags else notes[0] if notes else 'explained' if flags else trip['status']


def _brief(leg):
    return {'id': leg['id'], 'date': leg['departure_date'], 'origin': leg['origin'], 'destination': leg['destination']}
