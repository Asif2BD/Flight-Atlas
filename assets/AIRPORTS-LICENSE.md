# Airport reference data

`airports.csv` lists 7918 airports that have a three-letter IATA code: IATA, ICAO, name, city, ISO country, latitude, longitude (5 decimals) and IANA time zone. It is derived from [mwgg/Airports](https://github.com/mwgg/Airports) (`airports.json`, retrieved 2026-11-10), filtered to rows with an IATA code and re-encoded as CSV. Used by `scripts/airports.py` and `scripts/enrich.py`. City names of eleven airports were changed to their usual English names (local-language spellings replaced) so trip questions read naturally.

Airport data changes (new airports, renamed codes, time-zone rule changes). Unknown codes are reported, never guessed. UTC offsets come from the IANA database installed with Python, not from this file.

Original license, reproduced as required:

```text
The MIT License (MIT)

Copyright (c) 2014 mwgg

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

```
