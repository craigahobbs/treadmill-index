"""
The SEC insider-transaction data sets (Forms 3, 4 and 5): one zip file per calendar quarter
"""

import bisect
import csv
import datetime
import io
import json
import os
import re
import statistics
import time
from urllib.parse import urljoin
import zipfile

from .extract import F_ACCN, F_VAL, parse_date
from .sec import fetch_url


# The SEC page that lists the quarterly data sets. The files' folder has changed over time, so the links are
# read from the page instead of being built from a pattern.
INSIDER_PAGE_URL = 'https://www.sec.gov/data-research/sec-markets-data/insider-transactions-data-sets'

_RE_LINK = re.compile(r'href="([^"]*/insider-transactions-data-sets/(\d{4}q[1-4])_form345\.zip)"')


def insider_links(html):
    """
    Get the data set links from the SEC's insider-transaction data sets page

    :param str html: The page's HTML
    :returns: The dict of quarter, for example "2025q4", to the data set's URL
    """

    return {quarter: urljoin(INSIDER_PAGE_URL, href) for href, quarter in _RE_LINK.findall(html)}


def insider_quarters(today, years=5):
    """
    Get the quarters the index needs: from the first quarter of the calendar year some years back, through the
    last quarter that has ended

    :param datetime.date today: Today's date
    :param int years: The number of calendar years back to start from
    :returns: The list of quarters, for example "2025q4", oldest first
    """

    last_year, last_quarter = today.year, (today.month - 1) // 3
    if last_quarter == 0:
        last_year, last_quarter = last_year - 1, 4
    return [
        f'{year}q{quarter}'
        for year in range(today.year - years, last_year + 1)
        for quarter in range(1, 5)
        if (year, quarter) <= (last_year, last_quarter)
    ]


def download_insider(raw_dir, user_agent, today, pause=0.5, log=print):
    """
    Download the insider-transaction data sets the index needs to the raw directory's "insider" directory.
    Files that are already there are not downloaded again.

    :param str raw_dir: The raw data directory
    :param str user_agent: The User-Agent header for SEC requests. The SEC refuses these files without one that
        names the requester and gives a contact address. It is needed only if a file is downloaded.
    :param datetime.date today: Today's date
    :param float pause: The seconds to pause between SEC requests
    :param log: The log function
    :returns: The number of data sets that are still missing
    """

    insider_dir = os.path.join(raw_dir, 'insider')
    os.makedirs(insider_dir, exist_ok=True)
    quarters = [quarter for quarter in insider_quarters(today) if not os.path.exists(os.path.join(insider_dir, f'{quarter}_form345.zip'))]
    if not quarters:
        log('Every insider-transaction data set is already downloaded')
        return 0

    try:
        links = insider_links(fetch_url(INSIDER_PAGE_URL, user_agent).decode('utf-8'))
    except OSError as exc:
        log(f'The SEC refused the list of data sets: {exc}')
        log('Set SEC_USER_AGENT to a User-Agent that names you and gives a contact address, or download the files in a browser')
        return len(quarters)

    missing = 0
    for quarter in quarters:
        if quarter not in links:
            log(f'Warning: the SEC does not list a data set for {quarter}')
            missing += 1
            continue
        try:
            content = fetch_url(links[quarter], user_agent)
        except OSError as exc:
            log(f'Warning: the download of {quarter} failed: {exc}')
            missing += 1
            continue
        with open(os.path.join(insider_dir, f'{quarter}_form345.zip'), 'wb') as zip_file:
            zip_file.write(content)
        log(f'Downloaded {quarter} ({len(content):,} bytes)')
        time.sleep(pause)
    return missing


#
# Reading the data sets
#


# The insider cache version - bump when the parsed transactions change
INSIDER_VERSION = 2

# The forms used. Amended filings (4/A, 5/A) are not used: they restate transactions already reported.
INSIDER_FORMS = ('4', '5')

# Reporting owners with these words in their name are entities - funds, companies and trusts - not people
_RE_ENTITY = re.compile(
    r'\b(l\.?l?\.?l?\.?p\.?|l\.?l\.?c\.?|fund|funds|capital|partners|partnership|ventures|management|holdings|trust|inc\.?|ltd\.?|'
    r'corp\.?|corporation|advisors|advisers|associates|gp|group|investments?|company|co\.|limited|foundation|plc|estate|n\.v\.|s\.a\.)'
    r'(?![\w])',
    re.IGNORECASE
)

# Indirect holdings with these words in their nature of ownership are an insider's own: family, trusts and
# retirement accounts. An outside director's other indirect holdings are taken to be an investment fund's.
_RE_PERSONAL = re.compile(
    r'trust|spouse|wife|husband|family|child|son\b|daughter|minor|custodian|grantor|grat\b|descendant|estate|joint|\bira\b|401',
    re.IGNORECASE
)

# Derivative securities with these words in their title are options: their value is less than the shares they cover
_RE_OPTION = re.compile(r'option|right to buy|appreciation', re.IGNORECASE)

# The transaction kinds, by table, transaction code and acquired/disposed code
_KINDS = {
    ('NONDERIV_TRANS.tsv', 'S', 'D'): 'sale',
    ('NONDERIV_TRANS.tsv', 'P', 'A'): 'purchase',
    ('NONDERIV_TRANS.tsv', 'A', 'A'): 'grant',
    ('NONDERIV_TRANS.tsv', 'F', 'D'): 'withheld',
    ('NONDERIV_TRANS.tsv', 'D', 'D'): 'issuer',
    ('NONDERIV_TRANS.tsv', 'G', 'D'): 'gift',
    ('DERIV_TRANS.tsv', 'A', 'A'): 'grant'
}

_MONTHS = {
    month: index + 1
    for index, month in enumerate(('JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC'))
}


def parse_sec_date(text):
    """
    Parse a date from the insider data sets, for example "31-DEC-2025"

    :param str text: The date text
    :returns: The ISO date, or None if the text is not a date
    """

    parts = text.split('-')
    if len(parts) != 3 or parts[1].upper() not in _MONTHS or not (parts[0].isdigit() and parts[2].isdigit()):
        return None
    return f'{int(parts[2]):04d}-{_MONTHS[parts[1].upper()]:02d}-{int(parts[0]):02d}'


def parse_number(text):
    """
    Parse a number from the insider data sets

    :param str text: The number text
    :returns: The number, or None if the text is empty or not a number
    """

    try:
        return float(text)
    except ValueError:
        return None


def filing_insider(owners):
    """
    Get the insider a filing's transactions belong to. Insiders are officers and directors who are people. A
    filing made jointly with an entity counts only if one of its people is an officer: an officer's own trust
    or holding company is theirs, but an outside director filing with an entity is filing for a fund.

    An outside director's holdings through an entity are left out too, when the transactions are read: they are
    taken to be an investment fund's unless the nature of ownership names a trust, family or a retirement account.

    :param list(dict) owners: The filing's REPORTINGOWNER rows
    :returns: The insider's REPORTINGOWNER row, or None if the filing is not an insider's
    """

    people = [
        owner for owner in owners
        if not _RE_ENTITY.search(owner['RPTOWNERNAME']) and
        ('Officer' in owner['RPTOWNER_RELATIONSHIP'] or 'Director' in owner['RPTOWNER_RELATIONSHIP'])
    ]
    officers = [owner for owner in people if 'Officer' in owner['RPTOWNER_RELATIONSHIP']]
    if officers:
        return officers[0]
    if people and len(people) == len(owners):
        return people[0]
    return None


def _read_table(archive, name):
    with archive.open(name) as table_file:
        yield from csv.DictReader(io.TextIOWrapper(table_file, encoding='utf-8', errors='replace'), delimiter='\t', quoting=csv.QUOTE_NONE)


def read_insider_zip(zip_path, ciks):
    """
    Read the insiders' transactions in a quarterly data set

    :param str zip_path: The data set's zip file path
    :param set(int) ciks: The companies (issuers) to read
    :returns: The dict of company CIK to the list of transactions. A transaction is a dict of "accn", "filed",
        "owner" (the insider's CIK), "name", "title", "kind" ("sale", "purchase", "grant", "option", "withheld",
        "issuer" or "gift"), "date", "shares" and "price" (as reported; for an option, its exercise price).
    """

    transactions = {}
    with zipfile.ZipFile(zip_path) as archive:
        # The filings of the companies
        filings = {}
        for row in _read_table(archive, 'SUBMISSION.tsv'):
            if row['DOCUMENT_TYPE'] in INSIDER_FORMS and row['ISSUERCIK'].isdigit() and int(row['ISSUERCIK']) in ciks:
                filings[row['ACCESSION_NUMBER']] = {'cik': int(row['ISSUERCIK']), 'filed': parse_sec_date(row['FILING_DATE']), 'owners': []}
        for row in _read_table(archive, 'REPORTINGOWNER.tsv'):
            if row['ACCESSION_NUMBER'] in filings:
                filings[row['ACCESSION_NUMBER']]['owners'].append(row)
        for filing in filings.values():
            filing['insider'] = filing_insider(filing['owners'])

        # The insiders' transactions
        for table in ('NONDERIV_TRANS.tsv', 'DERIV_TRANS.tsv'):
            for row in _read_table(archive, table):
                filing = filings.get(row['ACCESSION_NUMBER'])
                kind = _KINDS.get((table, row['TRANS_CODE'], row['TRANS_ACQUIRED_DISP_CD']))
                date = parse_sec_date(row['TRANS_DATE'])
                if filing is None or filing['insider'] is None or kind is None or date is None:
                    continue
                insider = filing['insider']
                is_fund = 'Officer' not in insider['RPTOWNER_RELATIONSHIP'] and row['DIRECT_INDIRECT_OWNERSHIP'] == 'I' and \
                    not _RE_PERSONAL.search(row['NATURE_OF_OWNERSHIP'])
                if is_fund:
                    continue
                shares = parse_number(row['TRANS_SHARES'])
                price = parse_number(row['TRANS_PRICEPERSHARE'])
                if table == 'DERIV_TRANS.tsv':
                    # A derivative grant covers its underlying shares; an option's price is its exercise price
                    shares = parse_number(row['UNDLYNG_SEC_SHARES']) or shares
                    price = None
                    if _RE_OPTION.search(row['SECURITY_TITLE']):
                        kind = 'option'
                        price = parse_number(row['CONV_EXERCISE_PRICE'])
                if not shares or shares <= 0:
                    continue
                transactions.setdefault(filing['cik'], []).append({
                    'accn': row['ACCESSION_NUMBER'],
                    'filed': filing['filed'],
                    'owner': int(insider['RPTOWNERCIK']),
                    'name': insider['RPTOWNERNAME'],
                    'title': insider['RPTOWNER_TITLE'] or ('Director' if 'Director' in insider['RPTOWNER_RELATIONSHIP'] else 'Officer'),
                    'kind': kind,
                    'date': date,
                    'shares': shares,
                    'price': price if price and price > 0 else None
                })
    return transactions


def load_insider(raw_dir, ciks, log=print):
    """
    Read the insiders' transactions in every quarterly data set in the raw directory's "insider" directory, or
    load the cached read of the same files and companies

    :param str raw_dir: The raw data directory
    :param list(int) ciks: The companies (issuers) to read
    :param log: The log function
    :returns: The tuple of the dict of company CIK (as a string) to its list of transactions, and the sorted list
        of the data set file names. With no data sets, the dict is empty.
    """

    insider_dir = os.path.join(raw_dir, 'insider')
    names = sorted(name for name in os.listdir(insider_dir) if name.endswith('_form345.zip')) if os.path.isdir(insider_dir) else []
    if not names:
        return {}, []
    stamp = [INSIDER_VERSION, sorted(ciks), [[name, os.path.getsize(os.path.join(insider_dir, name))] for name in names]]
    cache_path = os.path.join(raw_dir, 'insider-cache.json')
    if os.path.exists(cache_path):
        with open(cache_path, 'r', encoding='utf-8') as cache_file:
            cache = json.load(cache_file)
        if cache['stamp'] == stamp:
            log('Using the cached read of the insider-transaction data sets')
            return cache['transactions'], names

    transactions = {}
    cik_set = set(ciks)
    for name in names:
        log(f'Reading {name} ...')
        for cik, cik_transactions in read_insider_zip(os.path.join(insider_dir, name), cik_set).items():
            transactions.setdefault(str(cik), []).extend(cik_transactions)
    with open(cache_path, 'w', encoding='utf-8') as cache_file:
        json.dump({'stamp': stamp, 'transactions': transactions}, cache_file)
    return transactions, names


#
# Summarizing a company's insiders
#


# The dollar amounts summed by year, by insider and by filing, and the transaction kind behind each
_AMOUNTS = {
    'sale': 'sales', 'purchase': 'purchases', 'withheld': 'withheld', 'issuer': 'toIssuer', 'grant': 'grants', 'option': 'optionGrants'
}


def price_series(transactions):
    """
    Build a company's share price series from the prices its insiders reported: the median reported price of the
    open-market sales, open-market purchases and tax withholdings on each day

    :param list(dict) transactions: The company's transactions
    :returns: The tuple of the sorted list of day ordinals and the list of each day's price
    """

    by_day = {}
    for transaction in transactions:
        if transaction['kind'] in ('sale', 'purchase', 'withheld') and transaction['price']:
            by_day.setdefault(datetime.date.fromisoformat(transaction['date']).toordinal(), []).append(transaction['price'])
    days = sorted(by_day)
    return days, [statistics.median(by_day[day]) for day in days]


def nearest_price(series, day, max_days):
    """
    Get the price on the day of the series nearest to a day

    :param tuple series: The price series
    :param int day: The day ordinal
    :param int max_days: The most days away the nearest day may be
    :returns: The price, or None if there is no price near enough
    """

    days, prices = series
    index = bisect.bisect_left(days, day)
    nearest = min((near for near in (index - 1, index) if 0 <= near < len(days)), key=lambda near: abs(days[near] - day), default=None)
    if nearest is None or abs(days[nearest] - day) > max_days:
        return None
    return prices[nearest]


def is_odd_price(series, day, price, window_days=30):
    """
    Test whether a reported price is far from the company's other reported prices around the day - more than three
    times, or less than a third of, the median of at least three days' prices. Such a price is nearly always an
    error in the filing, for example a total entered as a price.

    :param tuple series: The price series
    :param int day: The day ordinal
    :param float price: The reported price
    :param int window_days: The days either side to compare with
    :rtype: bool
    """

    days, prices = series
    window = prices[bisect.bisect_left(days, day - window_days):bisect.bisect_right(days, day + window_days)]
    if len(window) < 3:
        return False
    median = statistics.median(window)
    return price > 3 * median or price < median / 3


def buyback_quarters(periods):
    """
    Split a company's buybacks into quarters. Cash flow statements give year-to-date amounts, so a quarter is the
    year-to-date amount less the one before it. A fiscal year is used only as far as its periods step by a quarter.

    :param dict periods: The company record's buybacks: the dict of "start|end" to fact
    :returns: The list of quarters, oldest first: dicts of "start", "end", "buybacks" and "accn"
    """

    by_start = {}
    for key, fact in periods.items():
        start, end = key.split('|')
        by_start.setdefault(start, []).append((end, fact))

    # The longest chains first, so a year-to-date chain is used before a lone quarter's amount
    quarters = {}
    for start, facts in sorted(by_start.items(), key=lambda item: (-len(item[1]), item[0])):
        quarter_start = start
        previous = 0
        for end, fact in sorted(facts):
            if not 75 <= (parse_date(end) - parse_date(quarter_start)).days <= 105:
                break
            amount = abs(fact[F_VAL]) - previous
            if amount < 0:
                break
            quarters.setdefault(end, {'start': quarter_start, 'end': end, 'buybacks': amount, 'accn': fact[F_ACCN]})
            previous = abs(fact[F_VAL])
            quarter_start = (parse_date(end) + datetime.timedelta(days=1)).isoformat()
    return [quarters[end] for end in sorted(quarters)]


def insider_summary(transactions, last_year, thresholds, quarters=()):
    """
    Summarize a company's insiders' grants and sales over the latest calendar years

    Sales, purchases and tax withholdings are valued at the price reported for each. A grant is valued at the
    market value of the shares it covers: for a stock award, the company's nearest reported price; for an option,
    its exercise price. An option is worth less than the shares it covers, so this overstates option grants, and
    "salesToGrants" is the least the insiders' sales can be as a multiple of their grants. "salesToStockGrants"
    counts options as worth nothing and is the most it can be.

    :param list(dict) transactions: The company's transactions
    :param int last_year: The last calendar year
    :param dict thresholds: The thresholds
    :param list(dict) quarters: The company's buybacks by quarter. The quarters wholly inside the calendar years are
        returned with the insiders' open-market sales in each.
    :returns: The summary dict, or None if no insider reported a transaction in those years
    """

    first_year = last_year - thresholds['p3_years'] + 1
    quarters = [
        {**quarter, 'sales': 0} for quarter in quarters
        if quarter['start'] >= f'{first_year}-01-01' and quarter['end'] <= f'{last_year}-12-31'
    ]
    quarter_starts = [quarter['start'] for quarter in quarters]
    years = {year: {'year': year, 'grantShares': 0, 'giftShares': 0, **dict.fromkeys(_AMOUNTS.values(), 0)}
             for year in range(first_year, last_year + 1)}
    series = price_series(transactions)
    people = {}
    unvalued_shares = 0
    odd_prices = 0
    for transaction in sorted(transactions, key=lambda transaction: (transaction['filed'] or '', transaction['accn'])):
        year = years.get(int(transaction['date'][:4]))
        if year is None:
            continue
        kind = transaction['kind']
        shares = transaction['shares']
        price = transaction['price']
        day = datetime.date.fromisoformat(transaction['date']).toordinal()
        person = people.setdefault(transaction['owner'], {
            'cik': transaction['owner'], 'name': transaction['name'], 'title': transaction['title'], 'filings': {},
            **dict.fromkeys(_AMOUNTS.values(), 0)
        })
        person['title'] = transaction['title']  # the title on the insider's latest filing

        # Value the transaction
        if kind == 'gift':
            year['giftShares'] += shares
            continue
        if kind in ('grant', 'option'):
            year['grantShares'] += shares
            if kind == 'grant' or price is None:
                price = nearest_price(series, day, thresholds['p3_price_days'])
            if price is None:
                unvalued_shares += shares
                continue
        elif price is None:
            # Shares returned to the company for nothing are a forfeit, not a sale
            continue
        elif kind != 'issuer' and is_odd_price(series, day, price):
            odd_prices += 1
            continue

        # Add it to the year, the insider and the filing
        amount = _AMOUNTS[kind]
        value = shares * price
        year[amount] += value
        person[amount] += value
        filing = person['filings'].setdefault(transaction['accn'], {
            'accn': transaction['accn'], 'filed': transaction['filed'], **dict.fromkeys(_AMOUNTS.values(), 0)
        })
        filing[amount] += value

        # Add a sale to the quarter it fell in
        quarter = quarters[bisect.bisect_right(quarter_starts, transaction['date']) - 1] if quarters else None
        if kind == 'sale' and quarter and quarter['start'] <= transaction['date'] <= quarter['end']:
            quarter['sales'] += value

    if not people:
        return None

    # The totals, and the ratio of sales to grants
    summary = {amount: sum(year[amount] for year in years.values()) for amount in ('grantShares', 'giftShares', *_AMOUNTS.values())}
    grants = summary['grants'] + summary['optionGrants']
    ratio = None
    ratio_reason = None
    if summary['grantShares'] and unvalued_shares > thresholds['p3_unvalued_max'] * summary['grantShares']:
        ratio_reason = 'too many granted shares have no reported share price near the grant date'
    elif grants > 0:
        ratio = summary['sales'] / grants
    else:
        ratio_reason = 'no grants'

    # The largest sellers, with their filings
    sellers = sorted((person for person in people.values() if person['sales'] > 0), key=lambda person: (-person['sales'], person['name']))
    for person in sellers[:5]:
        person['filings'] = sorted(person['filings'].values(), key=lambda filing: (filing['filed'], filing['accn']))
    return {
        **summary,
        'years': list(years.values()),
        'bothYears': sum(1 for year in years.values() if year['grantShares'] > 0 and year['sales'] > 0),
        'salesToGrants': ratio,
        'salesToStockGrants': summary['sales'] / summary['grants'] if ratio is not None and summary['grants'] > 0 else None,
        'ratioReason': ratio_reason,
        'unvaluedShares': unvalued_shares,
        'oddPrices': odd_prices,
        'insiders': len(people),
        'sellers': len(sellers),
        'people': sellers[:5],
        'quarters': quarters,
        'buybacks': sum(quarter['buybacks'] for quarter in quarters),
        'buybackQuarters': sum(1 for quarter in quarters if quarter['buybacks'] > 0),
        'salesInQuarters': sum(quarter['sales'] for quarter in quarters),
        'salesInBuybackQuarters': sum(quarter['sales'] for quarter in quarters if quarter['buybacks'] > 0)
    }
