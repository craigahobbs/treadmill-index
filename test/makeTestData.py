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

from tests.helpers import REVENUE, annual, company_bytes
from treadmill_index.main import main


# The made-up companies - the company_bytes arguments, and the SEC company information
COMPANIES = [
    (
        {'cik': 1, 'name': 'Stock Pay Co'},
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


def fetch_submission(url, unused_user_agent):
    cik = int(url.split('CIK')[1].split('.')[0])
    return json.dumps(next(info for company, info in COMPANIES if company['cik'] == cik)).encode('utf-8')


def make_test_data(out_dir):
    with TemporaryDirectory() as raw_dir:
        with zipfile.ZipFile(os.path.join(raw_dir, 'companyfacts.zip'), 'w') as archive:
            for company, _ in COMPANIES:
                archive.writestr(f'CIK{company["cik"]:010d}.json', company_bytes(**company))
        shutil.rmtree(out_dir, ignore_errors=True)
        with patch('treadmill_index.extract.ProcessPoolExecutor', ThreadPoolExecutor), \
             patch('treadmill_index.sec.fetch_url', side_effect=fetch_submission), \
             patch('treadmill_index.output.file_sha256', return_value='0123456789abcdef'), \
             patch('os.path.getsize', return_value=123456789), \
             patch('time.sleep'):
            return main(['--raw', raw_dir, '--out', out_dir, '--processes', '1'])


if __name__ == '__main__':
    sys.exit(make_test_data(os.path.join(os.path.dirname(__file__), 'data')))
