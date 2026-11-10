import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from merge_ledgers import merge  # noqa: E402

HERE = Path(__file__).parent


def leg(ident, day='2025-03-01', o='AAA', d='BBB', status='itinerary_only', **kw):
    row = {'id': ident, 'traveler_id': 't', 'departure_date': day, 'origin': o, 'destination': d,
           'status': status, 'evidence_ids': ['src-' + ident]}
    row.update(kw)
    return row


class Merge(unittest.TestCase):
    def test_same_flight_from_two_searches_becomes_one_row(self):
        a = {'legs': [leg('a1', operating_flight='ZZ0101', departure_local='2025-03-01T09:00')]}
        b = {'legs': [leg('b1', status='strongly_supported', operating_flight='ZZ101', arrival_local='2025-03-01T11:00')]}
        out, log = merge([a, b])
        self.assertEqual(len(out['legs']), 1)
        row = out['legs'][0]
        self.assertEqual(row['status'], 'strongly_supported')
        self.assertEqual(row['evidence_ids'], ['src-a1', 'src-b1'])
        self.assertEqual(row['arrival_local'], '2025-03-01T11:00')
        self.assertTrue(any('merged b1 into a1' in x for x in log))

    def test_conflicting_times_stay_apart_for_review(self):
        a = {'legs': [leg('a1', operating_flight='ZZ1', departure_local='2025-03-01T09:00')]}
        b = {'legs': [leg('b1', operating_flight='ZZ1', departure_local='2025-03-01T21:00')]}
        out, log = merge([a, b])
        self.assertEqual(len(out['legs']), 2)
        self.assertTrue(any('different departure_local' in x for x in log))

    def test_cancelled_copy_is_not_merged_into_a_flown_one(self):
        a = {'legs': [leg('a1', status='flown', operating_flight='ZZ1')]}
        b = {'legs': [leg('b1', status='cancelled', operating_flight='ZZ1')]}
        out, _ = merge([a, b])
        self.assertEqual(sorted(l['status'] for l in out['legs']), ['cancelled', 'flown'])

    def test_no_flight_number_merges_only_on_the_same_printed_time(self):
        a = {'legs': [leg('a1', departure_local='2025-03-01T09:00'), leg('a2')]}
        b = {'legs': [leg('b1', departure_local='2025-03-01T09:00'), leg('b2')]}
        out, _ = merge([a, b])
        self.assertEqual(sorted(l['id'] for l in out['legs']), ['a1', 'a2', 'b2'])

    def test_clashing_ids_are_renamed_with_their_references(self):
        a = {'legs': [leg('x', day='2025-03-01')]}
        b = {'legs': [leg('x', day='2025-04-01', o='BBB', d='CCC'), leg('y', day='2025-04-02', o='CCC', d='DDD', supersedes_id='x', status='itinerary_only')],
             'ground_segments': [{'id': 'g', 'after_id': 'x', 'before_id': 'y', 'from': 'CCC', 'to': 'CCC'}]}
        out, log = merge([a, b], ['first', 'second'])
        ids = [l['id'] for l in out['legs']]
        self.assertIn('second-x', ids)
        y = next(l for l in out['legs'] if l['id'] == 'y')
        self.assertEqual(y['supersedes_id'], 'second-x')
        self.assertEqual(out['ground_segments'][0]['after_id'], 'second-x')

    def test_cli_sets_report_fields_and_output_analyzes(self):
        with tempfile.TemporaryDirectory() as d:
            p1, p2, out = Path(d) / 'h1.json', Path(d) / 'h2.json', Path(d) / 'draft.json'
            p1.write_text(json.dumps({'legs': [leg('a', operating_flight='ZZ1', departure_local='2025-03-01T09:00', arrival_local='2025-03-01T10:00', origin='LHR', destination='CDG')]}))
            p2.write_text(json.dumps({'legs': [leg('b', operating_flight='ZZ1', origin='LHR', destination='CDG')]}))
            r = subprocess.run([sys.executable, str(HERE / 'merge_ledgers.py'), str(p1), str(p2), '--out', str(out),
                                '--title', 'Test', '--start', '2025-01-01', '--end', '2025-12-31', '--as-of', '2025-12-31', '--home', 'lhr'],
                               capture_output=True, text=True, check=True)
            self.assertIn('1 legs written', r.stdout)
            ledger = json.loads(out.read_text())
            self.assertEqual(ledger['report']['home_airports'], ['LHR'])
            enriched = Path(d) / 'ledger.json'
            subprocess.run([sys.executable, str(HERE / 'enrich.py'), str(out), '--out', str(enriched)], capture_output=True, text=True, check=True)
            summary = Path(d) / 'summary.json'
            subprocess.run([sys.executable, str(HERE / 'analyze.py'), str(enriched), '--out', str(summary)], capture_output=True, text=True, check=True)
            self.assertEqual(json.loads(summary.read_text())['metrics']['flight_count'], 1)

    def test_scheduled_timestamps_count_as_timing_evidence(self):
        a = {'legs': [leg('a1', operating_flight='ZZ1', departure_scheduled='2025-03-01T10:00:00+04:00', arrival_scheduled='2025-03-01T14:00:00+00:00')]}
        same = {'legs': [leg('b1', operating_flight='ZZ1', departure_scheduled='2025-03-01T06:00:00Z')]}
        moved = {'legs': [leg('c1', operating_flight='ZZ1', arrival_scheduled='2025-03-01T15:30:00+00:00')]}
        out, _ = merge([a, same])
        self.assertEqual(len(out['legs']), 1)
        out, log = merge([a, moved])
        self.assertEqual(len(out['legs']), 2)
        self.assertTrue(any('arrival_scheduled' in x for x in log))

    def test_replacement_ids_never_collide_with_later_ids(self):
        a = {'legs': [leg('x', day='2025-03-01')]}
        b = {'legs': [leg('x', day='2025-04-01', o='BBB', d='CCC'), leg('second-x', day='2025-05-01', o='CCC', d='DDD')],
             'manual_gaps': [{'kind': 'return_unknown', 'leg_id': 'x'}, {'kind': 'return_unknown', 'leg_id': 'second-x'}]}
        out, _ = merge([a, b], ['first', 'second'])
        ids = [l['id'] for l in out['legs']]
        self.assertEqual(len(ids), len(set(ids)))
        renamed = next(l for l in out['legs'] if l['departure_date'] == '2025-04-01')['id']
        self.assertEqual([g['leg_id'] for g in out['manual_gaps']], [renamed, 'second-x'])

    def test_report_dates_span_every_part(self):
        h1 = {'report': {'title': 'T', 'start_date': '2025-01-01', 'end_date': '2025-06-30', 'as_of': '2025-06-30', 'home_airports': ['AAA']}, 'legs': [leg('a')]}
        h2 = {'report': {'title': 'T', 'start_date': '2025-07-01', 'end_date': '2025-12-31', 'as_of': '2025-12-31', 'home_airports': ['BBB']}, 'legs': [leg('b', day='2025-08-01')]}
        out, log = merge([h1, h2])
        r = out['report']
        self.assertEqual((r['start_date'], r['end_date'], r['as_of'], r['home_airports']), ('2025-01-01', '2025-12-31', '2025-12-31', ['AAA', 'BBB']))
        self.assertTrue(any('report.end_date' in x for x in log))

    def test_better_duration_source_wins_whatever_the_order(self):
        est = leg('a1', operating_flight='ZZ1', scheduled_minutes=100, duration_basis='estimated')
        tic = leg('b1', operating_flight='ZZ1', scheduled_minutes=100, duration_basis='ticket_advertised')
        for parts in ([{'legs': [dict(est)]}, {'legs': [dict(tic)]}], [{'legs': [dict(tic)]}, {'legs': [dict(est)]}]):
            out, _ = merge(parts)
            self.assertEqual(out['legs'][0]['duration_basis'], 'ticket_advertised')


if __name__ == '__main__':
    unittest.main()
