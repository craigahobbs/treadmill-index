"""
The stage-1 market screen and the screen score, as defined in docs/index-definition.md
"""

import datetime

from .extract import F_ACCN, F_START, F_TAG, F_VAL, parse_date


# The method version - bump when a scoring rule, threshold or source tag changes
METHOD_VERSION = '1.0.0'


# Every threshold in the definition
THRESHOLDS = {
    # Stage 1
    'still_filing_days': 548,       # the latest fiscal year ended within this many days of the data date
    'revenue_min': 1e9,             # latest annual revenue
    'years_min': 5,                 # years of data
    'growth_min': 0.5,              # revenue growth over those years
    'meaningful_margin': 0.03,      # owner cash under this share of revenue is not "meaningful"
    'sbc_revenue_min': 0.02,        # stock pay is the cause: SBC is at least this share of revenue ...
    'sbc_fcf_min': 0.5,             # ... and at least this share of free cash flow
    'capital_led_ratio': 2.0,       # capital spending above this multiple of SBC is "capital-led"
    'one_off_ocf_share': 0.25,      # inventory, lending or discontinued operations moved cash by this share of revenue

    # P1 (25 points)
    'p1_years_points': 10,
    'p1_cum_points': 8,
    'p1_cum_zero': 0.05,
    'p1_cum_full': -0.10,
    'p1_latest_points': 7,
    'p1_latest_zero': 0.05,
    'p1_latest_full': -0.05,

    # P2b (13 points, scaled to 25 for the screen score)
    'p2b_points': 13,
    'p2b_window_years': 5,
    'p2b_zero_drop': 10.0
}

# The thresholds the sensitivity test moves by a fifth
SENSITIVITY_KEYS = (
    'revenue_min', 'years_min', 'growth_min', 'meaningful_margin', 'sbc_revenue_min', 'sbc_fcf_min',
    'p1_cum_zero', 'p1_cum_full', 'p1_latest_zero', 'p1_latest_full', 'p2b_window_years', 'p2b_zero_drop'
)
INTEGER_THRESHOLDS = ('years_min', 'p2b_window_years')


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


# The ways to build operating expenses excluding cost of revenue, in the order tried. Method 0 is not in the
# definition; the prototype used it and it is kept only to reproduce the prototype's output.
COST_METHODS = {
    1: 'gross profit - operating income',
    2: 'total costs - cost of revenue',
    3: 'revenue - operating income - cost of revenue',
    0: 'the OperatingExpenses tag'
}


# The scoring options. PROTOTYPE_OPTIONS reproduces prototype/score.py.
DEFAULT_OPTIONS = {'ttm': True, 'opex_tag_fallback': False, 'still_filing_cutoff': None}
PROTOTYPE_OPTIONS = {'ttm': False, 'opex_tag_fallback': True, 'still_filing_cutoff': '2025-06-30'}


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
    Get the fiscal year label for a period end date. Years ending January to March belong to the prior year.

    :param str end: The period end date
    :rtype: str
    """

    return end[:4] if end[5:7] > '03' else str(int(end[:4]) - 1)


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
    ends = sorted(end for end, fact in annual['rev'].items() if end in annual['ocf'] and end in sbc and fact[F_VAL] > 0)
    by_label = {}
    for end in ends:
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


def find_period(facts, start, end, tolerance=10):
    """
    Find the fact whose period starts and ends within some days of the dates given

    :param dict facts: The dict of "start|end" to fact
    :param str start: The period start date
    :param str end: The period end date
    :param int tolerance: The days either date may differ by
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
        if start_distance <= tolerance and end_distance <= tolerance:
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
        if abs((parse_date(start) - parse_date(next_start)).days) <= 10 and (current_end is None or end > current_end):
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
    if method == 0 and end in annual['opex']:
        return annual['opex'][end][F_VAL], [annual['opex'][end]]
    return None, None


def cost_change(record, series, thresholds, options):
    """
    Compute the change in operating expenses (excluding cost of revenue) as a percent of revenue over the
    latest fiscal years, with the cost line built the same way in both years

    :param dict record: The company record
    :param list(dict) series: The company's yearly series
    :param dict thresholds: The thresholds
    :param dict options: The scoring options
    :returns: The cost change dict, or None if no method works for both years
    """

    window = thresholds['p2b_window_years']
    if len(series) < window:
        return None
    first = series[-window]
    last = series[-1]
    for method in ((1, 2, 3, 0) if options['opex_tag_fallback'] else (1, 2, 3)):
        first_value, first_facts = cost_line(record['annual'], first['end'], method)
        last_value, last_facts = cost_line(record['annual'], last['end'], method)
        if first_value is not None and last_value is not None and first_value > 0 and last_value > 0:
            first_ratio = first_value / first['rev'][F_VAL]
            last_ratio = last_value / last['rev'][F_VAL]
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
                'change': (last_ratio - first_ratio) * 100
            }
    return None


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


def evaluate(record, sic, data_date, thresholds=None, options=None):
    """
    Apply the stage-1 screen and the screen score to one company

    :param dict record: The company record
    :param int sic: The company's SIC code, or None if unknown
    :param str data_date: The date of the latest filing in the data
    :param dict thresholds: The thresholds (default is THRESHOLDS)
    :param dict options: The scoring options (default is DEFAULT_OPTIONS)
    :returns: A dict with "stage", how far the company got through the basic tests: "no_data", "not_current",
        "small", "short", "slow_growth" or "scored". A "scored" company's dict has every input and score.
    """

    thresholds = thresholds or THRESHOLDS
    options = options or DEFAULT_OPTIONS
    series = company_series(record)
    if not series:
        return {'stage': 'no_data'}

    # The basic tests
    last = series[-1]
    cutoff = options['still_filing_cutoff']
    if cutoff is None:
        cutoff = (parse_date(data_date) - datetime.timedelta(days=thresholds['still_filing_days'])).isoformat()
    if last['end'] < cutoff:
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

    # The latest-12-month owner-cash margin (the latest fiscal year if the quarterly data is unusable)
    ttm, ttm_reason = latest_twelve_months(record, last) if options['ttm'] else (None, 'not computed')
    latest_margin = ttm['margin'] if ttm else last['margin']

    # P1 - and P1 without the years moved by inventory, lending or discontinued operations
    p1 = pillar_one(series, latest_margin, thresholds)
    one_offs = one_off_years(record, series, thresholds)
    series_ex = [year for year in series if year['fy'] not in one_offs]
    p1_ex = pillar_one(series_ex, latest_margin, thresholds) if one_offs and series_ex else None

    # P2b and the screen score - with no cost line the company has P1 alone
    cost = cost_change(record, series, thresholds, options)
    p2b = None
    screen_score = None
    if cost is not None:
        p2b = lin(-cost['change'], thresholds['p2b_zero_drop'], 0, thresholds['p2b_points'])
        screen_score = p1['p1'] + (p1['p1'] / 25) * (p2b * 25 / thresholds['p2b_points'])

    # The company type
    excluded = sic_exclusion(sic)
    if excluded:
        company_type = 'excluded'
    elif p1['cumMargin'] >= thresholds['meaningful_margin']:
        company_type = 'cash_generative'
    elif fcf >= 0 and sbc >= thresholds['sbc_revenue_min'] * revenue and sbc >= thresholds['sbc_fcf_min'] * fcf:
        company_type = 'stock_pay'
    elif fcf < 0:
        company_type = 'cash_burner'
    else:
        company_type = 'thin_margin'

    # Data-quality flags
    share_growth, share_reason = share_change(record, series)
    flag_tests = (
        ('capex_missing', any(year['capexMissing'] for year in series)),
        ('no_cost_line', cost is None),
        ('latest_is_fiscal_year', options['ttm'] and ttm is None),
        ('one_off_years', bool(one_offs)),
        ('gap_years', int(last['fy']) - int(series[0]['fy']) + 1 != len(series)),
        ('revenue_jump', any(after['rev'][F_VAL] > 3 * before['rev'][F_VAL] for before, after in zip(series, series[1:]))),
        ('share_count_jump', share_reason is not None and 'jumps' in share_reason)
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
        'cumFcfMargin': fcf / revenue,
        'sbcRevenue': sbc / revenue,
        'buybacks': totals['bb'],
        'dividends': totals['div'],
        'withholding': totals['wh'],
        'capexToSbc': capex / sbc if sbc > 0 else None,
        'capitalLed': sbc > 0 and capex > thresholds['capital_led_ratio'] * sbc,
        'fyMargin': last['margin'],
        'latestMargin': latest_margin,
        'latestBasis': 'ttm' if ttm else 'fy',
        'latestEnd': ttm['end'] if ttm else last['end'],
        'ttm': ttm,
        'ttmReason': ttm_reason,
        'p1': p1,
        'oneOffs': one_offs,
        'p1Ex': p1_ex,
        'cost': cost,
        'p2b': p2b,
        'screenScore': screen_score,
        'capexMissingYears': sum(1 for year in series if year['capexMissing']),
        'shareGrowth': share_growth,
        'shareReason': share_reason,
        'flags': [flag for flag, test in flag_tests if test],
        'rank': None
    }


def run_screen(records, sics, data_date, thresholds=None, options=None):
    """
    Screen and score every company

    :param list(dict) records: The company records
    :param dict sics: The dict of CIK to SIC code
    :param str data_date: The date of the latest filing in the data
    :param dict thresholds: The thresholds (default is THRESHOLDS)
    :param dict options: The scoring options (default is DEFAULT_OPTIONS)
    :returns: The tuple of the "scored" results - the ranked companies, then the rest by P1, then the excluded
        industries - and the funnel: the count of companies left after each step of the screen
    """

    stage_counts = dict.fromkeys(('no_data', 'not_current', 'small', 'short', 'slow_growth', 'scored'), 0)
    results = []
    for record in records:
        result = evaluate(record, sics.get(record['cik']), data_date, thresholds, options)
        stage_counts[result['stage']] += 1
        if result['stage'] == 'scored':
            results.append(result)

    # Rank the stock-pay companies that have a screen score
    ranked = [result for result in results if result['type'] == 'stock_pay' and result['screenScore'] is not None]
    ranked.sort(key=lambda result: (-result['screenScore'], result['name'], result['cik']))
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


def sensitivity(records, sics, data_date, base_results):
    """
    Move each threshold by a fifth, up and down, and report how the top ten ranks change

    :param list(dict) records: The company records
    :param dict sics: The dict of CIK to SIC code
    :param str data_date: The date of the latest filing in the data
    :param list(dict) base_results: The scored results at the definition's thresholds
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
            results, _ = run_screen(records, sics, data_date, thresholds)
            names.update((result['cik'], result['name']) for result in results)
            changes = rank_changes(base, top_ten(results), names)
            report.append({'threshold': key, 'factor': factor, 'value': thresholds[key], 'changes': changes})
    return report
