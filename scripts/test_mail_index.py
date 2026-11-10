import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from mail_index import index, same_person, passenger_names, classify  # noqa: E402

HERE = Path(__file__).parent


def msg(ident, subject, snippet='', sender='no-reply@example-air.test', date='2025-03-01T10:00:00Z', thread=None):
    return {'id': ident, 'threadId': thread or ident, 'subject': subject, 'snippet': snippet, 'sender': sender, 'date': date}


def gmail(*messages):
    return {'threads': [{'id': m['threadId'], 'messages': [m]} for m in messages]}


class SamePerson(unittest.TestCase):
    def test_order_initials_and_titles(self):
        for name in ('LEE JORDAN', 'Jordan Lee', 'MR JORDAN LEE', 'J Jordan Lee', 'LEE/JORDANMR', 'Jordan'):
            self.assertTrue(same_person(name, 'Jordan Lee'), name)

    def test_shared_surname_is_someone_else(self):
        for name in ('SAM LEE', 'Priya Lee', 'LEE SAM'):
            self.assertFalse(same_person(name, 'Jordan Lee'), name)


class Passengers(unittest.TestCase):
    def test_salutation_names_stop_before_ordinary_words(self):
        self.assertEqual(passenger_names('Hello MS PRIYA LEE, Your air ticket has been issued'), ['PRIYA LEE'])
        self.assertEqual(passenger_names('Electronic ticket receipt, May 3 PARIS for MR SAM LEE Itinerary Confirmation'), ['SAM LEE'])

    def test_greetings_without_a_name(self):
        self.assertEqual(passenger_names('Dear Sir, hi user, Hello valued customer'), [])


class Classify(unittest.TestCase):
    def test_kinds_from_subjects(self):
        cases = {
            'Check in online for your flight to Lisbon on 30 July': 'checkin',
            'Boarding pass for Jordan Lee ZZ0101:AAA-BBB:22-JUN-2025': 'boarding',
            'Your itinerary - booking confirmed': 'booking',
            'Important: schedule change to your flight': 'change',
            'Your flight has been cancelled and refunded': 'cancel',
            'How was your check-in, Jordan?': 'noise',
            'Reminder: your meeting Q4 Check In is about to start': 'noise',
            'Booking Confirmation #12345': 'booking',
            'Your trip with Example Rides on Saturday': 'other',
        }
        for subject, kind in cases.items():
            self.assertEqual(classify(subject, '', 'no-reply@example-air.test'), kind, subject)

    def test_bus_and_hotel_by_sender(self):
        self.assertEqual(classify('Booking Confirmation #12345', '', 'noreply@booking.flixbus.test'), 'ground')
        self.assertEqual(classify('Ready for your trip?', '', 'reservations@hertz.example.test'), 'hotel')

    def test_free_cancellation_in_a_preview_is_not_a_cancellation(self):
        self.assertEqual(classify('Booking confirmation with Example Travel', 'Free cancellation until 1 May', 'x@t.test'), 'booking')


class Index(unittest.TestCase):
    def setUp(self):
        self.data = gmail(
            msg('m3', 'Boarding pass for Jordan Lee ZZ0450:AAA-BBB:14-MAY-2025', date='2025-05-13T08:00:00Z'),
            msg('m1', 'Flight Booking Confirmation #X1', 'Hello MS PRIYA LEE, Your air ticket has been issued.', date='2025-05-01T08:00:00Z'),
            msg('m2', 'Flight Booking Confirmation #X2', 'Hello MR LEE JORDAN, Your air ticket has been issued.', date='2025-05-02T08:00:00Z'),
            msg('m4', 'How was your check-in, Jordan?', date='2025-06-25T08:00:00Z'),
            msg('m5', 'Fwd: Your Example Air itinerary - ABC123', date='2025-05-03T08:00:00Z'),
        )

    def test_sorted_deduplicated_with_hints_and_flags(self):
        rows = index([self.data, self.data], traveler='Jordan Lee')
        self.assertEqual([r['id'] for r in rows], ['m1', 'm2', 'm5', 'm3', 'm4'])
        byid = {r['id']: r for r in rows}
        self.assertEqual(byid['m1']['flags'], ['other:PRIYA LEE'])
        self.assertEqual(byid['m2']['flags'], [])
        self.assertIn('forwarded', byid['m5']['flags'])
        self.assertEqual(byid['m3']['route'], 'AAA-BBB')
        self.assertEqual(byid['m3']['date_hint'], '14 May 2025')
        self.assertEqual(byid['m4']['kind'], 'noise')

    def test_cli_hides_noise_and_reads_tool_text_wrappers(self):
        with tempfile.TemporaryDirectory() as d:
            # Some hosts save tool output as [{"type": "text", "text": "<json>"}].
            path = Path(d) / 'page.json'
            path.write_text(json.dumps([{'type': 'text', 'text': json.dumps(self.data)}]))
            out = subprocess.run([sys.executable, str(HERE / 'mail_index.py'), '--traveler', 'Jordan Lee', str(path)],
                                 capture_output=True, text=True, check=True)
        self.assertIn('AAA-BBB 14 May 2025', out.stdout)
        self.assertIn('other:PRIYA LEE', out.stdout)
        self.assertNotIn('How was your check-in', out.stdout)
        self.assertIn('5 messages', out.stderr)


if __name__ == '__main__':
    unittest.main()
