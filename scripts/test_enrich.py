#!/usr/bin/env python3
"""Synthetic tests for the bundled airport table and ledger enrichment."""
import unittest
from airports import lookup, normalize, table
from enrich import enrich
from analyze import analyze


def ledger(**leg):
    base = {'id': 'x', 'traveler_id': 't', 'origin': 'DXB', 'destination': 'MAD', 'status': 'flown', 'evidence_ids': ['synthetic']}
    base.update(leg)
    return {'schema_version': 1, 'report': {'title': 'T', 'start_date': '2026-01-01', 'end_date': '2026-12-31', 'as_of': '2026-12-31'}, 'legs': [base]}


class AirportTableTests(unittest.TestCase):
    def test_table_shape(self):
        rows = table()
        self.assertGreater(len(rows), 7000)
        for code in ('DXB', 'MNL', 'LHR', 'JFK', 'NRT', 'AKL'):
            self.assertIn(code, rows)
        self.assertTrue(all(len(code) == 3 and code.isupper() for code in rows))

    def test_lookup_values(self):
        dxb = lookup(' dxb ')
        self.assertEqual((dxb['country'], dxb['tz']), ('AE', 'Asia/Dubai'))
        self.assertAlmostEqual(dxb['lat'], 25.25, places=1)
        self.assertAlmostEqual(dxb['lon'], 55.36, places=1)
        self.assertIsNone(lookup('ZZZ1'))
        self.assertIsNone(normalize('Dubai'))


class EnrichTests(unittest.TestCase):
    def test_fills_coordinates_country_and_tz(self):
        out, warnings, counts = enrich(ledger())
        leg = out['legs'][0]
        self.assertEqual(warnings, [])
        self.assertEqual((leg['origin_country'], leg['destination_country']), ('AE', 'ES'))
        self.assertEqual((leg['origin_tz'], leg['destination_tz']), ('Asia/Dubai', 'Europe/Madrid'))
        self.assertAlmostEqual(leg['destination_lat'], 40.47, places=1)
        self.assertEqual(counts['coordinates_filled'], 2)

    def test_input_not_mutated(self):
        data = ledger()
        enrich(data)
        self.assertNotIn('origin_lat', data['legs'][0])

    def test_dst_after_eu_change(self):
        # Europe left summer time on 25 Oct 2026: Madrid is +01:00 on 29 Oct.
        out, warnings, _ = enrich(ledger(departure_local='2026-10-29T10:05', arrival_local='2026-10-29T14:40', scheduled_minutes=455, duration_basis='ticket_advertised'))
        leg = out['legs'][0]
        self.assertEqual(warnings, [])
        self.assertEqual(leg['departure_scheduled'], '2026-10-29T10:05:00+04:00')
        self.assertEqual(leg['arrival_scheduled'], '2026-10-29T14:40:00+01:00')
        self.assertEqual(leg['departure_date'], '2026-10-29')
        s = analyze(out)
        self.assertEqual(s['metrics']['scheduled_minutes'], 455)
        self.assertEqual(s['warnings'], [])

    def test_dst_before_eu_change(self):
        out, _, _ = enrich(ledger(departure_local='2026-10-14T10:05', arrival_local='2026-10-14T14:40'))
        self.assertEqual(out['legs'][0]['arrival_scheduled'], '2026-10-14T14:40:00+02:00')

    def test_us_change_and_overnight(self):
        out, warnings, _ = enrich(ledger(origin='bos', destination='dxb', departure_local='2026-11-18T21:40', arrival_local='2026-11-19T18:35'))
        leg = out['legs'][0]
        self.assertEqual(warnings, [])
        self.assertEqual((leg['origin'], leg['destination']), ('BOS', 'DXB'))
        self.assertEqual(leg['departure_scheduled'], '2026-11-18T21:40:00-05:00')
        s = analyze(out)
        self.assertEqual(s['metrics']['scheduled_minutes'], 715)

    def test_wrong_offset_is_flagged(self):
        _, warnings, _ = enrich(ledger(departure_scheduled='2026-10-29T10:05:00+04:00', arrival_scheduled='2026-10-29T14:40:00+02:00'))
        self.assertEqual(len(warnings), 1)
        self.assertIn('check DST', warnings[0])

    def test_local_vs_existing_conflict_kept(self):
        out, warnings, _ = enrich(ledger(arrival_local='2026-10-29T14:40', arrival_scheduled='2026-10-29T14:40:00+02:00'))
        self.assertEqual(out['legs'][0]['arrival_scheduled'], '2026-10-29T14:40:00+02:00')
        self.assertIn('disagrees', warnings[0])
        out, _, _ = enrich(ledger(arrival_local='2026-10-29T14:40', arrival_scheduled='2026-10-29T14:40:00+02:00'), overwrite=True)
        self.assertEqual(out['legs'][0]['arrival_scheduled'], '2026-10-29T14:40:00+01:00')

    def test_dst_gap_and_ambiguous_refused(self):
        _, warnings, _ = enrich(ledger(origin='JFK', destination='BOS', departure_local='2026-03-08T02:30'))
        self.assertIn('DST gap', warnings[0])
        out, warnings, _ = enrich(ledger(origin='JFK', destination='BOS', departure_local='2026-11-01T01:30'))
        self.assertIn('ambiguous', warnings[0])
        self.assertNotIn('departure_scheduled', out['legs'][0])

    def test_unknown_code_and_bad_coordinates(self):
        _, warnings, _ = enrich(ledger(destination='QQQ'))
        self.assertIn('not in bundled airport table', warnings[0])
        _, warnings, _ = enrich(ledger(origin_lat=10.0, origin_lon=10.0))
        self.assertIn('differ from reference', warnings[0])
        _, warnings, _ = enrich(ledger(origin='Dubai'))
        self.assertIn('not a three-letter IATA code', warnings[0])

    def test_same_instant_other_zone_normalized(self):
        out, warnings, _ = enrich(ledger(departure_local='2026-10-29T01:15', departure_scheduled='2026-10-28T21:15:00+00:00', arrival_local='2026-10-29T05:50'))
        leg = out['legs'][0]
        self.assertEqual(warnings, [])
        self.assertEqual(leg['departure_scheduled'], '2026-10-29T01:15:00+04:00')
        self.assertEqual(analyze(out)['metrics']['known_duration_count'], 1)

    def test_existing_timestamp_in_dst_gap_flagged(self):
        _, warnings, _ = enrich(ledger(origin='JFK', destination='BOS', departure_scheduled='2026-03-08T02:30:00-05:00', arrival_scheduled='2026-03-08T04:30:00-04:00'))
        self.assertEqual(len(warnings), 1)
        self.assertIn('DST gap', warnings[0])
        _, warnings, _ = enrich(ledger(origin='JFK', destination='BOS', departure_scheduled='2026-11-01T01:30:00-04:00'))
        self.assertEqual(warnings, [])

    def test_date_only_local_time_rejected(self):
        out, warnings, _ = enrich(ledger(departure_local='2026-10-29', arrival_local='2026-10-29'))
        self.assertEqual(len(warnings), 2)
        self.assertIn('no clock time', warnings[0])
        self.assertNotIn('departure_scheduled', out['legs'][0])
        self.assertEqual(analyze(out)['metrics']['known_duration_count'], 0)

    def test_date_kept_when_offset_unresolved(self):
        out, warnings, _ = enrich(ledger(origin='JFK', destination='BOS', departure_local='2026-11-01T01:30'))
        self.assertIn('ambiguous', warnings[0])
        self.assertEqual(out['legs'][0]['departure_date'], '2026-11-01')
        s = analyze(out)
        self.assertEqual((s['metrics']['flight_count'], s['metrics']['unknown_duration_count']), (1, 1))

    def test_departure_date_mismatch(self):
        _, warnings, _ = enrich(ledger(departure_date='2026-10-28', departure_local='2026-10-29T10:05'))
        self.assertIn('differs from departure_local date', warnings[0])


if __name__ == '__main__':
    unittest.main()
