# pylint: disable=missing-class-docstring, missing-function-docstring, missing-module-docstring

import json
import os
from tempfile import TemporaryDirectory
import unittest

from treadmill_index.insider import insider_summary
from treadmill_index.output import CSV_FIELDS, build_meta, buyback_totals, check_output, company_json, dollars, fact_json, \
    file_sha256, index_row, insider_json, insider_totals, join_words, money, other_way, percent, ratio, summary_sentences, \
    write_archive, write_json, write_output
from treadmill_index.score import THRESHOLDS, evaluate, run_screen, sensitivity

from .helpers import DATA_DATE, REVENUE, annual, company_record
from .test_insider import TRANSACTIONS


INFO = {
    'sic': 7372,
    'sicDescription': 'Services-Prepackaged Software',
    'tickers': ['TEST', 'TESTW'],
    'exchanges': ['Nasdaq', 'Nasdaq'],
    'formerNames': ['Old Test Co']
}

ROW = {
    'cik': 1,
    'name': 'Test Co',
    'ticker': 'TEST',
    'exchange': 'Nasdaq',
    'sic': 7372,
    'sicDescription': 'Services-Prepackaged Software',
    'type': 'stock_pay',
    'excluded': None,
    'rank': None,
    'threeRank': None,
    'screenScore': 37.27,
    'threeScore': None,
    'p1': 18.63,
    'p1Years': 10.0,
    'p1Cum': 3.73,
    'p1Latest': 4.9,
    'p1Ex': None,
    'cumMarginEx': None,
    'p2b': 13,
    'costChange': 0.0,
    'costMethod': 1,
    'costFirst': 0.55,
    'costLast': 0.55,
    'years': 7,
    'firstYear': '2019',
    'lastYear': '2025',
    'lastEnd': '2025-12-31',
    'revenue': 2000e6,
    'growth': 2.0,
    'lowYears': 7,
    'cumMargin': -0.02,
    'fyMargin': -0.02,
    'latestMargin': -0.02,
    'latestBasis': 'ttm',
    'latestEnd': '2026-09-30',
    'cumRevenue': 10150e6,
    'cumFcf': 1015e6,
    'cumSbc': 1218e6,
    'cumCapex': 203e6,
    'cumOwnerCash': -203e6,
    'cumFcfMargin': 0.1,
    'sbcRevenue': 0.12,
    'buybacks': 0,
    'dividends': 0,
    'withholding': 0,
    'capexToSbc': 0.167,
    'capitalLed': False,
    'shareGrowth': None,
    'p3': None,
    'p3Years': None,
    'p3Ratio': None,
    'insiderSales': None,
    'insiderGrants': None,
    'insiderOptionGrants': None,
    'insiderPurchases': None,
    'salesToGrants': None,
    'salesToStockGrants': None,
    'insiderBothYears': None,
    'lowRun': 7,
    'ownerCashFive': -161000000,
    'buybacksFive': 0,
    'withholdingFive': 0,
    'shareGrowthFive': None,
    'flags': [],
    'margins': [-0.02, -0.02, -0.02, -0.02, -0.02, -0.02, -0.02]
}

INSIDER_ROW = {
    'threeScore': 39.06,
    'salesToStockGrants': 1.002,
    'p3': 2.4,
    'p3Years': 2.4,
    'p3Ratio': 0.0,
    'insiderSales': 110200,
    'insiderGrants': 110000,
    'insiderOptionGrants': 300000,
    'insiderPurchases': 4000,
    'salesToGrants': 0.269,
    'insiderBothYears': 1
}

NO_INSIDERS = {
    'companies': 0, 'soldMore': 0, 'ownerCash': 0, 'tookMore': 0, 'quarters': 0, 'buybackQuarters': 0, 'sales': 0, 'purchases': 0,
    'withheld': 0, 'toIssuer': 0,
    'grants': 0, 'optionGrants': 0, 'buybacks': 0, 'salesInQuarters': 0, 'salesInBuybackQuarters': 0
}

SUMMARY = [
    'From fiscal 2019 to 2025, Test Co reported $10.2 billion of revenue and $1.0 billion of free cash flow. Stock pay was '
    '$1.2 billion, which leaves -$203 million of owner cash: -2.0% of revenue.',
    'Owner cash was under 3.0% of revenue in 7 of 7 years.',
    'In the 12 months to 2026-09-30 it was -2.0% of revenue.'
]

SOURCES = {'companyfacts': {'latestFiling': DATA_DATE, 'sha256': 'abc'}, 'submissions': {'companies': 5}}


def screen():
    records = [
        company_record(cik=1),
        company_record(cik=2, name='Capital Co', ocf=0.4, capex=0.3),
        company_record(cik=3, name='No Cost Line Co', quarters=False, tags={'GrossProfit': None}),
        company_record(cik=4, name='Cash Co', sbc=0.02, operating=[50, 55, 62.5, 70, 80, 90, 400]),
        company_record(cik=5, name='Bank Co')
    ]
    sics = {1: 7372, 2: 3674, 3: 7372, 4: 7372, 5: 6021}
    results, funnel = run_screen(records, sics, DATA_DATE)
    return records, sics, results, funnel


class TestOutput(unittest.TestCase):

    def test_fact_json(self):
        self.assertIsNone(fact_json(None))
        self.assertEqual(
            fact_json([240e6, '0000000001-26-000010', '2026-02-15', '10-K', '2025-01-01', 'ShareBasedCompensation']),
            {'v': 240e6, 'accn': '0000000001-26-000010', 'filed': '2026-02-15', 'form': '10-K', 'tag': 'ShareBasedCompensation'}
        )


    def test_dollars(self):
        self.assertIsNone(dollars(None))
        self.assertEqual(dollars(110200.4), 110200)
        self.assertIsInstance(dollars(110200.0), int)


    def test_ratio(self):
        self.assertIsNone(ratio(None))
        self.assertEqual(ratio(0.123456789), 0.12346)
        self.assertEqual(ratio(18.6333333, 2), 18.63)


    def test_money(self):
        self.assertEqual(money(1.25e9), '$1.2 billion')
        self.assertEqual(money(1234.56e9), '$1,234.6 billion')
        self.assertEqual(money(-2.5e9), '-$2.5 billion')
        self.assertEqual(money(999e6), '$999 million')
        self.assertEqual(money(-203e6), '-$203 million')
        self.assertEqual(money(0), '$0 million')


    def test_join_words(self):
        self.assertEqual(join_words(['2021']), '2021')
        self.assertEqual(join_words(['2021', '2022']), '2021 and 2022')
        self.assertEqual(join_words(['2020', '2021', '2022']), '2020, 2021 and 2022')


    def test_percent(self):
        self.assertEqual(percent(0.03), '3.0%')
        self.assertEqual(percent(-0.0704), '-7.0%')


    def test_summary_sentences(self):
        self.assertEqual(summary_sentences(evaluate(company_record(), None, DATA_DATE), THRESHOLDS), SUMMARY)
        self.assertEqual(
            summary_sentences(evaluate(company_record(quarters=False), None, DATA_DATE), THRESHOLDS),
            SUMMARY[:2] + ['In the latest fiscal year, to 2025-12-31, it was -2.0% of revenue.']
        )


    def test_other_way(self):
        # Nothing cuts the other way
        self.assertEqual(other_way(evaluate(company_record(), None, DATA_DATE), THRESHOLDS), [])

        # The latest year is above the line, cash was returned, and costs fell
        result = evaluate(company_record(
            quarters=False,
            sbc=[120, 132, 150, 168, 192, 216, 100],
            operating=[50, 55, 62.5, 70, 80, 90, 200],
            tags={'PaymentsForRepurchaseOfCommonStock': [annual(2025, 150)], 'PaymentsOfDividends': [annual(2025, 20)]}
        ), None, DATA_DATE)
        self.assertEqual(other_way(result, THRESHOLDS), [
            {
                'kind': 'recent_improvement',
                'text': 'Owner cash in the latest fiscal year was 5.0% of revenue, above the 3.0% line.'
            },
            {
                'kind': 'cash_returned',
                'text': 'The company paid $150 million to buy back shares and $20 million in dividends over the period.'
            },
            {
                'kind': 'costs_fell',
                'text': 'Operating costs fell from 55.0% of revenue in 2021 to 50.0% in 2025.'
            }
        ])

        # The latest 12 months are better than the whole period, capital-led, and one-off years
        result = evaluate(company_record(
            ocf=[400, 440, 500, 560, 640, 720, 860],
            capex=0.3,
            sbc=0.14,
            tags={'IncreaseDecreaseInInventories': [annual(2019, -300), annual(2020, 300)]}
        ), None, DATA_DATE)
        self.assertEqual(other_way(result, THRESHOLDS), [
            {
                'kind': 'recent_improvement',
                'text': 'Owner cash in the latest 12 months was -1.0% of revenue, better than the -3.4% over the whole period.'
            },
            {
                'kind': 'one_off',
                'text': 'In 2019 and 2020, inventory moved operating cash flow by more than 25.0% of revenue. Without those years the '
                'cumulative owner-cash margin is -3.3% and P1 is 18.6 instead of 18.7.'
            },
            {
                'kind': 'capital_led',
                'text': 'Capital spending was 2.1 times stock pay. The shortfall is mostly investment, not stock pay.'
            }
        ])

        # Every year is a one-off year
        result = evaluate(company_record(tags={
            'IncreaseDecreaseInInventories': [annual(2019 + index, value * 0.3) for index, value in enumerate(REVENUE)],
            'CashProvidedByUsedInOperatingActivitiesDiscontinuedOperations': [annual(2025, 900)],
            'PaymentsOfDividends': [annual(2025, 20)]
        }), None, DATA_DATE)
        self.assertEqual(other_way(result, THRESHOLDS), [
            {
                'kind': 'one_off',
                'text': 'In 2019, 2020, 2021, 2022, 2023, 2024 and 2025, discontinued operations and inventory moved operating cash '
                'flow by more than 25.0% of revenue.'
            },
            {
                'kind': 'cash_returned',
                'text': 'The company paid $20 million in dividends over the period.'
            }
        ])


    def test_index_row(self):
        self.assertEqual(index_row(evaluate(company_record(), 7372, DATA_DATE), INFO), ROW)

        # No company information, no cost line, a one-off year and a share count
        result = evaluate(company_record(tags={
            'GrossProfit': None,
            'IncreaseDecreaseInInventories': [annual(2019, -300)],
            'WeightedAverageNumberOfDilutedSharesOutstanding': [
                annual(2019 + index, 100 * 1.05 ** index / 1e6) for index in range(7)
            ]
        }), None, DATA_DATE)
        result['rank'] = 4
        self.assertEqual(index_row(result, {}), {
            **ROW,
            'ticker': None,
            'exchange': None,
            'sic': None,
            'sicDescription': None,
            'rank': 4,
            'screenScore': None,
            'p1Ex': 18.63,
            'cumMarginEx': -0.02,
            'p2b': None,
            'costChange': None,
            'costMethod': None,
            'costFirst': None,
            'costLast': None,
            'shareGrowth': 0.05,
            'shareGrowthFive': 0.05,
            'flags': ['no_cost_line', 'one_off_years']
        })

        # An excluded industry has its inputs but no scores
        insider = insider_summary(TRANSACTIONS, 2025, THRESHOLDS)
        self.assertEqual(index_row(evaluate(company_record(), 6021, DATA_DATE, insider=insider), INFO), {
            **ROW,
            **INSIDER_ROW,
            'sic': 6021,
            'type': 'excluded',
            'excluded': 'bank',
            'screenScore': None,
            'p1': None,
            'p1Years': None,
            'p1Cum': None,
            'p1Latest': None,
            'p2b': None,
            'p3': None,
            'p3Years': None,
            'p3Ratio': None,
            'threeScore': None
        })

        # Insiders
        self.assertEqual(index_row(evaluate(company_record(), 7372, DATA_DATE, insider=insider), INFO), {**ROW, **INSIDER_ROW})


    def test_insider_json(self):
        self.assertIsNone(insider_json(None))

        def amounts(**kwargs):
            return {'sales': 0, 'purchases': 0, 'withheld': 0, 'toIssuer': 0, 'grants': 0, 'optionGrants': 0, **kwargs}

        self.assertEqual(insider_json(insider_summary(TRANSACTIONS, 2025, THRESHOLDS))['quarters'], [])
        quarters = [
            {'start': '2024-01-01', 'end': '2024-03-31', 'buybacks': 10e6, 'accn': 'Q1'},
            {'start': '2024-04-01', 'end': '2024-06-30', 'buybacks': 0.4, 'accn': 'Q2'}
        ]
        insider = insider_json(insider_summary(TRANSACTIONS, 2025, THRESHOLDS, quarters))
        self.assertEqual(sorted(insider), [
            'bothYears', 'buybackQuarters', 'buybacks', 'giftShares', 'grantShares', 'grants', 'insiders', 'oddPrices', 'optionGrants',
            'people', 'purchases', 'quarters', 'ratioReason', 'sales', 'salesInBuybackQuarters', 'salesInQuarters', 'salesToGrants',
            'salesToStockGrants', 'sellers', 'toIssuer', 'unvaluedShares', 'withheld', 'years'
        ])
        self.assertEqual(insider['quarters'], [
            {'start': '2024-01-01', 'end': '2024-03-31', 'buybacks': 10000000, 'accn': 'Q1', 'sales': 102000},
            {'start': '2024-04-01', 'end': '2024-06-30', 'buybacks': 0, 'accn': 'Q2', 'sales': 0}
        ])
        self.assertEqual({key: value for key, value in insider.items() if key not in ('people', 'years', 'quarters')}, {
            'buybackQuarters': 2,
            'buybacks': 10000000,
            'salesInQuarters': 102000,
            'salesInBuybackQuarters': 102000,
            'grantShares': 7000,
            'giftShares': 305,
            'bothYears': 1,
            'ratioReason': None,
            'unvaluedShares': 0,
            'oddPrices': 1,
            'insiders': 3,
            'sellers': 2,
            'salesToGrants': 0.269,
            'salesToStockGrants': 1.002,
            **amounts(sales=110200, purchases=4000, withheld=5500, toIssuer=540, grants=110000, optionGrants=300000)
        })
        self.assertEqual(insider['years'][3], {
            'year': 2024, 'grantShares': 7000, 'giftShares': 300,
            **amounts(sales=102000, withheld=5500, toIssuer=540, grants=110000, optionGrants=300000)
        })
        self.assertEqual([person['name'] for person in insider['people']], ['Doe Jane', 'Roe Rich'])
        self.assertEqual(insider['people'][1], {
            'cik': 1002,
            'name': 'Roe Rich',
            'title': 'Director',
            **amounts(sales=8200),
            'filings': [{'accn': 'B1', 'filed': '2025-02-04', **amounts(sales=8200)}]
        })
        self.assertIsInstance(insider['sales'], int)


    def test_insider_totals(self):
        quarters = [
            {'start': '2024-01-01', 'end': '2024-03-31', 'buybacks': 10e6, 'accn': 'Q1'},
            {'start': '2025-01-01', 'end': '2025-03-31', 'buybacks': 0, 'accn': 'Q5'}
        ]
        insider = insider_summary(TRANSACTIONS, 2025, THRESHOLDS, quarters)
        net_seller = {**insider, 'salesToGrants': 1.01}
        no_ratio = {**insider, 'salesToGrants': None}
        results = [
            {'insider': insider, 'five': {'ownerCash': 110200}},
            {'insider': None, 'five': {'ownerCash': 5e9}},
            {'insider': net_seller, 'five': {'ownerCash': -1e6}},
            {'insider': no_ratio, 'five': {'ownerCash': 110199.6}}
        ]
        self.assertEqual(insider_totals(results), {
            'companies': 3,
            'soldMore': 1,
            'ownerCash': -779600,
            'tookMore': 2,
            'quarters': 6,
            'buybackQuarters': 3,
            'sales': 330600,
            'purchases': 12000,
            'withheld': 16500,
            'toIssuer': 1620,
            'grants': 330000,
            'optionGrants': 900000,
            'buybacks': 30000000,
            'salesInQuarters': 330600,
            'salesInBuybackQuarters': 306000
        })
        self.assertEqual(insider_totals([]), NO_INSIDERS)


    def test_buyback_totals(self):
        def result(buybacks, withholding, share_growth):
            return {'five': {'buybacks': buybacks, 'withholding': withholding, 'shareGrowth': share_growth}}

        self.assertEqual(buyback_totals([
            # Bought back shares: the share count rose, fell, and did not change
            result(100e6, 10e6, 0.02),
            result(200e6, 0, -0.01),
            result(50e6, 5e6, 0),
            # Left out: no buybacks, and a share count that cannot be followed
            result(0, 7e6, 0.05),
            result(900e6, 0, None)
        ]), {'companies': 3, 'rose': 1, 'spent': 365000000, 'spentRose': 110000000})
        self.assertEqual(buyback_totals([]), {'companies': 0, 'rose': 0, 'spent': 0, 'spentRose': 0})


    def test_company_json(self):
        result = evaluate(company_record(tags={
            'IncreaseDecreaseInInventories': [annual(2025, -600)],
            'PaymentsForRepurchaseOfCommonStock': [annual(2025, 150)],
            'NetIncomeLoss': [annual(2025, -30)]
        }), 7372, DATA_DATE)
        company = company_json(result, INFO, THRESHOLDS)
        self.assertEqual(sorted(company), [
            'cost', 'formerNames', 'insider', 'otherWay', 'row', 'shareReason', 'spending', 'summary', 'ttm', 'ttmReason', 'years'
        ])
        self.assertIsNone(company['insider'])
        self.assertEqual(company['spending'], {})
        self.assertEqual(company['row'], {
            **ROW, 'p1Ex': 18.63, 'cumMarginEx': -0.02, 'buybacks': 150e6, 'buybacksFive': 150000000, 'flags': ['one_off_years']
        })
        self.assertEqual(company['formerNames'], ['Old Test Co'])
        self.assertEqual(company['summary'], SUMMARY)
        self.assertEqual([item['kind'] for item in company['otherWay']], ['one_off', 'cash_returned'])
        self.assertEqual(company['shareReason'], 'share count missing for the first or last year')
        self.assertIsNone(company['ttmReason'])
        self.assertEqual(company['ttm'], {
            'end': '2026-09-30',
            'sources': ['0000000001-26-000030', '0000000001-25-000030'],
            'rev': 2150e6,
            'ocf': 258e6,
            'sbc': 258e6,
            'capex': 43e6,
            'fcf': 215e6,
            'ownerCash': -43e6,
            'margin': -0.02
        })
        self.assertEqual(company['cost'], {
            'method': 1,
            'methodText': 'gross profit - operating income',
            'firstYear': '2021',
            'firstCost': 687.5e6,
            'firstRatio': 0.55,
            'firstFacts': [
                {'v': 750e6, 'accn': '0000000001-22-000010', 'filed': '2022-02-15', 'form': '10-K', 'tag': 'GrossProfit'},
                {'v': 62.5e6, 'accn': '0000000001-22-000010', 'filed': '2022-02-15', 'form': '10-K', 'tag': 'OperatingIncomeLoss'}
            ],
            'lastYear': '2025',
            'lastCost': 1100e6,
            'lastRatio': 0.55,
            'lastFacts': [
                {'v': 1200e6, 'accn': '0000000001-26-000010', 'filed': '2026-02-15', 'form': '10-K', 'tag': 'GrossProfit'},
                {'v': 100e6, 'accn': '0000000001-26-000010', 'filed': '2026-02-15', 'form': '10-K', 'tag': 'OperatingIncomeLoss'}
            ],
            'change': 0.0
        })
        self.assertEqual([year['fy'] for year in company['years']], ['2019', '2020', '2021', '2022', '2023', '2024', '2025'])

        def fact(value, tag):
            return {'v': value, 'accn': '0000000001-26-000010', 'filed': '2026-02-15', 'form': '10-K', 'tag': tag}

        self.assertEqual(company['years'][-1], {
            'fy': '2025',
            'end': '2025-12-31',
            'start': '2025-01-01',
            'rev': fact(2000e6, 'RevenueFromContractWithCustomerExcludingAssessedTax'),
            'ocf': fact(240e6, 'NetCashProvidedByUsedInOperatingActivities'),
            'capexBase': fact(40e6, 'PaymentsToAcquirePropertyPlantAndEquipment'),
            'capexSoftware': None,
            'capex': 40e6,
            'sbc': fact(240e6, 'ShareBasedCompensation'),
            'fcf': 200e6,
            'ownerCash': -40e6,
            'margin': -0.02,
            'oneOff': [{'cause': 'inventory', 'v': -600e6, 'fact': fact(-600e6, 'IncreaseDecreaseInInventories')}],
            'buybacks': fact(150e6, 'PaymentsForRepurchaseOfCommonStock'),
            'dividends': None,
            'withholding': None,
            'netIncome': fact(-30e6, 'NetIncomeLoss'),
            'shares': None
        })
        self.assertEqual(company['years'][0]['oneOff'], [])

        # No latest 12 months, no cost line, no capital spending, no company information
        result = evaluate(company_record(quarters=False, tags={
            'GrossProfit': None,
            'PaymentsToAcquirePropertyPlantAndEquipment': None
        }), None, DATA_DATE)
        company = company_json(result, {}, THRESHOLDS)
        self.assertIsNone(company['ttm'])
        self.assertEqual(company['ttmReason'], 'no quarterly report since the latest fiscal year')
        self.assertIsNone(company['cost'])
        self.assertIsNone(company['years'][-1]['capex'])
        self.assertEqual(company['formerNames'], [])

        # Insiders, and spending by kind
        record = company_record(tags={
            'SellingAndMarketingExpense': [annual(2019 + index, value * 0.3) for index, value in enumerate(REVENUE)]
        })
        result = evaluate(record, None, DATA_DATE, insider=insider_summary(TRANSACTIONS, 2025, THRESHOLDS))
        company = company_json(result, {}, THRESHOLDS)
        self.assertEqual((company['insider']['sales'], len(company['insider']['people'])), (110200, 2))
        tag = 'SellingAndMarketingExpense'
        self.assertEqual(company['spending'], {'sm': {
            'firstRatio': 0.3,
            'firstFact': {'v': 375e6, 'accn': '0000000001-22-000010', 'filed': '2022-02-15', 'form': '10-K', 'tag': tag},
            'lastRatio': 0.3,
            'lastFact': {'v': 600e6, 'accn': '0000000001-26-000010', 'filed': '2026-02-15', 'form': '10-K', 'tag': tag}
        }})


    def test_check_output(self):
        _, _, results, funnel = screen()
        infos = dict.fromkeys(range(1, 6), INFO)
        rows = [index_row(result, INFO) for result in results]
        self.assertEqual([(row['rank'], row['name']) for row in rows], [
            (1, 'Capital Co'), (2, 'Test Co'), (None, 'No Cost Line Co'), (None, 'Cash Co'), (None, 'Bank Co')
        ])
        self.assertEqual(check_output(rows, funnel, infos), [])

        # Problems
        rows[0]['p1'] = 26
        rows[0]['screenScore'] = 51
        rows[1]['rank'] = 3
        rows[2]['rank'] = 4
        rows[4]['rank'] = 5
        del infos[4]
        self.assertEqual(check_output(rows, {**funnel, 'stockPay': 0}, infos), [
            'No companies passed the screen',
            'Ranks are not 1 to N',
            'Capital Co (CIK 2): P1 is out of range',
            'Capital Co (CIK 2): the screen score is out of range',
            'No Cost Line Co (CIK 3): ranked without passing the screen',
            'Cash Co (CIK 4): no SEC company information, so the industry test was not applied',
            'Bank Co (CIK 5): ranked without passing the screen'
        ])


    def test_write_json(self):
        with TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, 'sub', 'test.json')
            write_json(path, {'b': 1, 'a': [1.5, None]})
            with open(path, 'r', encoding='utf-8') as json_file:
                self.assertEqual(json_file.read(), '{"a":[1.5,null],"b":1}\n')


    def test_file_sha256(self):
        with TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, 'test.txt')
            with open(path, 'w', encoding='utf-8') as text_file:
                text_file.write('abc')
            self.assertEqual(file_sha256(path), 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad')


    def test_build_meta(self):
        records, sics, results, funnel = screen()
        report = sensitivity(records, sics, DATA_DATE, results)
        meta = build_meta(results, funnel, 20609, SOURCES, report)
        self.assertEqual(sorted(meta), [
            'buybackShares', 'cost', 'costMethods', 'dataDate', 'excluded', 'funnel', 'insider', 'latest', 'methodVersion',
            'persistence', 'sensitivity', 'sicExclusions', 'sources', 'thresholds', 'totals', 'types'
        ])
        self.assertIsNone(meta['insider'])
        self.assertEqual(meta['persistence'], {'fivePlus': 3, 'latestAbove': 0})
        self.assertEqual(meta['buybackShares'], {
            'screened': {'companies': 0, 'rose': 0, 'spent': 0, 'spentRose': 0},
            'notCapitalLed': {'companies': 0, 'rose': 0, 'spent': 0, 'spentRose': 0},
            'cashGenerative': {'companies': 0, 'rose': 0, 'spent': 0, 'spentRose': 0}
        })
        self.assertEqual(meta['methodVersion'], '1.0.0')
        self.assertEqual(meta['dataDate'], DATA_DATE)
        self.assertEqual(meta['sources'], SOURCES)
        self.assertEqual(meta['thresholds'], {**THRESHOLDS, 'prefilter_revenue': 5e8})
        self.assertEqual(meta['sicExclusions'][0], {'first': 2834, 'last': 2834, 'group': 'drug developer'})
        self.assertEqual(meta['costMethods'], {
            '1': 'gross profit - operating income',
            '2': 'total costs - cost of revenue',
            '3': 'revenue - operating income - cost of revenue'
        })
        self.assertEqual(meta['funnel'], {
            'inFile': 20609,
            'prefilter': 5,
            'current': 5,
            'revenue': 5,
            'years': 5,
            'growth': 5,
            'industry': 4,
            'lowMargin': 3,
            'stockPay': 3,
            'ranked': 2,
            'rankedThree': 0
        })
        self.assertEqual(meta['types'], {'stock_pay': 3, 'excluded': 1, 'cash_generative': 1})
        self.assertEqual(meta['excluded'], {'bank': 1})
        self.assertEqual(meta['totals']['screened'], {
            'companies': 3,
            'cumRevenue': 30450e6,
            'cumFcf': 3045e6,
            'cumSbc': 3654e6,
            'cumOwnerCash': -609e6,
            'cumCapex': 3451e6,
            'buybacks': 0,
            'dividends': 0,
            'withholding': 0
        })
        self.assertEqual(meta['totals']['notCapitalLed']['companies'], 2)
        self.assertEqual(meta['totals']['notCapitalLed']['cumCapex'], 406e6)
        self.assertEqual(meta['latest'], {'cleared': 0, 'negative': 3, 'fiscalYearBasis': 1})
        self.assertEqual(meta['cost'], {'full': 2, 'zero': 0, 'missing': 1, 'missingAll': 1})
        self.assertIs(meta['sensitivity'], report)

        # A cash-generative latest year, and costs that fell more than ten points
        records = [company_record(
            sbc=[120, 132, 150, 168, 192, 216, 100], quarters=False, operating=[50, 55, 62.5, 70, 80, 90, 400]
        )]
        results, funnel = run_screen(records, {}, DATA_DATE)
        meta = build_meta(results, funnel, 1, SOURCES, [])
        self.assertEqual(meta['latest'], {'cleared': 1, 'negative': 0, 'fiscalYearBasis': 1})
        self.assertEqual(meta['cost'], {'full': 0, 'zero': 1, 'missing': 0, 'missingAll': 0})
        self.assertEqual(meta['persistence'], {'fivePlus': 0, 'latestAbove': 1})

        # Insiders: the first company is capital-led
        insider = insider_summary(TRANSACTIONS, 2025, THRESHOLDS)
        records, sics, _, _ = screen()
        results, funnel = run_screen(records, sics, DATA_DATE, insiders={1: insider, 2: {**insider, 'salesToGrants': 2.0}})
        meta = build_meta(results, funnel, 5, SOURCES, [], (2021, 2025))
        self.assertEqual(meta['insider'], {
            'firstYear': 2021,
            'lastYear': 2025,
            'screened': {
                **NO_INSIDERS, 'companies': 2, 'soldMore': 1, 'ownerCash': -322000000, 'tookMore': 2, 'sales': 220400, 'purchases': 8000,
                'withheld': 11000, 'toIssuer': 1080, 'grants': 220000, 'optionGrants': 600000
            },
            'notCapitalLed': {
                **NO_INSIDERS, 'companies': 1, 'ownerCash': -161000000, 'tookMore': 1, 'sales': 110200, 'purchases': 4000, 'withheld': 5500,
                'toIssuer': 540, 'grants': 110000, 'optionGrants': 300000
            },
            'cashGenerative': NO_INSIDERS
        })


    def test_write_output(self):
        _, _, results, funnel = screen()
        infos = dict.fromkeys(range(1, 6), INFO)
        meta = build_meta(results, funnel, 20609, SOURCES, [])
        with TemporaryDirectory() as temp_dir:
            # A file for a company no longer in the index, and a file that is not a company's
            os.makedirs(os.path.join(temp_dir, 'company'))
            for name in ('99.json', 'README.txt'):
                with open(os.path.join(temp_dir, 'company', name), 'w', encoding='utf-8') as stale_file:
                    stale_file.write('{}')

            self.assertEqual(write_output(temp_dir, results, infos, meta), [])
            self.assertEqual(sorted(os.listdir(temp_dir)), ['archive', 'company', 'index.csv', 'index.json', 'meta.json'])
            self.assertEqual(sorted(os.listdir(os.path.join(temp_dir, 'archive'))), [DATA_DATE, 'builds.json'])
            self.assertEqual(
                sorted(os.listdir(os.path.join(temp_dir, 'company'))),
                ['1.json', '2.json', '3.json', '4.json', '5.json', 'README.txt']
            )

            with open(os.path.join(temp_dir, 'index.json'), 'r', encoding='utf-8') as index_file:
                index = json.load(index_file)
            self.assertEqual(sorted(index), ['companies', 'dataDate', 'methodVersion'])
            self.assertEqual((index['dataDate'], index['methodVersion']), (DATA_DATE, '1.0.0'))
            self.assertEqual([company['cik'] for company in index['companies']], [2, 1, 3, 4, 5])
            self.assertEqual(index['companies'][1], {**ROW, 'rank': 2})

            with open(os.path.join(temp_dir, 'meta.json'), 'r', encoding='utf-8') as meta_file:
                self.assertEqual(json.load(meta_file), meta)

            with open(os.path.join(temp_dir, 'company', '1.json'), 'r', encoding='utf-8') as company_file:
                company = json.load(company_file)
            self.assertEqual(company['row'], {**ROW, 'rank': 2})
            self.assertEqual(company['summary'], SUMMARY)

            with open(os.path.join(temp_dir, 'index.csv'), 'r', encoding='utf-8') as csv_file:
                lines = csv_file.read().splitlines()
            self.assertEqual(lines[0], ','.join(CSV_FIELDS))
            self.assertEqual(len(lines), 6)
            self.assertEqual(
                lines[2],
                '2,,Test Co,TEST,1,stock_pay,,7372,Services-Prepackaged Software,37.27,,18.63,10.0,3.73,4.9,13,,7,2019,2025,2025-12-31,'
                '2000000000.0,2.0,7,-0.02,,-0.02,-0.02,ttm,2026-09-30,10150000000.0,1015000000.0,1218000000.0,203000000.0,'
                '-203000000.0,0.1,0.12,0,0,0,0.167,False,,0.0,1,0.55,0.55,,,,,,,,,,,7,-161000000,0,0,,'
            )
            self.assertTrue(lines[3].endswith(',no_cost_line latest_is_fiscal_year'))
            self.assertTrue(lines[5].startswith(',,Bank Co,TEST,5,excluded,bank,6021,Services-Prepackaged Software,,,,,,,,,7,2019,'))

            # An earlier build stays in the archive; a build with the same data date is replaced
            write_archive(temp_dir, {'dataDate': '2026-08-14', 'methodVersion': '0.9.0', 'funnel': {'ranked': 1}})
            write_archive(temp_dir, {'dataDate': DATA_DATE, 'methodVersion': '1.0.1', 'funnel': {'ranked': 3}})
            archive_dir = os.path.join(temp_dir, 'archive')
            self.assertEqual(sorted(os.listdir(archive_dir)), ['2026-08-14', DATA_DATE, 'builds.json'])
            self.assertEqual(sorted(os.listdir(os.path.join(archive_dir, DATA_DATE))), ['index.csv', 'index.json', 'meta.json'])
            with open(os.path.join(archive_dir, DATA_DATE, 'meta.json'), 'r', encoding='utf-8') as meta_file:
                self.assertEqual(json.load(meta_file), meta)
            with open(os.path.join(archive_dir, 'builds.json'), 'r', encoding='utf-8') as builds_file:
                self.assertEqual(json.load(builds_file), [
                    {'dataDate': DATA_DATE, 'methodVersion': '1.0.1', 'ranked': 3},
                    {'dataDate': '2026-08-14', 'methodVersion': '0.9.0', 'ranked': 1}
                ])

        # Nothing is written when a check fails
        with TemporaryDirectory() as temp_dir:
            self.assertEqual(write_output(temp_dir, results, {}, meta), [
                f'{name} (CIK {cik}): no SEC company information, so the industry test was not applied'
                for name, cik in (('Capital Co', 2), ('Test Co', 1), ('No Cost Line Co', 3), ('Cash Co', 4), ('Bank Co', 5))
            ])
            self.assertEqual(os.listdir(temp_dir), [])
