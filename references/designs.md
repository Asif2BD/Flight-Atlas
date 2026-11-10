# Ready-made designs and output choices

Flight Atlas by M Asif Rahman · [AR.bd](https://AR.bd)
## Layout first, color second

Offer Route Atlas (`routes`), Airport Pins (`points`), World Globe (`globe`), and Journey Ribbon (`journey`). These are different graphic encodings, not four palette swaps. Routes uses a projected connection map that draws each airport pair once, thicker when flown more often; points uses airport markers without route lines; globe uses two orthographic views centred on where the airports actually are (the busiest region first, then whatever it hides); journey lists up to eight legs one by one and groups longer histories into at most eight periods (months, quarters or years) with leg counts, busiest airports and the most-flown route. All four stay readable at 100+ flights. The complete report retains the same analytics and audit regardless of cover layout. Pair any layout with any palette below.

All themes use the same reviewed snapshot. Never change counts to fit a design.

- **Atlas** (default): light editorial palette, restrained blue/teal and generous whitespace. Good for a personal annual report.
- **Midnight**: dark navy, luminous route accents and large figures. Good for a presentation or screen-first recap; use a light print variant when needed.
- **Boarding Pass**: warm paper palette and ticket-inspired typography. Good for a souvenir; do not recreate real boarding pass barcodes or sensitive ticket data.
- **Executive**: compact white analytical layout, clear bars and evidence coverage. Good for comparison across years and auditing gaps.

## Standard composition

Cover: period, title, the chosen geographic or chronological graphic, recorded segments and scheduled hours with timed denominator. Avoid a cover crowded with every airport label; prioritize meaningful hubs, give remaining codes in the ledger. Route direction is from origin to destination, not inferred from a curve alone; preserve an origin→destination list.

Analytics: monthly segments and known scheduled hours; airline segments; common directional routes; longest/shortest known-duration flights; airports and airport-country count including transit; annual totals for a multi-year report. If comparative years have different evidence coverage or one is YTD, call that out prominently. No percent-growth headline comparing incomplete to complete years without qualification.

Completeness section: evidence-status counts, known vs unknown durations, gaps, excluded/cancelled/missed/future segments and why. Full private source ledger is separate. Ground connectors may be shown distinctly, never added to airborne counts.

## Geographic truth

Use genuine coastlines and verified airport coordinates. Default bundled Natural Earth geometry is public domain. Compute great-circle connections and split date-line crossings; these are approximate connections, not GPS tracks. Treat airports/transit as “airports reached” or “airport countries,” not countries visited. Missing coordinates reduce mapped route coverage; disclose this count.

## Delivery and QA

The bundled renderer produces offline HTML and SVG covers with four layouts and four independent palettes. Research rationale and source links are in [design-research.md](design-research.md). Use its CSS and assets as design presets for richer requested outputs. Export covers or PDFs through available rendering tooling, inspect visual output at desktop and phone widths, and fix clipped labels/legend collisions. For hosted/interactive report requests, use the host's supported site/report components and preserve the same data definitions. Never upload personal data to a public Site merely for convenience.

Possible next modules: two-year comparison, per-trip spreads, regional map covers, calendar heatmaps, airline/cabin mix, airport visit ranking. Add spend only when a fare can be allocated without double counting refunds and multi-passenger bookings; add emissions only with an explicit methodology and estimate label; add delay analysis only with actual movement data. Unknown values stay unknown.
