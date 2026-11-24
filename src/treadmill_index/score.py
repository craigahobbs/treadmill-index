# Licensed under the MIT License
# https://github.com/craigahobbs/treadmill-index/blob/main/LICENSE

"""
The market screen and the three signs of the index, as set out in docs/index-definition.md
"""

import datetime

from .extract import F_ACCN, F_START, F_TAG, F_VAL, fact_order, parse_date
from .insider import AMOUNTS


# The method version - bump when a scoring rule, threshold or source tag changes
METHOD_VERSION = '1.2.0'


# Each of the three signs is scored out of this many points
SIGN_POINTS = 25


# Every threshold of the index
THRESHOLDS = {
    # The screen
    'still_filing_days': 548,       # the latest fiscal year ended within this many days of the data date
    'revenue_min': 1e9,             # latest annual revenue
    'years_min': 5,                 # years of data
    'growth_min': 0.5,              # revenue growth over those years
    'meaningful_margin': 0.03,      # owner cash under this share of revenue is not "meaningful"
    'sbc_revenue_min': 0.02,        # stock pay is the cause: SBC is at least this share of revenue ...
    'sbc_fcf_min': 0.5,             # ... and at least this share of free cash flow
    'capital_led_ratio': 2.0,       # capital spending above this multiple of SBC is "capital-led": listed, not ranked
    'one_off_ocf_share': 0.25,      # inventory, lending or discontinued operations moved cash by this share of revenue

    # Sign 1, owner cash that stays near zero (P1): three parts
    'p1_years_points': 10,
    'p1_cum_points': 8,
    'p1_cum_zero': 0.05,
    'p1_cum_full': -0.10,
    'p1_latest_points': 7,
    'p1_latest_zero': 0.05,
    'p1_latest_full': -0.05,

    # Sign 2, revenue held up by costs: operating costs as a share of gross profit in the latest fiscal year
    'cost_level_zero': 0.7,
    'cost_level_full': 1.0,
    'cost_window_years': 5,         # the cost ratio's change over these years is reported, not scored

    # Sign 3, insiders cashing out: the cash insiders took out through stock, as a share of revenue
    'insider_years': 5,             # the latest whole calendar years
    'insider_zero': 0.005,
    'insider_full': 0.03,
    'grant_price_days': 90          # a stock award is valued, for display, at a reported share price within this many days
}

# The thresholds the sensitivity test moves by a fifth
SENSITIVITY_KEYS = (
    'revenue_min', 'years_min', 'growth_min', 'meaningful_margin', 'sbc_revenue_min', 'sbc_fcf_min', 'capital_led_ratio',
    'p1_cum_zero', 'p1_cum_full', 'p1_latest_zero', 'p1_latest_full', 'cost_level_zero', 'cost_level_full',
    'insider_zero', 'insider_full'
)
INTEGER_THRESHOLDS = ('years_min',)


# The industries the definition leaves out, by SIC code: (first code, last code, group)
SIC_EXCLUSIONS = (
    (2834, 2834, 'drug developer'),
    (2836, 2836, 'drug developer'),
    (6000, 6099, 'bank'),
    (6100, 6199, 'lender'),
    (6200, 6289, 'broker or asset manager'),
    (6300, 6399, 'insurer'),
    (6722, 6726, 'asset manager'),
    (6798, 6798, 'REIT'),
    (6799, 6799, 'asset manager')
)


# The days by which the start or end of a quarterly period may differ from the date expected. Fiscal quarters that
# end on a weekday move by a few days from year to year.
PERIOD_DAYS = 10


# The ways to build operating expenses excluding cost of revenue, in the order tried
COST_METHODS = {
    1: 'gross profit - operating income',
    2: 'total costs - cost of revenue',
    3: 'revenue - operating income - cost of revenue'
}


def lin(value, zero, full, points):
    """
    Score linearly between two values, capped at both ends

    :param float value: The value to score
    :param float zero: The value that scores zero
    :param float full: The value that scores full points
    :param float points: The full points
    :rtype: float
    """

    return max(0.0, min(points, points * (zero - value) / (zero - full)))


def year_label(end):
    """
    Get the fiscal year label for a period end date. Years ending from January to the first week of April belong to
    the prior year: a 52- or 53-week year that ends near March 31 can end on either side of it.

    :param str end: The period end date
    :rtype: str
    """

    return end[:4] if end[5:] > '04-07' else str(int(end[:4]) - 1)


def calendar_years(data_date, thresholds):
    """
    Get the latest whole calendar years: the years of the insider figures, and of the owner cash, buybacks and share
    counts set beside them

    :param str data_date: The date of the latest filing in the data
    :param dict thresholds: The thresholds
    :returns: The tuple of the first and last year
    """

    last_year = int(data_date[:4]) - 1
    return last_year - thresholds['insider_years'] + 1, last_year


def sic_exclusion(sic):
    """
    Get the excluded industry group for a SIC code

    :param int sic: The SIC code, or None
    :returns: The group name, or None if the industry is not excluded
    """

    if sic is not None:
        for first, last, group in SIC_EXCLUSIONS:
            if first <= sic <= last:
                return group
    return None


def company_series(record):
    """
    Build a company's yearly series, one entry per fiscal year that has revenue, operating cash flow and stock pay

    :param dict record: The company record
    :returns: The list of year dicts, oldest first
    """

    annual = record['annual']
    sbc = {**annual['sbc2'], **annual['sbc']}
    ends = [end for end, fact in annual['rev'].items() if end in annual['ocf'] and end in sbc and fact[F_VAL] > 0]

    # Two 12-month periods can have one label, for example a fiscal year and another 12 months reported in passing.
    # The one whose revenue is from an annual report is the fiscal year; failing that, the later.
    by_label = {}
    for end in sorted(ends, key=lambda end: (fact_order(annual['rev'][end])[0], end)):
        by_label[year_label(end)] = end

    series = []
    for label in sorted(by_label):
        end = by_label[label]
        base = annual['ppe'].get(end) or annual['prod'].get(end)
        software = annual['sw'].get(end)
        capex = abs(base[F_VAL] if base else 0) + abs(software[F_VAL] if software else 0)
        revenue = annual['rev'][end][F_VAL]
        fcf = annual['ocf'][end][F_VAL] - capex
        owner_cash = fcf - sbc[end][F_VAL]
        series.append({
            'fy': label,
            'end': end,
            'rev': annual['rev'][end],
            'ocf': annual['ocf'][end],
            'capexBase': base,
            'capexSoftware': software,
            'capexMissing': base is None and software is None,
            'capex': capex,
            'sbc': sbc[end],
            'fcf': fcf,
            'ownerCash': owner_cash,
            'margin': owner_cash / revenue
        })
    return series


def find_period(facts, start, end):
    """
    Find the fact whose period starts and ends within PERIOD_DAYS of the dates given

    :param dict facts: The dict of "start|end" to fact
    :param str start: The period start date
    :param str end: The period end date
    :returns: The closest fact, or None
    """

    start_date = parse_date(start)
    end_date = parse_date(end)
    best = None
    best_distance = None
    for key in sorted(facts):
        fact_start, fact_end = key.split('|')
        start_distance = abs((parse_date(fact_start) - start_date).days)
        end_distance = abs((parse_date(fact_end) - end_date).days)
        if start_distance <= PERIOD_DAYS and end_distance <= PERIOD_DAYS:
            if best is None or start_distance + end_distance < best_distance:
                best = facts[key]
                best_distance = start_distance + end_distance
    return best


def latest_twelve_months(record, year):
    """
    Compute the latest-12-month figures: the latest fiscal year, plus the year-to-date period reported since,
    less the same period a year earlier. Each figure uses one XBRL tag for all three periods.

    :param dict record: The company record
    :param dict year: The latest year of the company's series
    :returns: The tuple of the figures and None, or of None and the reason the quarterly data is unusable
    """

    recent = record['recent']
    next_start = (parse_date(year['end']) + datetime.timedelta(days=1)).isoformat()

    # The latest year-to-date period since the fiscal year end, from the revenue tag
    current_end = None
    for key in recent['rev'].get(year['rev'][F_TAG], {}):
        start, end = key.split('|')
        if abs((parse_date(start) - parse_date(next_start)).days) <= PERIOD_DAYS and (current_end is None or end > current_end):
            current_end = end
    if current_end is None:
        return None, 'no quarterly report since the latest fiscal year'
    prior_end = (parse_date(current_end) - datetime.timedelta(days=365)).isoformat()

    figures = {'end': current_end, 'sources': []}
    parts = (
        ('rev', year['rev'], ()),
        ('ocf', year['ocf'], ()),
        ('sbc', year['sbc'], ()),
        ('capexBase', year['capexBase'], ('ppe', 'prod')),
        ('capexSoftware', year['capexSoftware'], ('sw',))
    )
    for name, fy_fact, concepts in parts:
        # No annual figure (zero in the annual series)? The quarters must not have one either.
        if fy_fact is None:
            for concept in concepts:
                for facts in recent[concept].values():
                    if find_period(facts, next_start, current_end):
                        return None, 'capital spending is tagged in the quarters but not in the fiscal year'
            figures[name] = 0
            continue

        # The same tag for the fiscal year, the year-to-date period and the year-earlier period
        tag = fy_fact[F_TAG]
        facts = {}
        for concept_recent in recent.values():
            facts = concept_recent.get(tag, facts)
        current = find_period(facts, next_start, current_end)
        prior = find_period(facts, year['rev'][F_START], prior_end)
        if current is None or prior is None:
            return None, f'quarterly {tag} is missing for the latest or the year-earlier period'
        figures[name] = fy_fact[F_VAL] + current[F_VAL] - prior[F_VAL]
        for fact in (current, prior):
            if fact[F_ACCN] not in figures['sources']:
                figures['sources'].append(fact[F_ACCN])

    if figures['rev'] <= 0:
        return None, 'latest-12-month revenue is not positive'
    figures['capex'] = abs(figures.pop('capexBase')) + abs(figures.pop('capexSoftware'))
    figures['fcf'] = figures['ocf'] - figures['capex']
    figures['ownerCash'] = figures['fcf'] - figures['sbc']
    figures['margin'] = figures['ownerCash'] / figures['rev']
    return figures, None


def cost_line(annual, end, method):
    """
    Build operating expenses excluding cost of revenue for a fiscal year

    :param dict annual: The company record's annual facts
    :param str end: The fiscal year end date
    :param int method: The COST_METHODS method number
    :returns: The tuple of the value and the facts used, or of None and None
    """

    cost_of_revenue = annual['cor'].get(end) or annual['cogs'].get(end)
    if method == 1 and end in annual['gp'] and end in annual['opinc']:
        return annual['gp'][end][F_VAL] - annual['opinc'][end][F_VAL], [annual['gp'][end], annual['opinc'][end]]
    if method == 2 and end in annual['cae'] and cost_of_revenue is not None:
        return annual['cae'][end][F_VAL] - cost_of_revenue[F_VAL], [annual['cae'][end], cost_of_revenue]
    if method == 3 and end in annual['opinc'] and cost_of_revenue is not None:
        value = annual['rev'][end][F_VAL] - annual['opinc'][end][F_VAL] - cost_of_revenue[F_VAL]
        return value, [annual['rev'][end], annual['opinc'][end], cost_of_revenue]
    return None, None


def window_years(series, thresholds):
    """
    Get the first and last of the latest fiscal years: the years between which the change in costs is reported. A
    company with fewer years than the window has its first year.

    :param list(dict) series: The company's yearly series
    :param dict thresholds: The thresholds
    :returns: The tuple of the first and last year
    """

    return series[-min(thresholds['cost_window_years'], len(series))], series[-1]


def cost_change(record, series, thresholds):
    """
    Build operating expenses excluding cost of revenue for the first and last of the latest fiscal years, the same
    way in both, with the gross profit of the last year. The level in the last year is scored; the change is reported.

    :param dict record: The company record
    :param list(dict) series: The company's yearly series
    :param dict thresholds: The thresholds
    :returns: The cost dict, or None if no method works for both years
    """

    first, last = window_years(series, thresholds)
    annual = record['annual']
    for method in COST_METHODS:
        first_value, first_facts = cost_line(annual, first['end'], method)
        last_value, last_facts = cost_line(annual, last['end'], method)
        if first_value is not None and last_value is not None and first_value > 0 and last_value > 0:
            first_ratio = first_value / first['rev'][F_VAL]
            last_ratio = last_value / last['rev'][F_VAL]
            if method == 1:
                gross = annual['gp'][last['end']][F_VAL]
            else:
                gross = last['rev'][F_VAL] - (annual['cor'].get(last['end']) or annual['cogs'][last['end']])[F_VAL]
            return {
                'method': method,
                'firstYear': first['fy'],
                'firstCost': first_value,
                'firstRatio': first_ratio,
                'firstFacts': first_facts,
                'lastYear': last['fy'],
                'lastCost': last_value,
                'lastRatio': last_ratio,
                'lastFacts': last_facts,
                'lastGross': gross,
                'change': (last_ratio - first_ratio) * 100
            }
    return None


def costs_sign(cost, thresholds):
    """
    Score the second sign, "revenue held up by costs": how much of gross profit operating costs take in the latest
    fiscal year. Operating costs are mostly people, and have to go on for the revenue to go on.

    :param dict cost: The cost dict, or None
    :param dict thresholds: The thresholds
    :returns: The dict of "level" (operating costs / gross profit, or None if gross profit is not positive) and
        "points", or None if the cost line cannot be built
    """

    if cost is None:
        return None
    gross = cost['lastGross']
    level = cost['lastCost'] / gross if gross > 0 else None
    # With no gross profit at all, operating costs take more than all of it
    points = SIGN_POINTS if level is None else lin(level, thresholds['cost_level_zero'], thresholds['cost_level_full'], SIGN_POINTS)
    return {'level': level, 'points': points}


def one_off_years(record, series, thresholds):
    """
    Find the years in which inventory, lending or a discontinued business moved operating cash flow by more
    than the threshold share of revenue

    :param dict record: The company record
    :param list(dict) series: The company's yearly series
    :param dict thresholds: The thresholds
    :returns: The dict of fiscal year label to the list of [cause, value, fact]
    """

    annual = record['annual']
    found = {}
    for year in series:
        end = year['end']
        limit = thresholds['one_off_ocf_share'] * year['rev'][F_VAL]
        causes = []
        if end in annual['inv'] and abs(annual['inv'][end][F_VAL]) > limit:
            causes.append(['inventory', annual['inv'][end][F_VAL], annual['inv'][end]])
        if end in annual['disc'] and abs(annual['disc'][end][F_VAL]) > limit:
            causes.append(['discontinued operations', annual['disc'][end][F_VAL], annual['disc'][end]])
        if end in annual['loan_in'] and end in annual['loan_out']:
            net = abs(annual['loan_in'][end][F_VAL]) - abs(annual['loan_out'][end][F_VAL])
            if abs(net) > limit:
                causes.append(['lending', net, annual['loan_in'][end]])
        elif end in annual['loan_chg'] and abs(annual['loan_chg'][end][F_VAL]) > limit:
            causes.append(['lending', annual['loan_chg'][end][F_VAL], annual['loan_chg'][end]])
        if causes:
            found[year['fy']] = causes
    return found


def pillar_one(series, latest_margin, thresholds):
    """
    Score P1, "no meaningful cash for owners"

    :param list(dict) series: The company's yearly series
    :param float latest_margin: The latest-12-month owner-cash margin
    :param dict thresholds: The thresholds
    :returns: The dict of the inputs, the three parts and the total
    """

    low_years = sum(1 for year in series if year['margin'] < thresholds['meaningful_margin'])
    cum_margin = sum(year['ownerCash'] for year in series) / sum(year['rev'][F_VAL] for year in series)
    years_points = thresholds['p1_years_points'] * low_years / len(series)
    cum_points = lin(cum_margin, thresholds['p1_cum_zero'], thresholds['p1_cum_full'], thresholds['p1_cum_points'])
    latest_points = lin(latest_margin, thresholds['p1_latest_zero'], thresholds['p1_latest_full'], thresholds['p1_latest_points'])
    return {
        'lowYears': low_years,
        'cumMargin': cum_margin,
        'yearsPoints': years_points,
        'cumPoints': cum_points,
        'latestPoints': latest_points,
        'p1': years_points + cum_points + latest_points
    }


# The kinds of operating spending reported beside the cost line, where a company tags them: sales and marketing,
# research and development, and general and administrative
SPENDING = ('sm', 'rnd', 'ga')


def spending_change(record, series, thresholds):
    """
    Get each kind of operating spending as a share of revenue in the first and last of the latest fiscal years - the
    same years as the cost line. These are reported, not scored.

    :param dict record: The company record
    :param list(dict) series: The company's yearly series
    :param dict thresholds: The thresholds
    :returns: The dict of spending kind to a dict of "firstRatio", "firstFact", "lastRatio" and "lastFact". A kind
        the company does not tag in both years is left out.
    """

    first, last = window_years(series, thresholds)
    spending = {}
    for kind in SPENDING:
        first_fact = record['annual'][kind].get(first['end'])
        last_fact = record['annual'][kind].get(last['end'])
        if first_fact is not None and last_fact is not None:
            spending[kind] = {
                'firstRatio': first_fact[F_VAL] / first['rev'][F_VAL],
                'firstFact': first_fact,
                'lastRatio': last_fact[F_VAL] / last['rev'][F_VAL],
                'lastFact': last_fact
            }
    return spending


def low_run(series, thresholds):
    """
    Count the latest fiscal years running with an owner-cash margin under the meaningful line

    :param list(dict) series: The company's yearly series
    :param dict thresholds: The thresholds
    :rtype: int
    """

    run = 0
    for year in reversed(series):
        if year['margin'] >= thresholds['meaningful_margin']:
            break
        run += 1
    return run


def five_years(record, series, first_year, last_year, insider):
    """
    Total a company's revenue, owner cash and buybacks over the fiscal years labelled with the calendar years of the
    insider summary, with the change in its share count - what owners got - and, beside them, what its insiders took
    out in the same years. A calendar year for which the company has no fiscal year is left out of both, so that the
    two cover the same years.

    :param dict record: The company record
    :param list(dict) series: The company's yearly series
    :param int first_year: The first calendar year
    :param int last_year: The last calendar year
    :param dict insider: The company's insider summary, or None if it has no insider filings
    :returns: The dict of "years" (the count of fiscal years), "revenue", "ownerCash", "buybacks", "withholding",
        "shareGrowth" - the annualized change in the diluted share count, or None if it cannot be followed - and
        "insider" - the dict of the insiders' amounts over those years, or None
    """

    years = [year for year in series if first_year <= int(year['fy']) <= last_year]
    ends = {year['end'] for year in years}
    labels = {int(year['fy']) for year in years}
    annual = record['annual']
    return {
        'years': len(years),
        'insider': insider and {
            amount: sum(year[amount] for year in insider['years'] if year['year'] in labels) for amount in ('cashOut', *AMOUNTS)
        },
        'revenue': sum(year['rev'][F_VAL] for year in years),
        'ownerCash': sum(year['ownerCash'] for year in years),
        'buybacks': sum(abs(fact[F_VAL]) for end, fact in annual['bb'].items() if end in ends),
        'withholding': sum(abs(fact[F_VAL]) for end, fact in annual['wh'].items() if end in ends),
        'shareGrowth': share_change(record, years)[0] if len(years) > 1 else None
    }


def insiders_sign(five, thresholds):
    """
    Score the third sign, "insiders cashing out": the cash insiders took out through stock over the calendar years,
    as a share of the company's revenue over the same years - the yardstick the index uses for owner cash

    :param dict five: The company's five-year totals
    :param dict thresholds: The thresholds
    :returns: The dict of "share" (cash-out / revenue) and "points", or None with no insider filings or no revenue
        in those years
    """

    if five['insider'] is None or five['revenue'] <= 0:
        return None
    share = five['insider']['cashOut'] / five['revenue']
    return {'share': share, 'points': lin(share, thresholds['insider_zero'], thresholds['insider_full'], SIGN_POINTS)}


def share_change(record, series):
    """
    Compute the annualized change in the diluted share count over the series

    :param dict record: The company record
    :param list(dict) series: The company's yearly series
    :returns: The tuple of the change and None, or of None and the reason it cannot be computed: the first or
        last count is missing, or a year-on-year jump (a stock split, or a conversion at listing) that the data
        does not adjust for
    """

    shares = record['annual']['sh']
    counts = [(year['fy'], shares[year['end']][F_VAL]) for year in series if year['end'] in shares and shares[year['end']][F_VAL] > 0]
    if len(counts) < 2 or counts[0][0] != series[0]['fy'] or counts[-1][0] != series[-1]['fy']:
        return None, 'share count missing for the first or last year'
    for (_, before), (_, after) in zip(counts, counts[1:]):
        if after > 1.8 * before or after < before / 1.8:
            return None, 'share count jumps in one year (a stock split, or a conversion at listing); not adjusted'
    span = int(counts[-1][0]) - int(counts[0][0])
    return (counts[-1][1] / counts[0][1]) ** (1 / span) - 1, None


def evaluate(record, sic, data_date, thresholds=None, insider=None):
    """
    Apply the screen and score the three signs for one company

    :param dict record: The company record
    :param int sic: The company's SIC code, or None if unknown
    :param str data_date: The date of the latest filing in the data
    :param dict thresholds: The thresholds (default is THRESHOLDS)
    :param dict insider: The company's insider summary, or None if it has no insider filings
    :returns: A dict with "stage", how far the company got through the basic tests: "no_data", "not_current",
        "small", "short", "slow_growth" or "scored". A "scored" company's dict has every input and score.
    """

    thresholds = thresholds or THRESHOLDS
    series = company_series(record)
    if not series:
        return {'stage': 'no_data'}

    # The basic tests
    last = series[-1]
    if last['end'] < (parse_date(data_date) - datetime.timedelta(days=thresholds['still_filing_days'])).isoformat():
        return {'stage': 'not_current'}
    if last['rev'][F_VAL] < thresholds['revenue_min']:
        return {'stage': 'small'}
    if len(series) < thresholds['years_min']:
        return {'stage': 'short'}
    growth = last['rev'][F_VAL] / series[0]['rev'][F_VAL]
    if growth < 1 + thresholds['growth_min']:
        return {'stage': 'slow_growth'}

    # Totals
    revenue = sum(year['rev'][F_VAL] for year in series)
    fcf = sum(year['fcf'] for year in series)
    sbc = sum(year['sbc'][F_VAL] for year in series)
    capex = sum(year['capex'] for year in series)
    annual = record['annual']
    ends = {year['end'] for year in series}
    totals = {name: sum(abs(fact[F_VAL]) for end, fact in annual[name].items() if end in ends) for name in ('bb', 'div', 'wh')}
    five = five_years(record, series, *calendar_years(data_date, thresholds), insider)

    # The latest-12-month owner-cash margin (the latest fiscal year if the quarterly data is unusable)
    ttm, ttm_reason = latest_twelve_months(record, last)
    latest_margin = ttm['margin'] if ttm else last['margin']

    # Sign 1 - and without the years moved by inventory, lending or discontinued operations
    p1 = pillar_one(series, latest_margin, thresholds)
    one_offs = one_off_years(record, series, thresholds)
    series_ex = [year for year in series if year['fy'] not in one_offs]
    p1_ex = pillar_one(series_ex, latest_margin, thresholds) if one_offs and series_ex else None

    # Signs 2 and 3, and the score. Costs and insider selling count only to the extent owners are getting no cash.
    # A sign that cannot be built leaves the company without a score: missing is not treated as zero.
    cost = cost_change(record, series, thresholds)
    costs = costs_sign(cost, thresholds)
    insiders = insiders_sign(five, thresholds)
    score = None
    if costs is not None and insiders is not None:
        score = p1['p1'] + (p1['p1'] / SIGN_POINTS) * (costs['points'] + insiders['points'])

    # The company type
    excluded = sic_exclusion(sic)
    if excluded:
        company_type = 'excluded'
    elif p1['cumMargin'] >= thresholds['meaningful_margin']:
        company_type = 'cash_generative'
    elif fcf >= 0 and sbc >= thresholds['sbc_revenue_min'] * revenue and sbc >= thresholds['sbc_fcf_min'] * fcf:
        company_type = 'capital_led' if capex > thresholds['capital_led_ratio'] * sbc else 'stock_pay'
    elif fcf < 0:
        company_type = 'cash_burner'
    else:
        company_type = 'thin_margin'

    # Data-quality flags
    share_growth, share_reason = share_change(record, series)
    flag_tests = (
        ('capex_missing', any(year['capexMissing'] for year in series)),
        ('no_cost_line', cost is None),
        ('latest_is_fiscal_year', ttm is None),
        ('one_off_years', bool(one_offs)),
        ('gap_years', int(last['fy']) - int(series[0]['fy']) + 1 != len(series)),
        ('few_fiscal_years', 0 < five['years'] < thresholds['insider_years']),
        ('revenue_jump', any(after['rev'][F_VAL] > 3 * before['rev'][F_VAL] for before, after in zip(series, series[1:]))),
        ('share_count_jump', share_reason is not None and 'jumps' in share_reason),
        ('no_insider_filings', insider is None)
    )

    return {
        'stage': 'scored',
        'cik': record['cik'],
        'name': record['name'],
        'sic': sic,
        'excluded': excluded,
        'type': company_type,
        'series': series,
        'annual': annual,
        'years': len(series),
        'firstYear': series[0]['fy'],
        'lastYear': last['fy'],
        'lastEnd': last['end'],
        'revenue': last['rev'][F_VAL],
        'growth': growth,
        'cumRevenue': revenue,
        'cumFcf': fcf,
        'cumSbc': sbc,
        'cumCapex': capex,
        'cumOwnerCash': fcf - sbc,
        'buybacks': totals['bb'],
        'dividends': totals['div'],
        'withholding': totals['wh'],
        'capexToSbc': capex / sbc if sbc > 0 else None,
        'latestMargin': latest_margin,
        'latestBasis': 'ttm' if ttm else 'fy',
        'latestEnd': ttm['end'] if ttm else last['end'],
        'ttm': ttm,
        'ttmReason': ttm_reason,
        'p1': p1,
        'oneOffs': one_offs,
        'p1Ex': p1_ex,
        'cost': cost,
        'costs': costs,
        'insider': insider,
        'insiders': insiders,
        'score': score,
        'lowRun': low_run(series, thresholds),
        'five': five,
        'spending': spending_change(record, series, thresholds),
        'shareGrowth': share_growth,
        'shareReason': share_reason,
        'flags': [flag for flag, test in flag_tests if test],
        'rank': None
    }


def run_screen(records, sics, data_date, insiders, thresholds=None):
    """
    Screen and score every company

    :param list(dict) records: The company records
    :param dict sics: The dict of CIK to SIC code
    :param str data_date: The date of the latest filing in the data
    :param dict insiders: The dict of CIK to insider summary. A company with no insider filings is not in it.
    :param dict thresholds: The thresholds (default is THRESHOLDS)
    :returns: The tuple of the "scored" results - the ranked companies, then the rest by P1, then the excluded
        industries - and the funnel: the count of companies left after each step of the screen
    """

    stage_counts = dict.fromkeys(('no_data', 'not_current', 'small', 'short', 'slow_growth', 'scored'), 0)
    results = []
    for record in records:
        result = evaluate(record, sics.get(record['cik']), data_date, thresholds, insiders.get(record['cik']))
        stage_counts[result['stage']] += 1
        if result['stage'] == 'scored':
            results.append(result)

    # Rank the companies that pass the screen and have all three signs
    ranked = [result for result in results if result['type'] == 'stock_pay' and result['score'] is not None]
    ranked.sort(key=lambda result: (-result['score'], result['name'], result['cik']))
    for rank, result in enumerate(ranked, 1):
        result['rank'] = rank
    results.sort(key=lambda result: (
        result['rank'] is None, result['rank'] or 0, result['type'] == 'excluded', -result['p1']['p1'], result['name'], result['cik']
    ))

    # The funnel
    funnel = {'prefilter': len(records)}
    funnel['current'] = funnel['prefilter'] - stage_counts['no_data'] - stage_counts['not_current']
    funnel['revenue'] = funnel['current'] - stage_counts['small']
    funnel['years'] = funnel['revenue'] - stage_counts['short']
    funnel['growth'] = funnel['years'] - stage_counts['slow_growth']
    included = [result for result in results if result['type'] != 'excluded']
    funnel['industry'] = len(included)
    funnel['lowMargin'] = sum(1 for result in included if result['type'] != 'cash_generative')
    funnel['stockPayCause'] = sum(1 for result in included if result['type'] in ('stock_pay', 'capital_led'))
    funnel['stockPay'] = sum(1 for result in included if result['type'] == 'stock_pay')
    funnel['ranked'] = len(ranked)
    return results, funnel


def group_totals(results):
    """
    Total the cash figures of a group of scored companies

    :param list(dict) results: The scored results
    :rtype: dict
    """

    totals = {'companies': len(results)}
    for key in ('cumRevenue', 'cumFcf', 'cumSbc', 'cumOwnerCash', 'cumCapex', 'buybacks', 'dividends', 'withholding'):
        totals[key] = sum(result[key] for result in results)
    return totals


def loose_thresholds():
    """
    Get the thresholds with the basic tests loosened by a fifth. Companies that pass these may enter the index
    in the sensitivity test, so they need industry codes too.

    :rtype: dict
    """

    thresholds = dict(THRESHOLDS)
    thresholds['revenue_min'] *= 0.8
    thresholds['years_min'] -= 1
    thresholds['growth_min'] *= 0.8
    return thresholds


def sensitivity(records, sics, data_date, base_results, insiders):
    """
    Move each threshold by a fifth, up and down, and report how the top ten ranks change

    :param list(dict) records: The company records
    :param dict sics: The dict of CIK to SIC code
    :param str data_date: The date of the latest filing in the data
    :param list(dict) base_results: The scored results at the index's thresholds
    :param dict insiders: The dict of CIK to insider summary
    :returns: The list of {threshold, factor, value, changes}. "changes" is empty when the top ten is unchanged.
    """

    def top_ten(results):
        return {result['cik']: result['rank'] for result in results if result['rank'] is not None and result['rank'] <= 10}

    def rank_changes(base, moved, names):
        return [
            {'cik': cik, 'name': names[cik], 'from': base.get(cik), 'to': moved.get(cik)}
            for cik in sorted(set(base) | set(moved), key=lambda cik: (moved.get(cik, 99), base.get(cik, 99)))
            if base.get(cik) != moved.get(cik)
        ]

    names = {result['cik']: result['name'] for result in base_results}
    base = top_ten(base_results)
    report = []
    for key in SENSITIVITY_KEYS:
        for factor in (0.8, 1.2):
            thresholds = dict(THRESHOLDS)
            thresholds[key] = round(THRESHOLDS[key] * factor, None if key in INTEGER_THRESHOLDS else 6)
            results, _ = run_screen(records, sics, data_date, insiders, thresholds)
            names.update((result['cik'], result['name']) for result in results)
            report.append({
                'threshold': key, 'factor': factor, 'value': thresholds[key], 'changes': rank_changes(base, top_ten(results), names)
            })
    return report
