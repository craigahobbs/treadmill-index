# Treadmill Index

A public index ranking mature US companies on one pattern: years of revenue growth that never becomes meaningful cash for outside owners because it goes out as stock pay, while insiders steadily sell granted shares. The deliverable is a statically hosted web app (MarkdownUp + BareScript) fed by JSON built from SEC data.

This project was planned in an earlier chat session that you cannot see. Everything known is in this folder.

## The goal, in the owner's words (2026-11-24)

Identify companies that persistently keep free cash flow at zero as potentially a means of avoiding rational valuation, which, for those companies, a rational valuation would be far worse due to being propped up by high costs like sales labor, and then cashing out on the irrational valuation by treadmill-granting and selling shares.

The three parts must hold together: owner cash persistently near zero (P1), revenue held up by costs (P2), insiders granted shares and selling them (P3). Test new work against this: does it show whether cash reached owners, and where it went instead. The intent part is the index's stated view about the pattern; see the rules below before attaching it to anything.

## Read first

- docs/index-definition.md: the index, verbatim. Do not change scoring without the owner's agreement.
- docs/findings.md: results of the first whole-market run, how the prototype differs from the definition, known data problems.
- docs/plan.md: app architecture, reader needs, phases, open decisions.
- prototype/: extract.py, score.py, classify.py and their output. Superseded by src/treadmill_index/, which reproduces the prototype's output exactly (`make check-prototype`); kept as the record of the first run.

## Start here

Phases 1 to 3 of docs/plan.md are built, with the threshold explorer and build archive from phase 5. Next is phase 4 (curated pillars and the full score), which waits on the owner: see "Waiting on the owner" below.

## Layout

- src/treadmill_index/: the build step. extract.py reads companyfacts.zip; score.py is the screen, the screen score and P3, with every threshold in THRESHOLDS; sec.py fetches industry codes and tickers; insider.py downloads, reads and summarizes the SEC insider-transaction data sets; output.py writes data/ and runs the pre-publish checks; main.py is the command line.
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

## The three-signs score (added 2026-11-24, on the owner's "proceed as you see fit")

- Three-signs score (75) = P1 + (P1 / 25) x (costs + P3), in the definition's own form. It is the index page's default order; the definition's screen score and its rank stay beside it, unchanged. It is provisional.
- The costs sign (25) is half P2b (scaled to 12.5) and half a level: operating costs excluding cost of revenue as a share of gross profit in the latest year, 0 points at 70% and 12.5 at 100% (score.py `costs_sign`). The level was added because the owner's goal says "propped up by high costs" and P2b only measures change. Basis for the scale: the median is 93% at screened companies and 67% at cash-generative ones. The owner said "finish what's left" after being told this was a scoring change; he has not reviewed the scale.
- The sensitivity test covers both ranks. With insider data the index and data pages report the three-signs top ten.
- Each company page has a "Which way the numbers point" table: what each sign looks like for a growth bet paying off and for a treadmill, with the company's own figures. It states facts and leaves the reading to the reader.
- Group figures on the index page (2021-2025, screened companies without the capital-led): owner cash of -$5.8B against insider sales of $32.8B; insiders sold more than the business produced for owners at 47 of 59 (cash-generative: 18 of 566); of 44 that bought back shares, the share count still rose at 36 (cash-generative: 115 of 475).
- Sales and marketing, R&D and G&A shares of revenue are reported on company pages (not scored) where tagged: 44, 51 and 49 of the 70 screened companies.

## Pillar 3 as built (provisional; not agreed with the owner)

- Source: SEC insider-transaction data sets, Forms 4 and 5, latest five whole calendar years. Amended filings are not used.
- Insiders: officers and directors who file as people. A joint filing with an entity counts only if one of its people is an officer. An outside director's indirect holdings are left out unless the nature of ownership names a trust, family or a retirement account (insider.py `filing_insider`, `_RE_PERSONAL`).
- Grant value departs from the definition. The definition says grant-date value; the SEC financial data gives a usable stock-award fair value for only 7 of the 70 screened companies and an option fair value for 21 of the 39 that grant options to insiders. So every grant is valued at the market price of the shares it covers: a stock award at the nearest price insiders reported within 90 days, an option at its exercise price. This overstates options and performance awards and so understates sales / grants. Tesla's 2025 CEO award alone is about $180B on this basis.
- P3 is shown on company pages as provisional and is not part of any published score. The owner has not reviewed the valuation choice or the fund rules.
- Check on real data: Zillow's co-founder sales of about $30M in August 2025 (docs/findings.md) appear as $29.8M filed 2025-08-18.
- Sales beside buybacks: insider.py `buyback_quarters` splits each company's year-to-date buybacks into quarters, and each insider sale is put in the quarter it fell in. The company page and the group totals page show both. First result, 2021-2025, screened companies without the capital-led: 65% of quarters had a buyback and 64% of insider sales fell in them, so insiders did not sell more heavily while their company was buying. The pages say this shows timing only.

## Rules that matter

- Never call a company's conduct fraud, a scam, or misleading unless a court or regulator has. The index measures how owners were treated, not intent. The evidence gathered did not support fraud; what it supports is a governance and disclosure finding.
- It is not a short list or investment advice. Say so in the app.
- The index page states the owner's view that some companies keep the pattern going on purpose, at shareholders' expense (owner's decision, 2026-11-24, over the assistant's weaker wording). That view is about the pattern. It is never attached to a named company, and a company page never says or implies it.
- Every published figure must trace to an SEC filing (accession number). Compute in code; never estimate; show missing as missing.
- Include what cuts the other way: recent improvement, one-off causes, targets met.
- Keep screen scores and full scores separate.
- Recompute before quoting any number from findings.md.
- Never put the owner's email address, or any real contact address, in a file. SEC requests take their User-Agent from the `SEC_USER_AGENT` environment variable only; there is no default, and a step that needs the SEC fails without it. The owner sets it for the one command.

## Why key choices were made

- P1 gates the other pillars (score = P1 + P1/25 x rest) because steady insider selling and flat costs are common at cash-rich companies too. Salesforce's founder would otherwise max pillar 3.
- "Meaningful" cash means 3% of revenue, not zero, and points scale with size. Hard cut-offs made rankings flip on small changes.
- The cost test uses the latest five years because full history rewards any company that listed young.
- The stock-pay-cause rule exists because the unfiltered screen is dominated by distributors, retailers and cash-burners.
- P3 scores insiders as a group because the largest sellers are often not the founder.
- P4 scores framing (how much of adjusted profit is stock pay added back), because a search for broken promises found targets were mostly met on the companies' own measures.

## Status

- Tested on real data: stage 1 (P1 and P2b) across the market, including SIC exclusions, the capital-led flag, latest-12-month figures and the sensitivity test; and P3 as described above.
- Never run: P2a, P4, founding-age check, predecessor combining, split adjustment, long history. Their point scales, and P3's, are judgment and will need tuning.
- The index and company pages have been checked as static renders (`bare -l` output, screenshot of the HTML file). The live application in MarkdownUp (navigation, the find box) has not been looked at in a browser.

## Waiting on the owner

- A review of pillar 3's grant valuation and fund rules (see "Pillar 3 as built").
- Refreshing the insider-transaction data sets each quarter: the owner runs `SEC_USER_AGENT="..." make insider-data` himself. www.sec.gov refuses these without a User-Agent that gives a contact address. The 23 files for 2021 Q1 to 2026 Q3 are in data/raw/insider/ (git-ignored).
- The open decisions in docs/plan.md.
- Curated data for phase 4 (headcount, earnings-release measures, founding years). Each item needs a date and a source.
- A license, a corrections contact, and a lawyer's read of the methodology page before launch.

## Data

- SEC companyfacts.zip (1.4 GB) was downloaded to ~/Downloads/companyfacts.zip on 2026-11-23; data/raw/companyfacts.zip is a symlink to it. Bulk files are git-ignored.
- Sources and access notes are in docs/findings.md.

## Owner

Craig Hobbs, author of BareScript and MarkdownUp. Not a securities professional; wants the result usable by analysts, journalists and regulators. Prefers plain explanations of what the data implies.
