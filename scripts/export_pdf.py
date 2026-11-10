#!/usr/bin/env python3
"""Build the full Flight Atlas report as a PDF: cover page, maps, charts, every trip and every flight.

  python3 export_pdf.py summary.json --out flight-report.pdf --theme atlas --layout routes

It renders the full HTML report (cover on its own first page) and prints it with the first
engine it finds: headless Chrome, Chromium or Edge; the WeasyPrint Python package; or
wkhtmltopdf. If none is available it keeps the HTML and says so, so the report can be printed
from any browser (File > Print > Save as PDF). Stdlib only apart from the optional engines.
Always open the PDF and check every page before sending it.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from render_report import render

CHROMES = ('google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser', 'microsoft-edge', 'msedge', 'chrome')
MAC_APPS = ('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
            '/Applications/Chromium.app/Contents/MacOS/Chromium',
            '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge')
WIN_APPS = (r'C:\Program Files\Google\Chrome\Application\chrome.exe',
            r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe')


def find_chrome():
    for name in CHROMES:
        path = shutil.which(name)
        if path:
            return path
    for path in MAC_APPS + WIN_APPS:
        if os.path.exists(path):
            return path
    return None


def with_chrome(binary, html_path, pdf_path):
    command = [binary, '--headless', '--disable-gpu', '--no-sandbox', '--no-pdf-header-footer',
               f'--print-to-pdf={pdf_path}', Path(html_path).resolve().as_uri()]
    result = subprocess.run(command, capture_output=True, text=True, timeout=120)
    return result.returncode == 0 and Path(pdf_path).exists() and Path(pdf_path).stat().st_size > 0


def with_weasyprint(html_path, pdf_path):
    try:
        import weasyprint  # optional
    except ImportError:
        return False
    weasyprint.HTML(filename=str(html_path)).write_pdf(str(pdf_path))
    return Path(pdf_path).exists()


def with_wkhtmltopdf(html_path, pdf_path):
    binary = shutil.which('wkhtmltopdf')
    if not binary:
        return False
    result = subprocess.run([binary, '--enable-local-file-access', '--print-media-type', str(html_path), str(pdf_path)], capture_output=True, text=True, timeout=120)
    return result.returncode == 0 and Path(pdf_path).exists()


def page_count(pdf_path):
    """Page count when it can be read cheaply, else None (compressed PDFs hide it from a byte scan)."""
    try:
        import pypdfium2  # optional
        return len(pypdfium2.PdfDocument(str(pdf_path)))
    except Exception:
        pass
    counts = [int(n) for n in re.findall(rb'/Type\s*/Pages\b[^>]*?/Count\s+(\d+)', Path(pdf_path).read_bytes())]
    return max(counts) if counts else None


def export(summary, pdf_path, theme='atlas', layout='routes', engine='auto', keep_html=None):
    document, _ = render(summary, theme, layout, cover_page=True)
    pdf_path = Path(pdf_path)
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    html_path = Path(keep_html) if keep_html else Path(tempfile.mkdtemp()) / 'flight-report.html'
    html_path.write_text(document, encoding='utf-8')
    attempts = []
    chrome = find_chrome() if engine in ('auto', 'chrome') else None
    if chrome:
        attempts.append(('chrome', lambda: with_chrome(chrome, html_path, pdf_path)))
    if engine in ('auto', 'weasyprint'):
        attempts.append(('weasyprint', lambda: with_weasyprint(html_path, pdf_path)))
    if engine in ('auto', 'wkhtmltopdf'):
        attempts.append(('wkhtmltopdf', lambda: with_wkhtmltopdf(html_path, pdf_path)))
    for name, attempt in attempts:
        try:
            if attempt():
                return name, html_path
        except (OSError, subprocess.SubprocessError):
            continue
    return None, html_path


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('summary', type=Path)
    parser.add_argument('--out', required=True, type=Path, help='PDF to write')
    parser.add_argument('--theme', choices=['atlas', 'midnight', 'boarding-pass', 'executive'], default='atlas')
    parser.add_argument('--layout', choices=['routes', 'points', 'globe', 'journey', 'timeline'], default='routes')
    parser.add_argument('--engine', choices=['auto', 'chrome', 'weasyprint', 'wkhtmltopdf'], default='auto')
    parser.add_argument('--html', type=Path, help='also keep the full HTML here')
    args = parser.parse_args()
    try:
        summary = json.loads(args.summary.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as error:
        sys.exit(f'Could not read summary: {error}')
    html_out = args.html or args.out.with_suffix('.html')
    engine, html_path = export(summary, args.out, args.theme, args.layout, args.engine, html_out)
    if not engine:
        sys.exit(f'No PDF engine found (Chrome, Chromium, Edge, WeasyPrint or wkhtmltopdf). '
                 f'The full report is at {html_path}: open it in a browser and use Print > Save as PDF.')
    print(json.dumps({'pdf': str(args.out), 'pages': page_count(args.out), 'engine': engine, 'html': str(html_path)}))


if __name__ == '__main__':
    main()
