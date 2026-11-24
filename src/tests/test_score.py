# pylint: disable=missing-class-docstring, missing-function-docstring, missing-module-docstring

import unittest

from treadmill_index.score import DEFAULT_OPTIONS, PROTOTYPE_OPTIONS, SENSITIVITY_KEYS, THRESHOLDS, company_series, \
    cost_change, cost_line, costs_sign, evaluate, find_period, five_years, group_totals, latest_twelve_months, lin, \
    loose_thresholds, low_run, one_off_years, pillar_one, pillar_three, run_screen, sensitivity, share_change, sic_exclusion, \
    spending_change, year_label

from .helpers import DATA_DATE, REVENUE, annual, company_record, nine_months, unit


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
            'CostOfGoodsAndServicesSold': annuals([value * 0.4 for value in REVENUE]),
            'OperatingExpenses': annuals([value * 0.56 for value in REVENUE])
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

        value, facts = cost_line(annual_facts, end, 0)
        self.assertEqual(value, 1120e6)
        self.assertEqual([fact[5] for fact in facts], ['OperatingExpenses'])

        # Missing figures
        for method in (0, 1, 2, 3):
            self.assertEqual(cost_line(annual_facts, '2030-12-31', method), (None, None))
        self.assertEqual(cost_line(company_record()['annual'], end, 2), (None, None))
        self.assertEqual(cost_line(company_record()['annual'], end, 3), (None, None))


    def test_cost_change(self):
        # The first method: costs fall from 55% of revenue in 2021 to 50% in 2025
        record = company_record(operating=[50, 55, 62.5, 70, 80, 90, 200])
        series = company_series(record)
        cost = cost_change(record, series, THRESHOLDS, DEFAULT_OPTIONS)
        self.assertEqual(cost['method'], 1)
        self.assertEqual((cost['firstYear'], cost['firstCost'], cost['firstRatio']), ('2021', 687.5e6, 0.55))
        self.assertEqual((cost['lastYear'], cost['lastCost'], cost['lastRatio']), ('2025', 1000e6, 0.5))
        self.assertEqual(cost['lastGross'], 1200e6)
        self.assertAlmostEqual(cost['change'], -5)
        self.assertEqual([fact[5] for fact in cost['firstFacts']], ['GrossProfit', 'OperatingIncomeLoss'])
        self.assertEqual([fact[1] for fact in cost['lastFacts']], ['0000000001-26-000010', '0000000001-26-000010'])

        # The cost line is built the same way in both years: gross profit is missing in the first year, so the second
        # method is used
        record = company_record(tags={
            'GrossProfit': annuals([1200], first_year=2025),
            'CostsAndExpenses': annuals([value * 0.95 for value in REVENUE]),
            'CostOfRevenue': annuals([value * 0.35 for value in REVENUE])
        })
        cost = cost_change(record, series, THRESHOLDS, DEFAULT_OPTIONS)
        self.assertEqual(cost['method'], 2)
        self.assertAlmostEqual(cost['change'], 0)
        self.assertAlmostEqual(cost['lastGross'], 1300e6)

        # The third method
        record = company_record(tags={'GrossProfit': None, 'CostOfRevenue': annuals([value * 0.35 for value in REVENUE])})
        cost = cost_change(record, series, THRESHOLDS, DEFAULT_OPTIONS)
        self.assertEqual(cost['method'], 3)
        self.assertAlmostEqual(cost['firstRatio'], 0.6)

        # The OperatingExpenses tag is used only with the prototype's options
        record = company_record(tags={'GrossProfit': None, 'OperatingExpenses': annuals([value * 0.5 for value in REVENUE])})
        self.assertIsNone(cost_change(record, series, THRESHOLDS, DEFAULT_OPTIONS))
        cost = cost_change(record, series, THRESHOLDS, PROTOTYPE_OPTIONS)
        self.assertEqual((cost['method'], cost['lastGross']), (0, None))

        # A cost line that is not positive is not used
        record = company_record(gross=0.04)
        self.assertIsNone(cost_change(record, series, THRESHOLDS, DEFAULT_OPTIONS))

        # Fewer years than the window
        record = company_record()
        self.assertIsNone(cost_change(record, series[-4:], THRESHOLDS, DEFAULT_OPTIONS))
        self.assertEqual(cost_change(record, series[-5:], THRESHOLDS, DEFAULT_OPTIONS)['firstYear'], '2021')


    def test_costs_sign(self):
        def cost(last_cost, last_gross):
            return {'lastCost': last_cost, 'lastGross': last_gross}

        # No cost line, or no gross profit figure
        self.assertIsNone(costs_sign(None, None, THRESHOLDS))
        self.assertIsNone(costs_sign(cost(500, None), 13, THRESHOLDS))

        # Half is P2b; half is the share of gross profit operating costs take: 0 at 70%, 12.5 at 100%
        def sign(level, change_points, level_points):
            return {'level': level, 'changePoints': change_points, 'levelPoints': level_points, 'points': change_points + level_points}

        self.assertEqual(costs_sign(cost(700, 1000), 13, THRESHOLDS), sign(0.7, 12.5, 0))
        self.assertEqual(costs_sign(cost(400, 1000), 0, THRESHOLDS), sign(0.4, 0, 0))
        costs = costs_sign(cost(850, 1000), 6.5, THRESHOLDS)
        self.assertAlmostEqual(costs['levelPoints'], 6.25)
        self.assertAlmostEqual(costs['points'], 12.5)
        self.assertEqual(costs_sign(cost(1460, 1000), 0, THRESHOLDS), sign(1.46, 0, 12.5))

        # With no gross profit at all, operating costs take more than all of it
        self.assertEqual(costs_sign(cost(500, -20), 13, THRESHOLDS), sign(None, 12.5, 12.5))
        self.assertEqual(costs_sign(cost(500, 0), 0, THRESHOLDS)['levelPoints'], 12.5)


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
        spending = spending_change(record, series, {**THRESHOLDS, 'p2b_window_years': 2})
        self.assertEqual(sorted(spending), ['ga', 'sm'])
        self.assertAlmostEqual(spending['ga']['firstRatio'], 100 / 1800)

        # Fewer years than the window, and no spending tags
        self.assertEqual(spending_change(record, series[-4:], THRESHOLDS), {})
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
        five = five_years(record, series, 2025, THRESHOLDS)
        self.assertAlmostEqual(five.pop('ownerCash'), -161e6)
        self.assertAlmostEqual(five.pop('shareGrowth'), 0.1)
        self.assertEqual(five, {'years': 5, 'buybacks': 250e6, 'withholding': 3e6})

        # Years the company does not have, and too few years to follow the share count
        five = five_years(record, series, 2026, THRESHOLDS)
        self.assertEqual((five['years'], five['buybacks']), (4, 220e6))
        self.assertAlmostEqual(five['shareGrowth'], 0.1)
        five = five_years(record, series, 2029, THRESHOLDS)
        self.assertEqual((five['years'], five['buybacks'], five['shareGrowth']), (1, 70e6, None))
        self.assertAlmostEqual(five['ownerCash'], -40e6)
        self.assertEqual(five_years(record, series, 2035, THRESHOLDS), {
            'years': 0, 'ownerCash': 0, 'buybacks': 0, 'withholding': 0, 'shareGrowth': None
        })

        # A share count that cannot be followed
        self.assertIsNone(five_years(company_record(), series, 2025, THRESHOLDS)['shareGrowth'])


    def test_pillar_three(self):
        # No insider filings
        self.assertIsNone(pillar_three(None, THRESHOLDS))

        # Grants and sales in three of five years; sales of 1.0 times grants
        insider = {'bothYears': 3, 'salesToGrants': 1.0, 'grantShares': 1000, 'sales': 500}
        self.assertEqual(pillar_three(insider, THRESHOLDS), {'yearsPoints': 7.2, 'ratioPoints': 6.5, 'p3': 13.7})

        # The ratio scores 0 at 0.5 times and 13 at 1.5 times
        for ratio, points in ((0, 0), (0.5, 0), (0.75, 3.25), (1.5, 13), (56.7, 13)):
            insider = {'bothYears': 5, 'salesToGrants': ratio, 'grantShares': 1000, 'sales': 500}
            self.assertEqual(pillar_three(insider, THRESHOLDS), {'yearsPoints': 12, 'ratioPoints': points, 'p3': 12 + points})

        # Sales with no grants at all score the ratio in full; no sales and no grants score nothing
        insider = {'bothYears': 0, 'salesToGrants': None, 'grantShares': 0, 'sales': 500}
        self.assertEqual(pillar_three(insider, THRESHOLDS), {'yearsPoints': 0, 'ratioPoints': 13, 'p3': 13})
        insider = {'bothYears': 0, 'salesToGrants': None, 'grantShares': 0, 'sales': 0}
        self.assertEqual(pillar_three(insider, THRESHOLDS), {'yearsPoints': 0, 'ratioPoints': 0, 'p3': 0})

        # Grants that cannot be valued: no ratio and no P3
        insider = {'bothYears': 5, 'salesToGrants': None, 'grantShares': 1000, 'sales': 500}
        self.assertEqual(pillar_three(insider, THRESHOLDS), {'yearsPoints': 12, 'ratioPoints': None, 'p3': None})


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
        self.assertAlmostEqual(result.pop('screenScore'), 2 * (10 + 8 * 0.07 / 0.15 + 4.9))
        self.assertAlmostEqual(result.pop('cumFcfMargin'), 0.1)
        self.assertAlmostEqual(result.pop('sbcRevenue'), 0.12)
        self.assertAlmostEqual(result.pop('capexToSbc'), 1 / 6)
        self.assertAlmostEqual(result.pop('fyMargin'), -0.02)
        self.assertAlmostEqual(result.pop('latestMargin'), -0.02)
        costs = result.pop('costs')
        self.assertAlmostEqual(costs['level'], 1100 / 1200)
        self.assertAlmostEqual(costs['points'], 12.5 + 12.5 * (1100 / 1200 - 0.7) / 0.3)
        five = result.pop('five')
        self.assertAlmostEqual(five.pop('ownerCash'), -161e6)
        self.assertEqual(five, {'years': 5, 'buybacks': 0, 'withholding': 0, 'shareGrowth': None})
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
            'capitalLed': False,
            'latestBasis': 'ttm',
            'latestEnd': '2026-09-30',
            'ttmReason': None,
            'oneOffs': {},
            'p1Ex': None,
            'p2b': 13,
            'insider': None,
            'p3': None,
            'threeScore': None,
            'threeRank': None,
            'lowRun': 7,
            'spending': {},
            'capexMissingYears': 0,
            'shareGrowth': None,
            'shareReason': 'share count missing for the first or last year',
            'flags': [],
            'rank': None
        })


    def test_evaluate_stages(self):
        # No year with revenue, operating cash flow and stock pay
        record = company_record(tags={'NetCashProvidedByUsedInOperatingActivities': None})
        self.assertEqual(evaluate(record, None, DATA_DATE), {'stage': 'no_data'})

        # The latest fiscal year is too old
        self.assertEqual(evaluate(company_record(), None, '2027-07-03'), {'stage': 'not_current'})
        self.assertEqual(evaluate(company_record(), None, '2027-07-02')['stage'], 'scored')
        options = {**DEFAULT_OPTIONS, 'still_filing_cutoff': '2026-01-01'}
        self.assertEqual(evaluate(company_record(), None, DATA_DATE, None, options), {'stage': 'not_current'})

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
        self.assertAlmostEqual(result['screenScore'], 0)

        # Stock pay is the cause - and is not when it is under 2% of revenue or under half of free cash flow
        self.assertEqual(evaluate(company_record(ocf=0.045, sbc=0.02), None, DATA_DATE)['type'], 'stock_pay')
        self.assertEqual(evaluate(company_record(ocf=0.045, sbc=0.019), None, DATA_DATE)['type'], 'thin_margin')
        thresholds = {**THRESHOLDS, 'sbc_fcf_min': 1.5}
        self.assertEqual(evaluate(company_record(), None, DATA_DATE, thresholds)['type'], 'thin_margin')

        # Negative free cash flow before stock pay
        self.assertEqual(evaluate(company_record(ocf=0.01), None, DATA_DATE)['type'], 'cash_burner')

        # Capital-led
        result = evaluate(company_record(ocf=0.4, capex=0.3), None, DATA_DATE)
        self.assertEqual((result['type'], result['capitalLed']), ('stock_pay', True))
        self.assertAlmostEqual(result['capexToSbc'], 2.5)

        # No stock pay
        result = evaluate(company_record(sbc=0), None, DATA_DATE)
        self.assertEqual((result['type'], result['capitalLed'], result['capexToSbc']), ('cash_generative', False, None))


    def test_evaluate_scores(self):
        # Costs fall five points of revenue: half of P2b
        result = evaluate(company_record(operating=[50, 55, 62.5, 70, 80, 90, 200]), None, DATA_DATE)
        p1 = 10 + 8 * 0.07 / 0.15 + 4.9
        self.assertAlmostEqual(result['p2b'], 6.5)
        self.assertAlmostEqual(result['screenScore'], p1 + (p1 / 25) * 12.5)

        # No cost line: P1 alone, no screen score
        result = evaluate(company_record(tags={'GrossProfit': None}), None, DATA_DATE)
        self.assertAlmostEqual(result['p1']['p1'], p1)
        self.assertIsNone(result['p2b'])
        self.assertIsNone(result['screenScore'])
        self.assertEqual(result['flags'], ['no_cost_line'])

        # The latest fiscal year stands in for the latest 12 months
        result = evaluate(company_record(quarters=False), None, DATA_DATE)
        self.assertEqual((result['latestBasis'], result['latestEnd']), ('fy', '2025-12-31'))
        self.assertEqual(result['ttmReason'], 'no quarterly report since the latest fiscal year')
        self.assertIsNone(result['ttm'])
        self.assertEqual(result['flags'], ['latest_is_fiscal_year'])

        # The prototype's options: no latest 12 months, and no flag for it
        result = evaluate(company_record(), None, DATA_DATE, None, PROTOTYPE_OPTIONS)
        self.assertEqual((result['latestBasis'], result['ttmReason'], result['flags']), ('fy', 'not computed', []))

        # The latest 12 months differ from the latest fiscal year
        result = evaluate(company_record(tags={
            'ShareBasedCompensation': annuals([value * 0.12 for value in REVENUE]) + [nine_months(2025, 180), nine_months(2026, 73)]
        }), None, DATA_DATE)
        self.assertAlmostEqual(result['fyMargin'], -0.02)
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
        self.assertEqual(result['flags'], ['capex_missing', 'one_off_years', 'revenue_jump', 'share_count_jump'])
        self.assertEqual(result['capexMissingYears'], 7)
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
        self.assertEqual(result['flags'], ['latest_is_fiscal_year', 'gap_years'])


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
            company_record(cik=13, name='No Data Co', tags={'NetCashProvidedByUsedInOperatingActivities': None})
        ]
        results, funnel = run_screen(records, {5: 6021, 1: 7372}, DATA_DATE)
        self.assertEqual(funnel, {
            'prefilter': 13,
            'current': 11,
            'revenue': 10,
            'years': 9,
            'growth': 8,
            'industry': 7,
            'lowMargin': 6,
            'stockPay': 4,
            'ranked': 3,
            'rankedThree': 0
        })
        self.assertEqual(
            [(result['rank'], result['name'], result['type']) for result in results],
            [
                (1, 'Aardvark Stock Pay Co', 'stock_pay'),
                (2, 'Stock Pay Co', 'stock_pay'),
                (3, 'Better Stock Pay Co', 'stock_pay'),
                (None, 'Burner Co', 'cash_burner'),
                (None, 'No Cost Line Co', 'stock_pay'),
                (None, 'Thin Co', 'thin_margin'),
                (None, 'Cash Co', 'cash_generative'),
                (None, 'Bank Co', 'excluded')
            ]
        )
        self.assertEqual(results[0]['sic'], None)
        self.assertEqual(results[1]['sic'], 7372)
        self.assertEqual(results[7]['sic'], 6021)

        self.assertEqual([result['flags'] for result in results[:3]], [[], [], []])
        self.assertEqual([(result['insider'], result['p3']) for result in results[:3]], [(None, None)] * 3)

        # The prototype's options
        _, funnel = run_screen(records, {}, DATA_DATE, None, PROTOTYPE_OPTIONS)
        self.assertEqual(funnel['industry'], 8)

        # With insider data, a company's summary is scored and a company without one is flagged
        insider = {'bothYears': 5, 'salesToGrants': 1.0, 'grantShares': 1000, 'sales': 500}
        results, _ = run_screen(records[:2], {}, DATA_DATE, insiders={2: insider})
        self.assertEqual([(result['cik'], result['flags']) for result in results], [(1, ['no_insider_filings']), (2, [])])
        self.assertIsNone(results[0]['p3'])
        self.assertIs(results[1]['insider'], insider)
        self.assertEqual(results[1]['p3'], {'yearsPoints': 12, 'ratioPoints': 6.5, 'p3': 18.5})

        # The three-signs score is P1, plus the costs sign and P3 to the extent of P1, and has its own rank
        self.assertAlmostEqual(
            results[1]['threeScore'],
            results[1]['p1']['p1'] + (results[1]['p1']['p1'] / 25) * (results[1]['costs']['points'] + 18.5)
        )
        self.assertEqual([(result['rank'], result['threeRank'], result['threeScore'] is None) for result in results],
                         [(1, None, True), (2, 1, False)])
        results, funnel = run_screen(records[:3], {}, DATA_DATE, insiders={
            1: {**insider, 'salesToGrants': 0.6}, 2: insider, 3: {**insider, 'salesToGrants': None}, 4: insider
        })
        self.assertEqual([(result['cik'], result['rank'], result['threeRank']) for result in results], [(3, 1, None), (1, 2, 2), (2, 3, 1)])
        self.assertEqual((funnel['ranked'], funnel['rankedThree']), (3, 2))


    def test_group_totals(self):
        results, _ = run_screen([company_record(cik=1), company_record(cik=2, tags={
            'PaymentsForRepurchaseOfCommonStock': annuals([10, 20]),
            'PaymentsOfDividendsCommonStock': annuals([1]),
            'PaymentsRelatedToTaxWithholdingForShareBasedCompensation': annuals([4])
        })], {}, DATA_DATE)
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
        results, _ = run_screen(records, {}, DATA_DATE)
        self.assertEqual([(result['rank'], result['cik']) for result in results], [(1, 1), (2, 2), (3, 4)])
        report = sensitivity(records, {}, DATA_DATE, results)
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
        self.assertEqual([entry['changesThree'] for entry in report], [[]] * len(report))

        # With insider data, the three-signs ranks are tested too: the costs level reorders the first two
        insider = {'bothYears': 5, 'salesToGrants': 1.0, 'grantShares': 1000, 'sales': 500}
        insiders = {1: insider, 2: insider, 4: insider}
        results, _ = run_screen(records, {}, DATA_DATE, insiders=insiders)
        self.assertEqual([(result['threeRank'], result['cik']) for result in results], [(1, 1), (2, 2), (3, 4)])
        report = sensitivity(records, {}, DATA_DATE, results, insiders)
        by_key = {(entry['threshold'], entry['factor']): entry for entry in report}
        self.assertEqual(by_key[('meaningful_margin', 0.8)]['changesThree'], [
            {'cik': 4, 'name': 'Marginal Co', 'from': 3, 'to': None}
        ])
        self.assertEqual(by_key[('p3_ratio_zero', 1.2)]['changesThree'], [])
