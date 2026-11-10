#!/usr/bin/env python3
"""Synthetic regression checks; no mailbox access or personal data."""
import copy, unittest
from analyze import analyze

def ledger():
    return {'schema_version':1,'report':{'title':'Synthetic journeys','start_date':'2025-01-01','end_date':'2025-12-31','as_of':'2025-12-31'},'legs':[
        {'id':'a','traveler_id':'t','departure_date':'2025-03-01','origin':'LAX','destination':'HND','status':'flown','operating_flight':'ZZ1','airline':'Example Air','evidence_ids':['synthetic-a'],'departure_scheduled':'2025-03-01T10:00:00-08:00','arrival_scheduled':'2025-03-02T15:00:00+09:00','origin_lat':33.94,'origin_lon':-118.4,'destination_lat':35.55,'destination_lon':139.78,'origin_country':'US','destination_country':'JP'},
        {'id':'b','traveler_id':'t','departure_date':'2025-03-10','origin':'NRT','destination':'LAX','status':'user_confirmed','evidence_ids':['synthetic-b'],'scheduled_minutes':600,'duration_basis':'ticket_advertised'}]}

class AnalyzerTests(unittest.TestCase):
    def test_timezone_and_unknown_transfer(self):
        s=analyze(ledger()); self.assertEqual(s['metrics']['scheduled_minutes'],1320); self.assertEqual(s['metrics']['flight_count'],2); self.assertEqual(s['gaps'][0]['kind'],'unresolved_transfer')
    def test_ground_closure(self):
        d=ledger(); d['ground_segments']=[{'after_id':'a','before_id':'b','from':'HND','to':'NRT','status':'user_confirmed','mode':'train'}];self.assertFalse(analyze(d)['gaps'])
    def test_explained_transfer_and_hint(self):
        d=ledger(); d['manual_gaps']=[{'kind':'same_city_transfer','after_id':'a','before_id':'b','note':'Both Tokyo airports; stayed in the city.'},
                                     {'kind':'hint','after_id':'a','before_id':'b','note':'a hotel near the airport'}]
        s=analyze(d); self.assertEqual([g['kind'] for g in s['gaps']],['same_city_transfer'])
    def test_future_missed_cancelled(self):
        d=ledger();d['legs'][0]['status']='missed';d['report']['as_of']='2025-03-05';s=analyze(d);self.assertEqual(s['metrics']['flight_count'],0);self.assertEqual(len(s['exclusions']),2)
    def test_unknown_not_zero(self):
        d=ledger(); d['legs'][1].pop('scheduled_minutes');s=analyze(d);self.assertEqual(s['metrics']['flight_count'],2);self.assertEqual(s['metrics']['unknown_duration_count'],1);self.assertIsNone(s['included_legs'][1]['scheduled_minutes'])
    def test_conflict(self):
        d=ledger();d['legs'][0].update(scheduled_minutes=700,duration_basis='ticket_advertised');s=analyze(d);self.assertEqual(s['metrics']['known_duration_count'],1);self.assertIn('differs',s['warnings'][0])
    def test_modes_and_boundary(self):
        d=ledger();d['legs'][0]['status']='itinerary_only';d['report']['inclusion_mode']='confirmed';self.assertEqual(analyze(d)['metrics']['flight_count'],1)
        d=ledger();d['legs'][0]['departure_date']='2024-12-31';self.assertEqual(analyze(d)['metrics']['flight_count'],1)
    def test_naive_timestamp(self):
        d=ledger();d['legs'][0]['departure_scheduled']='2025-03-01T10:00:00';self.assertEqual(analyze(d)['metrics']['unknown_duration_count'],1)
    def test_estimate_excluded(self):
        d=ledger();d['legs'][1]['duration_basis']='estimated';self.assertEqual(analyze(d)['metrics']['scheduled_minutes'],720)
    def test_exact_duplicate(self):
        d=ledger();dup=copy.deepcopy(d['legs'][0]);dup['id']='copy';d['legs'].append(dup);self.assertEqual(analyze(d)['metrics']['flight_count'],2)
    def test_invalid_ids_and_travelers(self):
        d=ledger();d['legs'][1]['id']='a'
        with self.assertRaises(ValueError):analyze(d)
        d=ledger();d['legs'][1]['traveler_id']='someone-else'
        with self.assertRaises(ValueError):analyze(d)
    def test_output_omits_private_evidence(self):
        d=ledger();d['legs'][0]['pnr']='SECRET';s=analyze(d);self.assertNotIn('pnr',s['included_legs'][0]);self.assertNotIn('evidence_ids',s['included_legs'][0])
    def test_partial_date(self):
        d=ledger();d['legs'][0]['departure_date']='2025-03';s=analyze(d);self.assertEqual(s['metrics']['flight_count'],1);self.assertIn('unresolved',s['exclusions'][0]['reason'])
    def test_dst_offset_elapsed(self):
        d=ledger();l=d['legs'][0];l.update(departure_date='2025-11-02',departure_scheduled='2025-11-02T01:30:00-04:00',arrival_scheduled='2025-11-02T02:30:00-05:00');d['legs']= [l];self.assertEqual(analyze(d)['metrics']['scheduled_minutes'],120)
    def test_no_future_zero_months(self):
        d=ledger();d['report']['as_of']='2025-03-15';self.assertEqual(len(analyze(d)['monthly']),3)
    def test_total_consistency(self):
        s=analyze(ledger());self.assertEqual(sum(r['minutes'] for r in s['monthly']),s['metrics']['scheduled_minutes']);self.assertEqual(sum(r['flights'] for r in s['airlines']),s['metrics']['flight_count'])
    def test_codeshare_flagged(self):
        d=ledger();dup=copy.deepcopy(d['legs'][0]);dup.update(id='marketing',operating_flight=None);d['legs'].append(dup)
        s=analyze(d);self.assertEqual(s['metrics']['possible_duplicate_count'],1)
        self.assertTrue(any('possible codeshare' in w and 'marketing' in w for w in s['warnings']))
        d=ledger();dup=copy.deepcopy(d['legs'][0]);dup.update(id='other',operating_flight='YY900');d['legs'].append(dup)
        self.assertIn('different flight numbers',' '.join(analyze(d)['warnings']))
    def test_same_route_hours_apart_not_flagged(self):
        d=ledger();second=copy.deepcopy(d['legs'][0]);second.update(id='later',operating_flight='ZZ3',departure_scheduled='2025-03-01T18:00:00-08:00',arrival_scheduled='2025-03-02T23:00:00+09:00');d['legs'].append(second)
        s=analyze(d);self.assertEqual(s['metrics']['possible_duplicate_count'],0);self.assertEqual(s['metrics']['flight_count'],3)
    def test_codeshare_found_regardless_of_order(self):
        d=ledger();late=copy.deepcopy(d['legs'][0]);late.update(id='late',operating_flight='ZZ3',departure_scheduled='2025-03-01T18:00:00-08:00',arrival_scheduled='2025-03-02T23:00:00+09:00')
        copyleg=copy.deepcopy(d['legs'][0]);copyleg.update(id='copy',operating_flight=None)
        d['legs'][1:1]=[late,copyleg]
        s=analyze(d);self.assertEqual(s['metrics']['possible_duplicate_count'],1)
        self.assertTrue(any(w.startswith('copy: possible codeshare or duplicate of a') for w in s['warnings']))
    def test_lowercase_ground_transfer_still_closes(self):
        d=ledger();d['legs'][0]['destination']='hnd';d['legs'][1]['origin']='nrt'
        d['ground_segments']=[{'after_id':'a','before_id':'b','from':'hnd','to':'nrt','status':'user_confirmed','mode':'train'}]
        s=analyze(d);self.assertFalse(s['gaps']);self.assertEqual(s['ground_segments'][0]['from'],'HND')
    def test_lowercase_codes_normalized(self):
        d=ledger();d['legs'][0]['destination']='hnd';d['legs'][1]['origin']=' hnd '
        s=analyze(d);self.assertEqual(s['included_legs'][0]['destination'],'HND');self.assertFalse([g for g in s['gaps'] if g['kind']=='unresolved_transfer'])
        self.assertEqual(d['legs'][0]['destination'],'hnd')  # input untouched
    def test_missing_evidence_warns(self):
        d=ledger();d['legs'][1]['evidence_ids']=[];s=analyze(d)
        self.assertEqual(s['metrics']['flight_count'],1);self.assertIn('evidence_ids is empty',' '.join(s['warnings']))
    def test_integral_float_minutes(self):
        d=ledger();d['legs'][1]['scheduled_minutes']=600.0;self.assertEqual(analyze(d)['metrics']['scheduled_minutes'],1320)
        d['legs'][1]['scheduled_minutes']=600.5;self.assertEqual(analyze(d)['metrics']['unknown_duration_count'],1)
    def test_clear_errors(self):
        for broken,needle in ((lambda d:d.pop('report'),'"report" object'),(lambda d:d['report'].pop('start_date'),'report.start_date is required'),(lambda d:d['report'].update(end_date='soon'),"report.end_date 'soon' is not a date"),(lambda d:d.pop('legs'),'"legs" list')):
            d=ledger();broken(d)
            with self.assertRaises(ValueError) as caught:analyze(d)
            self.assertIn(needle,str(caught.exception))
    def test_other_traveler_outside_window_ignored(self):
        d=ledger();extra=copy.deepcopy(d['legs'][1]);extra.update(id='spouse',traveler_id='spouse',departure_date='2024-06-01');d['legs'].append(extra)
        self.assertEqual(analyze(d)['metrics']['flight_count'],2)
    def test_cancelled_future_keeps_status_reason(self):
        d=ledger();d['legs'][1].update(status='cancelled',departure_date='2026-01-05');d['report']['end_date']='2026-12-31'
        self.assertEqual([x['reason'] for x in analyze(d)['exclusions']],['status: cancelled'])
    def test_cli_friendly_error(self):
        import subprocess,sys,tempfile,os
        with tempfile.TemporaryDirectory() as tmp:
            bad=os.path.join(tmp,'bad.json')
            with open(bad,'w') as handle:handle.write('{"schema_version":1,')
            run=subprocess.run([sys.executable,os.path.join(os.path.dirname(os.path.abspath(__file__)),'analyze.py'),bad,'--out',os.path.join(tmp,'s.json')],capture_output=True,text=True,timeout=30)
            self.assertEqual(run.returncode,1);self.assertIn('not valid JSON',run.stderr);self.assertNotIn('Traceback',run.stderr)
if __name__=='__main__': unittest.main()
