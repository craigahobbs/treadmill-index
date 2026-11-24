"""
Generate the web application's unit test data, test/data/, by running the build step on a few made-up companies.
Run it with "make test-data" after a change to the data files' content.
"""

from concurrent.futures import ThreadPoolExecutor
import json
import os
import shutil
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch
import zipfile

from tests.helpers import REVENUE, annual, company_bytes, insider_filing, insider_zip, unit
from treadmill_index.main import main


# The made-up companies - the company_bytes arguments, and the SEC company information
COMPANIES = [
    (
        {'cik': 1, 'name': 'Stock Pay Co', 'tags': {'PaymentsForRepurchaseOfCommonStock': [
            annual(2024, 40),
            unit('2024-01-01', '2024-03-31', 10e6, accn='0000000001-24-000020', filed='2024-05-05', form='10-Q'),
            unit('2024-01-01', '2024-06-30', 10e6, accn='0000000001-24-000021', filed='2024-08-05', form='10-Q'),
            unit('2024-01-01', '2024-09-30', 40e6, accn='0000000001-24-000022', filed='2024-11-05', form='10-Q')
        ]}},
        {'sic': '7372', 'sicDescription': 'Services-Prepackaged Software', 'tickers': ['SPAY'], 'exchanges': ['Nasdaq']}
    ),
    (
        {'cik': 2, 'name': 'Capital & Sons [Holdings]', 'ocf': 0.4, 'capex': 0.3, 'operating': [50, 55, 62.5, 70, 80, 90, 150]},
        {'sic': '3674', 'sicDescription': 'Semiconductors & Related Devices', 'tickers': [], 'exchanges': []}
    ),
    (
        {'cik': 3, 'name': 'No Cost Line Co', 'sbc': 0.2, 'quarters': False, 'tags': {
            'GrossProfit': None,
            'PaymentsToAcquirePropertyPlantAndEquipment': [annual(2019, 20)]
        }},
        {'sic': '7372', 'sicDescription': 'Services-Prepackaged Software', 'tickers': ['NCL'], 'exchanges': ['NYSE']}
    ),
    (
        {'cik': 4, 'name': 'Cash Co', 'sbc': 0.02, 'operating': [50, 55, 62.5, 70, 80, 90, 400], 'tags': {
            'WeightedAverageNumberOfDilutedSharesOutstanding': [annual(2019 + index, 100 * 1.05 ** index) for index in range(7)],
            'PaymentsForRepurchaseOfCommonStock': [annual(2024, 100), annual(2025, 150)],
            'PaymentsOfDividends': [annual(2025, 20)]
        }},
        {'sic': '7372', 'sicDescription': 'Services-Prepackaged Software', 'tickers': ['CASH', 'CASHW'], 'exchanges': ['NYSE', 'NYSE'],
         'formerNames': [{'name': 'Old Cash Co'}, {'name': 'Older Cash Co'}]}
    ),
    (
        {'cik': 5, 'name': 'Bank Co', 'sbc': 0.2},
        {'sic': '6021', 'sicDescription': 'National Commercial Banks', 'tickers': ['BANK'], 'exchanges': ['NYSE']}
    ),
    (
        {'cik': 6, 'name': 'One-Off Co', 'sbc': 0.13, 'tags': {
            'IncreaseDecreaseInInventories': [annual(2019, -300), annual(2020, 300)],
            'PaymentsToDevelopSoftware': [annual(2019 + index, value * 0.01) for index, value in enumerate(REVENUE)],
            'WeightedAverageNumberOfDilutedSharesOutstanding': [annual(2019 + index, 100 * 3 ** (index > 2)) for index in range(7)]
        }},
        {'sic': '5961', 'sicDescription': 'Retail-Catalog & Mail-Order Houses', 'tickers': ['OOC'], 'exchanges': ['Nasdaq']}
    ),
    (
        {'cik': 7, 'name': 'Thin Co', 'ocf': 0.045, 'sbc': 0.019},
        {'sic': '5000', 'sicDescription': None, 'tickers': ['THIN'], 'exchanges': [None]}
    ),
    (
        {'cik': 8, 'name': 'Burner Co', 'ocf': 0.01},
        {'sic': None, 'sicDescription': None, 'tickers': ['BURN'], 'exchanges': ['Nasdaq']}
    ),
    (
        {'cik': 9, 'name': 'Slower Co', 'revenue': (1000, 1100, 1200, 1300, 1450), 'sbc': 0.2},
        {'sic': '7372', 'sicDescription': 'Services-Prepackaged Software', 'tickers': ['SLOW'], 'exchanges': ['Nasdaq']}
    ),
    (
        {'cik': 10, 'name': 'Marginal Co', 'sbc': 0.074},
        {'sic': '7372', 'sicDescription': 'Services-Prepackaged Software', 'tickers': ['MARG'], 'exchanges': ['Nasdaq']}
    )
]


# The made-up insider filings. Company 2 has none.
DIRECTOR = ('0000001002', 'Roe Rich', 'Director', '')
INSIDER_FILINGS = [
    # Company 1: grants and sales by two insiders
    insider_filing('0000000001-24-000101', cik=1, filed='18-MAR-2024', nonderiv=[
        ('15-MAR-2024', 'S', 'D', '1000.0', '50.0', 'D'),
        ('15-MAR-2024', 'S', 'D', '1000.0', '52.0', 'D')
    ]),
    insider_filing('0000000001-24-000102', cik=1, filed='25-MAR-2024', nonderiv=[
        ('20-MAR-2024', 'F', 'D', '100.0', '55.0', 'D'),
        ('22-MAR-2024', 'A', 'A', '2000.0', '0.0', 'D'),
        ('22-MAR-2024', 'G', 'D', '300.0', '', 'D'),
        ('22-MAR-2024', 'D', 'D', '10.0', '54.0', 'D')
    ], deriv=[
        ('22-MAR-2024', 'A', 'A', '5000.0', '', 'D', '', 'Stock Option (Right to Buy)', '60.0', '5000.0')
    ]),
    insider_filing('0000000001-25-000103', cik=1, filed='3-FEB-2025', nonderiv=[('1-FEB-2025', 'P', 'A', '100.0', '40.0', 'D')]),
    insider_filing('0000000001-25-000104', cik=1, filed='4-FEB-2025', owners=[DIRECTOR],
                   nonderiv=[('3-FEB-2025', 'S', 'D', '200.0', '41.0', 'D')]),

    # Company 6: a grant with no share price near it, so no ratio
    insider_filing('0000000006-23-000101', cik=6, filed='16-MAR-2023', nonderiv=[('15-MAR-2023', 'S', 'D', '100.0', '40.0', 'D')]),
    insider_filing('0000000006-25-000102', cik=6, filed='3-JUN-2025', nonderiv=[('1-JUN-2025', 'A', 'A', '500.0', '0.0', 'D')]),

    # Company 4: sales and no grants
    insider_filing('0000000004-22-000101', cik=4, filed='16-MAR-2022', nonderiv=[('15-MAR-2022', 'S', 'D', '50000000.0', '30.0', 'D')]),

    # Company 5, in an excluded industry
    insider_filing('0000000005-22-000101', cik=5, filed='16-MAR-2022', nonderiv=[('15-MAR-2022', 'S', 'D', '40000.0', '30.0', 'D')])
]


def fetch_submission(url, unused_user_agent):
    cik = int(url.split('CIK')[1].split('.')[0])
    return json.dumps(next(info for company, info in COMPANIES if company['cik'] == cik)).encode('utf-8')


def make_test_data(out_dir):
    # Build twice: with the insider data sets, and without them (to "noinsider")
    shutil.rmtree(out_dir, ignore_errors=True)
    for insider, build_dir in ((True, out_dir), (False, os.path.join(out_dir, 'noinsider'))):
        with TemporaryDirectory() as raw_dir:
            with zipfile.ZipFile(os.path.join(raw_dir, 'companyfacts.zip'), 'w') as archive:
                for company, _ in COMPANIES:
                    archive.writestr(f'CIK{company["cik"]:010d}.json', company_bytes(**company))
            if insider:
                os.mkdir(os.path.join(raw_dir, 'insider'))
                insider_zip(os.path.join(raw_dir, 'insider', '2025q4_form345.zip'), INSIDER_FILINGS)
            with patch('treadmill_index.extract.ProcessPoolExecutor', ThreadPoolExecutor), \
                 patch('treadmill_index.sec.fetch_url', side_effect=fetch_submission), \
                 patch('treadmill_index.output.file_sha256', return_value='0123456789abcdef'), \
                 patch('treadmill_index.main.os.path.getsize', return_value=123456789), \
                 patch('time.sleep'):
                if main(['--raw', raw_dir, '--out', build_dir, '--processes', '1', '--user-agent', 'test-client/1.0']):
                    return 1
    return 0


if __name__ == '__main__':
    sys.exit(make_test_data(os.path.join(os.path.dirname(__file__), 'data')))
