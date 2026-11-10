# Email reconstruction and continuity

Flight Atlas by M Asif Rahman · [AR.bd](https://AR.bd)
## Search plan

Record accounts searched, queries, accessible date ranges, attachment failures and cutoff. Discover the actual connector rather than hard-coding a tool name. Search recipient-owned inbox and sent mail where useful; don't send messages or change mail state.

Start with combinations such as `itinerary`, `e-ticket`, `eticket`, `flight confirmation`, `boarding pass`, `check-in`, `ticket receipt`, `schedule change`, `rebook`, `cancellation`, `refund`, `miles credited`, plus the requested year and airline names found. Include localized equivalents from the person's mail. Gmail-style date filters apply to message arrival, not travel date: use a broad window, then search the year as text and travel-chain identifiers. Handle pagination. Do not present results from a capped search as exhaustive.

## Read cheaply

Travel mail is mostly noise: a broad `itinerary OR e-ticket` search returns deal newsletters first, and one airline confirmation rendered as text can run to 15–20k tokens because of tracking links. A frequent flyer's year read naively will not fit in context. Work in three passes.

1. **Find, don't open.** Exclude marketing (Gmail: `-category:promotions -category:social`; elsewhere skip senders with deal/offer subjects). Query transactional senders first, then subjects: the large airlines and booking sites (for example `from:(emirates.email OR qatarairways OR trip.com OR expedia OR booking.com)`; regional carriers and agencies send from their own domains, so add the ones the person uses), and `subject:(itinerary OR e-ticket OR "ticket receipt" OR "boarding pass" OR "schedule change" OR cancel OR refund)`. Bare `ticket`, `check in` and place names pull in support desks, meetings and newsletters; pair them with a sender or a transactional term. Some airlines write subjects in another language (US-Bangla boarding passes say "carte d'embarquement"). Ask the search tool for the lightest view it offers (subjects, senders, dates, snippets; Gmail's summary view) and save each page to a file when the host allows. Page through results; note when a cap was hit.
2. **Index bookings from metadata.** Run `scripts/mail_index.py --traveler "First Last" page1.json page2.json …` on saved search pages: it prints one line per message, oldest first, with its kind (booking, change, cancel, checkin, boarding, loyalty, ground, hotel, noise), any route or date the subject gives, and `other:<name>` when the preview greets a different passenger (bookings made for family or colleagues). Many subjects already carry the booking reference, destination and date ("Check in online for your flight to Lisbon on 3 March"). Build a private index keyed by booking reference and traveler: every message ID, its date, and what kind it is (new booking, reissue/upgrade, change, cancellation/refund, check-in, boarding pass, loyalty credit). Check-in, boarding-pass and loyalty-credit messages are status evidence; record them from subject and snippet without opening.
3. **Open narrowly.** Per booking, open only the latest confirmation or itinerary and every change/cancellation/refund notice, newest first, in the lightest text format available (plain text, never HTML). Prefer the small mails that carry the same facts: check-in reminders, refund or contact-form echoes and airline 24-hour reminders often print route, date and passengers in a few kilobytes, while one online-agency confirmation or airline booking mail can be 20–40k tokens of tracking links. A keyword probe (sender + date + an airport code or passenger name, ids-only view) answers "which route?" or "whose booking?" without opening anything. If the host saves message bodies or exports to files, run `scripts/trim_email.py` on them and read the trimmed lines. When the plain-text body is a stub of a few lines (AirAsia does this), the itinerary is only in the HTML: save it and run `trim_email.py` on the file. Open an attachment only when the body lacks segment times. Stop reading a message once its segments are captured.

For periods with more than ~15 bookings, hand each booking, or each quarter or half-year, to a sub-agent that returns only ledger rows, doubts and an evidence note, so raw email never enters the main context. Give each the traveler's names as printed on tickets and tell it to list other passengers' bookings separately instead of making rows. Overlap the received-date windows by a few months so cross-boundary trips are seen, then combine the parts with `scripts/merge_ledgers.py part1.json part2.json … --out draft.json`: it merges a flight that two parts both found (same date, route and operating flight), keeps every evidence id and the strongest status, and lists conflicts for review. Keep a running count of messages opened and say in the coverage note which kinds were not opened.

Places mail hides flights:
- **Travel agents** often paste the itinerary as reservation-system lines (`ZZ 512 U 14FEB LHRJFK HK3 0925 1340`) into an ordinary email, sometimes to a relative with the traveler in copy. Airline and booking-site sender filters never see these: search for the traveler's name with `HK1`…`HK9` or a city pair such as `LHRJFK`. `trim_email.py` spells such lines out; `HK3` means three seats, so the booking covers other people too.
- **Forwards** in sent mail can be the only copy of a ticket: search `in:sent` for `Fwd:` with airline names.
- **Same subject, new ticket:** reissues often reuse the original subject (an "Electronic ticket receipt" that names only the first date and city; a string of "changes confirmed" mails under one booking reference). Open each version newest first and mark the older segments `superseded`.
- **Holds are not tickets:** some carriers send an unpaid "booking confirmation" before the "confirmation of issuance"; only the issued ticket counts.
- **Hotels, rentals and rides** are not flights, but their dates and cities form a location timeline: a hotel in a city with no flight there is a reason to search again or ask. Arrival cards, airport taxi or ride receipts ("pick-up: Terminal 1 Arrivals"), card payments in the traveler's own name and "new sign-in near <city>" alerts place them too. Search bus, train and car brands by their sender domain (FlixBus, BlaBlaCar, car-sharing and car-rental firms); the brand word alone pulls in newsletters. None of this is a flight: when it narrows a gap, put it in a `hint` so the question can say what you found, and let the person confirm the flight.
- **Outages:** bookings made during a country's internet shutdown or a card blocked abroad may leave no mail at all; ask rather than search forever.

Read attachments when the message only contains a summary. Search long before the period for advance bookings and after it for refunds/loyalty postings. Adjacent-year legs are context only unless their departure dates fall in scope. Keep multiple travelers separate. Resolve aliases against account/user evidence rather than assuming every itinerary in a mailbox belongs to its owner.

## Evidence ladder

- `flown`: completed-travel evidence such as a matched flown coupon, flight-specific post-travel loyalty credit, or equivalent completion record; retain its source.
- `user_confirmed`: the person explicitly says this physical segment was taken.
- `strongly_supported`: several consistent dated artifacts support travel, but no direct boarding/completion record exists.
- `itinerary_only`: historical ticket/itinerary, no cancellation found; do not silently call it confirmed travel.
- `planned`: future or explicitly not-yet-taken.
- `cancelled`, `missed`, `superseded`, `other_traveler`, `unresolved`: exclude from completed/reconstructed headline totals.

Documents the person uploads (e-tickets, boarding passes, booking screenshots, photos of paper tickets) are graded exactly like emails; read them closely, confirm the passenger name matches, and do not guess unreadable digits. If the person also says they took the flight, it is `user_confirmed`. Boarding passes/check-in imply preparation, not certain boarding. A generic refund can be a fare adjustment, not cancellation. Resolve which segment changed. A loyalty posting date can be weeks after flight date; do not use it as departure date. Keep uncertainty when the evidence cannot resolve it.

Default `reconstructed` includes flown/user_confirmed/strongly_supported/itinerary_only and displays their separate counts. Use `confirmed` mode when requested, including only flown/user_confirmed. Explain the choice. Never give a precise “hours flown” label to a total based on schedules and unverified itineraries.

## Deduplication and schedule changes

One physical segment per traveler, local departure date, origin/destination and operating flight. Marketing flight numbers are aliases. A codeshare copy must not create a second segment. Missing operating numbers need review: do not merge merely because two airports match on a date. Shared booking references can cover several people and legs; different references can describe one reissue.

Use stable internal leg IDs. Resolve versions with `supersedes_id`; keep cancelled/missed originals excluded. An explicit `duplicate_of` links a reviewed copy. The analyzer detects duplicate IDs and excludes probable exact duplicates (same traveler, date, route and operating flight). Same date and route with a missing or different operating flight, and no departure times at least an hour apart, is flagged as a possible codeshare and still counted (`possible_duplicate_count`): resolve each one with `duplicate_of` or the operating flight number before delivering. It does not guess which copy is real.

## Scheduled duration

Prefer the final ticket's advertised segment duration for that flight/date. Otherwise subtract scheduled departure from scheduled arrival in UTC, converting full local dates through the airports' IANA time zones, including DST. Do this with `scripts/enrich.py` from the printed local times (`departure_local`, `arrival_local`); it uses the bundled airport table and refuses DST gaps and ambiguous fall-back clocks instead of guessing. Record the advertised value and calculated value if both exist, investigate disagreement, and explain any chosen resolution. Never subtract wall clocks across zones. Do not guess the arrival day from the clock alone. If a local clock is ambiguous during DST fall-back, obtain an offset or flag unknown.

Current route marketing durations are not historical proof. A carrier source for the exact service/date is next best; a different date or seasonal schedule is an explicitly estimated supplement and excluded from the verified scheduled subtotal. Never blend actual airborne, gate-to-gate and advertised durations into one unlabelled measure. Layovers are not flight hours.

## Closing the chain

Compare each included destination with the next included origin. Same airport closes that link. Known ground transfer with matching endpoints/timing closes it without adding a flight. A mismatched airport, even within the same metro, is a transfer needing context, not necessarily a missing flight. Search adjacent itineraries, trains, rental cars and explicit user corrections. Do not assume home-base return; multi-city/open-jaw travel can be real. The first/last leg of a year may be part of a trip spanning years. Leave them as boundaries, not automatic missing flights.

When a gap persists, state: previous confirmed place/date; next confirmed place/date; candidate transfer only if evidence supports it; searches tried; what specific record would resolve it; whether excluded from totals. Offer the minimum useful question. Unknown geographic transfers and unknown durations are different gaps.

## Privacy and reproducibility

Private ledger: source message IDs/links, limited supporting snippets, calculations and corrections. Public/shareable report: no booking/PNR/ticket numbers, QR/barcodes, addresses, loyalty numbers, passports, private mailbox links, or raw emails. Dates/routes can themselves be private; don't publish without permission. Keep credentials out of files. The skill ships only generic code and synthetic examples; each person supplies their own authorized data.
