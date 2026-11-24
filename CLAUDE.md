# Treadmill Index

A public index ranking mature US companies on one pattern: years of revenue growth that never becomes meaningful cash for outside owners because it goes out as stock pay, while insiders steadily sell granted shares. The deliverable is a statically hosted web app (MarkdownUp + BareScript) fed by JSON built from SEC data.

This project was planned in an earlier chat session that you cannot see. Everything known is in this folder.

## The goal, in the owner's words (2026-11-24)

Identify companies that persistently keep free cash flow at zero as potentially a means of avoiding rational valuation, which, for those companies, a rational valuation would be far worse due to being propped up by high costs like sales labor, and then cashing out on the irrational valuation by treadmill-granting and selling shares.

The three parts must hold together: owner cash persistently near zero (P1), revenue held up by costs (P2), insiders granted shares and selling them (P3). Test new work against this: does it show whether cash reached owners, and where it went instead. The intent part is the index's stated view about the pattern; see the rules below before attaching it to anything.

## Read first

- docs/index-definition.md: the index. The amendment of 2026-11-24 at the top is what is built; the original definition is kept below it. Do not change scoring without the owner's agreement.
- docs/findings.md: results of the first whole-market run with the prototype, and known data problems. The prototype is no longer in the tree (git history up to cbb881f).
- docs/plan.md: the original app architecture, reader needs and phases, with a status note.

## Start here

The index is built: one score on three signs, five pages (index, company, group totals, methodology, data and limits). The owner asked on 2026-11-24 for fewer, simpler measures and no work that would not be insightful; hold new work to that. What remains needs the owner: see "Waiting on the owner" below.

## Layout

- src/treadmill_index/: the build step. extract.py reads companyfacts.zip; score.py is the screen and the score, with every threshold in THRESHOLDS; sec.py fetches industry codes and tickers; insider.py downloads, reads and summarizes the SEC insider-transaction data sets; output.py writes data/ and runs the pre-publish checks; main.py is the command line.
- data/: the published data files (index.json, index.csv, meta.json, company/<CIK>.json, archive/). data/raw/ holds the SEC bulk file and caches and is git-ignored.
- treadmillIndex.bare, treadmillIndex.md, index.html: the MarkdownUp application. All view state is in URL arguments. Headings, page titles and menu entries are title case, as in the owner's other projects.
- test/: the application's unit tests. test/data/ is made by `make test-data` from the made-up companies in test/makeTestData.py; test/testTreadmillIndexPages.bare holds the expected render of every page state. It is generated: capture each page's render log and write it out as the expected value, then read the result before trusting it.

## python-build

This is a [python-build](https://github.com/craigahobbs/python-build#readme) `Makefile.base` package. Read the python-build skill before running tests, lint, or changing the Makefile: [`../python-build/SKILL.md`](../python-build/SKILL.md) if that file exists, otherwise [https://raw.githubusercontent.com/craigahobbs/python-build/main/SKILL.md](https://raw.githubusercontent.com/craigahobbs/python-build/main/SKILL.md). When writing or modifying `.bare` files, invoke the `bare-script` skill.

Local Makefile:

- `TESTS_REQUIRE` - `bare-script` (provides the `bare` CLI)
- `test` and `lint` also run `test-app` (`bare -d -m test/runTests.bare`; `TEST_APP=` is an exact BareScript test name) and `lint-app`. The application's suite fails under 100% coverage, like `make cover` for the Python.
- `data` - build data/ from data/raw/companyfacts.zip. Python runs with `-I` because it reads downloaded files.
- `test-data` - remake test/data/. Run it after any change to the content of the data files, then update the expected renders.

## The score as built (owner approved the plan on 2026-11-24: "Proceed")

- Score (75) = P1 + (P1 / 25) x (costs + insiders). One score, one rank. Ranked = passes the screen and has all three signs.
- P1 (25), owner cash that stays near zero: as in the original definition. Latest 12 months are computed (fiscal year + year-to-date - prior year-to-date, one tag for all three periods); the latest fiscal year is the fallback and is flagged.
- Costs (25): operating costs excluding cost of revenue as a share of gross profit in the latest fiscal year, 0 points at 70% and 25 at 100% (score.py `costs_sign`). The cost line uses the definition's three methods. A missing cost line means no score.
- Insiders (25): net cash officers and directors took out through stock over the latest five whole calendar years (open-market sales + shares withheld for taxes + shares sold to the company - open-market purchases), as a share of revenue in the fiscal years with the same labels, 0 points at 0.5% and 25 at 3% (score.py `insiders_sign`, insider.py `insider_summary`). No insider filings means no score.
- The owner approved the plan and the measures. He has not reviewed the 70%/100% and 0.5%/3% scales number by number.
- Capital-led companies (capital spending more than twice stock pay) are their own unranked type, `capital_led`, not a flag on ranked companies.
- Reported, not scored: the five-year change in the cost ratio; sales and marketing, R&D and G&A shares of revenue where tagged; the value of grants (stock at the nearest price insiders reported within 90 days, options at exercise price, which overstates them); insider sales beside the company's buybacks by quarter (one group line on the totals page).
- Industries are excluded by SIC code (score.py SIC_EXCLUSIONS). Securities brokers (62xx) are excluded with asset managers because they hold customer money. Insurance agents and brokers (6411) are not excluded: they are not insurers. The owner left both calls to the assistant on 2026-11-24. Excluded industries have inputs but no scores in the data files.
- "Still filing" is the latest fiscal year ending within 548 days of the latest filing date in the data, not a fixed date.
- Insiders are officers and directors who file as people. A joint filing with an entity counts only if one of its people is an officer. An outside director's indirect holdings are left out unless the nature of ownership names a trust, family or a retirement account (insider.py `filing_insider`, `_RE_PERSONAL`). Forms 4 and 5; amended filings are not used.

## Why the measures were simplified (data of 2026-11-20, screened against cash-generative companies)

- P2b (cost ratio flat or rising over five years) pointed the wrong way: 28% against 57%. Averaging its window did not steady ranks either. Dropped from the score.
- Costs as a share of gross profit separate the groups: median 93.6% against 67.0%.
- "Years with both grants and sales" had no signal: 77% against 73%. Dropped.
- "Sold more than they were granted" was partly an artifact: insiders settle vesting taxes either by selling on the market or by having shares withheld, and counting only market sales made the first kind look like heavier sellers. Counting both is why cash-out includes shares withheld. Grant fair values are also unavailable for most companies.
- Insider cash-out as a share of revenue separates the groups: median 2.9% against 0.4%; at or above 3% at 49% against 6%.
- Insider sales are not concentrated in buyback quarters (65% of quarters had a buyback, 64% of sales fell in them). The pages say this shows timing only.
- Dropped as not worth the work: headcount (P2a), earnings-release measures (P4), the full score and stage 2, curated data, the threshold explorer, the separate downloads page.

## Current results (recompute before quoting)

- Funnel: 20,609 in the file; 1,097 pass the basic tests; 902 after industries; 301 under the line; 70 with stock pay as the cause; 64 after the capital-led; 50 ranked.
- Top ten: Cloudflare, Snowflake, Procore, Hims & Hers, MongoDB, Zscaler, Axon, Zillow, Klaviyo, Unity. Moving one threshold by a fifth changes the top ten in 16 of 30 tests; only two other names (Five9, Inspire Medical) ever enter.
- 2021-2025, the 59 screened companies with insider filings: insiders took out $34.6B, 4.0% of revenue; owners got -$5.8B, -0.7%. Cash-generative (566): 0.5% and 12.3%. Insiders took out more than the owner cash at 47 of 59 against 19 of 566.
- Of 44 screened companies that bought back shares, the share count still rose at 36 (cash-generative: 115 of 475).
- What cuts the other way: 45 of the 64 had owner cash of 3% of revenue or more in their latest 12 months.
- Check on real data: Zillow's co-founder sales of about $30M in August 2025 (docs/findings.md) appear as $29.8M filed 2025-08-18.
- Known distortion: insider years are calendar years and revenue is by fiscal-year label, so the two can be up to eight months apart. Credo Technology's 78.6% is overstated by this; it does not change its points. The data page states the limit.

## Rules that matter

- Never call a company's conduct fraud, a scam, or misleading unless a court or regulator has. The index measures how owners were treated, not intent. The evidence gathered did not support fraud; what it supports is a governance and disclosure finding.
- It is not a short list or investment advice. Say so in the app.
- The index page states the owner's view that some companies keep the pattern going on purpose, at shareholders' expense (owner's decision, 2026-11-24, over the assistant's weaker wording). That view is about the pattern. It is never attached to a named company, and a company page never says or implies it.
- Every published figure must trace to an SEC filing (accession number). Compute in code; never estimate; show missing as missing.
- Include what cuts the other way: recent improvement, one-off causes, targets met.
- Recompute before quoting any number from findings.md.
- Never put the owner's email address, or any real contact address, in a file. SEC requests take their User-Agent from the `SEC_USER_AGENT` environment variable only; there is no default, and a step that needs the SEC fails without it. The owner sets it for the one command.

## Why key choices were made

- P1 gates the other signs (score = P1 + P1/25 x rest) because steady insider selling and high costs are common at cash-rich companies too. Salesforce's founder would otherwise max the insiders sign.
- "Meaningful" cash means 3% of revenue, not zero, and points scale with size. Hard cut-offs made rankings flip on small changes.
- The top of the insiders scale is the same 3% of revenue: insiders taking out what would count as meaningful cash had it gone to owners.
- The stock-pay-cause rule exists because the unfiltered screen is dominated by distributors, retailers and cash-burners.
- Insiders are scored as a group because the largest sellers are often not the founder.

## Status

- Tested on real data: the whole build, on companyfacts.zip with a latest filing of 2026-11-20 and the insider data sets for 2021 Q1 to 2026 Q3.
- Never done: founding-age check, predecessor combining, split adjustment, history before 2009.
- The pages have been checked as static renders (`bare -l` output, screenshot of the HTML file). The live application in MarkdownUp (navigation, the find box) has not been looked at in a browser.

## Waiting on the owner

- Refreshing the insider-transaction data sets each quarter: the owner runs `SEC_USER_AGENT="..." make insider-data` himself. www.sec.gov refuses these without a User-Agent that gives a contact address. The 23 files for 2021 Q1 to 2026 Q3 are in data/raw/insider/ (git-ignored).
- Publishing: the GitHub repository and Pages. The data page's corrections link points at github.com/craigahobbs/treadmill-index, which does not exist yet.
- A license, and a lawyer's read of the index page's headline paragraph and the methodology page before launch.
- Update cadence (quarterly suggested).

## Data

- SEC companyfacts.zip (1.4 GB) was downloaded to ~/Downloads/companyfacts.zip on 2026-11-23; data/raw/companyfacts.zip is a symlink to it. Bulk files are git-ignored.
- Sources and access notes are in docs/findings.md.

## Owner

Craig Hobbs, author of BareScript and MarkdownUp. Not a securities professional; wants the result usable by analysts, journalists and regulators. Prefers plain explanations of what the data implies.
