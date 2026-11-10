#!/usr/bin/env python3
"""Synthetic-only renderer regressions."""
import unittest
import xml.etree.ElementTree as ET
from analyze import analyze
from test_analyze import ledger
from render_report import render, arc, route_path, coordinates

class RendererTests(unittest.TestCase):
    def test_themes_and_svg(self):
        data=analyze(ledger())
        for theme in ('atlas','midnight','boarding-pass','executive'):
            document,cover=render(data,theme)
            ET.fromstring(cover)
            self.assertIn('countries visited',document)
            self.assertIn('COUNTRIES VISITED',cover)
            # An older summary without places still renders the airport-country card.
            old={k:v for k,v in data.items() if k!='places'}; old['metrics']={k:v for k,v in data['metrics'].items() if not k.startswith(('visited_','transit_only'))}
            self.assertIn('airport countries (incl. transit)',render(old,theme)[0])
            self.assertIn('2/2 legs known',document)
            self.assertIn('Monthly scheduled hours',document)
            self.assertIn('flown: 1 legs',document)
            self.assertIn('The longer journeys',document)
            self.assertIn('Geographic coverage: 1/2',document)
            self.assertNotIn('<script',document)
            self.assertIn('Made with Flight Atlas by M Asif Rahman · AR.bd',cover)
            self.assertIn('Made with <a href="https://AR.bd">Flight Atlas by M Asif Rahman',document)
            # Bar charts carry literal colours so PDF renderers do not paint them black.
            self.assertNotIn('fill="var(',document)
    def test_annual_and_warnings(self):
        data=analyze(ledger());data['annual'].append({'year':2026,'flights':1,'minutes':120,'unknown_duration_count':0});data['warnings']=['Review <timing>']
        document,_=render(data)
        self.assertIn('Annual comparison',document);self.assertIn('Review &lt;timing&gt;',document)
    def test_gap_labels_ground_and_shortest(self):
        data=analyze(ledger())
        data['gaps']=[{'kind':'unknown_duration','leg_id':'a','note':'Timing unavailable'},{'kind':'boundary_gap','note':'Start of period incomplete'}]
        data['ground_segments']=[{'from':'HND','to':'NRT','mode':'train'}]
        document,_=render(data)
        self.assertNotIn('? → ?',document)
        self.assertIn('Unknown duration · a',document)
        self.assertIn('Boundary gap',document)
        self.assertIn('Ground transfers (not flights)',document)
        self.assertIn('HND → NRT',document)
        self.assertIn('Shortest known scheduled leg',document)
        self.assertIn('NRT → LAX · 10h 00m',document)
    def test_empty(self):
        document,cover=render({});ET.fromstring(cover);self.assertIn('No included flights',document)
    def test_routes(self):
        for coords in ((0,170,0,-170),(0,-170,0,170)):
            self.assertEqual(route_path(arc(*coords)).count('M'),2)
        for coords in ((0,0,0,180),(10,20,10,20)):
            self.assertNotIn('nan',route_path(arc(*coords)).lower())
        self.assertIsNone(coordinates({'origin_lat':float('nan')}))
if __name__=='__main__':unittest.main()
