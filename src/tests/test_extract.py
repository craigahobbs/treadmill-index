# pylint: disable=missing-class-docstring, missing-function-docstring, missing-module-docstring

from concurrent.futures import ThreadPoolExecutor
import datetime
import json
import os
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import zipfile

from treadmill_index.extract import annual_facts, extract_all, extract_company, extract_members, load_records, parse_date, period_facts

from .helpers import annual, company_bytes, company_doc, company_record, nine_months, unit


def write_zip(zip_path, members):
    with zipfile.ZipFile(zip_path, 'w') as archive:
        for name, content in members.items():
            archive.writestr(name, content)


class TestExtract(unittest.TestCase):

    def test_parse_date(self):
        self.assertEqual(parse_date('2025-12-31'), datetime.date(2025, 12, 31))


    def test_period_facts(self):
        units = [
            # An instant fact (no start) is skipped
            {'end': '2025-12-31', 'val': 1},
            # Too short and too long
            unit('2025-01-01', '2025-01-31', 2),
            unit('2024-01-01', '2025-12-31', 3),
            # The most recently filed fact wins; the first wins a tie
            unit('2025-01-01', '2025-09-30', 4, accn='A', filed='2025-11-01', form='10-Q'),
            unit('2025-01-01', '2025-09-30', 5, accn='B', filed='2026-11-01', form='10-Q'),
            unit('2025-01-01', '2025-09-30', 6, accn='C', filed='2026-11-01', form='10-Q'),
            # No filed date
            {'start': '2025-01-01', 'end': '2025-06-30', 'val': 7}
        ]
        self.assertEqual(period_facts(units, 60, 349), {
            '2025-01-01|2025-09-30': [5, 'B', '2026-11-01', '10-Q', '2025-01-01'],
            '2025-01-01|2025-06-30': [7, None, '', None, '2025-01-01']
        })


    def test_annual_facts(self):
        units = [
            unit('2025-01-01', '2025-12-31', 1, accn='A', filed='2026-02-01'),
            unit('2024-12-28', '2025-12-31', 2, accn='B', filed='2027-02-01'),
            unit('2024-12-29', '2025-12-31', 3, accn='C', filed='2026-06-01'),
            unit('2025-01-01', '2025-09-30', 4, form='10-Q'),
            unit('2024-01-01', '2024-12-31', 5, accn='D', filed='2025-02-01')
        ]
        self.assertEqual(annual_facts(units), {
            '2025-12-31': [2, 'B', '2027-02-01', '10-K', '2024-12-28'],
            '2024-12-31': [5, 'D', '2025-02-01', '10-K', '2024-01-01']
        })


    def test_extract_company(self):
        record = company_record(cik='0000000007', name='Seven Inc')
        self.assertEqual(record['cik'], 7)
        self.assertEqual(record['name'], 'Seven Inc')
        self.assertEqual(record['filed_max'], '2026-11-05')
        self.assertEqual(sorted(record['annual']['rev']), [f'{year}-12-31' for year in range(2019, 2026)])
        self.assertEqual(
            record['annual']['rev']['2025-12-31'],
            [2e9, '0000000001-26-000010', '2026-02-15', '10-K', '2025-01-01', 'RevenueFromContractWithCustomerExcludingAssessedTax']
        )
        self.assertEqual(record['annual']['sbc']['2025-12-31'][0], 240e6)
        self.assertEqual(record['annual']['sbc2'], {})
        self.assertEqual(record['recent']['rev'], {
            'RevenueFromContractWithCustomerExcludingAssessedTax': {
                '2025-01-01|2025-09-30': [1500e6, '0000000001-25-000030', '2025-11-05', '10-Q', '2025-01-01'],
                '2026-01-01|2026-09-30': [1650e6, '0000000001-26-000030', '2026-11-05', '10-Q', '2026-01-01']
            }
        })
        self.assertEqual(record['recent']['sw'], {})


    def test_extract_company_rejected(self):
        # No stock-pay tags
        self.assertIsNone(extract_company(company_bytes(tags={'ShareBasedCompensation': None})))

        # No revenue tags
        self.assertIsNone(extract_company(company_bytes(tags={'RevenueFromContractWithCustomerExcludingAssessedTax': None})))

        # Invalid JSON
        self.assertIsNone(extract_company(b'{"ShareBasedCompensation": "Revenues"'))

        # Never had $500M of annual revenue
        self.assertIsNone(extract_company(company_bytes(revenue=(100, 200, 300, 400, 499))))

        # No annual revenue
        self.assertIsNone(extract_company(company_bytes(tags={
            'RevenueFromContractWithCustomerExcludingAssessedTax': [nine_months(2025, 1500)]
        })))


    def test_extract_company_tags(self):
        doc = company_doc(tags={
            # Revenue is the largest value across the revenue tags
            'Revenues': [annual(2024, 1900), annual(2025, 1900)],
            # The first operating cash flow tag wins
            'NetCashProvidedByUsedInOperatingActivitiesContinuingOperations': [annual(2025, 1), annual(2018, 2)],
            # Old part-year facts are not kept
            'PaymentsToDevelopSoftware': [annual(2025, 10), nine_months(2022, 5)]
        })
        doc['facts']['us-gaap']['ShareBasedCompensation']['units']['EUR'] = [annual(2017, 1)]
        record = extract_company(json.dumps(doc).encode('utf-8'))
        self.assertEqual(record['annual']['rev']['2024-12-31'][0], 1900e6)
        self.assertEqual(record['annual']['rev']['2024-12-31'][5], 'Revenues')
        self.assertEqual(record['annual']['rev']['2025-12-31'][0], 2000e6)
        self.assertEqual(record['annual']['rev']['2025-12-31'][5], 'RevenueFromContractWithCustomerExcludingAssessedTax')
        self.assertEqual(record['annual']['ocf']['2025-12-31'][0], 240e6)
        self.assertEqual(record['annual']['ocf']['2018-12-31'][0], 2e6)
        self.assertNotIn('2017-12-31', record['annual']['sbc'])
        self.assertEqual(record['annual']['sw']['2025-12-31'][0], 10e6)
        self.assertEqual(record['recent']['sw'], {})


    def test_extract_members(self):
        with TemporaryDirectory() as temp_dir:
            zip_path = os.path.join(temp_dir, 'companyfacts.zip')
            write_zip(zip_path, {
                'CIK0000000002.json': company_bytes(cik=2),
                'CIK0000000003.json': b'{}',
                'CIK0000000001.json': company_bytes(cik=1)
            })
            records = extract_members(zip_path, ['CIK0000000002.json', 'CIK0000000003.json', 'CIK0000000001.json'])
            self.assertEqual([record['cik'] for record in records], [2, 1])


    def test_extract_all(self):
        with TemporaryDirectory() as temp_dir:
            zip_path = os.path.join(temp_dir, 'companyfacts.zip')
            members = {f'CIK{cik:010d}.json': company_bytes(cik=cik) for cik in range(70, 0, -1)}
            members['CIK0000000071.json'] = b'{}'
            members['README.txt'] = b'Not a company'
            write_zip(zip_path, members)
            with patch('treadmill_index.extract.ProcessPoolExecutor', ThreadPoolExecutor):
                records, in_file = extract_all(zip_path, 2)
            self.assertEqual([record['cik'] for record in records], list(range(1, 71)))
            self.assertEqual(in_file, 71)


    def test_load_records(self):
        with TemporaryDirectory() as temp_dir:
            zip_path = os.path.join(temp_dir, 'companyfacts.zip')
            cache_path = os.path.join(temp_dir, 'extract-cache.json')
            write_zip(zip_path, {'CIK0000000001.json': company_bytes(), 'CIK0000000002.json': b'{}'})
            logs = []

            # Extract, then use the cache
            with patch('treadmill_index.extract.ProcessPoolExecutor', ThreadPoolExecutor):
                records, in_file = load_records(zip_path, cache_path, 1, log=logs.append)
            self.assertEqual([record['cik'] for record in records], [1])
            self.assertEqual(in_file, 2)
            with patch('treadmill_index.extract.extract_all') as mock_extract_all:
                self.assertEqual(load_records(zip_path, cache_path, 1, log=logs.append), (records, 2))
            mock_extract_all.assert_not_called()

            # A changed zip is extracted again
            write_zip(zip_path, {'CIK0000000003.json': company_bytes(cik=3)})
            with patch('treadmill_index.extract.ProcessPoolExecutor', ThreadPoolExecutor):
                records, in_file = load_records(zip_path, cache_path, 1, log=logs.append)
            self.assertEqual([record['cik'] for record in records], [3])
            self.assertEqual(in_file, 1)
            self.assertEqual(logs, [
                f'Extracting {zip_path} ...',
                f'Using the cached extract of {zip_path}',
                f'Extracting {zip_path} ...'
            ])
