#!/usr/bin/env python3
"""Packaging and intake-flow checks: SKILL.md frontmatter, links, license, no-email path."""
import re
import unittest
from pathlib import Path
from enrich import enrich
from analyze import analyze

ROOT = Path(__file__).resolve().parent.parent
SKILL = (ROOT / 'SKILL.md').read_text(encoding='utf-8')
INTAKE = (ROOT / 'references' / 'intake.md').read_text(encoding='utf-8')


class PackageTests(unittest.TestCase):
    def test_frontmatter(self):
        match = re.match(r'^---\nname: (.+)\ndescription: (.+)\n---\n', SKILL)
        self.assertIsNotNone(match)
        name, description = match.groups()
        self.assertRegex(name, r'^[a-z0-9-]{1,64}$')
        self.assertLessEqual(len(description), 1024)
        self.assertIn('not connected', description)

    def test_local_links_exist(self):
        for doc in [ROOT / 'SKILL.md', *sorted((ROOT / 'references').glob('*.md'))]:
            for target in re.findall(r'\]\(([^)#]+)\)', doc.read_text(encoding='utf-8')):
                if target.startswith('http'):
                    continue
                self.assertTrue((doc.parent / target).exists(), f'{doc.name} links missing {target}')

    def test_mit_license(self):
        text = (ROOT / 'LICENSE').read_text(encoding='utf-8')
        self.assertTrue(text.startswith('MIT License'))
        self.assertIn('M Asif Rahman', text)
        self.assertIn('MIT License', (ROOT / 'README.md').read_text(encoding='utf-8'))


class IntakeFlowTests(unittest.TestCase):
    def test_skill_asks_to_connect_then_three_questions(self):
        start = SKILL.index('## Start: connect email')
        self.assertLess(start, SKILL.index('## Choose the report and design first'))
        section = SKILL[start:SKILL.index('## Choose the report')]
        for word in ('connect their email', '**timeframe**', '**design**', '**gaps**', 'Never stall'):
            self.assertIn(word, section)

    def test_intake_message_covers_all_three(self):
        for word in ('**Timeframe:**', '**Design:**', '**Gaps:**', '**Home and format:**', 'full PDF report', 'connect', 'never ask for a password'):
            self.assertIn(word, INTAKE)

    def test_skill_asks_about_missing_trips_and_pdf(self):
        section = SKILL[SKILL.index("## Ask about what's missing"):SKILL.index('## Calculate and render')]
        for word in ('clarify.py', 'home_airports', 'boarding pass', 'screenshot', 'Never add a flight', 'outbound_before_period'):
            self.assertIn(word, section)
        self.assertIn('export_pdf.py', SKILL)
        self.assertIn('**full PDF report**', SKILL)

    def test_no_email_ledger_from_user_statements(self):
        """Flights a person lists themselves: user_confirmed, local times, one without times."""
        legs = [
            {'id': 'u1', 'traveler_id': 'me', 'origin': 'lis', 'destination': 'ord', 'status': 'user_confirmed', 'evidence_ids': ['user-statement-1'], 'departure_local': '2026-03-03T09:40', 'arrival_local': '2026-03-03T12:55'},
            {'id': 'u2', 'traveler_id': 'me', 'origin': 'ORD', 'destination': 'LIS', 'status': 'user_confirmed', 'evidence_ids': ['user-statement-2'], 'departure_date': '2026-03-10'},
        ]
        data = {'schema_version': 1, 'report': {'title': 'From my own list', 'start_date': '2026-03-01', 'end_date': '2026-03-31', 'as_of': '2026-03-31', 'coverage_note': 'Built from the traveler\'s own account; no email connected.'},
                'legs': legs, 'manual_gaps': [{'kind': 'missing_flight', 'note': 'Traveler recalls a weekend trip in late March; no details yet.'}]}
        enriched, warnings, _ = enrich(data)
        self.assertEqual(warnings, [])
        summary = analyze(enriched)
        m = summary['metrics']
        self.assertEqual((m['flight_count'], m['scheduled_minutes'], m['unknown_duration_count']), (2, 555, 1))
        self.assertEqual(summary['status_counts'], {'user_confirmed': 2})
        self.assertIn('missing_flight', [g['kind'] for g in summary['gaps']])


class InstallPackageTests(unittest.TestCase):
    def test_package_has_skill_files_only(self):
        import re, tempfile, zipfile
        from package_skill import ROOT, skill_files, write_zip, copy_to
        files = {f.as_posix() for f in skill_files()}
        self.assertIn('SKILL.md', files)
        self.assertIn('scripts/analyze.py', files)
        self.assertIn('assets/airports.csv', files)
        self.assertFalse([f for f in files if f.startswith('docs/') or '__pycache__' in f or f == 'README.md'])
        # Every local file SKILL.md points to ships with the package.
        skill = (ROOT / 'SKILL.md').read_text(encoding='utf-8')
        for target in re.findall(r'\]\(([^)#:]+)\)|`((?:assets|references|scripts)/[^`\s]+)`', skill):
            path = next(t for t in target if t)
            self.assertIn(path, files, path)
        with tempfile.TemporaryDirectory() as tmp:
            archive = write_zip(Path(tmp) / 'flight-atlas.zip', skill_files())
            names = zipfile.ZipFile(archive).namelist()
            self.assertIn('flight-atlas/SKILL.md', names)
            self.assertTrue(all(n.startswith('flight-atlas/') for n in names))
            installed = copy_to(Path(tmp) / 'skills' / 'flight-atlas', skill_files())
            self.assertTrue((installed / 'scripts' / 'render_report.py').exists())
            with self.assertRaises(SystemExit):
                copy_to(installed, skill_files())


if __name__ == '__main__':
    unittest.main()
