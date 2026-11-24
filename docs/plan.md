# Web app plan

Goal: a statically hosted page that shows the Treadmill Index, explains every computation, and traces every figure to its SEC filing.

## Architecture

Build step (Python, run by make or CI):

1. Download SEC bulk files: companyfacts.zip, submissions.zip, quarterly insider-transaction sets. Cache them; never commit them.
2. Extract and score.
3. Write JSON; run checks before publishing.

Data files:

- index.json: one row per company (about 1,100) with inputs, pillar scores, type, flags.
- company/<cik>.json: yearly series, loaded on demand. Every figure carries its accession number and filing date.
- meta.json: build date, source file dates and hashes, funnel counts, every threshold, method version.
- curated/*.json: hand-checked items in git (headcount, earnings-release measures, governance facts, overrides with reasons). Each item has a date and a source.

App: MarkdownUp + BareScript on GitHub Pages. All view state in URL arguments so every sort and company page is a shareable link. The owner wrote BareScript and MarkdownUp; follow his conventions and ask when unsure.

Views: ranked index with filters; company page; methodology; data and limits; group totals; downloads.

## Decisions made

- Score at build time. Ship inputs and thresholds too, so the company page shows the arithmetic and a threshold explorer can recompute client-side.
- Two tiers, visibly separate: screen score (automated, whole market) and full score (top 25, needs curated data).
- Insider trades are automatable. Headcount and earnings-release measures are curated.
- State on every chart that history starts about 2009.

## What each reader needs

Analyst: exact definitions, tickers, sector filter, CSV download, yearly series, control companies, data-quality flags on each row. Owner-cash yield needs a licensed price source; deferred.

Journalist: one plain sentence per company generated from the numbers; group totals as the headline; an as-of date everywhere; glossary; a "what cuts the other way" block per company; corrections contact; change log.

Investigator: every number links to its filing; insider ledger linking each Form 4; governance facts linked to the proxy; archived versioned builds so a cited figure can be reproduced; no statements about intent.

## Risks

- Mislabelled source data: anomaly checks plus a documented overrides file.
- Legal exposure from ranking named companies: careful wording, "not investment advice", fast corrections. Have a lawyer read the methodology page before launch.
- SEC access rules; CI runners are sometimes refused, so cache.
- Curated data going stale.

## Phases

1. Pipeline, screen score, index table, methodology page.
2. Company pages with source links and plain-language summaries.
3. Insider ledger and pillar 3.
4. Curated pillars for the top 25; full score.
5. Versioned archives and the threshold explorer.

## Open decisions for the owner

- Update cadence (quarterly suggested).
- Whether pillar 3 is in the first release.
- Show all 1,100 companies or only the stock-pay group, with the rest downloadable.
- Whether and how to pursue 20-30 years of history (see index-definition.md).
