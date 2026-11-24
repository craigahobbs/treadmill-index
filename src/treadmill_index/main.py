"""
The Treadmill Index build step's command-line script main module
"""

import argparse
import datetime
import json
import os
import sys

from .extract import load_records
from .insider import INSIDER_PAGE_URL, buyback_quarters, download_insider, insider_summary, load_insider
from .output import build_meta, file_sha256, write_output
from .score import THRESHOLDS, evaluate, loose_thresholds, run_screen, sensitivity
from .sec import UserAgentError, load_submissions


def main(argv=None):
    """
    The Treadmill Index build step's command-line script main entry point
    """

    # Command line arguments
    argument_parser_args = {'prog': 'treadmill-index'}
    if sys.version_info >= (3, 14): # pragma: no cover
        argument_parser_args['color'] = False
    parser = argparse.ArgumentParser(**argument_parser_args, description='Build the Treadmill Index data files from SEC bulk data')
    parser.add_argument('--raw', metavar='DIR', default='data/raw',
                        help='the directory that holds the SEC "companyfacts.zip" bulk file (default is "data/raw")')
    parser.add_argument('--out', metavar='DIR', default='data',
                        help='the output directory (default is "data")')
    parser.add_argument('--processes', metavar='N', type=int, default=os.cpu_count(),
                        help='the number of extraction processes (default is the CPU count)')
    parser.add_argument('--user-agent', metavar='TEXT', default=os.environ.get('SEC_USER_AGENT'),
                        help='the User-Agent header for SEC requests, required if any are made: your name and a contact address '
                        '(default is the SEC_USER_AGENT environment variable)')
    parser.add_argument('--download-insider', action='store_true',
                        help='download the SEC insider-transaction data sets to the "insider" directory of --raw, and exit')
    args = parser.parse_args(args=argv)
    try:
        return build(args)
    except UserAgentError as exc:
        print(exc, file=sys.stderr)
        return 1


def build(args):
    """
    Run the build step

    :param args: The parsed command-line arguments
    :returns: The exit code
    """

    # Download the insider-transaction data sets?
    if args.download_insider:
        missing = download_insider(args.raw, args.user_agent, datetime.date.today())
        if missing:
            print(f'{missing} insider-transaction data sets are missing', file=sys.stderr)
        return 1 if missing else 0

    # Extract the companies
    zip_path = os.path.join(args.raw, 'companyfacts.zip')
    records, in_file = load_records(zip_path, os.path.join(args.raw, 'extract-cache.json'), args.processes)
    data_date = max(record['filed_max'] for record in records)

    # Load industry codes and tickers for every company that passes the basic tests, or would if they moved by a fifth
    loose = loose_thresholds()
    ciks = [record['cik'] for record in records if evaluate(record, None, data_date, loose)['stage'] == 'scored']
    infos = load_submissions(ciks, args.raw, args.user_agent)
    sics = {cik: info['sic'] for cik, info in infos.items()}

    # Summarize the insiders' grants and sales over the latest whole calendar years, if the data sets are there
    transactions, insider_files = load_insider(args.raw, ciks)
    last_year = int(data_date[:4]) - 1
    insiders = None
    insider_years = None
    if insider_files:
        insiders = {}
        insider_years = (last_year - THRESHOLDS['p3_years'] + 1, last_year)
        buybacks = {record['cik']: record['buybacks'] for record in records}
        for cik, cik_transactions in transactions.items():
            summary = insider_summary(cik_transactions, last_year, THRESHOLDS, buyback_quarters(buybacks[int(cik)]))
            if summary is not None:
                insiders[int(cik)] = summary

    # Screen, score and write
    results, funnel = run_screen(records, sics, data_date, insiders=insiders)
    sources = {
        'companyfacts': {
            'url': 'https://www.sec.gov/Archives/edgar/daily-index/xbrl/companyfacts.zip',
            'sha256': file_sha256(zip_path),
            'bytes': os.path.getsize(zip_path),
            'latestFiling': data_date
        },
        'submissions': {'url': 'https://data.sec.gov/submissions/', 'companies': len(infos)},
        'insider': {'url': INSIDER_PAGE_URL, 'files': insider_files}
    }
    meta = build_meta(results, funnel, in_file, sources, sensitivity(records, sics, data_date, results, insiders), insider_years)
    problems = write_output(args.out, results, infos, meta)
    if problems:
        for problem in problems:
            print(f'Check failed: {problem}', file=sys.stderr)
        return 1
    print(json.dumps(meta['funnel']))
    print(f'Wrote {len(results)} companies to "{args.out}" - data as of {data_date}')
    return 0
