"""
Check that the build step, run with the prototype's options, reproduces the prototype's output row for row.

The prototype's output, treadmill_market_screen.csv, came from the SEC companyfacts.zip downloaded on 2026-11-23,
so the check only holds against that file. Run it with "make check-prototype".
"""

import csv
import os
import sys

from treadmill_index.extract import load_records
from treadmill_index.score import PROTOTYPE_OPTIONS, run_screen


def number(text):
    return None if text in ('', 'None') else float(text)


def compare(raw_dir, csv_path):
    records, _ = load_records(os.path.join(raw_dir, 'companyfacts.zip'), os.path.join(raw_dir, 'extract-cache.json'), os.cpu_count())
    data_date = max(record['filed_max'] for record in records)
    results, funnel = run_screen(records, {}, data_date, None, PROTOTYPE_OPTIONS)
    print(funnel)
    mine = {result['cik']: result for result in results}
    with open(csv_path, 'r', encoding='utf-8') as csv_file:
        prototype = {int(row['cik']): row for row in csv.DictReader(csv_file)}

    different = len(set(mine) ^ set(prototype))
    for cik in sorted(set(mine) & set(prototype)):
        result = mine[cik]
        row = prototype[cik]
        cost = result['cost']
        p1 = result['p1']['p1']
        p2 = None if result['p2b'] is None else result['p2b'] * 25 / 13
        pairs = {
            'years': (result['years'], int(row['years'])),
            'first': (result['firstYear'], row['first']),
            'last_fye': (result['lastEnd'], row['last_fye']),
            'rev_last_m': (round(result['revenue'] / 1e6), int(row['rev_last_m'])),
            'low_years': (result['p1']['lowYears'], int(row['low_years'])),
            'cum_owner_margin': (round(result['p1']['cumMargin'] * 100, 1), number(row['cum_owner_margin'])),
            'last_owner_margin': (round(result['fyMargin'] * 100, 1), number(row['last_owner_margin'])),
            'cum_fcf_margin': (round(result['cumFcfMargin'] * 100, 1), number(row['cum_fcf_margin'])),
            'sbc_pct_rev': (round(result['sbcRevenue'] * 100, 1), number(row['sbc_pct_rev'])),
            'cum_owner_cash_m': (round(result['cumOwnerCash'] / 1e6), int(row['cum_owner_cash_m'])),
            'cum_sbc_m': (round(result['cumSbc'] / 1e6), int(row['cum_sbc_m'])),
            'buybacks_m': (round(result['buybacks'] / 1e6), int(row['buybacks_m'])),
            'dividends_m': (round(result['dividends'] / 1e6), int(row['dividends_m'])),
            'opex_change_pts': (None if cost is None else round(cost['change'], 1), number(row['opex_change_pts'])),
            'opex_method': (None if cost is None else cost['method'], number(row['opex_method'])),
            'capex_missing_years': (result['capexMissingYears'], int(row['capex_missing_years'])),
            'P1': (round(p1, 1), number(row['P1'])),
            'P2_cost': (None if p2 is None else round(p2, 1), number(row['P2_cost'])),
            # The prototype scored a missing cost line as zero
            'screen_score': (round(p1 + (p1 / 25) * (p2 or 0), 1), number(row['screen_score']))
        }
        differences = {name: pair for name, pair in pairs.items() if pair[0] != pair[1]}
        if differences:
            different += 1
            print(row['name'], differences)
    print(f'{len(prototype)} prototype rows, {len(mine)} build rows, {different} rows differ')
    return 1 if different else 0


if __name__ == '__main__':
    sys.exit(compare('data/raw', os.path.join(os.path.dirname(__file__), 'treadmill_market_screen.csv')))
