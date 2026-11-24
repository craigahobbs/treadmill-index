# Licensed under the MIT License
# https://github.com/craigahobbs/treadmill-index/blob/main/LICENSE

"""
Write the web application's data files: index.json, index.csv, meta.json and company/<cik>.json
"""

import csv
import hashlib
import json
import os
import shutil

from .extract import F_ACCN, F_FILED, F_FORM, F_TAG, F_VAL, PREFILTER_REVENUE
from .insider import AMOUNTS
from .score import COST_METHODS, METHOD_VERSION, SIC_EXCLUSIONS, SIGN_POINTS, THRESHOLDS, calendar_years, group_totals


# The files copied to the archive of each build
ARCHIVE_FILES = ('index.json', 'index.csv', 'meta.json')

# The index row's scores - a company in an excluded industry has none
SCORE_FIELDS = ('score', 'p1', 'p1Years', 'p1Cum', 'p1Latest', 'p1Ex', 'costs', 'insiders')

# The insider summary's dollar amounts, and its amounts over the quarters that have the company's buybacks
INSIDER_AMOUNTS = ('cashOut', *AMOUNTS)
INSIDER_QUARTER_AMOUNTS = ('buybacks', 'salesInQuarters', 'salesInBuybackQuarters')


def fact_json(fact):
    """
    Get a sourced figure's JSON: its value, XBRL tag, and the filing it came from

    :param list fact: The fact, or None
    :rtype: dict
    """

    if fact is None:
        return None
    return {'v': fact[F_VAL], 'accn': fact[F_ACCN], 'filed': fact[F_FILED], 'form': fact[F_FORM], 'tag': fact[F_TAG]}


def dollars(value):
    """
    Round dollars for output

    :param float value: The dollar amount, or None
    :rtype: int
    """

    return None if value is None else round(value)


def ratio(value, digits=5):
    """
    Round a ratio for output

    :param float value: The ratio, or None
    :param int digits: The decimal places to keep
    :rtype: float
    """

    return None if value is None else round(value, digits)


def money(value):
    """
    Format dollars for a sentence

    :param float value: The dollar amount
    :rtype: str
    """

    millions = round(abs(value) / 1e6)
    sign = '-' if value < 0 and millions else ''
    if millions >= 1000:
        return f'{sign}${abs(value) / 1e9:,.1f} billion'
    return f'{sign}${millions:,} million'


def percent(value):
    """
    Format a ratio as a percent for a sentence

    :param float value: The ratio
    :rtype: str
    """

    return f'{value * 100:.1f}%'


def join_words(words):
    """
    Join words for a sentence: "a", "a and b", "a, b and c"

    :param list(str) words: The words
    :rtype: str
    """

    return ' and '.join(filter(None, [', '.join(words[:-1]), words[-1]]))


def summary_sentences(result, thresholds):
    """
    Describe a company's numbers in plain sentences

    :param dict result: The company's scored result
    :param dict thresholds: The thresholds
    :returns: The list of sentences
    """

    if result['latestBasis'] == 'ttm':
        latest = f'In the 12 months to {result["latestEnd"]} it was {percent(result["latestMargin"])} of revenue.'
    else:
        latest = f'In the latest fiscal year, to {result["latestEnd"]}, it was {percent(result["latestMargin"])} of revenue.'
    return [
        f'From fiscal {result["firstYear"]} to {result["lastYear"]}, {result["name"]} reported {money(result["cumRevenue"])} of '
        f'revenue and {money(result["cumFcf"])} of free cash flow. Stock pay was {money(result["cumSbc"])}, which leaves '
        f'{money(result["cumOwnerCash"])} of owner cash: {percent(result["p1"]["cumMargin"])} of revenue.',
        f'Owner cash was under {percent(thresholds["meaningful_margin"])} of revenue in {result["p1"]["lowYears"]} of '
        f'{result["years"]} years.',
        latest
    ]


def other_way(result, thresholds):
    """
    List what cuts the other way: facts in the numbers that weigh against a company's place in the index

    :param dict result: The company's scored result
    :param dict thresholds: The thresholds
    :returns: The list of sentences
    """

    items = []
    line = thresholds['meaningful_margin']
    period = 'latest 12 months' if result['latestBasis'] == 'ttm' else 'latest fiscal year'
    if result['latestMargin'] >= line:
        items.append(f'Owner cash in the {period} was {percent(result["latestMargin"])} of revenue, above the {percent(line)} line.')
    elif result['latestMargin'] > result['p1']['cumMargin'] + 0.02:
        items.append(
            f'Owner cash in the {period} was {percent(result["latestMargin"])} of revenue, better than the '
            f'{percent(result["p1"]["cumMargin"])} over the whole period.'
        )
    if result['oneOffs']:
        years = join_words(sorted(result['oneOffs']))
        causes = join_words(sorted({cause[0] for causes in result['oneOffs'].values() for cause in causes}))
        text = f'In {years}, {causes} moved operating cash flow by more than {percent(thresholds["one_off_ocf_share"])} of revenue.'
        if result['p1Ex'] and not result['excluded']:
            text += f' Without those years the cumulative owner-cash margin is {percent(result["p1Ex"]["cumMargin"])}' \
                f' and the owner-cash sign scores {result["p1Ex"]["p1"]:.1f} instead of {result["p1"]["p1"]:.1f}.'
        items.append(text)
    if result['type'] == 'capital_led':
        items.append(f'Capital spending was {result["capexToSbc"]:.1f} times stock pay. The shortfall is mostly investment, not stock pay.')
    returned = [
        text for amount, text in (
            (result['buybacks'], f'{money(result["buybacks"])} to buy back shares'),
            (result['dividends'], f'{money(result["dividends"])} in dividends')
        ) if amount
    ]
    if returned:
        items.append(f'The company paid {join_words(returned)} over the period.')
    cost = result['cost']
    if cost and cost['change'] <= -2:
        items.append(
            f'Operating costs fell from {percent(cost["firstRatio"])} of revenue in {cost["firstYear"]} to '
            f'{percent(cost["lastRatio"])} in {cost["lastYear"]}.'
        )
    return items


def index_row(result, info):
    """
    Build a company's row of index.json and index.csv, in the order of the CSV's columns. A company in an excluded
    industry has its inputs but no scores.

    :param dict result: The company's scored result
    :param dict info: The company's SEC company information
    :rtype: dict
    """

    p1 = result['p1']
    p1_ex = result['p1Ex'] or {}
    costs = result['costs'] or {}
    insiders = result['insiders'] or {}
    five = result['five']
    row = {
        'rank': result['rank'],
        'name': result['name'],
        'ticker': (info.get('tickers') or [None])[0],
        'exchange': (info.get('exchanges') or [None])[0],
        'cik': result['cik'],
        'type': result['type'],
        'excluded': result['excluded'],
        'sic': result['sic'],
        'sicDescription': info.get('sicDescription'),
        'score': ratio(result['score'], 2),
        'p1': ratio(p1['p1'], 2),
        'p1Years': ratio(p1['yearsPoints'], 2),
        'p1Cum': ratio(p1['cumPoints'], 2),
        'p1Latest': ratio(p1['latestPoints'], 2),
        'p1Ex': ratio(p1_ex.get('p1'), 2),
        'costs': ratio(costs.get('points'), 2),
        'insiders': ratio(insiders.get('points'), 2),
        'years': result['years'],
        'firstYear': result['firstYear'],
        'lastYear': result['lastYear'],
        'lastEnd': result['lastEnd'],
        'revenue': result['revenue'],
        'growth': ratio(result['growth'], 3),
        'lowYears': p1['lowYears'],
        'lowRun': result['lowRun'],
        'cumMargin': ratio(p1['cumMargin']),
        'cumMarginEx': ratio(p1_ex.get('cumMargin')),
        'latestMargin': ratio(result['latestMargin']),
        'latestBasis': result['latestBasis'],
        'latestEnd': result['latestEnd'],
        'cumRevenue': result['cumRevenue'],
        'cumFcf': result['cumFcf'],
        'cumSbc': result['cumSbc'],
        'cumCapex': result['cumCapex'],
        'cumOwnerCash': result['cumOwnerCash'],
        'buybacks': result['buybacks'],
        'dividends': result['dividends'],
        'withholding': result['withholding'],
        'shareGrowth': ratio(result['shareGrowth']),
        'costLevel': ratio(costs.get('level')),
        'costChange': ratio((result['cost'] or {}).get('change'), 2),
        'yearsFive': five['years'],
        'cashOut': dollars((five['insider'] or {}).get('cashOut')),
        'cashOutRevenue': ratio(insiders.get('share')),
        'revenueFive': dollars(five['revenue']),
        'ownerCashFive': dollars(five['ownerCash']),
        'ownerMarginFive': ratio(five['ownerCash'] / five['revenue']) if five['revenue'] > 0 else None,
        'buybacksFive': dollars(five['buybacks']),
        'withholdingFive': dollars(five['withholding']),
        'shareGrowthFive': ratio(five['shareGrowth']),
        'flags': result['flags']
    }
    if result['excluded']:
        row.update(dict.fromkeys(SCORE_FIELDS))
    return row


def insider_json(insider):
    """
    Build a company file's insider section: the yearly amounts, and the insiders who took out the most with their filings

    :param dict insider: The company's insider summary, or None
    :rtype: dict
    """

    if insider is None:
        return None

    def amounts(item, keys):
        return {**{key: item[key] for key in keys}, **{amount: dollars(item[amount]) for amount in INSIDER_AMOUNTS}}

    return {
        **amounts(insider, ('insiders', 'sellers')),
        'years': [amounts(year, ('year',)) for year in insider['years']],
        'people': [
            {
                **amounts(person, ('cik', 'name', 'title')),
                'filings': [amounts(filing, ('accn', 'filed')) for filing in person['filings']]
            }
            for person in insider['people']
        ]
    }


def company_json(result, info, thresholds):
    """
    Build a company's file: its index row, its yearly series with sources, and its generated text

    :param dict result: The company's scored result
    :param dict info: The company's SEC company information
    :param dict thresholds: The thresholds
    :rtype: dict
    """

    years = []
    for year in result['series']:
        entry = {
            'fy': year['fy'],
            'end': year['end'],
            'rev': fact_json(year['rev']),
            'ocf': fact_json(year['ocf']),
            'capexBase': fact_json(year['capexBase']),
            'capexSoftware': fact_json(year['capexSoftware']),
            'capex': None if year['capexMissing'] else year['capex'],
            'sbc': fact_json(year['sbc']),
            'fcf': year['fcf'],
            'ownerCash': year['ownerCash'],
            'margin': ratio(year['margin']),
            'oneOff': [
                {'cause': cause, 'v': value, 'fact': fact_json(fact)} for cause, value, fact in result['oneOffs'].get(year['fy'], [])
            ]
        }
        for name, concept in (('buybacks', 'bb'), ('dividends', 'div'), ('withholding', 'wh'), ('shares', 'sh')):
            entry[name] = fact_json(result['annual'][concept].get(year['end']))
        years.append(entry)

    cost = result['cost']
    ttm = result['ttm']
    return {
        'row': index_row(result, info),
        'formerNames': info.get('formerNames') or [],
        'summary': summary_sentences(result, thresholds),
        'otherWay': other_way(result, thresholds),
        'years': years,
        'ttm': ttm and {**ttm, 'margin': ratio(ttm['margin'])},
        'ttmReason': result['ttmReason'],
        'cost': cost and {
            **cost,
            'methodText': COST_METHODS[cost['method']],
            'level': ratio(result['costs']['level']),
            'firstRatio': ratio(cost['firstRatio']),
            'firstFacts': [fact_json(fact) for fact in cost['firstFacts']],
            'lastRatio': ratio(cost['lastRatio']),
            'lastFacts': [fact_json(fact) for fact in cost['lastFacts']],
            'change': ratio(cost['change'], 2)
        },
        'shareReason': result['shareReason'],
        'insider': insider_json(result['insider']),
        'spending': {
            kind: {
                'firstRatio': ratio(item['firstRatio']),
                'firstFact': fact_json(item['firstFact']),
                'lastRatio': ratio(item['lastRatio']),
                'lastFact': fact_json(item['lastFact'])
            }
            for kind, item in result['spending'].items()
        }
    }


def check_output(rows, funnel, infos):
    """
    Check the output before it is published

    :param list(dict) rows: The index.json rows
    :param dict funnel: The screen funnel
    :param dict infos: The dict of CIK to SEC company information
    :returns: The list of problems. An empty list passes.
    """

    problems = []
    if funnel['ranked'] == 0:
        problems.append('No companies are ranked')
    ranks = sorted(row['rank'] for row in rows if row['rank'] is not None)
    if ranks != list(range(1, len(ranks) + 1)):
        problems.append('Ranks are not 1 to N')
    for row in rows:
        label = f'{row["name"]} (CIK {row["cik"]})'
        if row['cik'] not in infos:
            problems.append(f'{label}: no SEC company information, so the industry test was not applied')
        if row['p1'] is not None and not 0 <= row['p1'] <= SIGN_POINTS:
            problems.append(f'{label}: the owner-cash sign is out of range')
        if row['score'] is not None and not 0 <= row['score'] <= 3 * SIGN_POINTS:
            problems.append(f'{label}: the score is out of range')
        if row['rank'] is not None and (row['type'] != 'stock_pay' or row['score'] is None):
            problems.append(f'{label}: ranked without passing the screen')
    return problems


def insider_totals(results):
    """
    Total the insiders' amounts of a group of scored companies, beside what the companies produced for their owners

    :param list(dict) results: The scored results
    :returns: The dict of the count of companies with insider filings, their revenue and owner cash over the same
        years, the count whose insiders took out more than that owner cash, the total of each insider amount over
        those years, and the insiders' sales beside the companies' buybacks by quarter
    """

    fives = [result['five'] for result in results if result['insider'] is not None]
    insiders = [result['insider'] for result in results if result['insider'] is not None]
    return {
        'companies': len(fives),
        'revenue': dollars(sum(five['revenue'] for five in fives)),
        'ownerCash': dollars(sum(five['ownerCash'] for five in fives)),
        'tookMore': sum(1 for five in fives if five['insider']['cashOut'] > max(five['ownerCash'], 0)),
        'quarters': sum(insider['quarters'] for insider in insiders),
        'buybackQuarters': sum(insider['buybackQuarters'] for insider in insiders),
        **{amount: dollars(sum(five['insider'][amount] for five in fives)) for amount in INSIDER_AMOUNTS},
        **{amount: dollars(sum(insider[amount] for insider in insiders)) for amount in INSIDER_QUARTER_AMOUNTS}
    }


def buyback_totals(results):
    """
    Set a group of scored companies' buybacks beside their share counts, over the five calendar years

    :param list(dict) results: The scored results
    :returns: The dict of the count of companies that bought back shares and whose share count can be followed, the
        count of those whose share count still rose, and what each spent on buybacks and employees' vesting taxes
    """

    bought = [result['five'] for result in results if result['five']['buybacks'] > 0 and result['five']['shareGrowth'] is not None]
    rose = [five for five in bought if five['shareGrowth'] > 0]
    return {
        'companies': len(bought),
        'rose': len(rose),
        'spent': dollars(sum(five['buybacks'] + five['withholding'] for five in bought)),
        'spentRose': dollars(sum(five['buybacks'] + five['withholding'] for five in rose))
    }


def write_json(path, value):
    """
    Write a JSON file

    :param str path: The file path
    :param value: The JSON value
    """

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as json_file:
        json_file.write(json.dumps(value, sort_keys=True, separators=(',', ':')) + '\n')


def file_sha256(path):
    """
    Compute the SHA-256 hash of a file

    :param str path: The file path
    :returns: The hash, in hex
    """

    digest = hashlib.sha256()
    with open(path, 'rb') as hashed:
        for block in iter(lambda: hashed.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def build_meta(results, funnel, companies_in_file, sources, sensitivity_report, built):
    """
    Build meta.json: the as-of date, the date of the build, sources, funnel, thresholds, group totals and sensitivity

    :param list(dict) results: The scored results
    :param dict funnel: The screen funnel
    :param int companies_in_file: The count of companies in the companyfacts file
    :param dict sources: The source files' descriptions - "companyfacts" has "latestFiling", the as-of date
    :param list(dict) sensitivity_report: The sensitivity report
    :param str built: The date of the build
    :rtype: dict
    """

    # The screened group, and the companies that do produce meaningful owner cash as the baseline
    screened = [result for result in results if result['type'] == 'stock_pay']
    groups = {'screened': screened, 'cashGenerative': [result for result in results if result['type'] == 'cash_generative']}
    types = {}
    excluded = {}
    for result in results:
        types[result['type']] = types.get(result['type'], 0) + 1
        if result['excluded']:
            excluded[result['excluded']] = excluded.get(result['excluded'], 0) + 1
    line = THRESHOLDS['meaningful_margin']
    data_date = sources['companyfacts']['latestFiling']
    first_year, last_year = calendar_years(data_date, THRESHOLDS)
    return {
        'methodVersion': METHOD_VERSION,
        'dataDate': data_date,
        'built': built,
        'years': {'first': first_year, 'last': last_year},
        'sources': sources,
        'thresholds': {**THRESHOLDS, 'prefilter_revenue': PREFILTER_REVENUE},
        'sicExclusions': [{'first': first, 'last': last, 'group': group} for first, last, group in SIC_EXCLUSIONS],
        'costMethods': {str(method): text for method, text in COST_METHODS.items()},
        'funnel': {'inFile': companies_in_file, **funnel},
        'types': types,
        'excluded': excluded,
        'totals': group_totals(screened),
        'insider': {name: insider_totals(group) for name, group in groups.items()},
        'buybackShares': {name: buyback_totals(group) for name, group in groups.items()},
        'lowFiveYears': sum(1 for result in screened if result['lowRun'] >= 5),
        'latest': {
            'cleared': sum(1 for result in screened if result['latestMargin'] >= line),
            'negative': sum(1 for result in screened if result['latestMargin'] < 0),
            'fiscalYearBasis': sum(1 for result in screened if result['latestBasis'] == 'fy')
        },
        'cost': {
            'allGross': sum(1 for result in screened if result['costs'] is not None and result['costs']['points'] >= SIGN_POINTS),
            'missing': sum(1 for result in screened if result['costs'] is None),
            'missingAll': sum(1 for result in results if result['costs'] is None)
        },
        'sensitivity': sensitivity_report
    }


def write_output(out_dir, results, infos, meta):
    """
    Write index.json, index.csv, meta.json and company/<cik>.json, and archive the build. Nothing is written if a
    check fails.

    :param str out_dir: The output directory
    :param list(dict) results: The scored results
    :param dict infos: The dict of CIK to SEC company information
    :param dict meta: The meta.json value
    :returns: The list of check problems. An empty list means the files were written.
    """

    rows = [index_row(result, infos.get(result['cik'], {})) for result in results]
    problems = check_output(rows, meta['funnel'], infos)
    if problems:
        return problems

    write_json(os.path.join(out_dir, 'index.json'), {'dataDate': meta['dataDate'], 'methodVersion': METHOD_VERSION, 'companies': rows})
    with open(os.path.join(out_dir, 'index.csv'), 'w', encoding='utf-8', newline='') as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=list(rows[0]))
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, 'flags': ' '.join(row['flags'])})
    write_json(os.path.join(out_dir, 'meta.json'), meta)

    # Write the company files and remove the files of companies no longer in the index
    company_dir = os.path.join(out_dir, 'company')
    os.makedirs(company_dir, exist_ok=True)
    keep = set()
    for result in results:
        name = f'{result["cik"]}.json'
        keep.add(name)
        write_json(os.path.join(company_dir, name), company_json(result, infos.get(result['cik'], {}), meta['thresholds']))
    for name in os.listdir(company_dir):
        if name.endswith('.json') and name not in keep:
            os.remove(os.path.join(company_dir, name))

    write_archive(out_dir, meta)
    return []


def write_archive(out_dir, meta):
    """
    Archive the build so a figure cited from it can be found again: copy index.json, index.csv and meta.json to
    archive/<data date>/<method version>/ and list the build in archive/builds.json, newest first. A build with the
    same data date and method version is replaced.

    :param str out_dir: The output directory
    :param dict meta: The meta.json value
    """

    build = {
        'dataDate': meta['dataDate'], 'methodVersion': meta['methodVersion'], 'built': meta['built'], 'ranked': meta['funnel']['ranked']
    }
    build_dir = os.path.join(out_dir, 'archive', build['dataDate'], build['methodVersion'])
    os.makedirs(build_dir, exist_ok=True)
    for name in ARCHIVE_FILES:
        shutil.copyfile(os.path.join(out_dir, name), os.path.join(build_dir, name))

    def build_key(other):
        return other['dataDate'], [int(part) for part in other['methodVersion'].split('.')]

    builds_path = os.path.join(out_dir, 'archive', 'builds.json')
    builds = []
    if os.path.exists(builds_path):
        with open(builds_path, 'r', encoding='utf-8') as builds_file:
            builds = [other for other in json.load(builds_file) if build_key(other) != build_key(build)]
    write_json(builds_path, sorted([*builds, build], key=build_key, reverse=True))
