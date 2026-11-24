# Licensed under the MIT License
# https://github.com/craigahobbs/treadmill-index/blob/main/LICENSE

# pylint: disable=missing-class-docstring, missing-function-docstring, missing-module-docstring

import json
import os
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import MagicMock, patch
import zipfile

from treadmill_index.sec import UserAgentError, fetch_url, load_submissions, slim_submission


SUBMISSION = {
    'cik': '0000000001',
    'name': 'Test Co',
    'sic': '7372',
    'sicDescription': 'Services-Prepackaged Software',
    'tickers': ['TEST', 'TESTW'],
    'exchanges': ['Nasdaq', 'Nasdaq'],
    'formerNames': [{'name': 'Old Test Co', 'from': '2010-01-01T00:00:00.000Z', 'to': '2015-01-01T00:00:00.000Z'}],
    'filings': {'recent': {}}
}

SLIM = {
    'sic': 7372,
    'sicDescription': 'Services-Prepackaged Software',
    'tickers': ['TEST', 'TESTW'],
    'exchanges': ['Nasdaq', 'Nasdaq'],
    'formerNames': ['Old Test Co']
}

EMPTY = {'sic': None, 'sicDescription': None, 'tickers': [], 'exchanges': [], 'formerNames': []}


class TestSec(unittest.TestCase):

    def test_slim_submission(self):
        self.assertEqual(slim_submission(SUBMISSION), SLIM)
        self.assertEqual(slim_submission({'sic': '', 'sicDescription': '', 'tickers': None}), EMPTY)


    def test_fetch_url(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'{}'
        with patch('urllib.request.urlopen', return_value=response) as mock_urlopen:
            self.assertEqual(fetch_url('https://data.sec.gov/submissions/CIK0000000001.json', 'test-client/1.0'), b'{}')
        request = mock_urlopen.call_args.args[0]
        self.assertEqual(request.full_url, 'https://data.sec.gov/submissions/CIK0000000001.json')
        self.assertEqual(request.get_header('User-agent'), 'test-client/1.0')
        self.assertEqual(mock_urlopen.call_args.kwargs, {'timeout': 60})


    def test_fetch_url_no_user_agent(self):
        for user_agent in (None, ''):
            with patch('urllib.request.urlopen') as mock_urlopen:
                with self.assertRaises(UserAgentError) as cm_exc:
                    fetch_url('https://data.sec.gov/submissions/CIK0000000001.json', user_agent)
            mock_urlopen.assert_not_called()
            self.assertEqual(
                str(cm_exc.exception),
                'SEC requests need a User-Agent that names you and gives a contact address. Set the SEC_USER_AGENT environment '
                'variable, for example: SEC_USER_AGENT="Your Name you@example.com"'
            )


    def test_load_submissions_no_user_agent(self):
        with TemporaryDirectory() as temp_dir:
            # A company that must be fetched needs a User-Agent
            with patch('urllib.request.urlopen') as mock_urlopen, \
                 patch('time.sleep'):
                with self.assertRaises(UserAgentError):
                    load_submissions([1], temp_dir, None)
            mock_urlopen.assert_not_called()
            self.assertEqual(os.listdir(temp_dir), [])

            # Cached companies do not
            with open(os.path.join(temp_dir, 'submissions-cache.json'), 'w', encoding='utf-8') as cache_file:
                json.dump({'1': SLIM}, cache_file)
            self.assertEqual(load_submissions([1], temp_dir, None), {1: SLIM})


    def test_load_submissions(self):
        def fetch(url, user_agent):
            self.assertEqual(user_agent, 'test-client/1.0')
            if url.endswith('CIK0000000002.json'):
                raise OSError('HTTP Error 404')
            if url.endswith('CIK0000000003.json'):
                return b'not JSON'
            return json.dumps(SUBMISSION).encode('utf-8')

        with TemporaryDirectory() as temp_dir:
            logs = []
            with patch('treadmill_index.sec.fetch_url', side_effect=fetch) as mock_fetch, \
                 patch('time.sleep') as mock_sleep:
                infos = load_submissions([3, 2, 1], temp_dir, 'test-client/1.0', log=logs.append)
            self.assertEqual(infos, {1: SLIM})
            self.assertEqual([call.args[0] for call in mock_fetch.call_args_list], [
                'https://data.sec.gov/submissions/CIK0000000001.json',
                'https://data.sec.gov/submissions/CIK0000000002.json',
                'https://data.sec.gov/submissions/CIK0000000003.json'
            ])
            self.assertEqual([call.args for call in mock_sleep.call_args_list], [(0.15,), (0.15,), (0.15,)])
            self.assertEqual(logs, [
                'Warning: no SEC company information for CIK 2: HTTP Error 404',
                'Warning: no SEC company information for CIK 3: Expecting value: line 1 column 1 (char 0)'
            ])
            with open(os.path.join(temp_dir, 'submissions-cache.json'), 'r', encoding='utf-8') as cache_file:
                self.assertEqual(json.load(cache_file), {'1': SLIM})

            # Cached companies are not fetched again
            with patch('treadmill_index.sec.fetch_url') as mock_fetch:
                self.assertEqual(load_submissions([1], temp_dir, 'test-client/1.0', log=logs.append), {1: SLIM})
            mock_fetch.assert_not_called()


    def test_load_submissions_progress(self):
        with TemporaryDirectory() as temp_dir:
            logs = []
            with patch('treadmill_index.sec.fetch_url', return_value=b'{}'), \
                 patch('time.sleep'):
                infos = load_submissions(range(1, 202), temp_dir, 'test-client/1.0', pause=0, log=logs.append)
            self.assertEqual(infos, dict.fromkeys(range(1, 202), EMPTY))
            self.assertEqual(logs, ['Fetched 100 SEC company records ...', 'Fetched 200 SEC company records ...'])


    def test_load_submissions_zip(self):
        with TemporaryDirectory() as temp_dir:
            with zipfile.ZipFile(os.path.join(temp_dir, 'submissions.zip'), 'w') as archive:
                archive.writestr('CIK0000000001.json', json.dumps(SUBMISSION))
                archive.writestr('CIK0000000001-submissions-001.json', '{}')

            # The bulk file has the first company; the second is fetched
            with patch('treadmill_index.sec.fetch_url', return_value=b'{}') as mock_fetch, \
                 patch('time.sleep'):
                infos = load_submissions([1, 2], temp_dir, 'test-client/1.0')
            self.assertEqual(infos, {1: SLIM, 2: EMPTY})
            mock_fetch.assert_called_once_with('https://data.sec.gov/submissions/CIK0000000002.json', 'test-client/1.0')
