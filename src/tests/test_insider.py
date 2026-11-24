# pylint: disable=missing-class-docstring, missing-function-docstring, missing-module-docstring

import datetime
import os
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from treadmill_index.insider import INSIDER_PAGE_URL, download_insider, filing_insider, insider_links, insider_quarters, \
    insider_summary, is_odd_price, load_insider, nearest_price, parse_number, parse_sec_date, price_series, read_insider_zip

from .helpers import insider_filing, insider_zip


PAGE = '''
<a href="/files/datastandardsinnovation/data/insider-transactions-data-sets/2026q3_form345.zip">2026 Q3</a>
<a href="/files/structureddata/data/insider-transactions-data-sets/2026q1_form345.zip">2026 Q1</a>
<a href="/files/structureddata/data/insider-transactions-data-sets/2025q4_form345.zip">2025 Q4</a>
<a href="/files/insider_transactions_readme.pdf">Insiders Transactions (PDF)</a>
'''

URL_2026Q3 = 'https://www.sec.gov/files/datastandardsinnovation/data/insider-transactions-data-sets/2026q3_form345.zip'
URL_2026Q1 = 'https://www.sec.gov/files/structureddata/data/insider-transactions-data-sets/2026q1_form345.zip'
URL_2025Q4 = 'https://www.sec.gov/files/structureddata/data/insider-transactions-data-sets/2025q4_form345.zip'


class TestInsider(unittest.TestCase):

    def test_insider_links(self):
        self.assertEqual(insider_links(PAGE), {'2026q3': URL_2026Q3, '2026q1': URL_2026Q1, '2025q4': URL_2025Q4})
        self.assertEqual(insider_links('<html></html>'), {})


    def test_insider_quarters(self):
        quarters = insider_quarters(datetime.date(2026, 11, 24))
        self.assertEqual(len(quarters), 23)
        self.assertEqual(quarters[:5], ['2021q1', '2021q2', '2021q3', '2021q4', '2022q1'])
        self.assertEqual(quarters[-4:], ['2025q4', '2026q1', '2026q2', '2026q3'])

        # In the first quarter, the last quarter that has ended is in the prior year
        quarters = insider_quarters(datetime.date(2027, 2, 1))
        self.assertEqual(len(quarters), 20)
        self.assertEqual((quarters[0], quarters[-1]), ('2022q1', '2026q4'))

        # The first and last days of a quarter
        self.assertEqual(insider_quarters(datetime.date(2026, 4, 1), years=0), ['2026q1'])
        self.assertEqual(insider_quarters(datetime.date(2026, 6, 30), years=0), ['2026q1'])
        self.assertEqual(insider_quarters(datetime.date(2026, 3, 31), years=0), [])


    def test_download_insider(self):
        def fetch(url, user_agent):
            self.assertEqual(user_agent, 'Test Person test@example.com')
            if url == URL_2026Q1:
                raise OSError('HTTP Error 500')
            return PAGE.encode('utf-8') if url == INSIDER_PAGE_URL else url.encode('utf-8')

        with TemporaryDirectory() as temp_dir:
            insider_dir = os.path.join(temp_dir, 'insider')
            logs = []
            today = datetime.date(2026, 11, 24)

            # 2025 Q4 is already downloaded, 2026 Q1 fails and 2026 Q2 is not listed
            os.mkdir(insider_dir)
            with open(os.path.join(insider_dir, '2025q4_form345.zip'), 'wb') as zip_file:
                zip_file.write(b'already here')
            with patch('treadmill_index.insider.insider_quarters', return_value=['2025q4', '2026q1', '2026q2', '2026q3']), \
                 patch('treadmill_index.insider.fetch_url', side_effect=fetch) as mock_fetch, \
                 patch('time.sleep') as mock_sleep:
                self.assertEqual(download_insider(temp_dir, 'Test Person test@example.com', today, log=logs.append), 2)
            self.assertEqual([call.args[0] for call in mock_fetch.call_args_list], [INSIDER_PAGE_URL, URL_2026Q1, URL_2026Q3])
            self.assertEqual([call.args for call in mock_sleep.call_args_list], [(0.5,)])
            self.assertEqual(logs, [
                'Warning: the download of 2026q1 failed: HTTP Error 500',
                'Warning: the SEC does not list a data set for 2026q2',
                f'Downloaded 2026q3 ({len(URL_2026Q3)} bytes)'
            ])
            self.assertEqual(sorted(os.listdir(insider_dir)), ['2025q4_form345.zip', '2026q3_form345.zip'])
            with open(os.path.join(insider_dir, '2025q4_form345.zip'), 'rb') as zip_file:
                self.assertEqual(zip_file.read(), b'already here')
            with open(os.path.join(insider_dir, '2026q3_form345.zip'), 'rb') as zip_file:
                self.assertEqual(zip_file.read(), URL_2026Q3.encode('utf-8'))

            # Nothing to download
            logs.clear()
            with patch('treadmill_index.insider.insider_quarters', return_value=['2025q4', '2026q3']), \
                 patch('treadmill_index.insider.fetch_url') as mock_fetch:
                self.assertEqual(download_insider(temp_dir, 'Test Person test@example.com', today, log=logs.append), 0)
            mock_fetch.assert_not_called()
            self.assertEqual(logs, ['Every insider-transaction data set is already downloaded'])


    def test_download_insider_refused(self):
        with TemporaryDirectory() as temp_dir:
            logs = []
            with patch('treadmill_index.insider.fetch_url', side_effect=OSError('HTTP Error 403: Forbidden')), \
                 patch('time.sleep'):
                self.assertEqual(download_insider(temp_dir, 'sec-data-client/1.0', datetime.date(2026, 11, 24), log=logs.append), 23)
            self.assertEqual(logs, [
                'The SEC refused the list of data sets: HTTP Error 403: Forbidden',
                'Set SEC_USER_AGENT to a User-Agent that names you and gives a contact address, or download the files in a browser'
            ])
            self.assertEqual(os.listdir(os.path.join(temp_dir, 'insider')), [])


def transaction(kind, date, shares, price=None, accn='A1', filed='2024-03-18', owner=1001, name='Doe Jane',
                title='Chief Executive Officer'):
    return {'accn': accn, 'filed': filed, 'owner': owner, 'name': name, 'title': title, 'kind': kind, 'date': date, 'shares': shares,
            'price': price}


# A company's transactions: two insiders, every kind, and rows that are left out
TRANSACTIONS = [
    transaction('sale', '2024-03-15', 1000, 50),
    transaction('sale', '2024-03-15', 1000, 52),
    transaction('withheld', '2024-03-20', 100, 55, accn='A2', filed='2024-03-21'),
    transaction('grant', '2024-03-22', 2000, accn='A3', filed='2024-03-25'),
    transaction('option', '2024-03-22', 5000, 60, accn='A3', filed='2024-03-25'),
    transaction('gift', '2024-04-01', 300, accn='A4', filed='2024-04-02'),
    transaction('issuer', '2024-05-01', 50, accn='A5', filed='2024-05-03'),
    transaction('issuer', '2024-05-02', 10, 54, accn='A5', filed='2024-05-03'),
    transaction('purchase', '2025-02-01', 100, 40, accn='A6', filed='2025-02-03', title='Executive Chair'),
    # A sale at a price far from the company's other prices is left out
    transaction('sale', '2024-03-25', 10, 5000, accn='A7', filed='2024-03-26'),
    # Before the five years
    transaction('sale', '2020-12-31', 1000, 30, accn='A0', filed='2021-01-04'),
    transaction('sale', '2025-02-03', 200, 41, accn='B1', filed='2025-02-04', owner=1002, name='Roe Rich', title='Director'),
    transaction('gift', '2025-03-01', 5, accn='C1', filed='2025-03-03', owner=1003, name='Poe Pat', title='Director')
]

THRESHOLDS = {'p3_years': 5, 'p3_price_days': 90, 'p3_unvalued_max': 0.05}


class TestInsiderRead(unittest.TestCase):

    def test_parse_sec_date(self):
        self.assertEqual(parse_sec_date('31-DEC-2025'), '2025-12-31')
        self.assertEqual(parse_sec_date('5-jan-2021'), '2021-01-05')
        for text in ('', '2025-12-31', '31-XXX-2025', 'AA-DEC-2025', '31-DEC-YYYY'):
            self.assertIsNone(parse_sec_date(text))


    def test_parse_number(self):
        self.assertEqual(parse_number('288032.0'), 288032)
        self.assertEqual(parse_number('12.68'), 12.68)
        self.assertIsNone(parse_number(''))
        self.assertIsNone(parse_number('n/a'))


    def test_filing_insider(self):
        def owner(name, relationship):
            return {'RPTOWNERNAME': name, 'RPTOWNER_RELATIONSHIP': relationship}

        officer = owner('Doe Jane', 'Director,Officer')
        director = owner('Roe Rich', 'Director')
        fund = owner('Fund Partners IV, L.P.', 'Director,TenPercentOwner')
        vehicle = owner('Doe Ventures II, LLC', 'TenPercentOwner')
        holder = owner('Poe Pat', 'TenPercentOwner')

        # Officers and directors who are people
        self.assertIs(filing_insider([officer]), officer)
        self.assertIs(filing_insider([director]), director)
        self.assertIs(filing_insider([director, officer]), officer)
        self.assertIs(filing_insider([director, owner('Roe Rita', 'Director')]), director)

        # An officer's own entity is theirs; an outside director filing with an entity is filing for a fund
        self.assertIs(filing_insider([vehicle, officer]), officer)
        self.assertIsNone(filing_insider([director, fund]))
        self.assertIsNone(filing_insider([fund]))
        self.assertIsNone(filing_insider([director, holder]))

        # Neither an officer nor a director
        self.assertIsNone(filing_insider([holder]))
        self.assertIsNone(filing_insider([]))

        # Entity names
        for name in ('Silver Lake Group, L.L.C.', 'TA ASSOCIATES, L.P.', 'ADVANCE PUBLICATIONS, INC', 'Smith Family Trust', 'Acme Corp',
                     'XYZ Capital Management', 'Big Fund LP', 'Holdings Ltd.', 'Shell plc', 'ASML Holding N.V.'):
            self.assertIsNone(filing_insider([owner(name, 'Director')]), name)
        for name in ('BARTON RICHARD N', 'Musk Elon', 'Incledon Ann', 'Trustman Lee', 'Fundakowski Al'):
            self.assertIsNotNone(filing_insider([owner(name, 'Director')]), name)


    def test_read_insider_zip(self):
        director = ('0000001002', 'Roe Rich', 'Director', '')
        officer = ('0000001004', 'Low Lee', 'Officer', '')
        with TemporaryDirectory() as temp_dir:
            zip_path = os.path.join(temp_dir, '2024q1_form345.zip')
            insider_zip(zip_path, [
                insider_filing('A1', nonderiv=[
                    ('15-MAR-2024', 'S', 'D', '1000.0', '50.0', 'D'),
                    ('15-MAR-2024', 'P', 'A', '10.0', '49.0', 'D'),
                    ('15-MAR-2024', 'A', 'A', '2000.0', '0.0', 'D'),
                    ('15-MAR-2024', 'F', 'D', '100.0', '55.0', 'D'),
                    ('15-MAR-2024', 'D', 'D', '50.0', '', 'D'),
                    ('15-MAR-2024', 'G', 'D', '300.0', '', 'I', 'By LLC'),
                    # Left out: a code that is not counted, no date, and no shares
                    ('15-MAR-2024', 'M', 'A', '500.0', '10.0', 'D'),
                    ('15-MAR-2024', 'S', 'A', '500.0', '10.0', 'D'),
                    ('', 'S', 'D', '500.0', '50.0', 'D'),
                    ('15-MAR-2024', 'S', 'D', '', '50.0', 'D'),
                    ('15-MAR-2024', 'S', 'D', '0.0', '50.0', 'D')
                ], deriv=[
                    ('16-MAR-2024', 'A', 'A', '5000.0', '', 'D', '', 'Stock Option (Right to Buy)', '60.0', '5000.0'),
                    ('16-MAR-2024', 'A', 'A', '', '', 'D', '', 'Employee Stock Option (right to buy)', '', '700.0'),
                    ('16-MAR-2024', 'A', 'A', '400.0', '', 'D', '', 'Restricted Stock Units', '0.0', ''),
                    ('16-MAR-2024', 'A', 'A', '1.0', '', 'D', '', 'Performance Stock Units', '0.0', '250.0'),
                    ('16-MAR-2024', 'M', 'D', '5000.0', '', 'D', '', 'Stock Option (Right to Buy)', '60.0', '5000.0')
                ]),

                # An outside director: direct and family holdings count, other indirect holdings are a fund's
                insider_filing('B1', filed='5-FEB-2025', owners=[director], nonderiv=[
                    ('3-FEB-2025', 'S', 'D', '200.0', '41.0', 'D'),
                    ('3-FEB-2025', 'S', 'D', '300.0', '41.0', 'I', 'By the Roe Family Trust'),
                    ('3-FEB-2025', 'S', 'D', '90000.0', '41.0', 'I', 'By Fund Partners IV, L.P.'),
                    ('3-FEB-2025', 'S', 'D', '80000.0', '41.0', 'I', 'See footnote')
                ]),

                # An officer with no title, selling through an entity
                insider_filing('D1', owners=[officer], nonderiv=[('15-MAR-2024', 'S', 'D', '7.0', '50.0', 'I', 'By Low Holdings LLC')]),

                # Left out: a fund's filing, an amended filing, an initial statement, other companies
                insider_filing('E1', owners=[director, ('0000009001', 'Fund Partners IV, L.P.', 'Director', '')],
                               nonderiv=[('15-MAR-2024', 'S', 'D', '90000.0', '50.0', 'I')]),
                insider_filing('F1', form='4/A', nonderiv=[('15-MAR-2024', 'S', 'D', '1000.0', '50.0', 'D')]),
                insider_filing('G1', form='3'),
                insider_filing('H1', cik=3, nonderiv=[('15-MAR-2024', 'S', 'D', '1000.0', '50.0', 'D')]),
                insider_filing('I1', cik='', nonderiv=[('15-MAR-2024', 'S', 'D', '1000.0', '50.0', 'D')]),

                # A second company, on Form 5
                insider_filing('J1', cik=2, form='5', nonderiv=[('31-DEC-2023', 'G', 'D', '25.0', '', 'D')])
            ])
            transactions = read_insider_zip(zip_path, {1, 2})

        def ceo(kind, date, shares, price=None):
            return transaction(kind, date, shares, price)

        self.assertEqual(sorted(transactions), [1, 2])
        self.assertEqual(transactions[1], [
            ceo('sale', '2024-03-15', 1000, 50),
            ceo('purchase', '2024-03-15', 10, 49),
            ceo('grant', '2024-03-15', 2000),
            ceo('withheld', '2024-03-15', 100, 55),
            ceo('issuer', '2024-03-15', 50),
            ceo('gift', '2024-03-15', 300),
            transaction('sale', '2025-02-03', 200, 41, accn='B1', filed='2025-02-05', owner=1002, name='Roe Rich', title='Director'),
            transaction('sale', '2025-02-03', 300, 41, accn='B1', filed='2025-02-05', owner=1002, name='Roe Rich', title='Director'),
            transaction('sale', '2024-03-15', 7, 50, accn='D1', owner=1004, name='Low Lee', title='Officer'),
            ceo('option', '2024-03-16', 5000, 60),
            ceo('option', '2024-03-16', 700),
            ceo('grant', '2024-03-16', 400),
            ceo('grant', '2024-03-16', 250)
        ])
        self.assertEqual(transactions[2], [transaction('gift', '2023-12-31', 25, accn='J1')])


    def test_load_insider(self):
        with TemporaryDirectory() as temp_dir:
            logs = []

            # No data sets
            self.assertEqual(load_insider(temp_dir, [1, 2], log=logs.append), ({}, []))
            insider_dir = os.path.join(temp_dir, 'insider')
            os.mkdir(insider_dir)
            with open(os.path.join(insider_dir, 'readme.txt'), 'w', encoding='utf-8') as readme_file:
                readme_file.write('Not a data set')
            self.assertEqual(load_insider(temp_dir, [1, 2], log=logs.append), ({}, []))
            self.assertEqual(logs, [])
            self.assertEqual(os.listdir(temp_dir), ['insider'])

            # Two data sets
            insider_zip(os.path.join(insider_dir, '2024q1_form345.zip'), [
                insider_filing('A1', nonderiv=[('15-MAR-2024', 'S', 'D', '1000.0', '50.0', 'D')]),
                insider_filing('H1', cik=3, nonderiv=[('15-MAR-2024', 'S', 'D', '1000.0', '50.0', 'D')])
            ])
            insider_zip(os.path.join(insider_dir, '2023q4_form345.zip'), [
                insider_filing('A0', filed='2-JAN-2024', nonderiv=[('29-DEC-2023', 'S', 'D', '500.0', '45.0', 'D')]),
                insider_filing('J1', cik=2, nonderiv=[('31-DEC-2023', 'G', 'D', '25.0', '', 'D')])
            ])
            expected = {
                '1': [
                    transaction('sale', '2023-12-29', 500, 45, accn='A0', filed='2024-01-02'),
                    transaction('sale', '2024-03-15', 1000, 50)
                ],
                '2': [transaction('gift', '2023-12-31', 25, accn='J1')]
            }
            names = ['2023q4_form345.zip', '2024q1_form345.zip']
            self.assertEqual(load_insider(temp_dir, [2, 1], log=logs.append), (expected, names))
            self.assertEqual(logs, ['Reading 2023q4_form345.zip ...', 'Reading 2024q1_form345.zip ...'])
            self.assertEqual(sorted(os.listdir(temp_dir)), ['insider', 'insider-cache.json'])

            # The same files and companies are read from the cache
            logs.clear()
            with patch('treadmill_index.insider.read_insider_zip') as mock_read:
                self.assertEqual(load_insider(temp_dir, [1, 2], log=logs.append), (expected, names))
            mock_read.assert_not_called()
            self.assertEqual(logs, ['Using the cached read of the insider-transaction data sets'])

            # Other companies are read again
            logs.clear()
            transactions, names = load_insider(temp_dir, [1, 3], log=logs.append)
            self.assertEqual(sorted(transactions), ['1', '3'])
            self.assertEqual(logs, ['Reading 2023q4_form345.zip ...', 'Reading 2024q1_form345.zip ...'])


class TestInsiderSummary(unittest.TestCase):
    maxDiff = None

    def test_price_series(self):
        dates = ((2020, 12, 31), (2024, 3, 15), (2024, 3, 20), (2024, 3, 25), (2025, 2, 1), (2025, 2, 3))
        days = [datetime.date(*date).toordinal() for date in dates]
        self.assertEqual(price_series(TRANSACTIONS), (days, [30, 51, 55, 5000, 40, 41]))
        self.assertEqual(price_series([]), ([], []))


    def test_nearest_price(self):
        series = ([100, 110, 200], [10, 11, 20])
        self.assertEqual(nearest_price(series, 100, 90), 10)
        self.assertEqual(nearest_price(series, 104, 90), 10)
        self.assertEqual(nearest_price(series, 106, 90), 11)
        self.assertEqual(nearest_price(series, 50, 90), 10)
        self.assertEqual(nearest_price(series, 290, 90), 20)
        self.assertIsNone(nearest_price(series, 291, 90))
        self.assertIsNone(nearest_price(series, 9, 90))
        self.assertEqual(nearest_price(series, 155, 90), 11)
        self.assertIsNone(nearest_price(series, 155, 30))
        self.assertIsNone(nearest_price(([], []), 100, 90))


    def test_is_odd_price(self):
        series = ([100, 110, 120, 200], [10, 11, 12, 500])

        # Compared with the median of the days within 30 days: 11
        self.assertFalse(is_odd_price(series, 110, 11))
        self.assertFalse(is_odd_price(series, 110, 33))
        self.assertTrue(is_odd_price(series, 110, 33.1))
        self.assertFalse(is_odd_price(series, 110, 3.67))
        self.assertTrue(is_odd_price(series, 110, 3.66))
        self.assertTrue(is_odd_price(series, 80, 1000, window_days=40))

        # Fewer than three days to compare with
        self.assertFalse(is_odd_price(series, 200, 500))
        self.assertFalse(is_odd_price(series, 80, 1000))
        self.assertFalse(is_odd_price(([], []), 100, 1000))


    def test_insider_summary(self):
        def amounts(**kwargs):
            return {'sales': 0, 'purchases': 0, 'withheld': 0, 'toIssuer': 0, 'grants': 0, 'optionGrants': 0, **kwargs}

        def year(value, **kwargs):
            return {'year': value, 'grantShares': 0, 'giftShares': 0, **amounts(**kwargs)}

        summary = insider_summary(TRANSACTIONS, 2025, THRESHOLDS)
        self.assertEqual(summary, {
            'sales': 110200,
            'purchases': 4000,
            'withheld': 5500,
            'toIssuer': 540,
            'grants': 110000,
            'optionGrants': 300000,
            'grantShares': 7000,
            'giftShares': 305,
            'years': [
                year(2021),
                year(2022),
                year(2023),
                year(2024, grantShares=7000, giftShares=300, sales=102000, withheld=5500, toIssuer=540, grants=110000, optionGrants=300000),
                year(2025, giftShares=5, sales=8200, purchases=4000)
            ],
            'bothYears': 1,
            'salesToGrants': 110200 / 410000,
            'ratioReason': None,
            'unvaluedShares': 0,
            'oddPrices': 1,
            'insiders': 3,
            'sellers': 2,
            'people': [
                {
                    'cik': 1001,
                    'name': 'Doe Jane',
                    'title': 'Executive Chair',
                    **amounts(sales=102000, purchases=4000, withheld=5500, toIssuer=540, grants=110000, optionGrants=300000),
                    'filings': [
                        {'accn': 'A1', 'filed': '2024-03-18', **amounts(sales=102000)},
                        {'accn': 'A2', 'filed': '2024-03-21', **amounts(withheld=5500)},
                        {'accn': 'A3', 'filed': '2024-03-25', **amounts(grants=110000, optionGrants=300000)},
                        {'accn': 'A5', 'filed': '2024-05-03', **amounts(toIssuer=540)},
                        {'accn': 'A6', 'filed': '2025-02-03', **amounts(purchases=4000)}
                    ]
                },
                {
                    'cik': 1002,
                    'name': 'Roe Rich',
                    'title': 'Director',
                    **amounts(sales=8200),
                    'filings': [{'accn': 'B1', 'filed': '2025-02-04', **amounts(sales=8200)}]
                }
            ]
        })

        # Other years
        summary = insider_summary(TRANSACTIONS, 2021, THRESHOLDS)
        self.assertEqual([year['year'] for year in summary['years']], [2017, 2018, 2019, 2020, 2021])
        self.assertEqual((summary['sales'], summary['insiders'], summary['bothYears']), (30000, 1, 0))
        self.assertEqual((summary['salesToGrants'], summary['ratioReason']), (None, 'no grants'))

        # No insider reported a transaction in the years
        self.assertIsNone(insider_summary(TRANSACTIONS, 2019, THRESHOLDS))
        self.assertIsNone(insider_summary([], 2025, THRESHOLDS))


    def test_insider_summary_unvalued(self):
        # An option with no exercise price is valued at the nearest share price; a grant with no price within 90 days
        # is not valued
        transactions = [
            transaction('sale', '2024-03-15', 1000, 50),
            transaction('option', '2024-03-18', 100),
            transaction('grant', '2024-06-13', 300),
            transaction('grant', '2024-06-14', 10),
            transaction('option', '2022-01-10', 10)
        ]
        summary = insider_summary(transactions, 2025, {**THRESHOLDS, 'p3_unvalued_max': 0.05})
        self.assertEqual((summary['grants'], summary['optionGrants']), (15000, 5000))
        self.assertEqual((summary['grantShares'], summary['unvaluedShares']), (420, 20))
        self.assertEqual(summary['salesToGrants'], 2.5)
        self.assertEqual([year['grantShares'] for year in summary['years']], [0, 10, 0, 410, 0])
        self.assertEqual(summary['people'][0]['filings'], [{
            'accn': 'A1', 'filed': '2024-03-18', 'sales': 50000, 'purchases': 0, 'withheld': 0, 'toIssuer': 0, 'grants': 15000,
            'optionGrants': 5000
        }])

        # With too many granted shares unvalued, there is no ratio
        summary = insider_summary(transactions, 2025, {**THRESHOLDS, 'p3_unvalued_max': 0.04})
        self.assertEqual(summary['unvaluedShares'], 20)
        self.assertIsNone(summary['salesToGrants'])
        self.assertEqual(summary['ratioReason'], 'too many granted shares have no reported share price near the grant date')

        # Grants that are all unvalued, and no sales
        summary = insider_summary([transaction('grant', '2024-06-14', 10)], 2025, THRESHOLDS)
        self.assertEqual((summary['grantShares'], summary['unvaluedShares'], summary['sellers'], summary['people']), (10, 10, 0, []))
        self.assertEqual(summary['ratioReason'], 'too many granted shares have no reported share price near the grant date')
