# Findings so far

All figures below came from the prototype scripts run on SEC companyfacts.zip downloaded 2026-11-23. Regenerate before quoting; treat as a check for the build, not as publishable numbers. The prototype was removed from the tree on 2026-11-24 (it is in git history up to commit cbb881f), and the scoring has since been simplified: see the amendment at the top of index-definition.md.

## Whole-market screen (stage 1)

| Step | Companies |
| --- | --- |
| In the SEC file | 20,609 |
| Ever had $500M+ annual revenue and report SBC | 3,802 |
| Still filing (latest fiscal year end on or after 2025-06-30) | 2,106 |
| Latest revenue $1B+ | 1,581 |
| 5+ years of data | 1,490 |
| Revenue up 50%+ over the period | 1,097 |
| Cumulative owner-cash margin under 3% | 340 |
| ...where stock pay is the cause ("stock_pay_treadmill") | 79 |

Types among the 1,097: cash_generative 757; thin_margin_low_stock_pay 143; cash_burner_other 80; stock_pay_treadmill 79; cash_burner_heavy_stock_pay 26; excluded_financial_or_reit 12.

The 79: cumulative FCF $274B, SBC $296B, owner cash -$22B, buybacks $68B, dividends $2B. Amazon is $134B of the SBC. Excluding Amazon: SBC $162B, owner cash -$33B, buybacks $60B. 47 of 79 had a latest-year owner-cash margin of 3% or more; 16 were negative. On the cost test, 19 scored 20+, 40 scored zero, 10 had no usable cost line.

Top screen scores (of 50): Zillow 42.2; HubSpot 33.1; Roku 31.9; Wayfair 29.8; Calix 27.0; Walker & Dunlop 25.8 (a lender, should be excluded); Atlassian 25.7; Cloudflare, Pinterest, Block, Snowflake, Arm 25.0; Amazon 23.9; Trupanion 23.5; Roblox 23.4.

Sanity values to reproduce: Zillow 13 years, cumulative owner-cash margin -7.0%, latest year -6.0%, SBC 15.2% of revenue, cumulative SBC $2,980M, buybacks $2,644M. Salesforce cumulative +15.6%, latest +26.2%, screen score 0.5.

## How the prototype differs from the definition

- Latest fiscal year used in place of latest 12 months.
- Fiscal years ending January-March are assigned to the prior calendar year.
- P2b scaled to 25 points (screen score); P2a not computed (no headcount in the file).
- Missing P2b is scored as zero. The definition says leave unranked. Fix this.
- Financials and REITs excluded by a hand-written name list in classify.py. Replace with SIC codes.
- "Capital-led" flag, founding-age check and biotech exclusion are not implemented.
- History is whatever XBRL holds, roughly 2009 on.
- score.py was patched mid-run (five-year cost window, fourth cost method). classify.py was a separate one-off. Merge into one tested script.
- Capital spending = PaymentsToAcquirePropertyPlantAndEquipment (else PaymentsToAcquireProductiveAssets) + PaymentsToDevelopSoftware. Missing tags are treated as zero and counted in capex_missing_years.
- Revenue = max across Revenues, RevenueFromContractWithCustomerExcludingAssessedTax, ...IncludingAssessedTax, SalesRevenueNet.

## Problems the run exposed

1. Without the stock-pay rule the screen passes 340 companies, mostly distributors, retailers and cash-burners.
2. Measuring the cost ratio over full history gives zero to anything that listed young. Five years is used instead.
3. companyfacts.zip has no industry codes or tickers; submissions.zip is needed.
4. The cost line is missing for about 31% of the 1,097 because of inconsistent tagging.
5. Amazon and Tesla pass the screen; their thin owner cash is mostly capital spending.
6. Dividends are not scored; Equinix ranked second before exclusion.
7. Founding dates are not in the data; some listed companies are under 10 years old.
8. Pass-through revenue (for example Block's bitcoin revenue) distorts revenue-based ratios.

## Earlier 19-company research (hand-gathered, five-year windows)

- Founder grants versus sales: Zillow co-founders were granted options worth about $38M and $33M over 2023-2025 and sold about $30M and $21M in August 2025. At Roblox, Snap and Wayfair founders sold far more than they were granted.
- Board ties at Zillow: Jay Hoag (TCV, investor since 2005) chairs the compensation committee and chairs Netflix's board, where Rich Barton is a director. Bill Gurley (Benchmark) rejoined in 2024. Roblox's CEO's brother sits on its board. Wayfair's lead independent director is from early investor Great Hill.
- Promises versus delivery: no company was found promising cash after stock pay and failing. Targets were stated in adjusted measures and mostly met.
- Legal record: Zillow Offers securities class action settled for $212.5M with no admission. SEC comment letters questioned non-GAAP presentation at Zillow (2019), Wayfair (2021) and Roblox (2023, 2024). An earlier Wayfair suit was dismissed.
- These items were sourced one at a time from web pages and are not verified to publication standard. Re-source each from the filing before use.

## Data access notes

- sec.gov was blocked from the assistant's sandboxes; the owner downloaded companyfacts.zip by hand. A normal terminal should reach it. SEC requires a User-Agent that identifies the requester and a rate under 10 requests a second.
- Bulk URLs: https://www.sec.gov/Archives/edgar/daily-index/xbrl/companyfacts.zip and https://www.sec.gov/Archives/edgar/daily-index/bulkdata/submissions.zip. Insider data sets: https://www.sec.gov/data-research/sec-markets-data/insider-transactions-data-sets
- Extraction of all 20,609 files took about 30 seconds on 4 cores by reading the zip directly.
