#!/usr/bin/env python3
"""Cities and countries visited, from the order of flights. Synthetic data only."""
import unittest

from analyze import analyze
from places import places
from render_report import render
from test_trips import leg, ledger


def timed(ident, o, d, dep, arr):
    """A leg with offset-aware times (UTC for simplicity)."""
    row = leg(ident, dep[:10], o, d, minutes=None)
    row.update(departure_scheduled=dep + ':00+00:00', arrival_scheduled=arr + ':00+00:00')
    return row


class PlacesTests(unittest.TestCase):
    def test_short_connection_is_transit_long_stop_is_a_visit(self):
        legs = [timed('a', 'DXB', 'LHR', '2025-02-01T08:00', '2025-02-01T12:00'),
                timed('b', 'LHR', 'JFK', '2025-02-01T14:00', '2025-02-01T22:00'),
                timed('c', 'JFK', 'LHR', '2025-02-10T22:00', '2025-02-11T06:00'),
                timed('d', 'LHR', 'DXB', '2025-02-13T09:00', '2025-02-13T16:00')]
        s = analyze(ledger(legs))
        p = s['places']
        self.assertEqual([c['country'] for c in p['countries']], ['AE', 'US', 'GB'])
        self.assertEqual(p['transit_airports'], [])  # LHR became a visit on the way back
        self.assertEqual(s['metrics']['visited_country_count'], 3)
        self.assertEqual(s['metrics']['transit_only_country_count'], 0)

    def test_country_seen_only_on_connections_is_transit_only(self):
        legs = [timed('a', 'DXB', 'LHR', '2025-02-01T08:00', '2025-02-01T12:00'),
                timed('b', 'LHR', 'JFK', '2025-02-01T14:00', '2025-02-01T22:00'),
                timed('c', 'JFK', 'LHR', '2025-02-10T22:00', '2025-02-11T06:00'),
                timed('d', 'LHR', 'DXB', '2025-02-11T09:00', '2025-02-11T16:00')]
        p = analyze(ledger(legs))['places']
        self.assertEqual([c['country'] for c in p['countries']], ['AE', 'US'])
        self.assertEqual([c['name'] for c in p['transit_only_countries']], ['United Kingdom'])
        self.assertEqual({t['airport'] for t in p['transit_airports']}, {'LHR'})

    def test_day_trip_back_home_counts_and_a_gap_counts_both_ends(self):
        legs = [timed('a', 'MNL', 'SIN', '2025-03-01T02:00', '2025-03-01T08:00'),
                timed('b', 'SIN', 'MNL', '2025-03-01T18:00', '2025-03-01T22:00'),
                leg('c', '2025-04-01', 'MNL', 'CDG'), leg('d', '2025-04-08', 'ORY', 'BOS'), leg('e', '2025-04-12', 'BOS', 'MNL')]
        p = places(legs, ['MNL'])
        cities = {c['city'] for c in p['cities']}
        self.assertIn('Singapore', cities)  # flew straight back: a day trip, not a connection
        self.assertIn('Paris', cities)      # left from another airport: they were there
        self.assertEqual(sum(c['city'] == 'Paris' for c in p['cities']), 1)  # CDG and ORY are one city
        self.assertTrue(next(c for c in p['countries'] if c['country'] == 'PH')['home'])

    def test_unknown_times_on_the_same_day_count_as_a_connection(self):
        legs = [leg('a', '2025-05-01', 'DXB', 'LHR'), leg('b', '2025-05-01', 'LHR', 'JFK'), leg('c', '2025-05-20', 'JFK', 'DXB')]
        p = places(legs, ['DXB'])
        self.assertNotIn('GB', [c['country'] for c in p['countries']])

    def test_departure_dates_alone_do_not_prove_a_stay(self):
        # Departs 1 May, could land 3 May and connect on the same morning: unknown, so a connection.
        legs = [leg('a', '2025-05-01', 'JFK', 'SIN', minutes=None), leg('b', '2025-05-03', 'SIN', 'MNL', minutes=None),
                leg('c', '2025-05-20', 'MNL', 'JFK', minutes=None)]
        self.assertNotIn('SG', [c['country'] for c in places(legs, ['JFK'])['countries']])
        # With the landing date known, a full day on the ground is a stay.
        legs[0]['arrival_local'] = '2025-05-01T23:00'
        self.assertIn('SG', [c['country'] for c in places(legs, ['JFK'])['countries']])

    def test_date_line_crossing_is_bounded_by_the_full_offset_gap(self):
        # UTC-11 to UTC+13: a one-hour flight leaving 1 May 08:00 lands 2 May 09:00 local.
        def row(ident, day, o, d, oc, dc, minutes=None):
            return {'id': ident, 'departure_date': day, 'origin': o, 'destination': d, 'origin_country': oc,
                    'destination_country': dc, 'scheduled_minutes': minutes}
        legs = [row('a', '2025-05-01', 'PPG', 'APW', 'AS', 'WS', 60), row('b', '2025-05-03', 'APW', 'SYD', 'WS', 'AU'),
                row('c', '2025-05-20', 'SYD', 'PPG', 'AU', 'AS')]
        legs[0]['departure_local'] = '2025-05-01T08:00'
        self.assertNotIn('WS', [c['country'] for c in places(legs, ['PPG'])['countries']])

    def test_analyze_keeps_the_ledger_landing_date(self):
        legs = [leg('a', '2025-05-01', 'DXB', 'SIN', minutes=None), leg('b', '2025-05-03', 'SIN', 'MNL', minutes=None),
                leg('c', '2025-05-20', 'MNL', 'DXB', minutes=None)]
        legs[0]['arrival_local'] = '2025-05-01T23:00'
        self.assertIn('SG', [c['country'] for c in analyze(ledger(legs))['places']['countries']])

    def test_flights_just_outside_the_period_decide_the_end_airports(self):
        legs = [timed('a', 'DXB', 'LHR', '2025-12-31T16:00', '2025-12-31T20:00')]
        after = timed('z', 'LHR', 'JFK', '2026-01-01T01:00', '2026-01-01T09:00')
        self.assertNotIn('GB', [c['country'] for c in places(legs, ['DXB'], after=after)['countries']])
        self.assertIn('GB', [c['country'] for c in places(legs, ['DXB'])['countries']])
        start = [timed('b', 'LHR', 'JFK', '2025-01-01T01:00', '2025-01-01T09:00')]
        before = timed('y', 'DXB', 'LHR', '2024-12-31T16:00', '2024-12-31T20:00')
        p = places(start, ['DXB'], before=before)
        self.assertNotIn('GB', [c['country'] for c in p['countries']])
        self.assertEqual([t['airport'] for t in p['transit_airports']], ['LHR'])

    def test_analyze_passes_boundary_flights_without_counting_them(self):
        legs = [timed('a', 'DXB', 'LHR', '2025-12-31T16:00', '2025-12-31T20:00'),
                timed('z', 'LHR', 'JFK', '2026-01-01T01:00', '2026-01-01T09:00')]
        s = analyze(ledger(legs))
        self.assertEqual(s['metrics']['flight_count'], 1)
        self.assertNotIn('GB', [c['country'] for c in s['places']['countries']])

    def test_transit_country_path_has_one_fill(self):
        import re
        import json
        from render_report import places_svg, ASSETS
        theme = json.loads((ASSETS / 'themes.json').read_text())['atlas']
        svg = places_svg({'countries': [], 'cities': [], 'transit_only_countries': [{'country': 'GB'}]}, theme)
        for path in re.findall(r'<path [^>]*>', svg):
            self.assertLessEqual(path.count(' fill='), 1, path[-120:])

    def test_report_shows_map_and_lists(self):
        legs = [leg('a', '2025-02-01', 'DXB', 'SIN'), leg('b', '2025-02-09', 'SIN', 'DXB')]
        s = analyze(ledger(legs))
        html, cover = render(s)
        self.assertIn('Where you stayed', html)
        self.assertIn('Countries and cities visited', html)
        self.assertIn('Singapore', html)
        self.assertIn('COUNTRIES VISITED', cover)

    def test_stops_on_a_ground_journey_count_as_visited(self):
        legs = [leg('a', '2025-08-01', 'DXB', 'CDG'), leg('b', '2025-08-09', 'LHR', 'DXB')]
        data = ledger(legs)
        data['ground_segments'] = [{'id': 'g', 'after_id': 'a', 'before_id': 'b', 'from': 'CDG', 'to': 'LHR', 'status': 'documented',
                                    'mode': 'train', 'via': [{'city': 'Brussels', 'country': 'be', 'lat': 50.85, 'lon': 4.35}]}]
        s = analyze(data)
        self.assertIn(('Brussels', 'BE'), {(c['city'], c['country']) for c in s['places']['cities']})
        self.assertIn('Belgium', [c['name'] for c in s['places']['countries']])
        html, _ = render(s)
        self.assertIn('<title>Brussels</title>', html)


if __name__ == '__main__':
    unittest.main()
