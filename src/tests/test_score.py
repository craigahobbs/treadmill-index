# Licensed under the MIT License
# https://github.com/craigahobbs/treadmill-index/blob/main/LICENSE

# pylint: disable=missing-class-docstring, missing-function-docstring, missing-module-docstring

import unittest

from treadmill_index.score import SENSITIVITY_KEYS, THRESHOLDS, calendar_years, company_series, cost_change, cost_line, costs_sign, \
    evaluate, find_period, five_years, group_totals, insiders_sign, latest_twelve_months, lin, loose_thresholds, low_run, \
    one_off_years, pillar_one, run_screen, sensitivity, share_change, sic_exclusion, spending_change, window_years, year_label

from .helpers import DATA_DATE, REVENUE, annual, company_record, insider_fixture, nine_months, unit


def annuals(tag_values, first_year=2019):
    return [annual(first_year + index, value) for index, value in enumerate(tag_values)]


class TestScore(unittest.TestCase):

    def test_lin(self):
        self.assertEqual(lin(0.05, 0.05, -0.10, 8), 0)
        self.assertEqual(lin(0.10, 0.05, -0.10, 8), 0)
        self.assertEqual(lin(-0.10, 0.05, -0.10, 8), 8)
        self.assertEqual(lin(-0.50, 0.05, -0.10, 8), 8)
        self.assertAlmostEqual(lin(-0.025, 0.05, -0.10, 8), 4)


    def test_year_label(self):
        self.assertEqual(year_label('2025-12-31'), '2025')
        self.assertEqual(year_label('2025-04-30'), '2025')
        self.assertEqual(year_label('2025-03-31'), '2024')

        # A 52- or 53-week year that ends near March 31 has one label, whichever side of it the year ends
        self.assertEqual((year_label('2024-03-30'), year_label('2023-04-01'), year_label('2022-04-02')), ('2023', '2022', '2021'))
        self.assertEqual((year_label('2025-04-07'), year_label('2025-04-08')), ('2024', '2025'))
        self.assertEqual(year_label('2026-01-31'), '2025')


    def test_sic_exclusion(self):
        self.assertIsNone(sic_exclusion(None))
        self.assertIsNone(sic_exclusion(7372))
        self.assertEqual(sic_exclusion(2834), 'drug developer')
        self.assertEqual(sic_exclusion(6022), 'bank')
        self.assertEqual(sic_exclusion(6162), 'lender')
        self.assertEqual(sic_exclusion(6282), 'broker or asset manager')
        self.assertEqual(sic_exclusion(6726), 'asset manager')
        self.assertEqual(sic_exclusion(6331), 'insurer')
        self.assertIsNone(sic_exclusion(6411))
        self.assertEqual(sic_exclusion(6798), 'REIT')


    def test_company_series(self):
        series = company_series(company_record())
        self.assertEqual([year['fy'] for year in series], ['2019', '2020', '2021', '2022', '2023', '2024', '2025'])
        last = series[-1]
        self.assertEqual(last['end'], '2025-12-31')
        self.assertEqual(last['rev'][0], 2000e6)
        self.assertEqual(last['capexBase'][0], 40e6)
        self.assertIsNone(last['capexSoftware'])
        self.assertFalse(last['capexMissing'])
        self.assertEqual(last['capex'], 40e6)
        self.assertEqual(last['fcf'], 200e6)
        self.assertEqual(last['ownerCash'], -40e6)
        self.assertAlmostEqual(last['margin'], -0.02)


    def test_company_series_tags(self):
        record = company_record(tags={
            # Capital spending: the productive-assets tag stands in for a missing property tag, software is added,
            # outflows may be reported negative, and a year with neither tag is counted as missing
            'PaymentsToAcquirePropertyPlantAndEquipment': annuals([20, 22, 25]),
            'PaymentsToAcquireProductiveAssets': annuals([99, 99, 99, -28]),
            'PaymentsToDevelopSoftware': annuals([5, 5, 5, 5, -6]),
            # Stock pay: the allocated-expense tag stands in for a missing year; a year with neither is dropped
            'ShareBasedCompensation': annuals([120, 132, 150, 168, 192, 216]),
            'AllocatedShareBasedCompensationExpense': annuals([1, 1, 1, 1, 1, 1, 77]) + [annual(2018, 5)],
            # A year without positive revenue is dropped; a January year end belongs to the prior year
            'RevenueFromContractWithCustomerExcludingAssessedTax': annuals(REVENUE) + [
                annual(2018, 0), unit('2025-02-01', '2026-01-31', 2100e6)
            ],
            'NetCashProvidedByUsedInOperatingActivities': annuals([value * 0.12 for value in REVENUE]) + [
                annual(2018, 50), unit('2025-02-01', '2026-01-31', 250e6)
            ]
        })
        series = company_series(record)
        self.assertEqual([year['fy'] for year in series], ['2019', '2020', '2021', '2022', '2023', '2024', '2025'])
        self.assertEqual([year['capex'] for year in series], [25e6, 27e6, 30e6, 33e6, 6e6, 0, 0])
        self.assertEqual([year['capexMissing'] for year in series], [False, False, False, False, False, True, True])
        self.assertEqual(series[5]['sbc'][0], 216e6)
        self.assertEqual(series[6]['sbc'][0], 77e6)
        self.assertEqual(series[6]['sbc'][5], 'AllocatedShareBasedCompensationExpense')

        # The later of two year ends with the same label wins - there is no stock pay for the January year end
        self.assertEqual(series[6]['end'], '2025-12-31')
        record['annual']['sbc']['2026-01-31'] = [80e6, 'A', '2026-03-20', '10-K', '2025-02-01', 'ShareBasedCompensation']
        series = company_series(record)
        self.assertEqual(len(series), 7)
        self.assertEqual(series[6]['end'], '2026-01-31')
        self.assertEqual(series[6]['rev'][0], 2100e6)

        # ... unless only the earlier year end's revenue is from an annual report: the other is not the fiscal year
        record['annual']['rev']['2026-01-31'][3] = '8-K'
        self.assertEqual(company_series(record)[6]['end'], '2025-12-31')


    def test_find_period(self):
        facts = {
            '2026-01-01|2026-09-30': [1],
            '2025-12-28|2026-09-27': [2],
            '2025-01-01|2025-09-30': [3]
        }
        self.assertEqual(find_period(facts, '2026-01-01', '2026-09-30'), [1])
        self.assertEqual(find_period(facts, '2025-12-29', '2026-09-26'), [2])
        self.assertEqual(find_period(facts, '2026-01-03', '2026-09-30'), [1])
        self.assertEqual(find_period(facts, '2025-01-05', '2025-10-04'), [3])
        self.assertIsNone(find_period(facts, '2025-01-01', '2025-06-30'))
        self.assertIsNone(find_period(facts, '2025-04-01', '2025-09-30'))
        self.assertIsNone(find_period({}, '2025-01-01', '2025-09-30'))


    def test_latest_twelve_months(self):
        record = company_record()
        figures, reason = latest_twelve_months(record, company_series(record)[-1])
        self.assertIsNone(reason)
        self.assertEqual(figures, {
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


    def test_latest_twelve_months_no_capex(self):
        # No capital spending in the fiscal year, and none in the quarters since - an older quarter does not count
        record = company_record(tags={
            'PaymentsToAcquirePropertyPlantAndEquipment': [nine_months(2025, 30)],
            'PaymentsToDevelopSoftware': [nine_months(2025, 3)]
        })
        figures, reason = latest_twelve_months(record, company_series(record)[-1])
        self.assertIsNone(reason)
        self.assertEqual(figures['capex'], 0)
        self.assertEqual(figures['fcf'], 258e6)


    def test_latest_twelve_months_unusable(self):
        # No quarterly report since the latest fiscal year
        record = company_record(quarters=False)
        self.assertEqual(
            latest_twelve_months(record, company_series(record)[-1]),
            (None, 'no quarterly report since the latest fiscal year')
        )

        # A figure is missing for the year-earlier period
        record = company_record(tags={
            'ShareBasedCompensation': annuals([value * 0.12 for value in REVENUE]) + [nine_months(2026, 198)]
        })
        self.assertEqual(
            latest_twelve_months(record, company_series(record)[-1]),
            (None, 'quarterly ShareBasedCompensation is missing for the latest or the year-earlier period')
        )

        # A figure is missing for the latest period
        record = company_record(tags={
            'ShareBasedCompensation': annuals([value * 0.12 for value in REVENUE]) + [nine_months(2025, 180)]
        })
        self.assertEqual(
            latest_twelve_months(record, company_series(record)[-1]),
            (None, 'quarterly ShareBasedCompensation is missing for the latest or the year-earlier period')
        )

        # Capital spending is tagged in the quarters but not in the fiscal year
        record = company_record(tags={'PaymentsToDevelopSoftware': [nine_months(2026, 3)]})
        self.assertEqual(
            latest_twelve_months(record, company_series(record)[-1]),
            (None, 'capital spending is tagged in the quarters but not in the fiscal year')
        )

        # Revenue is not positive
        record = company_record(tags={
            'RevenueFromContractWithCustomerExcludingAssessedTax': annuals(REVENUE) + [nine_months(2025, 2500), nine_months(2026, 100)]
        })
        self.assertEqual(
            latest_twelve_months(record, company_series(record)[-1]),
            (None, 'latest-12-month revenue is not positive')
        )


    def test_cost_line(self):
        annual_facts = company_record(tags={
            'CostsAndExpenses': annuals([value * 0.95 for value in REVENUE]),
            'CostOfGoodsAndServicesSold': annuals([value * 0.4 for value in REVENUE])
        })['annual']
        end = '2025-12-31'

        value, facts = cost_line(annual_facts, end, 1)
        self.assertEqual(value, 1100e6)
        self.assertEqual([fact[5] for fact in facts], ['GrossProfit', 'OperatingIncomeLoss'])

        value, facts = cost_line(annual_facts, end, 2)
        self.assertEqual(value, 1100e6)
        self.assertEqual([fact[5] for fact in facts], ['CostsAndExpenses', 'CostOfGoodsAndServicesSold'])

        value, facts = cost_line(annual_facts, end, 3)
        self.assertEqual(value, 1100e6)
        self.assertEqual(
            [fact[5] for fact in facts],
            ['RevenueFromContractWithCustomerExcludingAssessedTax', 'OperatingIncomeLoss', 'CostOfGoodsAndServicesSold']
        )

        # Missing figures
        for method in (1, 2, 3):
            self.assertEqual(cost_line(annual_facts, '2030-12-31', method), (None, None))
        self.assertEqual(cost_line(company_record()['annual'], end, 2), (None, None))
        self.assertEqual(cost_line(company_record()['annual'], end, 3), (None, None))


    def test_cost_change(self):
        # The first method: costs fall from 55% of revenue in 2021 to 50% in 2025
        record = company_record(operating=[50, 55, 62.5, 70, 80, 90, 200])
        series = company_series(record)
        cost = cost_change(record, series, THRESHOLDS)
        self.assertEqual(cost['method'], 1)
        self.assertEqual((cost['firstYear'], cost['firstCost'], cost['firstRatio']), ('2021', 687.5e6, 0.55))
        self.assertEqual((cost['lastYear'], cost['lastCost'], cost['lastRatio']), ('2025', 1000e6, 0.5))
        self.assertEqual(cost['lastGross'], 1200e6)
        self.assertAlmostEqual(cost['change'], -5)
        self.assertEqual([fact[5] for fact in cost['firstFacts']], ['GrossProfit', 'OperatingIncomeLoss'])
        self.assertEqual([fact[1] for fact in cost['lastFacts']], ['0000000001-26-000010', '0000000001-26-000010'])

        # The cost line is built the same way in both years: gross profit is missing in the first year, so the second
        # method is used, and gross profit is revenue less cost of revenue
        record = company_record(tags={
            'GrossProfit': annuals([1200], first_year=2025),
            'CostsAndExpenses': annuals([value * 0.95 for value in REVENUE]),
            'CostOfRevenue': annuals([value * 0.35 for value in REVENUE])
        })
        cost = cost_change(record, series, THRESHOLDS)
        self.assertEqual(cost['method'], 2)
        self.assertAlmostEqual(cost['change'], 0)
        self.assertAlmostEqual(cost['lastGross'], 1300e6)

        # The third method, with the other cost-of-revenue tag
        record = company_record(tags={'GrossProfit': None, 'CostOfGoodsAndServicesSold': annuals([value * 0.35 for value in REVENUE])})
        cost = cost_change(record, series, THRESHOLDS)
        self.assertEqual(cost['method'], 3)
        self.assertAlmostEqual(cost['firstRatio'], 0.6)
        self.assertAlmostEqual(cost['lastGross'], 1300e6)

        # No method works, and a cost line that is not positive
        self.assertIsNone(cost_change(company_record(tags={'GrossProfit': None}), series, THRESHOLDS))
        self.assertIsNone(cost_change(company_record(gross=0.04), series, THRESHOLDS))

        # A company with fewer years than the window has its first year
        record = company_record()
        self.assertEqual(cost_change(record, series[-4:], THRESHOLDS)['firstYear'], '2022')
        self.assertEqual(cost_change(record, series[-5:], THRESHOLDS)['firstYear'], '2021')
        self.assertEqual(window_years(series[-1:], THRESHOLDS), (series[-1], series[-1]))


    def test_costs_sign(self):
        def cost(last_cost, last_gross):
            return {'lastCost': last_cost, 'lastGross': last_gross}

        # No cost line
        self.assertIsNone(costs_sign(None, THRESHOLDS))

        # The share of gross profit that operating costs take: 0 points at 70%, 25 at 100%
        self.assertEqual(costs_sign(cost(700, 1000), THRESHOLDS), {'level': 0.7, 'points': 0})
        self.assertEqual(costs_sign(cost(400, 1000), THRESHOLDS), {'level': 0.4, 'points': 0})
        self.assertAlmostEqual(costs_sign(cost(850, 1000), THRESHOLDS)['points'], 12.5)
        self.assertEqual(costs_sign(cost(1000, 1000), THRESHOLDS), {'level': 1, 'points': 25})
        self.assertEqual(costs_sign(cost(1460, 1000), THRESHOLDS), {'level': 1.46, 'points': 25})

        # With no gross profit at all, operating costs take more than all of it
        self.assertEqual(costs_sign(cost(500, -20), THRESHOLDS), {'level': None, 'points': 25})
        self.assertEqual(costs_sign(cost(500, 0), THRESHOLDS), {'level': None, 'points': 25})


    def test_one_off_years(self):
        record = company_record(tags={
            'IncreaseDecreaseInInventories': annuals([10, 300, -400]),
            'CashProvidedByUsedInOperatingActivitiesDiscontinuedOperations': annuals([0, 0, -500, 20]),
            'ProceedsFromSaleOfMortgageLoansHeldForSale': annuals([0, 0, 0, 0, 5000, 5000]),
            'PaymentsForOriginationOfMortgageLoansHeldForSale': annuals([0, 0, 0, 0, 5500, 5100]),
            'IncreaseDecreaseInLoansHeldForSale': annuals([0, 0, 0, 0, 0, 0, 600])
        })
        found = one_off_years(record, company_series(record), THRESHOLDS)
        self.assertEqual(sorted(found), ['2020', '2021', '2023', '2025'])
        self.assertEqual([cause[:2] for cause in found['2020']], [['inventory', 300e6]])
        self.assertEqual([cause[:2] for cause in found['2021']], [['inventory', -400e6], ['discontinued operations', -500e6]])
        self.assertEqual([cause[:2] for cause in found['2023']], [['lending', -500e6]])
        self.assertEqual([cause[:2] for cause in found['2025']], [['lending', 600e6]])
        self.assertEqual(found['2025'][0][2][5], 'IncreaseDecreaseInLoansHeldForSale')
        self.assertEqual(one_off_years(company_record(), company_series(record), THRESHOLDS), {})


    def test_pillar_one(self):
        series = company_series(company_record())
        p1 = pillar_one(series, -0.02, THRESHOLDS)
        self.assertEqual(p1['lowYears'], 7)
        self.assertAlmostEqual(p1['cumMargin'], -0.02)
        self.assertAlmostEqual(p1['yearsPoints'], 10)
        self.assertAlmostEqual(p1['cumPoints'], 8 * 0.07 / 0.15)
        self.assertAlmostEqual(p1['latestPoints'], 4.9)
        self.assertAlmostEqual(p1['p1'], 10 + 8 * 0.07 / 0.15 + 4.9)

        # Two of seven years under 3%, cumulative above 5%, latest well above 5%
        series = company_series(company_record(sbc=[120, 132, 12, 14, 16, 18, 20]))
        p1 = pillar_one(series, 0.09, THRESHOLDS)
        self.assertEqual(p1['lowYears'], 2)
        self.assertAlmostEqual(p1['yearsPoints'], 10 * 2 / 7)
        self.assertEqual(p1['cumPoints'], 0)
        self.assertEqual(p1['latestPoints'], 0)


    def test_spending_change(self):
        record = company_record(tags={
            'SellingAndMarketingExpense': annuals([value * 0.3 for value in REVENUE[:6]] + [500]),
            'ResearchAndDevelopmentExpense': annuals([value * 0.2 for value in REVENUE[:6]]),
            'GeneralAndAdministrativeExpense': annuals([100, 100], first_year=2024)
        })
        series = company_series(record)

        # Sales and marketing is tagged in the first and last of the latest five years; the others are not
        spending = spending_change(record, series, THRESHOLDS)
        self.assertEqual(sorted(spending), ['sm'])
        self.assertAlmostEqual(spending['sm']['firstRatio'], 0.3)
        self.assertAlmostEqual(spending['sm']['lastRatio'], 0.25)
        self.assertEqual((spending['sm']['firstFact'][0], spending['sm']['firstFact'][5]), (375e6, 'SellingAndMarketingExpense'))
        self.assertEqual(spending['sm']['lastFact'][0], 500e6)

        # A window of two years
        spending = spending_change(record, series, {**THRESHOLDS, 'cost_window_years': 2})
        self.assertEqual(sorted(spending), ['ga', 'sm'])
        self.assertAlmostEqual(spending['ga']['firstRatio'], 100 / 1800)

        # Fewer years than the window, and no spending tags
        self.assertAlmostEqual(spending_change(record, series[-4:], THRESHOLDS)['sm']['firstRatio'], 0.3)
        self.assertEqual(spending_change(company_record(), series, THRESHOLDS), {})


    def test_low_run(self):
        # Under 3% every year
        self.assertEqual(low_run(company_series(company_record()), THRESHOLDS), 7)

        # Above it in the latest year, in an earlier year, and never under it
        self.assertEqual(low_run(company_series(company_record(sbc=[120, 132, 150, 168, 192, 216, 100])), THRESHOLDS), 0)
        self.assertEqual(low_run(company_series(company_record(sbc=[120, 132, 150, 68, 192, 216, 240])), THRESHOLDS), 3)
        self.assertEqual(low_run(company_series(company_record(sbc=0.02)), THRESHOLDS), 0)
        self.assertEqual(low_run([], THRESHOLDS), 0)


    def test_five_years(self):
        record = company_record(tags={
            'PaymentsForRepurchaseOfCommonStock': annuals([10, -20, 30, 40, 50, 60, 70]),
            'PaymentsRelatedToTaxWithholdingForShareBasedCompensation': annuals([1, 2, 3]),
            'WeightedAverageNumberOfDilutedSharesOutstanding': annuals([100, 100, 100, 110, 121, 133.1, 146.41])
        })
        series = company_series(record)

        # The fiscal years 2021 to 2025: owner cash is -2% of revenue; the share count grows 10% a year
        five = five_years(record, series, 2021, 2025, None)
        self.assertAlmostEqual(five.pop('ownerCash'), -161e6)
        self.assertAlmostEqual(five.pop('shareGrowth'), 0.1)
        self.assertEqual(five, {'years': 5, 'insider': None, 'revenue': 8050e6, 'buybacks': 250e6, 'withholding': 3e6})

        # The insiders' amounts over the same years
        insider = insider_fixture(50e6, purchases=1e6, grants=3e6)
        self.assertEqual(five_years(record, series, 2021, 2025, insider)['insider'], {
            'cashOut': 49e6, 'sales': 50e6, 'purchases': 1e6, 'exercised': 0, 'withheld': 0, 'toIssuer': 0, 'grants': 3e6,
            'optionGrants': 0
        })

        # Years the company does not have: the insiders' amounts in them are left out too. And too few years to
        # follow the share count.
        five = five_years(record, series, 2022, 2026, insider_fixture(50e6, year=2026))
        self.assertEqual((five['years'], five['revenue'], five['buybacks'], five['insider']['cashOut']), (4, 6800e6, 220e6, 0))
        self.assertAlmostEqual(five['shareGrowth'], 0.1)
        five = five_years(record, series, 2025, 2029, insider)
        self.assertEqual((five['years'], five['revenue'], five['buybacks'], five['shareGrowth']), (1, 2000e6, 70e6, None))
        self.assertEqual(five['insider']['cashOut'], 49e6)
        self.assertAlmostEqual(five['ownerCash'], -40e6)
        self.assertEqual(five_years(record, series, 2031, 2035, None), {
            'years': 0, 'insider': None, 'revenue': 0, 'ownerCash': 0, 'buybacks': 0, 'withholding': 0, 'shareGrowth': None
        })

        # A share count that cannot be followed
        self.assertIsNone(five_years(company_record(), series, 2021, 2025, None)['shareGrowth'])


    def test_calendar_years(self):
        self.assertEqual(calendar_years('2026-11-20', THRESHOLDS), (2021, 2025))
        self.assertEqual(calendar_years('2027-01-04', {**THRESHOLDS, 'insider_years': 3}), (2024, 2026))


    def test_insiders_sign(self):
        def five(cash_out, revenue=1000e6):
            return {'revenue': revenue, 'insider': {'cashOut': cash_out}}

        # No insider filings, and no revenue in the years
        self.assertIsNone(insiders_sign({'revenue': 1000e6, 'insider': None}, THRESHOLDS))
        self.assertIsNone(insiders_sign(five(5e6, 0), THRESHOLDS))

        # The cash insiders took out as a share of revenue: 0 points at 0.5%, 25 at 3%
        for cash_out, share, points in ((5e6, 0.005, 0), (30e6, 0.03, 25), (270e6, 0.27, 25), (0, 0, 0), (-10e6, -0.01, 0)):
            self.assertEqual(insiders_sign(five(cash_out), THRESHOLDS), {'share': share, 'points': points})
        sign = insiders_sign(five(17.5e6), THRESHOLDS)
        self.assertAlmostEqual(sign['share'], 0.0175)
        self.assertAlmostEqual(sign['points'], 12.5)


    def test_share_change(self):
        tag = 'WeightedAverageNumberOfDilutedSharesOutstanding'

        # Growth of 5% a year
        record = company_record(tags={tag: annuals([100 * 1.05 ** index for index in range(7)])})
        series = company_series(record)
        change, reason = share_change(record, series)
        self.assertAlmostEqual(change, 0.05)
        self.assertIsNone(reason)

        # A missing first or last year, or no counts
        for values in ([0, 105, 110, 116, 122, 128, 134], [100, 105, 110, 116, 122, 128], []):
            record = company_record(tags={tag: annuals(values)})
            self.assertEqual(share_change(record, series), (None, 'share count missing for the first or last year'))

        # A jump up or down
        for values in ([100, 105, 110, 330, 340, 350, 360], [100, 105, 110, 50, 52, 54, 56]):
            record = company_record(tags={tag: annuals(values)})
            self.assertEqual(
                share_change(record, series),
                (None, 'share count jumps in one year (a stock split, or a conversion at listing); not adjusted')
            )


    def test_evaluate(self):
        result = evaluate(company_record(cik=5, name='Five Co'), 7372, DATA_DATE)
        series = result.pop('series')
        annual_facts = result.pop('annual')
        cost = result.pop('cost')
        p1 = result.pop('p1')
        ttm = result.pop('ttm')
        self.assertEqual(len(series), 7)
        self.assertEqual(sorted(annual_facts['rev']), [f'{year}-12-31' for year in range(2019, 2026)])
        self.assertEqual(cost['method'], 1)
        self.assertAlmostEqual(p1['p1'], 10 + 8 * 0.07 / 0.15 + 4.9)
        self.assertEqual(ttm['end'], '2026-09-30')
        self.assertAlmostEqual(result.pop('capexToSbc'), 1 / 6)
        self.assertAlmostEqual(result.pop('latestMargin'), -0.02)
        costs = result.pop('costs')
        self.assertAlmostEqual(costs['level'], 1100 / 1200)
        self.assertAlmostEqual(costs['points'], 25 * (1100 / 1200 - 0.7) / 0.3)
        five = result.pop('five')
        self.assertAlmostEqual(five.pop('ownerCash'), -161e6)
        self.assertEqual(five, {'years': 5, 'insider': None, 'revenue': 8050e6, 'buybacks': 0, 'withholding': 0, 'shareGrowth': None})
        self.assertEqual(result, {
            'stage': 'scored',
            'cik': 5,
            'name': 'Five Co',
            'sic': 7372,
            'excluded': None,
            'type': 'stock_pay',
            'years': 7,
            'firstYear': '2019',
            'lastYear': '2025',
            'lastEnd': '2025-12-31',
            'revenue': 2000e6,
            'growth': 2,
            'cumRevenue': 10150e6,
            'cumFcf': 1015e6,
            'cumSbc': 1218e6,
            'cumCapex': 203e6,
            'cumOwnerCash': -203e6,
            'buybacks': 0,
            'dividends': 0,
            'withholding': 0,
            'latestBasis': 'ttm',
            'latestEnd': '2026-09-30',
            'ttmReason': None,
            'oneOffs': {},
            'p1Ex': None,
            'insider': None,
            'insiders': None,
            'score': None,
            'lowRun': 7,
            'spending': {},
            'shareGrowth': None,
            'shareReason': 'share count missing for the first or last year',
            'flags': ['no_insider_filings'],
            'rank': None
        })


    def test_evaluate_stages(self):
        # No year with revenue, operating cash flow and stock pay
        record = company_record(tags={'NetCashProvidedByUsedInOperatingActivities': None})
        self.assertEqual(evaluate(record, None, DATA_DATE), {'stage': 'no_data'})

        # The latest fiscal year is too old
        self.assertEqual(evaluate(company_record(), None, '2027-07-03'), {'stage': 'not_current'})
        self.assertEqual(evaluate(company_record(), None, '2027-07-02')['stage'], 'scored')

        # Latest revenue under $1B
        self.assertEqual(evaluate(company_record(revenue=(500, 600, 700, 800, 999)), None, DATA_DATE), {'stage': 'small'})

        # Fewer than five years
        self.assertEqual(evaluate(company_record(revenue=(1000, 1200, 1400, 1600)), None, DATA_DATE), {'stage': 'short'})

        # Revenue up less than 50%
        self.assertEqual(evaluate(company_record(revenue=(1000, 1100, 1200, 1300, 1499)), None, DATA_DATE), {'stage': 'slow_growth'})
        self.assertEqual(evaluate(company_record(revenue=(1000, 1100, 1200, 1300, 1500)), None, DATA_DATE)['stage'], 'scored')

        # Other thresholds
        thresholds = {**THRESHOLDS, 'years_min': 4, 'growth_min': 0.4}
        self.assertEqual(evaluate(company_record(revenue=(1000, 1200, 1400, 1600)), None, DATA_DATE, thresholds)['stage'], 'scored')
        self.assertEqual(evaluate(company_record(revenue=(1000, 1100, 1200, 1300, 1400)), None, DATA_DATE, thresholds)['stage'], 'scored')


    def test_evaluate_types(self):
        # An excluded industry
        result = evaluate(company_record(), 6798, DATA_DATE)
        self.assertEqual((result['type'], result['excluded']), ('excluded', 'REIT'))

        # Owner cash of 8% of revenue
        result = evaluate(company_record(sbc=0.02), None, DATA_DATE)
        self.assertEqual((result['type'], result['excluded'], result['sic']), ('cash_generative', None, None))
        self.assertAlmostEqual(result['p1']['p1'], 0)

        # Stock pay is the cause - and is not when it is under 2% of revenue or under half of free cash flow
        self.assertEqual(evaluate(company_record(ocf=0.045, sbc=0.02), None, DATA_DATE)['type'], 'stock_pay')
        self.assertEqual(evaluate(company_record(ocf=0.045, sbc=0.019), None, DATA_DATE)['type'], 'thin_margin')
        thresholds = {**THRESHOLDS, 'sbc_fcf_min': 1.5}
        self.assertEqual(evaluate(company_record(), None, DATA_DATE, thresholds)['type'], 'thin_margin')

        # Negative free cash flow before stock pay
        self.assertEqual(evaluate(company_record(ocf=0.01), None, DATA_DATE)['type'], 'cash_burner')

        # Capital-led: stock pay would be the cause, but capital spending is more than twice it
        result = evaluate(company_record(ocf=0.4, capex=0.3), None, DATA_DATE)
        self.assertEqual(result['type'], 'capital_led')
        self.assertAlmostEqual(result['capexToSbc'], 2.5)
        thresholds = {**THRESHOLDS, 'capital_led_ratio': 2.5}
        self.assertEqual(evaluate(company_record(ocf=0.4, capex=0.3), None, DATA_DATE, thresholds)['type'], 'stock_pay')

        # A cash-generative company with heavy capital spending keeps its type
        result = evaluate(company_record(ocf=0.5, capex=0.3, sbc=0.02), None, DATA_DATE)
        self.assertEqual(result['type'], 'cash_generative')

        # No stock pay
        result = evaluate(company_record(sbc=0), None, DATA_DATE)
        self.assertEqual((result['type'], result['capexToSbc']), ('cash_generative', None))


    def test_evaluate_scores(self):
        # The three signs: P1, costs at 91.7% of gross profit, and insiders who took out 1.75% of five years' revenue
        p1 = 10 + 8 * 0.07 / 0.15 + 4.9
        costs = 25 * (1100 / 1200 - 0.7) / 0.3
        insider = insider_fixture(0.0175 * 8050e6)
        result = evaluate(company_record(), None, DATA_DATE, insider=insider)
        self.assertIs(result['insider'], insider)
        self.assertAlmostEqual(result['insiders']['share'], 0.0175)
        self.assertAlmostEqual(result['insiders']['points'], 12.5)
        self.assertAlmostEqual(result['score'], p1 + (p1 / 25) * (costs + 12.5))

        # Costs and insider selling count only to the extent owners are getting no cash
        result = evaluate(company_record(sbc=0.02), None, DATA_DATE, insider=insider)
        self.assertAlmostEqual(result['score'], 0)

        # No cost line or no insider filings: no score
        result = evaluate(company_record(tags={'GrossProfit': None}), None, DATA_DATE, insider=insider)
        self.assertAlmostEqual(result['p1']['p1'], p1)
        self.assertIsNone(result['costs'])
        self.assertIsNone(result['score'])
        self.assertEqual(result['flags'], ['no_cost_line'])
        result = evaluate(company_record(), None, DATA_DATE)
        self.assertIsNone(result['insiders'])
        self.assertIsNone(result['score'])
        self.assertEqual(result['flags'], ['no_insider_filings'])

        # A company with no fiscal year for some of the calendar years: its insiders' amounts in those years are left out
        result = evaluate(company_record(last_year=2024), None, '2026-02-20', insider=insider)
        self.assertEqual((result['five']['years'], result['five']['revenue'], result['five']['insider']['cashOut']), (4, 6800e6, 0))
        self.assertEqual(result['flags'], ['few_fiscal_years'])

        # The latest fiscal year stands in for the latest 12 months
        result = evaluate(company_record(quarters=False), None, DATA_DATE)
        self.assertEqual((result['latestBasis'], result['latestEnd']), ('fy', '2025-12-31'))
        self.assertEqual(result['ttmReason'], 'no quarterly report since the latest fiscal year')
        self.assertIsNone(result['ttm'])
        self.assertEqual(result['flags'], ['latest_is_fiscal_year', 'no_insider_filings'])

        # The latest 12 months differ from the latest fiscal year
        result = evaluate(company_record(tags={
            'ShareBasedCompensation': annuals([value * 0.12 for value in REVENUE]) + [nine_months(2025, 180), nine_months(2026, 73)]
        }), None, DATA_DATE)
        self.assertAlmostEqual(result['latestMargin'], (215 - 133) / 2150)
        self.assertAlmostEqual(result['p1']['latestPoints'], 7 * (0.05 - 82 / 2150) / 0.1)


    def test_evaluate_flags(self):
        result = evaluate(company_record(
            revenue=(1000, 3100, 3200, 3300, 3400, 3500, 3600),
            sbc=[0, 372, 384, 396, 408, 420, 432],
            tags={
                'PaymentsToAcquirePropertyPlantAndEquipment': None,
                'IncreaseDecreaseInInventories': annuals([-400]),
                'WeightedAverageNumberOfDilutedSharesOutstanding': annuals([100, 300, 310, 320, 330, 340, 350]),
                'PaymentsForRepurchaseOfCommonStock': annuals([10, -20]) + [annual(2018, 500)],
                'PaymentsOfDividends': annuals([1, 2, 3]),
                'PaymentsRelatedToTaxWithholdingForShareBasedCompensation': annuals([4, 5])
            }
        ), None, DATA_DATE)
        self.assertEqual(result['flags'], ['capex_missing', 'one_off_years', 'revenue_jump', 'share_count_jump', 'no_insider_filings'])
        self.assertEqual((result['buybacks'], result['dividends'], result['withholding']), (30e6, 6e6, 9e6))
        self.assertEqual(sorted(result['oneOffs']), ['2019'])

        # P1 without the one-off year, the only year with meaningful owner cash: the same latest margin, six years
        self.assertEqual(result['p1']['lowYears'], 6)
        self.assertEqual(result['p1Ex']['lowYears'], 6)
        self.assertAlmostEqual(result['p1']['yearsPoints'], 60 / 7)
        self.assertAlmostEqual(result['p1Ex']['yearsPoints'], 10)
        self.assertEqual(result['p1Ex']['latestPoints'], result['p1']['latestPoints'])

        # Every year is a one-off year
        result = evaluate(company_record(tags={
            'IncreaseDecreaseInInventories': annuals([value * 0.3 for value in REVENUE])
        }), None, DATA_DATE)
        self.assertEqual(len(result['oneOffs']), 7)
        self.assertIsNone(result['p1Ex'])

        # A missing year
        result = evaluate(company_record(tags={
            'ShareBasedCompensation': [fact for fact in annuals([value * 0.12 for value in REVENUE]) if fact['end'] != '2022-12-31']
        }), None, DATA_DATE)
        self.assertEqual(result['years'], 6)
        self.assertEqual(result['flags'], ['latest_is_fiscal_year', 'gap_years', 'few_fiscal_years', 'no_insider_filings'])


    def test_run_screen(self):
        records = [
            company_record(cik=1, name='Stock Pay Co'),
            company_record(cik=2, name='Better Stock Pay Co', sbc=0.11),
            company_record(cik=3, name='Aardvark Stock Pay Co'),
            company_record(cik=4, name='No Cost Line Co', sbc=0.2, tags={'GrossProfit': None}),
            company_record(cik=5, name='Bank Co', sbc=0.2),
            company_record(cik=6, name='Cash Co', sbc=0.02),
            company_record(cik=7, name='Thin Co', ocf=0.045, sbc=0.019),
            company_record(cik=8, name='Burner Co', ocf=0.01),
            company_record(cik=9, name='Slow Co', revenue=(1000, 1100, 1200, 1300, 1400)),
            company_record(cik=10, name='Short Co', revenue=(1000, 1200, 1400, 1600)),
            company_record(cik=11, name='Small Co', revenue=(500, 600, 700, 800, 900)),
            company_record(cik=12, name='Old Co', revenue=(1000, 1200, 1400, 1600, 1800), last_year=2021),
            company_record(cik=13, name='No Data Co', tags={'NetCashProvidedByUsedInOperatingActivities': None}),
            company_record(cik=14, name='Capital Co', ocf=0.4, capex=0.3)
        ]
        insider = insider_fixture(0.0175 * 8050e6)
        insiders = {1: insider, 2: insider, 3: insider, 4: insider, 14: insider}
        results, funnel = run_screen(records, {5: 6021, 1: 7372}, DATA_DATE, insiders)
        self.assertEqual(funnel, {
            'prefilter': 14,
            'current': 12,
            'revenue': 11,
            'years': 10,
            'growth': 9,
            'industry': 8,
            'lowMargin': 7,
            'stockPayCause': 5,
            'stockPay': 4,
            'ranked': 3
        })

        # Ranked by score, then name; then the rest by P1; then the excluded industries. A capital-led company and a
        # company without one of the signs are not ranked.
        self.assertEqual(
            [(result['rank'], result['name'], result['type']) for result in results],
            [
                (1, 'Aardvark Stock Pay Co', 'stock_pay'),
                (2, 'Stock Pay Co', 'stock_pay'),
                (3, 'Better Stock Pay Co', 'stock_pay'),
                (None, 'Burner Co', 'cash_burner'),
                (None, 'No Cost Line Co', 'stock_pay'),
                (None, 'Capital Co', 'capital_led'),
                (None, 'Thin Co', 'thin_margin'),
                (None, 'Cash Co', 'cash_generative'),
                (None, 'Bank Co', 'excluded')
            ]
        )
        self.assertEqual([result['sic'] for result in results[:3]], [None, 7372, None])
        self.assertEqual(results[8]['sic'], 6021)
        self.assertAlmostEqual(results[0]['score'], results[1]['score'])
        self.assertGreater(results[1]['score'], results[2]['score'])
        self.assertIsNone(results[4]['score'])
        self.assertIsNotNone(results[5]['score'])

        # A company with no insider filings is flagged
        self.assertEqual([result['flags'] for result in results[:3]], [[], [], []])
        self.assertEqual(results[3]['flags'], ['no_insider_filings'])
        self.assertEqual(results[4]['flags'], ['no_cost_line'])

        # With no insider filings at all, no company has the third sign, so none is ranked
        results, funnel = run_screen(records, {}, DATA_DATE, {})
        self.assertEqual((funnel['industry'], funnel['stockPay'], funnel['ranked']), (9, 5, 0))
        self.assertEqual([result['rank'] for result in results], [None] * 9)


    def test_group_totals(self):
        results, _ = run_screen([company_record(cik=1), company_record(cik=2, tags={
            'PaymentsForRepurchaseOfCommonStock': annuals([10, 20]),
            'PaymentsOfDividendsCommonStock': annuals([1]),
            'PaymentsRelatedToTaxWithholdingForShareBasedCompensation': annuals([4])
        })], {}, DATA_DATE, {})
        self.assertEqual(group_totals(results), {
            'companies': 2,
            'cumRevenue': 20300e6,
            'cumFcf': 2030e6,
            'cumSbc': 2436e6,
            'cumOwnerCash': -406e6,
            'cumCapex': 406e6,
            'buybacks': 30e6,
            'dividends': 1e6,
            'withholding': 4e6
        })
        self.assertEqual(group_totals([])['companies'], 0)


    def test_loose_thresholds(self):
        thresholds = loose_thresholds()
        self.assertEqual(thresholds['revenue_min'], 0.8e9)
        self.assertEqual(thresholds['years_min'], 4)
        self.assertAlmostEqual(thresholds['growth_min'], 0.4)
        self.assertEqual(THRESHOLDS['years_min'], 5)
        self.assertEqual({key: value for key, value in thresholds.items() if value != THRESHOLDS[key]}.keys(),
                         {'revenue_min', 'years_min', 'growth_min'})


    def test_sensitivity(self):
        records = [
            company_record(cik=1, name='Stock Pay Co'),
            company_record(cik=2, name='Better Stock Pay Co', sbc=0.11),
            # Enters when the growth test falls to 40%
            company_record(cik=3, name='Slower Co', revenue=(1000, 1100, 1200, 1300, 1450), sbc=0.2),
            # Leaves when the meaningful-cash line falls to 2.4%
            company_record(cik=4, name='Marginal Co', sbc=0.074)
        ]
        insiders = dict.fromkeys((1, 2, 3, 4), insider_fixture(0.0175 * 8050e6))
        results, _ = run_screen(records, {}, DATA_DATE, insiders)
        self.assertEqual([(result['rank'], result['cik']) for result in results], [(1, 1), (2, 2), (3, 4)])
        report = sensitivity(records, {}, DATA_DATE, results, insiders)
        self.assertEqual([(entry['threshold'], entry['factor']) for entry in report],
                         [(key, factor) for key in SENSITIVITY_KEYS for factor in (0.8, 1.2)])
        by_key = {(entry['threshold'], entry['factor']): entry for entry in report}
        self.assertEqual(by_key[('years_min', 0.8)]['value'], 4)
        self.assertEqual(by_key[('years_min', 1.2)]['value'], 6)
        self.assertEqual(by_key[('p1_cum_zero', 0.8)]['value'], 0.04)
        self.assertEqual(by_key[('revenue_min', 1.2)]['value'], 1.2e9)
        self.assertEqual(by_key[('revenue_min', 1.2)]['changes'], [])
        self.assertEqual(by_key[('growth_min', 0.8)]['changes'], [
            {'cik': 3, 'name': 'Slower Co', 'from': None, 'to': 1},
            {'cik': 1, 'name': 'Stock Pay Co', 'from': 1, 'to': 2},
            {'cik': 2, 'name': 'Better Stock Pay Co', 'from': 2, 'to': 3},
            {'cik': 4, 'name': 'Marginal Co', 'from': 3, 'to': 4}
        ])
        self.assertEqual(by_key[('meaningful_margin', 0.8)]['changes'], [
            {'cik': 4, 'name': 'Marginal Co', 'from': 3, 'to': None}
        ])

        # With no insider filings no company is ranked, so nothing changes
        results, _ = run_screen(records, {}, DATA_DATE, {})
        self.assertEqual([entry['changes'] for entry in sensitivity(records, {}, DATA_DATE, results, {})], [[]] * len(report))
