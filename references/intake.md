# Opening the conversation

Flight Atlas by M Asif Rahman · [AR.bd](https://AR.bd)

The first message decides whether the report is built from email or from what the person tells you. Never stall waiting for a connection, and never ask more than one round of setup questions.

## 1. Check for email first

Look at the tools actually available (mail search/read connectors, for example Gmail or Outlook). Do not ask the person whether email is connected when the tool list already shows it.

- **Connected:** say which mailbox(es) you will read, then go to the report and design choice in SKILL.md. Skip this file's section 2.
- **Not connected:** send one message that does both things below, so the person can either connect or carry on without connecting.

## 2. Not connected: ask to connect, and ask the questions in the same message

Lead with the connect request, in one or two sentences: Flight Atlas builds the most complete report by reading flight confirmations from their email, so ask them to connect their mailbox through the assistant's usual connector or settings flow (name the flow only if the host offers one; never ask for a password, app password or forwarding). Then, without waiting, ask the three questions. Example wording, adapted to the person's language and what they already said:

> Flight Atlas works best with your email connected, so it can find your flight confirmations automatically. You can connect it in your assistant's connectors and I'll pick it up from there.
>
> Or we can start right now without email:
> 1. **Timeframe:** which year, trip or date range? (For example "2025", "this year so far", or "Japan, 4–18 June".)
> 2. **Design:** Route Atlas, Airport Pins, World Globe or Journey Ribbon, in Atlas, Midnight, Boarding Pass or Executive colours? Say "you choose" for Route Atlas in Atlas colours.
> 3. **Gaps:** were there stretches in that period when you didn't fly, or trips you know happened that you'd like to make sure are included? Rough dates are fine.
> 4. **Home and format:** which airport is home (more than one is fine), and would you like just the cover image or the full PDF report with every trip?

If the person already gave any of these, do not ask again; ask only for what is missing. If they say "you choose", use the defaults in SKILL.md.

## 3. Building without email

When they reply without connecting:

- Ask them to list their flights in any form they like (pasted itineraries, a spreadsheet, exported `.eml` files, or plain lines such as "3 Mar LIS–ORD ZZ401 09:40–12:55"). Run `scripts/trim_email.py` on any exported email files.
- Record each flight they state as `status: user_confirmed` with `evidence_ids` such as `["user-statement-1"]` (opaque, no personal data). Put printed times in `departure_local`/`arrival_local` and run `scripts/enrich.py`; if they gave no times, leave durations unknown rather than estimating.
- Use their gap answer as a checklist, not as flights: a stretch they say had no flying is recorded in `report.coverage_note`; a trip they say happened but gave no details for becomes a `manual_gaps` entry (`kind: missing_flight` or `date_unknown`) and a short follow-up question, never an invented leg.
- Say in the report's coverage note that it was built from the person's own account, not from email.

## 4. Gaps question when email is connected

With email, reconstruct first, then run `scripts/clarify.py summary.json` and send its message: it names each open trip by the exact flight found (an outbound with no return, a return with no outbound, a landing at one airport and a departure from another) and lets the person answer with a word or by sending the ticket, boarding pass or a screenshot. Mention also any long silent periods and flights that might be booked elsewhere (another inbox, a company travel desk, someone else's booking). Ask once per round, after searches are exhausted; SKILL.md ("Ask about what's missing") says how each answer goes into the ledger.
