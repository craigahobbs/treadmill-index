# Treadmill Index

A public index ranking mature US companies on one pattern: years of revenue growth that never becomes meaningful cash for outside owners because it goes out as stock pay, while insiders steadily sell granted shares. The deliverable is a statically hosted web app (MarkdownUp + BareScript) fed by JSON built from SEC data.

This project was planned in an earlier chat session that you cannot see. Everything known is in this folder.

## Read first

- docs/index-definition.md: the index, verbatim. Do not change scoring without the owner's agreement.
- docs/findings.md: results of the first whole-market run, how the prototype differs from the definition, known data problems.
- docs/plan.md: app architecture, reader needs, phases, open decisions.
- prototype/: extract.py, score.py, classify.py and their output. Superseded by src/treadmill_index/, which reproduces the prototype's output exactly (`make check-prototype`); kept as the record of the first run.

## Start here

Phases 1 and 2 of docs/plan.md are built, with the threshold explorer and build archive from phase 5. Next is phase 3 (insider ledger and pillar 3), then phase 4 (curated pillars and the full score). Both wait on the owner: see "Waiting on the owner" below.

## Layout

- src/treadmill_index/: the build step. extract.py reads companyfacts.zip; score.py is the screen and the screen score, with every threshold in THRESHOLDS; sec.py fetches industry codes and tickers; output.py writes data/ and runs the pre-publish checks; main.py is the command line.
- data/: the published data files (index.json, index.csv, meta.json, company/<CIK>.json, archive/). data/raw/ holds the SEC bulk file and caches and is git-ignored.
- treadmillIndex.bare, treadmillIndex.md, index.html: the MarkdownUp application. All view state is in URL arguments.
- test/: the application's unit tests. test/data/ is made by `make test-data` from the made-up companies in test/makeTestData.py; test/testTreadmillIndexPages.bare holds the expected render of every page state.

## python-build

This is a [python-build](https://github.com/craigahobbs/python-build#readme) `Makefile.base` package. Read the python-build skill before running tests, lint, or changing the Makefile: [`../python-build/SKILL.md`](../python-build/SKILL.md) if that file exists, otherwise [https://raw.githubusercontent.com/craigahobbs/python-build/main/SKILL.md](https://raw.githubusercontent.com/craigahobbs/python-build/main/SKILL.md). When writing or modifying `.bare` files, invoke the `bare-script` skill.

Local Makefile:

- `TESTS_REQUIRE` - `bare-script` (provides the `bare` CLI)
- `test` and `lint` also run `test-app` (`bare -d -m test/runTests.bare`; `TEST_APP=` is an exact BareScript test name) and `lint-app`. The application's suite fails under 100% coverage, like `make cover` for the Python.
- `data` - build data/ from data/raw/companyfacts.zip. Python runs with `-I` because it reads downloaded files.
- `test-data` - remake test/data/. Run it after any change to the content of the data files, then update the expected renders.
- `check-prototype` - reproduce prototype/treadmill_market_screen.csv. Holds only against the companyfacts.zip of 2026-11-23.

## How the build differs from the prototype

- Latest 12 months are computed (fiscal year + year-to-date - prior year-to-date, one tag for all three periods); the latest fiscal year is the fallback and is flagged.
- A missing cost line leaves the company unranked with P1 alone. The cost line uses the definition's three methods only; the prototype's fourth (the OperatingExpenses tag) is used only by `PROTOTYPE_OPTIONS`.
- Industries are excluded by SIC code (score.py SIC_EXCLUSIONS). Securities brokers (62xx) are excluded with asset managers because they hold customer money. Insurance agents and brokers (6411) are not excluded: they are not insurers. The owner left both calls to the assistant on 2026-11-24.
- Averaging the cost change over four-, five- and six-year windows was tested on 2026-11-24 and did not steady the top ten (names replaced across the 24 threshold moves: 18 with one window, 17 averaged), so P2b is unchanged. Ranks 3 to 14 sit within about four points; the index page says to read ranks as rough positions.
- Excluded industries have inputs but no scores in the data files.
- Capital-led flag, one-off-year P1, sensitivity test, group totals and pre-publish checks are implemented.
- "Still filing" is the latest fiscal year ending within 548 days of the latest filing date in the data, not a fixed date.

## Rules that matter

- Never call a company's conduct fraud, a scam, or misleading unless a court or regulator has. The index measures how owners were treated, not intent. The evidence gathered did not support fraud; what it supports is a governance and disclosure finding.
- It is not a short list or investment advice. Say so in the app.
- The index page states the owner's view that some companies keep the pattern going on purpose, at shareholders' expense (owner's decision, 2026-11-24, over the assistant's weaker wording). That view is about the pattern. It is never attached to a named company, and a company page never says or implies it.
- Every published figure must trace to an SEC filing (accession number). Compute in code; never estimate; show missing as missing.
- Include what cuts the other way: recent improvement, one-off causes, targets met.
- Keep screen scores and full scores separate.
- Recompute before quoting any number from findings.md.

## Why key choices were made

- P1 gates the other pillars (score = P1 + P1/25 x rest) because steady insider selling and flat costs are common at cash-rich companies too. Salesforce's founder would otherwise max pillar 3.
- "Meaningful" cash means 3% of revenue, not zero, and points scale with size. Hard cut-offs made rankings flip on small changes.
- The cost test uses the latest five years because full history rewards any company that listed young.
- The stock-pay-cause rule exists because the unfiltered screen is dominated by distributors, retailers and cash-burners.
- P3 scores insiders as a group because the largest sellers are often not the founder.
- P4 scores framing (how much of adjusted profit is stock pay added back), because a search for broken promises found targets were mostly met on the companies' own measures.

## Status

- Tested on real data: stage 1 (P1 and P2b) across the market, including SIC exclusions, the capital-led flag, latest-12-month figures and the sensitivity test.
- Never run: P2a, P3, P4, founding-age check, predecessor combining, split adjustment, long history. Their point scales are judgment and will need tuning.
- The index and company pages have been checked as static renders (`bare -l` output, screenshot of the HTML file). The live application in MarkdownUp (navigation, the find box) has not been looked at in a browser.

## Waiting on the owner

- A User-Agent with a contact address for SEC requests (`SEC_USER_AGENT`). www.sec.gov refuses bulk files, filing indexes and the insider-transaction data sets without one; data.sec.gov accepts a generic client name. Phase 3 cannot start without it.
- The open decisions in docs/plan.md.
- Curated data for phase 4 (headcount, earnings-release measures, founding years). Each item needs a date and a source.
- A license, a corrections contact, and a lawyer's read of the methodology page before launch.

## Data

- SEC companyfacts.zip (1.4 GB) was downloaded to ~/Downloads/companyfacts.zip on 2026-11-23; data/raw/companyfacts.zip is a symlink to it. Bulk files are git-ignored.
- Sources and access notes are in docs/findings.md.

## Owner

Craig Hobbs, author of BareScript and MarkdownUp. Not a securities professional; wants the result usable by analysts, journalists and regulators. Prefers plain explanations of what the data implies.
