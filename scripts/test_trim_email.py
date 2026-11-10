#!/usr/bin/env python3
"""Synthetic tests for trim_email (no real mail)."""
import tempfile
import unittest
from pathlib import Path
from trim_email import trim, html_to_text, load

TRACK = '<https://track.example-airline.test/click/' + 'eyJ' + 'A' * 600 + '>'
AIRLINE = '\n'.join([
    'Example Air ' + TRACK, '* Add Example Air to your safe senders list ' + TRACK,
    '= Your booking is confirmed =', 'Hello Sam,', 'Thanks for your booking. Your itinerary is below.',
    'Please read our *terms and conditions* ' + TRACK, 'Booking reference * ZZ9XYZ *',
    'The carriage of certain hazardous materials like aerosols is forbidden. ' * 4,
    '*Your itinerary* * Outbound | Lisbon to Chicago | Duration: 8 hr 15 min *',
    '*Depart* *Arrive* * LIS * Lisbon * ORD * Chicago * 09:40 * Tuesday 03 Mar 26 * 12:55 * Tuesday 03 Mar 26',
    '* Flight * ZZ401 *Aircraft* Airbus A330-900 *Stops* Non-stop *Class / Fare* Economy *Status* Confirmed',
    '* Inbound | Chicago to Lisbon | Duration: 7 hr 15 min *',
    '* ORD * Chicago * LIS * Lisbon * 21:30 * Tuesday 10 Mar 26 * 09:45 * Wednesday 11 Mar 26',
    '* Flight * ZZ402 *Stops* Non-stop *Status* Confirmed',
] + [f'*Explore offer {i}* {TRACK}' for i in range(30)] + [
    'Follow Example Air ' + TRACK, '© 2026 Example Air. All rights reserved. Privacy policy ' + TRACK])

OTA_HTML = ('<html><head><style>.x{color:red}</style></head><body><table>'
            '<tr><td>Departure: Manila - Osaka | April 14, 2025</td></tr>'
            '<tr><td>9:05 AM</td><td>MNL Example International Airport T1</td></tr>'
            '<tr><td>Example Lines ZZ190 | Economy | Airbus A330-200</td></tr>'
            '<tr><td>1:20 PM</td><td>KIX Example Airport</td></tr>'
            '<tr><td><a href="https://ota.test/app">Download our app</a></td></tr>'
            '</table><script>track()</script></body></html>')


class TrimTests(unittest.TestCase):
    def test_airline_email_shrinks_and_keeps_segments(self):
        out = trim(AIRLINE)
        self.assertLess(len(out), len(AIRLINE) * 0.1)
        for needle in ('ZZ401', 'ZZ402', '09:40', '12:55', '21:30', '09:45', '8 hr 15 min', '7 hr 15 min', 'LIS', 'ORD', 'ZZ9XYZ', '11 Mar 26', 'Confirmed'):
            self.assertIn(needle, out)
        self.assertNotIn('http', out)
        self.assertNotIn('All rights reserved', out)
        self.assertNotIn('safe senders', out)

    def test_long_flattened_line_keeps_segments(self):
        line = ' | '.join(['Your booking is confirmed', 'Booking reference ZZ9XYZ'] + ['Lorem ipsum dolor sit amet ' * 3] * 6 + [
            'ZZ401 LIS 09:40 03 Mar 26 ORD 12:55 03 Mar 26', 'ZZ402 ORD 21:30 10 Mar 26 LIS 09:45 11 Mar 26'])
        self.assertGreater(len(line), 400)
        out = trim(line)
        for needle in ('ZZ401', '09:40', 'ZZ402', '09:45', 'ZZ9XYZ'):
            self.assertIn(needle, out)

    def test_eml_declared_charset(self):
        raw = ('From: bookings@example-air.test\r\nSubject: Itinerary\r\nMIME-Version: 1.0\r\n'
               'Content-Type: text/plain; charset=ISO-8859-1\r\nContent-Transfer-Encoding: 8bit\r\n\r\n'
               'Passenger: Jos\u00e9 Garc\u00eda\r\nFlight ZZ401 LIS 09:40 ORD 12:55\r\n').encode('latin-1')
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'message.eml'
            path.write_bytes(raw)
            header, body = load(str(path))
        self.assertIn('Subject: Itinerary', header)
        self.assertIn('Jos\u00e9 Garc\u00eda', trim(body))

    def test_ota_html(self):
        out = trim(html_to_text(OTA_HTML))
        for needle in ('April 14, 2025', '9:05 AM', 'MNL', 'ZZ190', '1:20 PM', 'KIX'):
            self.assertIn(needle, out)
        self.assertNotIn('track()', out)
        self.assertNotIn('color:red', out)
        self.assertNotIn('Download our app', out)


class GdsLines(unittest.TestCase):
    def test_agent_pasted_segments_are_spelled_out(self):
        from trim_email import gds_segments, trim
        text = "Dear sir, please find the itinerary\n 1 ZZ 271 K 08FEB DXBLHR HK3 1615 2045\n 2 ZZ 512 U 14FEB 6 LHRDXB HK3 2110 0800+1\n"
        segs = gds_segments(text)
        self.assertEqual([(s['flight'], s['origin'], s['destination'], s['departure'], s['arrival_day_offset'], s['status'], s['seats']) for s in segs],
                         [('ZZ271', 'DXB', 'LHR', '16:15', 0, 'confirmed', 3), ('ZZ512', 'LHR', 'DXB', '21:10', 1, 'confirmed', 3)])
        out = trim(text)
        self.assertIn('[GDS segment] ZZ512 14FEB LHR→DXB dep 21:10 arr 08:00 (+1 day), confirmed, 3 seat(s)', out)

    def test_ordinary_text_has_no_segments(self):
        from trim_email import gds_segments
        self.assertEqual(gds_segments('Flight ZZ 101 departs 10:30 from DXB to LHR on 6 Jan'), [])


if __name__ == '__main__':
    unittest.main()
