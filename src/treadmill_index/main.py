"""
The Treadmill Index build step's command-line script main module
"""

import argparse
import json
import os
import sys

from .extract import load_records
from .output import build_meta, file_sha256, write_output
from .score import evaluate, loose_thresholds, run_screen, sensitivity
from .sec import load_submissions


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
    parser.add_argument('--user-agent', metavar='TEXT', default=os.environ.get('SEC_USER_AGENT', 'sec-data-client/1.0'),
                        help='the User-Agent header for SEC requests (default is the SEC_USER_AGENT environment variable)')
    args = parser.parse_args(args=argv)

    # Extract the companies
    zip_path = os.path.join(args.raw, 'companyfacts.zip')
    records, in_file = load_records(zip_path, os.path.join(args.raw, 'extract-cache.json'), args.processes)
    data_date = max(record['filed_max'] for record in records)

    # Load industry codes and tickers for every company that passes the basic tests, or would if they moved by a fifth
    loose = loose_thresholds()
    ciks = [record['cik'] for record in records if evaluate(record, None, data_date, loose)['stage'] == 'scored']
    infos = load_submissions(ciks, args.raw, args.user_agent)
    sics = {cik: info['sic'] for cik, info in infos.items()}

    # Screen, score and write
    results, funnel = run_screen(records, sics, data_date)
    sources = {
        'companyfacts': {
            'url': 'https://www.sec.gov/Archives/edgar/daily-index/xbrl/companyfacts.zip',
            'sha256': file_sha256(zip_path),
            'bytes': os.path.getsize(zip_path),
            'latestFiling': data_date
        },
        'submissions': {'url': 'https://data.sec.gov/submissions/', 'companies': len(infos)}
    }
    meta = build_meta(results, funnel, in_file, sources, sensitivity(records, sics, data_date, results))
    problems = write_output(args.out, results, infos, meta)
    if problems:
        for problem in problems:
            print(f'Check failed: {problem}', file=sys.stderr)
        return 1
    print(json.dumps(meta['funnel']))
    print(f'Wrote {len(results)} companies to "{args.out}" - data as of {data_date}')
    return 0
