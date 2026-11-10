"""Synthetic tests for independent travel graphic layouts."""
import unittest,xml.etree.ElementTree as ET
from layouts import endpoints,orthographic,visible_path,ordered_legs
from render_report import render
from analyze import analyze
from test_analyze import ledger

class LayoutTests(unittest.TestCase):
    def test_all_combinations_and_brand(self):
        data=analyze(ledger())
        for theme in ('atlas','midnight','boarding-pass','executive'):
            for layout in ('routes','points','globe','journey','timeline'):
                doc,cover=render(data,theme,layout);ET.fromstring(cover)
                self.assertIn('https://AR.bd',doc);self.assertIn('https://AR.bd',cover)
                # The credit stays on every cover, as a small footer line rather than the headline.
                self.assertIn('Made with Flight Atlas by M Asif Rahman · AR.bd',cover)
                self.assertNotIn('FLIGHT ATLAS BY M ASIF RAHMAN',cover)
                self.assertLess(cover.index('FLIGHT ATLAS'),cover.index('Made with Flight Atlas'))
                self.assertNotIn('nan',cover.lower())
    def test_horizon_clipping(self):
        self.assertLess(orthographic(180,0,0,0)[2],0)
        self.assertGreater(orthographic(0,0,0,0)[2],0)
        self.assertEqual(visible_path([(170,0),(180,0)],(0,0)),'')
        crossing=visible_path([(80,0),(90,0),(100,0)],(0,0))
        self.assertIn('495.00,225.00',crossing)
        # A hidden segment must not bridge two visible segments.
        self.assertEqual(visible_path([(0,0),(120,0),(0,0)],(0,0)).count('M'),2)
    def test_globe_covers_both_hemispheres(self):
        data={'included_legs':[{'origin':'AAA','destination':'BBB','origin_lat':0,'origin_lon':0,'destination_lat':0,'destination_lon':180}]}
        _,cover=render(data,layout='globe')
        self.assertIn('data-airport="AAA"',cover)
        self.assertIn('data-airport="BBB"',cover)
        self.assertIn('OPPOSITE HEMISPHERE',cover)
        self.assertIn('globe-clip-1',cover)
    def test_points_do_not_invent_visits(self):
        data=analyze(ledger());data['included_legs'][0].pop('destination_lat')
        pts=endpoints(data['included_legs']);self.assertEqual(set(pts),{'LAX'})
        doc,cover=render(data,layout='points')
        self.assertIn('data-airport="LAX"',cover)
        self.assertNotIn('data-airport="HND"',cover)
        self.assertNotIn('data-airport="NRT"',cover)
        self.assertIn('No country visits are inferred',doc)
    def test_chronology_stable_and_limited(self):
        rows=[{'id':'b','departure_date':'2025-02-02'},{'id':'a','departure_date':'2025-01-01'},{'id':'c','departure_date':'2025-02-02'}]
        self.assertEqual([l['id'] for l in ordered_legs(rows)],['a','b','c'])
        data=analyze(ledger());data['included_legs']=data['included_legs'][::-1]
        _,cover=render(data,layout='timeline')
        self.assertLess(cover.index('2025-03-01'),cover.index('2025-03-10'))
        self.assertIn('Showing 2 of 2',cover)
    def test_unconfirmed_disclosure(self):
        data=analyze(ledger());data['included_legs'][0]['status']='itinerary_only'
        for layout in ('routes','points','globe','journey'):
            doc,cover=render(data,layout=layout)
            self.assertIn('Reconstructed records include unconfirmed itineraries.',doc)
            self.assertIn('Reconstructed records include unconfirmed itineraries.',cover)
    def test_dense_points_numbered_key(self):
        import re,math
        data={'included_legs':[{'origin':'JFK','origin_lat':40.64,'origin_lon':-73.78,'destination':'LGA','destination_lat':40.77,'destination_lon':-73.87},{'origin':'LGA','origin_lat':40.77,'origin_lon':-73.87,'destination':'BOS','destination_lat':42.36,'destination_lon':-71.01}]}
        _,cover=render(data,layout='points')
        circles=re.findall(r'<circle cx="([0-9.]+)" cy="([0-9.]+)" r="9"',cover)
        self.assertEqual(len(circles),3)
        for i,(x,y) in enumerate(circles):
            for xx,yy in circles[i+1:]:self.assertGreater(math.hypot(float(x)-float(xx),float(y)-float(yy)),20)
        self.assertNotIn('0 of 0 legs mapped',cover)
    def test_empty_layouts(self):
        for layout in ('routes','points','globe','journey','timeline'):
            _,cover=render({},layout=layout);ET.fromstring(cover)
    def test_title_block_tightens(self):
        data=analyze(ledger())
        _,short=render(data)
        data['report']['title']='Our family journeys across Asia and Europe in 2025'
        _,two=render(data)
        data['report']['title']='A much longer report title that needs to wrap across more than one line on the cover'
        _,three=render(data)
        self.assertIn('height="972"',short);self.assertIn('height="1026"',two);self.assertIn('height="1080"',three)
        for cover in (short,two,three):ET.fromstring(cover)

def many_legs(n=143):
    import random
    rnd=random.Random(7);airports={'DXB':(25.25,55.36),'LHR':(51.47,-0.45),'JFK':(40.64,-73.78),'SIN':(1.36,103.99),'SYD':(-33.95,151.18),'MNL':(14.51,121.02),'CDG':(49.01,2.55),'NRT':(35.77,140.39)}
    codes=sorted(airports);legs=[]
    for i in range(n):
        o,d=rnd.sample(codes,2);day=f'{2024+i*3//n}-{(i*36//n)%12+1:02d}-{i%27+1:02d}'
        legs.append({'id':str(i),'departure_date':day,'origin':o,'destination':d,'origin_lat':airports[o][0],'origin_lon':airports[o][1],'destination_lat':airports[d][0],'destination_lon':airports[d][1],'scheduled_minutes':300,'status':'flown','airline':'Example Air'})
    return {'report':{'title':'Three years','start_date':'2024-01-01','end_date':'2026-12-31'},'included_legs':legs}

class ScaleTests(unittest.TestCase):
    def test_journey_groups_long_histories(self):
        from layouts import journey_periods
        data=many_legs();periods=journey_periods(data['included_legs'])
        self.assertLessEqual(len(periods),8);self.assertEqual(sum(p['legs'] for p in periods),143)
        self.assertIn('2024',periods[0]['label']);self.assertIn('2026',periods[-1]['label'])
        _,cover=render(data,layout='journey');ET.fromstring(cover)
        self.assertIn('All 143 legs, grouped into',cover);self.assertIn('2026',cover)
    def test_routes_drawn_once_weighted(self):
        import re
        data=many_legs();_,cover=render(data,layout='routes')
        pairs={tuple(sorted((l['origin'],l['destination']))) for l in data['included_legs']}
        widths=re.findall(r'<path d="M[^"]*" stroke-width="([0-9.]+)" stroke-opacity="[0-9.]+"><title>',cover)
        self.assertEqual(len(widths),len(pairs))
        self.assertGreater(max(map(float,widths)),min(map(float,widths)))
        self.assertIn('flights</title>',cover)
    def test_globe_centred_on_airports(self):
        from layouts import globe_centers,endpoints,orthographic
        legs=[{'origin':'LHR','origin_lat':51.47,'origin_lon':-0.45,'destination':'CDG','destination_lat':49.01,'destination_lon':2.55},{'origin':'CDG','origin_lat':49.01,'origin_lon':2.55,'destination':'SYD','destination_lat':-33.95,'destination_lon':151.18}]
        pts=endpoints(legs);centers,_=globe_centers(legs,pts)
        # Every airport faces the viewer in at least one view, and Europe is in the first.
        for pt in pts.values():self.assertGreaterEqual(max(orthographic(*pt,*c)[2] for c in centers),0)
        self.assertGreater(orthographic(-0.45,51.47,*centers[0])[2],0.5)
        _,cover=render({'included_legs':legs},layout='globe');ET.fromstring(cover)
        for code in pts:self.assertIn(f'data-airport="{code}"',cover)

if __name__=='__main__':unittest.main()
