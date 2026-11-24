# Licensed under the MIT License
# https://github.com/craigahobbs/treadmill-index/blob/main/LICENSE

"""
SEC company information: industry (SIC) codes, tickers and former names
"""

import json
import os
import time
import urllib.request
import zipfile


# The SEC's per-company API
SUBMISSIONS_URL = 'https://data.sec.gov/submissions/CIK{cik:010d}.json'


def slim_submission(doc):
    """
    Keep the fields the index uses from an SEC submissions document

    :param dict doc: The submissions document
    :rtype: dict
    """

    sic = doc.get('sic')
    return {
        'sic': int(sic) if sic else None,
        'sicDescription': doc.get('sicDescription') or None,
        'tickers': doc.get('tickers') or [],
        'exchanges': doc.get('exchanges') or [],
        'formerNames': [former.get('name') for former in doc.get('formerNames') or []]
    }


class UserAgentError(Exception):
    """
    An SEC request was needed and no User-Agent was given
    """

    def __init__(self):
        super().__init__(
            'SEC requests need a User-Agent that names you and gives a contact address. Set the SEC_USER_AGENT environment '
            'variable, for example: SEC_USER_AGENT="Your Name you@example.com"'
        )


def fetch_url(url, user_agent):
    """
    Fetch a URL from the SEC

    :param str url: The URL
    :param str user_agent: The User-Agent header. There is no default: the requester must supply their own.
    :rtype: bytes
    :raises UserAgentError: There is no User-Agent
    """

    if not user_agent:
        raise UserAgentError()
    request = urllib.request.Request(url, headers={'User-Agent': user_agent})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def load_submissions(ciks, raw_dir, user_agent, pause=0.15, log=print):
    """
    Load SEC company information: from the SEC bulk file "submissions.zip" when it is in the raw directory, else
    from the SEC's per-company API. Results are cached in "submissions-cache.json" in the raw directory.

    :param list(int) ciks: The companies' CIKs
    :param str raw_dir: The raw data directory
    :param str user_agent: The User-Agent header for SEC requests. It is needed only if a company is fetched.
    :param float pause: The seconds to pause between SEC requests (the SEC allows ten requests a second)
    :param log: The log function
    :returns: The dict of CIK to company information. Companies the SEC has nothing for are left out.
    """

    cache_path = os.path.join(raw_dir, 'submissions-cache.json')
    cache = {}
    if os.path.exists(cache_path):
        with open(cache_path, 'r', encoding='utf-8') as cache_file:
            cache = json.load(cache_file)
    missing = [cik for cik in sorted(ciks) if str(cik) not in cache]

    # Read the bulk file
    zip_path = os.path.join(raw_dir, 'submissions.zip')
    if missing and os.path.exists(zip_path):
        with zipfile.ZipFile(zip_path) as archive:
            members = set(archive.namelist())
            for cik in missing:
                member = f'CIK{cik:010d}.json'
                if member in members:
                    cache[str(cik)] = slim_submission(json.loads(archive.read(member)))

    # Fetch what is still missing
    fetched = 0
    for cik in missing:
        if str(cik) not in cache:
            try:
                cache[str(cik)] = slim_submission(json.loads(fetch_url(SUBMISSIONS_URL.format(cik=cik), user_agent)))
            except (OSError, ValueError) as exc:
                log(f'Warning: no SEC company information for CIK {cik}: {exc}')
            fetched += 1
            if fetched % 100 == 0:
                log(f'Fetched {fetched} SEC company records ...')
            time.sleep(pause)

    if missing:
        with open(cache_path, 'w', encoding='utf-8') as cache_file:
            json.dump(cache, cache_file, sort_keys=True)
    return {cik: cache[str(cik)] for cik in ciks if str(cik) in cache}
