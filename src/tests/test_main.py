# pylint: disable=missing-class-docstring, missing-function-docstring, missing-module-docstring

from concurrent.futures import ThreadPoolExecutor
from io import StringIO
import json
import os
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import zipfile

import treadmill_index.__main__
from treadmill_index.main import main

from .helpers import company_bytes, insider_filing, insider_zip, unit


def fetch_submission(url, unused_user_agent):
    if url.endswith('CIK0000000004.json'):
        raise OSError('HTTP Error 404')
    sic = '6021' if url.endswith('CIK0000000003.json') else '7372'
    return json.dumps({'sic': sic, 'sicDescription': 'Test Industry', 'tickers': ['TEST'], 'exchanges': ['Nasdaq']}).encode('utf-8')


def write_companyfacts(raw_dir, ciks):
    names = {1: 'Stock Pay Co', 2: 'Cash Co', 3: 'Bank Co', 4: 'Unknown Co'}
    buybacks = [unit('2025-01-01', '2025-03-31', 20e6, form='10-Q'), unit('2025-01-01', '2025-06-30', 20e6, form='10-Q')]
    with zipfile.ZipFile(os.path.join(raw_dir, 'companyfacts.zip'), 'w') as archive:
        for cik in ciks:
            archive.writestr(f'CIK{cik:010d}.json', company_bytes(
                cik=cik, name=names[cik], sbc=(0.02 if cik == 2 else 0.12), tags={'PaymentsForRepurchaseOfCommonStock': buybacks}
            ))
        archive.writestr('CIK0000000009.json', '{}')


class TestMain(unittest.TestCase):

    def test_main_submodule(self):
        self.assertTrue(treadmill_index.__main__)


    def test_main(self):
        with TemporaryDirectory() as temp_dir:
            raw_dir = os.path.join(temp_dir, 'raw')
            out_dir = os.path.join(temp_dir, 'out')
            os.mkdir(raw_dir)
            write_companyfacts(raw_dir, [1, 2, 3])
            with patch('treadmill_index.extract.ProcessPoolExecutor', ThreadPoolExecutor), \
                 patch('treadmill_index.sec.fetch_url', side_effect=fetch_submission) as mock_fetch, \
                 patch('time.sleep'), \
                 patch('sys.stdout', StringIO()) as stdout, \
                 patch('sys.stderr', StringIO()) as stderr:
                self.assertEqual(main(['--raw', raw_dir, '--out', out_dir, '--processes', '1', '--user-agent', 'test-client/1.0']), 0)

            zip_path = os.path.join(raw_dir, 'companyfacts.zip')
            self.assertEqual(stdout.getvalue().splitlines(), [
                f'Extracting {zip_path} ...',
                '{"inFile": 4, "prefilter": 3, "current": 3, "revenue": 3, "years": 3, "growth": 3, "industry": 2, "lowMargin": 1, '
                '"stockPay": 1, "ranked": 1, "rankedThree": 0}',
                f'Wrote 3 companies to "{out_dir}" - data as of 2026-11-05'
            ])
            self.assertEqual(stderr.getvalue(), '')
            self.assertEqual([call.args[1] for call in mock_fetch.call_args_list], ['test-client/1.0'] * 3)
            self.assertEqual(sorted(os.listdir(raw_dir)), ['companyfacts.zip', 'extract-cache.json', 'submissions-cache.json'])
            self.assertEqual(sorted(os.listdir(out_dir)), ['archive', 'company', 'index.csv', 'index.json', 'meta.json'])
            self.assertEqual(sorted(os.listdir(os.path.join(out_dir, 'company'))), ['1.json', '2.json', '3.json'])

            with open(os.path.join(out_dir, 'index.json'), 'r', encoding='utf-8') as index_file:
                index = json.load(index_file)
            self.assertEqual(
                [(row['rank'], row['name'], row['type'], row['ticker'], row['sic']) for row in index['companies']],
                [
                    (1, 'Stock Pay Co', 'stock_pay', 'TEST', 7372),
                    (None, 'Cash Co', 'cash_generative', 'TEST', 7372),
                    (None, 'Bank Co', 'excluded', 'TEST', 6021)
                ]
            )

            with open(os.path.join(out_dir, 'meta.json'), 'r', encoding='utf-8') as meta_file:
                meta = json.load(meta_file)
            self.assertEqual(meta['dataDate'], '2026-11-05')
            self.assertEqual(meta['sources']['companyfacts']['bytes'], os.path.getsize(zip_path))
            self.assertEqual(len(meta['sources']['companyfacts']['sha256']), 64)
            self.assertEqual(meta['sources']['submissions'], {'url': 'https://data.sec.gov/submissions/', 'companies': 3})
            self.assertEqual(meta['sources']['insider'], {
                'url': 'https://www.sec.gov/data-research/sec-markets-data/insider-transactions-data-sets',
                'files': []
            })
            self.assertIsNone(meta['insider'])
            self.assertEqual(len(meta['sensitivity']), 24)
            self.assertEqual([row['flags'] for row in index['companies']], [[], [], []])


    def test_main_insider(self):
        with TemporaryDirectory() as temp_dir:
            raw_dir = os.path.join(temp_dir, 'raw')
            out_dir = os.path.join(temp_dir, 'out')
            os.makedirs(os.path.join(raw_dir, 'insider'))
            write_companyfacts(raw_dir, [1, 2, 3])

            # The first company's insiders sell in 2025; the second's only before the five years; the third has none
            insider_zip(os.path.join(raw_dir, 'insider', '2025q1_form345.zip'), [
                insider_filing('A1', cik=1, filed='18-MAR-2025', nonderiv=[
                    ('14-MAR-2025', 'A', 'A', '1000.0', '0.0', 'D'),
                    ('17-MAR-2025', 'S', 'D', '1000.0', '50.0', 'D')
                ]),
                insider_filing('B1', cik=2, filed='18-MAR-2020', nonderiv=[('17-MAR-2020', 'S', 'D', '1000.0', '50.0', 'D')])
            ])
            with patch('treadmill_index.extract.ProcessPoolExecutor', ThreadPoolExecutor), \
                 patch('treadmill_index.sec.fetch_url', side_effect=fetch_submission), \
                 patch('time.sleep'), \
                 patch('sys.stdout', StringIO()) as stdout, \
                 patch('sys.stderr', StringIO()):
                self.assertEqual(main(['--raw', raw_dir, '--out', out_dir, '--processes', '1', '--user-agent', 'test-client/1.0']), 0)
            self.assertIn('Reading 2025q1_form345.zip ...', stdout.getvalue().splitlines())

            with open(os.path.join(out_dir, 'index.json'), 'r', encoding='utf-8') as index_file:
                index = json.load(index_file)
            self.assertEqual(
                [(row['name'], row['insiderSales'], row['insiderGrants'], row['salesToGrants'], row['p3'], row['flags'])
                 for row in index['companies']],
                [
                    ('Stock Pay Co', 50000, 50000, 1.0, 8.9, []),
                    ('Cash Co', None, None, None, None, ['no_insider_filings']),
                    ('Bank Co', None, None, None, None, ['no_insider_filings'])
                ]
            )
            self.assertEqual(
                [(row['rank'], row['threeRank'], row['screenScore'], row['threeScore'], row['buybacksFive']) for row in index['companies']],
                [(1, 1, 37.27, 43.9, 0), (None, None, 0.0, None, 0), (None, None, None, None, 0)]
            )
            with open(os.path.join(out_dir, 'meta.json'), 'r', encoding='utf-8') as meta_file:
                meta = json.load(meta_file)
            self.assertEqual(meta['sources']['insider']['files'], ['2025q1_form345.zip'])
            self.assertEqual((meta['insider']['firstYear'], meta['insider']['lastYear']), (2021, 2025))
            self.assertEqual(meta['insider']['screened'], {
                'companies': 1, 'soldMore': 0, 'ownerCash': -161000000, 'tookMore': 1, 'quarters': 2, 'buybackQuarters': 1,
                'sales': 50000, 'purchases': 0, 'withheld': 0, 'toIssuer': 0, 'grants': 50000, 'optionGrants': 0, 'buybacks': 20000000,
                'salesInQuarters': 50000, 'salesInBuybackQuarters': 50000
            })
            self.assertEqual(meta['funnel']['rankedThree'], 1)
            with open(os.path.join(out_dir, 'company', '1.json'), 'r', encoding='utf-8') as company_file:
                company = json.load(company_file)
            self.assertEqual(company['insider']['people'][0]['name'], 'Doe Jane')
            self.assertEqual(company['insider']['quarters'], [
                {'start': '2025-01-01', 'end': '2025-03-31', 'buybacks': 20000000, 'accn': '0000000001-26-000001', 'sales': 50000},
                {'start': '2025-04-01', 'end': '2025-06-30', 'buybacks': 0, 'accn': '0000000001-26-000001', 'sales': 0}
            ])


    def test_main_download_insider(self):
        page = '<a href="/files/structureddata/data/insider-transactions-data-sets/2021q1_form345.zip">2021 Q1</a>'
        with TemporaryDirectory() as temp_dir:
            # Every data set but one is missing from the SEC's list
            with patch('treadmill_index.insider.fetch_url', side_effect=[page.encode('utf-8'), b'zip']) as mock_fetch, \
                 patch('treadmill_index.insider.insider_quarters', return_value=['2021q1', '2021q2']), \
                 patch('time.sleep'), \
                 patch('sys.stdout', StringIO()) as stdout, \
                 patch('sys.stderr', StringIO()) as stderr:
                self.assertEqual(main(['--raw', temp_dir, '--download-insider', '--user-agent', 'Test Person test@example.com']), 1)
            self.assertEqual([call.args[1] for call in mock_fetch.call_args_list], ['Test Person test@example.com'] * 2)
            self.assertEqual(stdout.getvalue().splitlines(), [
                'Downloaded 2021q1 (3 bytes)',
                'Warning: the SEC does not list a data set for 2021q2'
            ])
            self.assertEqual(stderr.getvalue(), '1 insider-transaction data sets are missing\n')
            self.assertEqual(os.listdir(os.path.join(temp_dir, 'insider')), ['2021q1_form345.zip'])

            # Every data set is downloaded
            with patch('treadmill_index.insider.insider_quarters', return_value=['2021q1']), \
                 patch('sys.stdout', StringIO()) as stdout, \
                 patch('sys.stderr', StringIO()) as stderr:
                self.assertEqual(main(['--raw', temp_dir, '--download-insider']), 0)
            self.assertEqual(stdout.getvalue(), 'Every insider-transaction data set is already downloaded\n')
            self.assertEqual(stderr.getvalue(), '')


    def test_main_no_user_agent(self):
        message = 'SEC requests need a User-Agent that names you and gives a contact address. Set the SEC_USER_AGENT ' \
            'environment variable, for example: SEC_USER_AGENT="Your Name you@example.com"\n'
        with TemporaryDirectory() as temp_dir, \
             patch.dict('os.environ'):
            os.environ.pop('SEC_USER_AGENT', None)
            raw_dir = os.path.join(temp_dir, 'raw')
            out_dir = os.path.join(temp_dir, 'out')
            os.mkdir(raw_dir)
            write_companyfacts(raw_dir, [1])

            # The build needs SEC company information
            with patch('treadmill_index.extract.ProcessPoolExecutor', ThreadPoolExecutor), \
                 patch('urllib.request.urlopen') as mock_urlopen, \
                 patch('sys.stdout', StringIO()), \
                 patch('sys.stderr', StringIO()) as stderr:
                self.assertEqual(main(['--raw', raw_dir, '--out', out_dir]), 1)
            self.assertEqual(stderr.getvalue(), message)
            self.assertFalse(os.path.exists(out_dir))

            # The insider-transaction data sets need downloading
            with patch('urllib.request.urlopen') as mock_urlopen_insider, \
                 patch('sys.stdout', StringIO()), \
                 patch('sys.stderr', StringIO()) as stderr:
                self.assertEqual(main(['--raw', raw_dir, '--download-insider']), 1)
            self.assertEqual(stderr.getvalue(), message)
            mock_urlopen.assert_not_called()
            mock_urlopen_insider.assert_not_called()

            # The environment variable is the default
            os.environ['SEC_USER_AGENT'] = 'Test Person test@example.com'
            with patch('treadmill_index.insider.fetch_url', side_effect=OSError('HTTP Error 403')) as mock_fetch, \
                 patch('sys.stdout', StringIO()), \
                 patch('sys.stderr', StringIO()):
                self.assertEqual(main(['--raw', raw_dir, '--download-insider']), 1)
            self.assertEqual(mock_fetch.call_args.args[1], 'Test Person test@example.com')


    def test_main_check_failed(self):
        with TemporaryDirectory() as temp_dir:
            raw_dir = os.path.join(temp_dir, 'raw')
            out_dir = os.path.join(temp_dir, 'out')
            os.mkdir(raw_dir)
            write_companyfacts(raw_dir, [1, 4])
            with patch('treadmill_index.extract.ProcessPoolExecutor', ThreadPoolExecutor), \
                 patch('treadmill_index.sec.fetch_url', side_effect=fetch_submission), \
                 patch('time.sleep'), \
                 patch('sys.stdout', StringIO()) as stdout, \
                 patch('sys.stderr', StringIO()) as stderr:
                self.assertEqual(main(['--raw', raw_dir, '--out', out_dir]), 1)
            self.assertEqual(stdout.getvalue().splitlines(), [
                f'Extracting {os.path.join(raw_dir, "companyfacts.zip")} ...',
                'Warning: no SEC company information for CIK 4: HTTP Error 404'
            ])
            self.assertEqual(
                stderr.getvalue(),
                'Check failed: Unknown Co (CIK 4): no SEC company information, so the industry test was not applied\n'
            )
            self.assertFalse(os.path.exists(out_dir))
