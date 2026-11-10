# Acceptance checks and synthetic rehearsal

Flight Atlas by M Asif Rahman · [AR.bd](https://AR.bd)
Run `python3 -m unittest discover -s scripts -p 'test_*.py'`. `test_enrich.py` covers the airport table, EU and US DST changes, overnight arrivals, wrong offsets, DST gaps and ambiguous times; `test_trim_email.py` covers link and boilerplate removal. `test_analyze.py` exercises duration arithmetic, cross-date-line schedule conversion, duplicate handling, cancellation/future exclusions, unknown values, evidence modes, partial dates, privacy filtering and aggregate reconciliation. Run the example pipeline with `assets/example-ledger.json`, writing artifacts outside the installed skill. The example is synthetic and must never become a user's report.

For a real report, check:
1. Every included leg belongs to the traveler, has a supported departure date within the requested interval/cutoff, and has not been replaced or cancelled.
2. Each codeshare/reissue chain represents one physical segment; included versions are final, not merely first-found.
3. Known scheduled minutes equal monthly, annual and carrier subtotals. Unknown and estimated minutes are not silently counted. Layover/ground time is excluded.
4. The route chain identifies unresolved transfers; documented ground segments and period boundaries do not become invented flights.
5. Map coordinates and airport labels come from `enrich.py` (bundled table) or are verified manually, with no unresolved enrich warnings. Date-line routes do not cross the whole map spuriously. Airports/countries without location data remain disclosed.
6. All design variants preserve identical values and evidence labels. Cover, charts, table and narrative agree; comparison coverage is fair.
7. Exported files have no private evidence links, ticket/PNR/passport/loyalty fields or raw mail. Inspect supplied title/notes too: the renderer escapes HTML but cannot detect secrets in arbitrary prose.
8. Open desktop and phone layouts and any PDF/cover exports. Check readable typography, contrast, clipping, page breaks and labels. If rendering tools are unavailable, state the exact unverified aspect rather than claiming visual QA.
9. Every trip in the summary starts and ends at a home airport, or carries an open status that `clarify.py` asks about (or a recorded answer explains). Trip flight counts add up to the headline flight count; no leg was added to close a trip without the person's confirmation or a document.

Useful forward-test prompts:
- “Build my 2025 annual report from these synthetic itineraries. I missed the original flight and took a replacement; the airport transfer was by train.”
- “Compare 2024 with 2025 year-to-date. Some return emails are missing.”
- “Make a shareable map cover, but don’t include private booking identifiers.”
- “Here are a ticket and boarding pass for the same codeshare. How many hours did I fly?”

The analyzer intentionally cannot settle uncertain passenger identity, approximate flight dates, conflicting schedule versions or missing evidence. A test passes only when those cases are surfaced, not guessed.
