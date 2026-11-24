# The Treadmill Index: definition

This is the agreed definition, verbatim. Stage 1 has been run on the whole market. Stage 2 (P2a, P3, P4) has never been scored with real data; its point scales are untested judgment.

## What it measures

Mature companies whose revenue growth has not become meaningful cash for outside owners because the cash goes out as stock pay, while insiders steadily turn grants into personal cash. It ranks how owners have been treated. It does not predict share prices and is not a trading recommendation.

## Definitions

- Free cash flow (FCF) = operating cash flow - capital spending (including capitalized software).
- Owner cash = FCF - stock-based compensation (SBC).
- Owner-cash margin = owner cash / revenue.
- Insiders = Section 16 officers and directors, excluding investment funds.
- Sales = open-market sales only, excluding shares withheld for taxes and gifts.

## Data

SEC bulk files: companyfacts.zip (financials) and submissions.zip (industry codes, tickers). Form 4 data sets for insiders. 10-Ks for headcount and founding year. Fourth-quarter 8-K earnings releases. Use annual figures; take the most recently filed value for each year.

## Stage 1: market screen (every company in the bulk file)

Keep a company if all of these hold:

- Still filing; latest annual revenue above $1B; 5+ years of data; revenue up 50%+ over those years.
- Not a bank, insurer, lender, asset manager, REIT or drug developer (by SIC code).
- Cumulative owner-cash margin under 3%.
- Stock pay is the cause: cumulative FCF is zero or positive, SBC is at least 2% of revenue, and SBC is at least half of FCF.

Report the count at each step. List separately, unranked: companies that fail only the last test (thin-margin businesses and those burning cash before stock pay). Flag as "capital-led" any company whose capital spending is more than twice its SBC; its shortfall is mostly investment, not stock pay.

## Scoring (linear between the two points given, capped)

**P1. No meaningful cash for owners (25)**

- Share of years with owner-cash margin under 3%: 0-10
- Cumulative owner-cash margin: 0 pts at +5%, 8 at -10%
- Latest-12-month owner-cash margin (latest fiscal year if quarterly data is unusable): 0 pts at +5%, 7 at -5%

**P2. Revenue that needs headcount (25)**

- a. Real (CPI-adjusted) gross profit per employee, annual growth over full history: 12 pts at 0%, 0 at 6%
- b. Operating expenses excluding cost of revenue, as % of revenue, change over the latest five fiscal years: 13 pts if flat or up, 0 if down 10 points. Build the cost line the same way in both years: gross profit - operating income; else total costs - cost of revenue; else revenue - operating income - cost of revenue.

**P3. Insiders granting and selling (25), latest five calendar years**

- Share of years with both new grants and open-market sales: 0-12
- Total sales / total grant-date value of grants: 0 pts at 0.5x, 13 at 1.5x

**P4. Headline numbers that leave out stock pay (25), latest eight Q4 earnings releases**

- SBC as % of headline adjusted profit, averaged: 0 pts at 0%, 15 at 100% or when adjusted profit is negative
- Share of years in which guidance or stated targets use only measures that exclude SBC: 0-10

## Scores

- Screen score (50) = P1 + (P1/25) x (P2b scaled to 25) [whole market]
- Full score (100) = P1 + (P1/25) x (P2 + P3 + P4) [top 25]

P2-P4 count only to the extent owners are getting no cash. Never rank screen scores against full scores. If P2b cannot be built, show P1 alone and leave the company unranked; do not treat missing as zero.

## Stage 2: full index

For the 25 highest screen scores: confirm founding 10+ years ago, add headcount (P2a), score P3 and P4, and compute the full score. Score three cash-generative peers the same way as a baseline.

## Report alongside (not scored)

- Totals for the screened group: cumulative FCF, SBC, owner cash, buybacks and dividends.
- Valuation: owner-cash yield (owner cash / market cap), EV/sales.
- Dilution: annualized share count change, split by employee equity, acquisitions and convertibles; buyback spend, including cash paid for employees' vesting taxes, against the net change in share count.
- Dividends paid.
- Governance: founders' voting power versus economic stake; directors who are early investors, family, or share other boards with the founder; compensation committee chair.
- Record: SEC comment letters on non-GAAP measures; securities suits that survived dismissal or settled.

## Method

- Compute in code from filings. Do not estimate; mark missing periods.
- Combine predecessor registrants; adjust for splits.
- Where inventory, lending or a discontinued business moved operating cash flow by more than 25% of revenue, show P1 with and without those years.

## Output

1. A data table, one row per company, with every input and its type (stock-pay, thin-margin, cash-burner, cash-generative).
2. The ranked screen, then the ranked full index for the top 25.
3. One page per top-ten company with sources linked, the five largest insider sellers with their grants and sales, and what cuts the other way (recent improvement, one-off causes, targets met).
4. How many screened companies cleared 3% in their latest year.
5. Which top-ten ranks change if any threshold moves by a fifth.

## Rules

Quote management exactly, with date and link. P4 measures framing, which is usually legal and disclosed. Do not call any statement false or fraudulent unless a court or regulator has.

## Proposed addition, not yet adopted: longer history

The owner wants 20-30 years of history. Free SEC structured data starts about 2009.

- Use the longest history available, up to 30 years; require at least 10. Label each year by era.
- 2006 onward: SBC as expensed. 1996-2005: SBC = pro forma option expense from the 10-K footnote. Before 1996: SBC unavailable; score P1 on FCF and report dilution only.
- Compute split-adjusted share count change for every year available. Include companies that were acquired, delisted or went bankrupt.
- Pre-2009 data needs a paid database (Compustat/CRSP via WRDS, Capital IQ) or hand extraction from old 10-Ks for a shortlist.
- Most current top names listed after 2010, so a hard 20-year minimum would remove them. The more useful long-run study is of past cohorts.
