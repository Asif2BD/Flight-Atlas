#!/usr/bin/env python3
"""Trips, clarifying questions and the full report. Synthetic data only."""
import copy
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from analyze import analyze
from clarify import message, word
from render_report import render

AIR = {'DXB': (25.25, 55.36, 'AE'), 'LHR': (51.47, -0.45, 'GB'), 'JFK': (40.64, -73.78, 'US'), 'BOS': (42.36, -71.01, 'US'),
       'SIN': (1.36, 103.99, 'SG'), 'MNL': (14.51, 121.02, 'PH'), 'CDG': (49.01, 2.55, 'FR'), 'ORY': (48.72, 2.38, 'FR')}


def leg(ident, day, o, d, minutes=300, status='flown'):
    row = {'id': ident, 'traveler_id': 't', 'departure_date': day, 'origin': o, 'destination': d, 'status': status,
           'evidence_ids': ['synthetic-' + ident], 'airline': 'Example Air'}
    if minutes:
        row.update(scheduled_minutes=minutes, duration_basis='ticket_advertised')
    for side, code in (('origin', o), ('destination', d)):
        lat, lon, country = AIR[code]
        row.update({side + '_lat': lat, side + '_lon': lon, side + '_country': country})
    return row


def ledger(legs, **report):
    base = {'title': 'Synthetic trips', 'start_date': '2025-01-01', 'end_date': '2025-12-31', 'as_of': '2025-12-31', 'home_airports': ['DXB']}
    base.update(report)
    return {'schema_version': 1, 'report': {k: v for k, v in base.items() if v is not None}, 'legs': legs}


ROUND = [leg('a', '2025-02-01', 'DXB', 'LHR'), leg('b', '2025-02-09', 'LHR', 'DXB')]


class TripTests(unittest.TestCase):
    def test_round_trip_complete(self):
        s = analyze(ledger(copy.deepcopy(ROUND)))
        self.assertEqual(len(s['trips']), 1)
        trip = s['trips'][0]
        self.assertEqual((trip['status'], trip['route'], trip['flights'], trip['minutes']), ('complete', ['DXB', 'LHR', 'DXB'], 2, 600))
        self.assertEqual(s['clarifications'], [])
        self.assertFalse(s['home_inferred'])

    def test_missing_outbound_and_return_become_questions(self):
        legs = [leg('in', '2025-03-05', 'JFK', 'DXB'), leg('out', '2025-06-01', 'DXB', 'SIN')]
        s = analyze(ledger(legs))
        self.assertEqual([t['status'] for t in s['trips']], ['outbound_missing', 'return_missing'])
        kinds = [q['kind'] for q in s['clarifications']]
        self.assertEqual(kinds, ['missing_outbound', 'missing_return'])
        # No flight is ever invented to close a trip.
        self.assertEqual(s['metrics']['flight_count'], 2)
        self.assertEqual(sum(t['flights'] for t in s['trips']), 2)

    def test_return_booked_later_is_a_note(self):
        legs = [leg('out', '2025-12-20', 'DXB', 'LHR'), leg('back', '2026-01-04', 'LHR', 'DXB', status='planned')]
        s = analyze(ledger(legs))
        self.assertEqual(s['trips'][0]['status'], 'return_after_snapshot')
        self.assertEqual(s['trips'][0]['return_booked']['date'], '2026-01-04')
        self.assertEqual(s['clarifications'], [])
        doc, _ = render(s)
        self.assertIn('Return booked 4 Jan', doc)

    def test_transfer_gap_question_and_ground_closure(self):
        legs = [leg('a', '2025-04-01', 'DXB', 'CDG'), leg('b', '2025-04-08', 'ORY', 'DXB')]
        s = analyze(ledger(copy.deepcopy(legs)))
        self.assertEqual(s['trips'][0]['status'], 'gap')
        self.assertEqual([q['kind'] for q in s['clarifications']], ['missing_transfer'])
        text, _ = word(s['clarifications'][0])
        self.assertIn('Paris', text)
        data = ledger(copy.deepcopy(legs)); data['ground_segments'] = [{'after_id': 'a', 'before_id': 'b', 'from': 'CDG', 'to': 'ORY', 'status': 'user_confirmed', 'mode': 'taxi'}]
        s = analyze(data)
        self.assertEqual((s['trips'][0]['status'], s['clarifications']), ('complete', []))

    def test_gap_stays_open_until_every_transfer_is_answered(self):
        legs = [leg('a', '2025-04-01', 'DXB', 'LHR'), leg('b', '2025-04-05', 'CDG', 'BOS'), leg('c', '2025-04-09', 'JFK', 'DXB')]
        data = ledger(legs)
        data['manual_gaps'] = [{'kind': 'unresolved_transfer', 'after_id': 'a', 'before_id': 'b', 'note': 'Eurostar.'}]
        s = analyze(data)
        self.assertEqual(s['trips'][0]['status'], 'gap')
        self.assertEqual(s['metrics']['open_trip_count'], 1)
        self.assertEqual([q['kind'] for q in s['clarifications']], ['missing_transfer'])
        data['manual_gaps'].append({'kind': 'unresolved_transfer', 'after_id': 'b', 'before_id': 'c', 'note': 'Drove.'})
        s = analyze(data)
        self.assertEqual((s['trips'][0]['status'], s['metrics']['open_trip_count']), ('explained', 0))

    def test_superseded_return_is_not_a_booked_return(self):
        old = leg('old', '2026-01-04', 'LHR', 'DXB', status='planned')
        new = leg('new', '2026-01-04', 'CDG', 'DXB', status='planned'); new['supersedes_id'] = 'old'
        s = analyze(ledger([leg('out', '2025-12-20', 'DXB', 'LHR'), old, new]))
        self.assertEqual(s['trips'][0]['status'], 'return_missing')
        self.assertEqual([q['kind'] for q in s['clarifications']], ['missing_return'])

    def test_ground_transfer_home_ends_the_trip(self):
        legs = [leg('a', '2025-02-01', 'LHR', 'CDG'), leg('b', '2025-06-01', 'LHR', 'JFK'), leg('c', '2025-06-09', 'JFK', 'LHR')]
        data = ledger(legs, home_airports=['LHR'])
        data['ground_segments'] = [{'after_id': 'a', 'before_id': 'b', 'from': 'CDG', 'to': 'LHR', 'status': 'user_confirmed', 'mode': 'train'}]
        s = analyze(data)
        self.assertEqual([t['route'] for t in s['trips']], [['LHR', 'CDG'], ['LHR', 'JFK', 'LHR']])
        self.assertEqual(s['metrics']['flight_count'], 3)

    def test_booked_return_belongs_to_the_last_trip_only(self):
        legs = [leg('feb', '2025-02-01', 'DXB', 'LHR'), leg('jun', '2025-06-01', 'DXB', 'LHR'), leg('back', '2026-01-10', 'LHR', 'DXB', status='planned')]
        s = analyze(ledger(legs))
        self.assertEqual([t['status'] for t in s['trips']], ['return_missing', 'return_after_snapshot'])
        self.assertEqual([q['kind'] for q in s['clarifications']], ['missing_return'])

    def test_someone_elses_booking_is_not_your_return(self):
        other = leg('theirs', '2026-01-04', 'LHR', 'DXB', status='planned'); other['traveler_id'] = 'someone-else'
        s = analyze(ledger([leg('out', '2025-12-20', 'DXB', 'LHR'), other]))
        self.assertEqual(s['trips'][0]['status'], 'return_missing')
        self.assertEqual([q['kind'] for q in s['clarifications']], ['missing_return'])

    def test_answers_stop_the_questions(self):
        legs = [leg('in', '2025-03-05', 'JFK', 'DXB'), leg('out', '2025-06-01', 'DXB', 'SIN')]
        data = ledger(legs)
        data['manual_gaps'] = [{'kind': 'outbound_before_period', 'leg_id': 'in', 'note': 'Flew to New York in 2024.'},
                               {'kind': 'return_not_known', 'leg_id': 'out', 'note': 'Person is not sure how they came back.'}]
        s = analyze(data)
        self.assertEqual(s['clarifications'], [])
        self.assertEqual([t['status'] for t in s['trips']], ['explained', 'explained'])
        self.assertIn('outbound_before_period', [g['kind'] for g in s['gaps']])

    def test_two_homes_and_inferred_home(self):
        legs = [leg('a', '2025-01-10', 'MNL', 'DXB'), leg('b', '2025-02-10', 'DXB', 'MNL')]
        s = analyze(ledger(copy.deepcopy(legs), home_airports=['DXB', 'MNL']))
        self.assertEqual([t['status'] for t in s['trips']], ['between_homes', 'between_homes'])
        s = analyze(ledger(copy.deepcopy(legs), home_airports=None))
        self.assertTrue(s['home_inferred'])
        self.assertEqual(s['clarifications'][0]['kind'], 'confirm_home')
        import json
        json.dumps(s)  # the summary must stay JSON-serializable when the home is inferred

    def test_unknown_durations_grouped(self):
        legs = [leg('a', '2025-02-01', 'DXB', 'LHR', minutes=None), leg('b', '2025-02-09', 'LHR', 'DXB', minutes=None)]
        s = analyze(ledger(legs))
        self.assertEqual([q['kind'] for q in s['clarifications']], ['unknown_duration'])
        self.assertIn('2 flights have no scheduled time', message(s))


class MessageTests(unittest.TestCase):
    def test_message_wording(self):
        legs = [leg('in', '2025-03-05', 'JFK', 'DXB'), leg('a', '2025-04-01', 'DXB', 'CDG'), leg('b', '2025-04-08', 'ORY', 'DXB'), leg('out', '2025-06-01', 'DXB', 'SIN')]
        text = message(analyze(ledger(legs)))
        self.assertIn("I won't add any flight you haven't confirmed or sent a document for.", text)
        self.assertIn('How did you get to New York?', text)
        self.assertIn('How did you leave Singapore?', text)
        self.assertIn('boarding pass or a screenshot', text)
        self.assertIn('**another way**', text)
        self.assertTrue(text.splitlines()[2].startswith('1. '))

    def test_message_limit_and_empty(self):
        legs = []
        for i in range(8):
            legs.append(leg(f'x{i}', f'2025-{i + 1:02d}-02', 'DXB', 'LHR'))
        s = analyze(ledger(legs))
        self.assertEqual(len(s['clarifications']), 8)
        text = message(s)
        self.assertIn('There are 3 more open items', text)
        self.assertEqual(text.count('\n1. '), 1)
        self.assertEqual(message(analyze(ledger(copy.deepcopy(ROUND)))), '')


class FullReportTests(unittest.TestCase):
    def test_trips_section_and_cover_page(self):
        legs = [leg('in', '2025-03-05', 'JFK', 'DXB')] + copy.deepcopy(ROUND)
        s = analyze(ledger(legs))
        doc, cover = render(s, 'midnight', 'globe', cover_page=True)
        ET.fromstring(cover)
        self.assertIn('05 / Trips', doc)
        self.assertIn('06 / Flight ledger', doc)
        self.assertIn('Outbound not found', doc)
        self.assertIn('Round trip', doc)
        self.assertLess(doc.index('class="cover-page"'), doc.index('<header>'))
        self.assertIn('Made with Flight Atlas by M Asif Rahman', doc[doc.index('class="cover-page"'):doc.index('<header>')])
        plain, _ = render(s)
        self.assertNotIn('class="cover-page"', plain)

    def test_export_pdf(self):
        import export_pdf
        s = analyze(ledger(copy.deepcopy(ROUND)))
        with tempfile.TemporaryDirectory() as tmp:
            engine, html = export_pdf.export(s, Path(tmp) / 'r.pdf', engine='wkhtmltopdf' if not export_pdf.shutil.which('wkhtmltopdf') else 'auto', keep_html=Path(tmp) / 'r.html')
            self.assertTrue(html.exists())
            self.assertIn('class="cover-page"', html.read_text(encoding='utf-8'))
            try:
                import weasyprint  # noqa: F401
            except ImportError:
                return
            engine, _ = export_pdf.export(s, Path(tmp) / 'w.pdf', engine='weasyprint')
            self.assertEqual(engine, 'weasyprint')
            self.assertTrue((Path(tmp) / 'w.pdf').read_bytes().startswith(b'%PDF'))
            self.assertGreaterEqual(export_pdf.page_count(Path(tmp) / 'w.pdf') or 2, 2)


class MultiHomeAndBoundaryTests(unittest.TestCase):
    def test_landing_at_one_home_and_leaving_from_another_is_asked(self):
        legs = [leg('a', '2025-02-01', 'DXB', 'MNL'), leg('b', '2025-03-01', 'DXB', 'LHR'), leg('c', '2025-03-08', 'LHR', 'DXB')]
        s = analyze(ledger(legs, home_airports=['DXB', 'MNL']))
        q = [x for x in s['clarifications'] if x.get('home_change')]
        self.assertEqual(len(q), 1)
        self.assertEqual((q[0]['after']['id'], q[0]['before']['id']), ('a', 'b'))
        self.assertEqual(s['trips'][1]['home_change'], {'from': 'MNL', 'to': 'DXB'})
        text, _ = word(q[0])
        self.assertIn('after your flight into Manila on 1 Feb (DXB → MNL), your next flight left from Dubai on 1 Mar', text)

    def test_home_change_answered_or_closed_by_ground_is_not_asked(self):
        legs = [leg('a', '2025-02-01', 'DXB', 'MNL'), leg('b', '2025-03-01', 'DXB', 'LHR'), leg('c', '2025-03-08', 'LHR', 'DXB')]
        answered = ledger(copy.deepcopy(legs), home_airports=['DXB', 'MNL'])
        answered['manual_gaps'] = [{'kind': 'unverified_ground', 'after_id': 'a', 'before_id': 'b', 'note': 'not sure'}]
        self.assertFalse([x for x in analyze(answered)['clarifications'] if x.get('home_change')])
        driven = ledger(copy.deepcopy(legs), home_airports=['DXB', 'MNL'])
        driven['ground_segments'] = [{'id': 'g', 'after_id': 'a', 'before_id': 'b', 'from': 'MNL', 'to': 'DXB', 'status': 'user_confirmed', 'mode': 'ship'}]
        self.assertFalse([x for x in analyze(driven)['clarifications'] if x.get('home_change')])

    def test_one_home_never_triggers_a_home_change(self):
        legs = [leg('a', '2025-02-01', 'DXB', 'LHR'), leg('b', '2025-02-05', 'LHR', 'DXB'), leg('c', '2025-03-01', 'DXB', 'SIN'), leg('d', '2025-03-05', 'SIN', 'DXB')]
        self.assertEqual(analyze(ledger(legs))['clarifications'], [])

    def test_trip_running_past_the_report_end_is_a_note(self):
        legs = [leg('out', '2025-12-28', 'DXB', 'JFK'), leg('next', '2026-01-10', 'BOS', 'DXB')]
        s = analyze(ledger(legs, as_of='2026-02-01'))
        self.assertEqual(s['trips'][-1]['status'], 'return_after_period')
        self.assertEqual(s['trips'][-1]['continues']['date'], '2026-01-10')
        self.assertEqual(s['clarifications'], [])

    def test_trip_begun_before_the_report_is_a_note(self):
        legs = [leg('prev', '2024-12-20', 'DXB', 'JFK'), leg('back', '2025-01-03', 'BOS', 'DXB')]
        s = analyze(ledger(legs))
        self.assertEqual(s['trips'][0]['status'], 'outbound_before_period')
        self.assertEqual(s['clarifications'], [])

    def test_open_return_without_later_flights_is_still_asked(self):
        legs = [leg('out', '2025-12-28', 'DXB', 'JFK')]
        self.assertEqual([q['kind'] for q in analyze(ledger(legs))['clarifications']], ['missing_return'])


class OverlapTests(unittest.TestCase):
    def test_overlapping_schedules_are_flagged(self):
        a = leg('a', '2025-02-22', 'DXB', 'LHR', minutes=None)
        a.update(departure_scheduled='2025-02-22T10:00:00+04:00', arrival_scheduled='2025-02-22T14:00:00+00:00')
        b = leg('b', '2025-02-22', 'DXB', 'SIN', minutes=None)
        b.update(departure_scheduled='2025-02-22T12:00:00+04:00', arrival_scheduled='2025-02-22T23:00:00+08:00')
        s = analyze(ledger([a, b], home_airports=['DXB']))
        self.assertTrue(any('both cannot have been flown' in w for w in s['warnings']))

    def test_back_to_back_connection_is_fine(self):
        a = leg('a', '2025-02-22', 'DXB', 'LHR', minutes=None)
        a.update(departure_scheduled='2025-02-22T08:00:00+04:00', arrival_scheduled='2025-02-22T12:00:00+00:00')
        b = leg('b', '2025-02-22', 'LHR', 'JFK', minutes=None)
        b.update(departure_scheduled='2025-02-22T13:30:00+00:00', arrival_scheduled='2025-02-22T16:30:00-05:00')
        s = analyze(ledger([a, b], home_airports=['DXB']))
        self.assertFalse(any('both cannot' in w for w in s['warnings']))


class BetweenHomesTests(unittest.TestCase):
    def test_flight_between_two_homes_is_not_a_round_trip(self):
        legs = [leg('a', '2025-02-01', 'DXB', 'MNL'), leg('b', '2025-03-01', 'MNL', 'SIN'), leg('c', '2025-03-05', 'SIN', 'MNL')]
        s = analyze(ledger(legs, home_airports=['DXB', 'MNL']))
        self.assertEqual([t['status'] for t in s['trips']], ['between_homes', 'complete'])
        self.assertEqual(s['clarifications'], [])
        html, _ = render(s)
        self.assertIn('1 trips away from home (DXB, MNL) and 1 flight between homes. 0 are not closed', html)
        self.assertIn('Between homes', html)
        self.assertIn('Dubai → Manila', html)

    def test_trip_with_a_stay_that_ends_at_the_other_home_is_a_trip(self):
        legs = [leg('a', '2025-07-25', 'MNL', 'SIN'), leg('b', '2025-07-30', 'SIN', 'DXB')]
        s = analyze(ledger(legs, home_airports=['DXB', 'MNL']))
        self.assertEqual(s['trips'][0]['status'], 'complete')
        html, _ = render(s)
        self.assertIn('Ended at Dubai', html)

    def test_connection_between_homes_is_a_move(self):
        legs = [leg('a', '2025-10-09', 'MNL', 'SIN'), leg('b', '2025-10-09', 'SIN', 'DXB')]
        self.assertEqual(analyze(ledger(legs, home_airports=['DXB', 'MNL']))['trips'][0]['status'], 'between_homes')

    def test_questions_most_likely_to_hide_a_flight_come_first(self):
        legs = [leg('a', '2025-02-01', 'DXB', 'CDG'), leg('b', '2025-02-05', 'ORY', 'LHR'), leg('c', '2025-02-07', 'JFK', 'DXB', minutes=None),
                leg('d', '2025-03-01', 'DXB', 'MNL'), leg('e', '2025-04-01', 'DXB', 'SIN'), leg('f', '2025-04-05', 'SIN', 'DXB')]
        s = analyze(ledger(legs, home_airports=['DXB', 'MNL']))
        order = [(q['kind'], q.get('home_change', False), q.get('after', {}).get('destination')) for q in s['clarifications']]
        self.assertEqual(order, [('missing_transfer', True, 'MNL'), ('missing_transfer', False, 'LHR'),
                                 ('missing_transfer', False, 'CDG'), ('unknown_duration', False, None)])

    def test_unrelated_later_trip_from_home_does_not_close_an_open_return(self):
        legs = [leg('out', '2025-03-01', 'DXB', 'JFK'), leg('next', '2026-06-01', 'DXB', 'SIN')]
        s = analyze(ledger(legs, as_of='2026-07-01'))
        self.assertEqual(s['trips'][-1]['status'], 'return_missing')
        self.assertEqual([q['kind'] for q in s['clarifications']], ['missing_return'])

    def test_later_flight_from_home_soon_after_still_asks(self):
        legs = [leg('out', '2025-12-28', 'DXB', 'JFK'), leg('next', '2026-01-10', 'DXB', 'SIN')]
        s = analyze(ledger(legs, as_of='2026-02-01'))
        self.assertEqual([q['kind'] for q in s['clarifications']], ['missing_return'])

    def test_earlier_flight_that_landed_at_home_does_not_explain_an_outbound(self):
        legs = [leg('prev', '2024-12-20', 'JFK', 'DXB'), leg('back', '2025-01-03', 'BOS', 'DXB')]
        s = analyze(ledger(legs))
        self.assertEqual([q['kind'] for q in s['clarifications']], ['missing_outbound'])

    def test_hint_shows_in_the_question_but_does_not_answer_it(self):
        legs = [leg('a', '2025-02-01', 'DXB', 'CDG'), leg('b', '2025-02-05', 'LHR', 'DXB')]
        data = ledger(legs)
        data['manual_gaps'] = [{'kind': 'hint', 'after_id': 'a', 'before_id': 'b', 'note': 'a train booking on 3 Feb.'}]
        s = analyze(data)
        q = [x for x in s['clarifications'] if x['kind'] == 'missing_transfer']
        self.assertEqual(q[0]['hint'], 'a train booking on 3 Feb.')
        self.assertIn('I found: a train booking on 3 Feb.', message(s))


if __name__ == '__main__':
    unittest.main()
