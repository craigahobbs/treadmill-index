# Licensed under the MIT License
# https://github.com/craigahobbs/treadmill-index/blob/main/LICENSE

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

from .extract import F_VAL, parse_date
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


def insider_quarters(today, years):
    """
    Get the quarters to download: from the first quarter of the calendar year some years back, through the last
    quarter that has ended

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


def download_insider(raw_dir, user_agent, today, years, pause=0.5, log=print):
    """
    Download the insider-transaction data sets of the latest calendar years to the raw directory's "insider"
    directory. Files that are already there are not downloaded again.

    :param str raw_dir: The raw data directory
    :param str user_agent: The User-Agent header for SEC requests. The SEC refuses these files without one that
        names the requester and gives a contact address. It is needed only if a file is downloaded.
    :param datetime.date today: Today's date
    :param int years: The number of calendar years back to start from
    :param float pause: The seconds to pause between SEC requests
    :param log: The log function
    :returns: The number of data sets that are still missing
    """

    insider_dir = os.path.join(raw_dir, 'insider')
    os.makedirs(insider_dir, exist_ok=True)
    quarters = [
        quarter for quarter in insider_quarters(today, years)
        if not os.path.exists(os.path.join(insider_dir, f'{quarter}_form345.zip'))
    ]
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
INSIDER_VERSION = 6

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
    r'trust|spouse|wife|husband|family|child|\bsons?\b|daughter|minor|custodian|grantor|grat\b|descendant|estate|joint|\bira\b|401',
    re.IGNORECASE
)

# A nature of ownership that names a company or partnership, such as "By Zelnick Media Corporation": the form its
# name ends with, and at least one word that is a name. Two insiders who share such an entity each report its
# transactions. "By Trust" and "See footnote" name nothing: two co-founders with equal holdings report equal, separate
# sales in those words.
_RE_COMPANY = re.compile(
    r'\b(l\.?l?\.?l?\.?p\.?|l\.?l\.?c\.?|inc\.?|incorporated|corp\.?|corporation|ltd\.?|limited|company|co\.|holdings|partners|'
    r'partnership|advisors|advisers|associates|investments?|ventures|capital|management|group)(?![\w])',
    re.IGNORECASE
)
_GENERIC_WORDS = frozenset((
    'a', 'an', 'and', 'by', 'family', 'footnote', 'footnotes', 'for', 'held', 'her', 'his', 'in', 'indirect', 'indirectly', 'of',
    'owned', 'see', 'spouse', 'the', 'their', 'through', 'trust'
))


def shared_holding(nature):
    """
    Get the name of the company or partnership that a nature of ownership names

    :param str nature: The nature of ownership
    :returns: The name, in lower case, or None if the nature of ownership does not name a company or partnership
    """

    name = nature.strip().lower()
    words = [word for word in re.findall(r"[a-z0-9&']+", _RE_COMPANY.sub(' ', name)) if word not in _GENERIC_WORDS]
    return name if _RE_COMPANY.search(name) and words else None


# Derivative securities with these words in their title are options: their value is less than the shares they cover
_RE_OPTION = re.compile(r'option|right to buy|appreciation', re.IGNORECASE)

# The transaction kinds, by table, transaction code and acquired/disposed code
_KINDS = {
    ('NONDERIV_TRANS.tsv', 'S', 'D'): 'sale',
    ('NONDERIV_TRANS.tsv', 'P', 'A'): 'purchase',
    ('NONDERIV_TRANS.tsv', 'A', 'A'): 'grant',
    ('NONDERIV_TRANS.tsv', 'F', 'D'): 'withheld',
    ('NONDERIV_TRANS.tsv', 'D', 'D'): 'issuer',
    ('DERIV_TRANS.tsv', 'A', 'A'): 'grant',
    ('DERIV_TRANS.tsv', 'M', 'D'): 'exercise',
    ('DERIV_TRANS.tsv', 'X', 'D'): 'exercise'
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
        "owner" (the insider's CIK), "name", "title", "kind" ("sale", "purchase", "grant", "option", "exercise",
        "withheld" or "issuer"), "date", "shares", "price" (as reported; for an option, its exercise price) and
        "holding" - for shares held through a named company or partnership, its name and the shares it held
        afterward; None for other shares.
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
                holding = shared_holding(row['NATURE_OF_OWNERSHIP']) if row['DIRECT_INDIRECT_OWNERSHIP'] == 'I' else None
                if table == 'DERIV_TRANS.tsv':
                    # A derivative covers its underlying shares; an option's price is its exercise price. Only an
                    # option costs anything to exercise: share units convert for nothing.
                    is_option = _RE_OPTION.search(row['SECURITY_TITLE'])
                    if kind == 'exercise' and not is_option:
                        continue
                    shares = parse_number(row['UNDLYNG_SEC_SHARES']) or shares
                    price = parse_number(row['CONV_EXERCISE_PRICE']) if is_option else None
                    if kind == 'grant' and is_option:
                        kind = 'option'
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
                    'price': price if price and price > 0 else None,
                    'holding': holding and [holding, parse_number(row['SHRS_OWND_FOLWNG_TRANS'])]
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
    stats = [os.stat(os.path.join(insider_dir, name)) for name in names]
    stamp = [INSIDER_VERSION, sorted(ciks), [[name, stat.st_size, int(stat.st_mtime)] for name, stat in zip(names, stats)]]
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


def missing_quarters(names, first_year, last_year):
    """
    Get the quarters of some calendar years that have no data set. Without one, a year's figures would be short.

    :param list(str) names: The data set file names
    :param int first_year: The first calendar year
    :param int last_year: The last calendar year
    :returns: The list of quarters, for example "2025q4", oldest first
    """

    quarters = [f'{year}q{quarter}' for year in range(first_year, last_year + 1) for quarter in range(1, 5)]
    return [quarter for quarter in quarters if f'{quarter}_form345.zip' not in names]


#
# Summarizing a company's insiders
#


# The dollar amount each transaction kind adds to, by year, by insider and by filing
_KIND_AMOUNTS = {
    'sale': 'sales', 'purchase': 'purchases', 'exercise': 'exercised', 'withheld': 'withheld', 'issuer': 'toIssuer', 'grant': 'grants',
    'option': 'optionGrants'
}

# The dollar amounts
AMOUNTS = tuple(_KIND_AMOUNTS.values())

# The days either side of a transaction within which its price is compared with the company's other reported prices,
# and how many times the median of those prices, or what part of it, a price can be before it is taken as an error
PRICE_DAYS = 30
PRICE_FACTOR = 25


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
            by_day.setdefault(parse_date(transaction['date']).toordinal(), []).append(transaction['price'])
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


def is_odd_price(series, day, price):
    """
    Test whether a reported price is far from the company's other reported prices - nearly always an error in the
    filing, such as a total entered as a price.

    The price is compared with the median of the prices reported within PRICE_DAYS of it or, with fewer than three
    such days, of all the company's reported prices. It is odd if it is more than PRICE_FACTOR times the median, or
    less than the median over PRICE_FACTOR. The band is wide so that trades on either side of a stock split are
    kept: the prices are as reported, not adjusted for splits.

    :param tuple series: The price series
    :param int day: The day ordinal
    :param float price: The reported price
    :rtype: bool
    """

    days, prices = series
    window = prices[bisect.bisect_left(days, day - PRICE_DAYS):bisect.bisect_right(days, day + PRICE_DAYS)]
    if len(window) < 3:
        window = prices
    if len(window) < 3:
        return False
    median = statistics.median(window)
    return price > PRICE_FACTOR * median or price < median / PRICE_FACTOR


def buyback_quarters(periods):
    """
    Split a company's buybacks into quarters. Cash flow statements give year-to-date amounts, so a quarter is the
    year-to-date amount less the one before it. A fiscal year is used only as far as its periods step by a quarter.

    :param dict periods: The company record's buybacks: the dict of "start|end" to fact
    :returns: The list of quarters, oldest first: dicts of "start", "end" and "buybacks"
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
            # A quarter reported again with dates a day or two off is the same quarter
            if not any(quarter['start'] <= end and quarter_start <= quarter['end'] for quarter in quarters.values()):
                quarters[end] = {'start': quarter_start, 'end': end, 'buybacks': amount}
            previous = abs(fact[F_VAL])
            quarter_start = (parse_date(end) + datetime.timedelta(days=1)).isoformat()
    return [quarters[end] for end in sorted(quarters)]


def insider_summary(transactions, first_year, last_year, thresholds, quarters=()):
    """
    Summarize what a company's insiders took out through stock, and were granted, over some calendar years

    Sales, purchases and withholdings are valued at the price reported for each. "cashOut" is the net cash the
    insiders took out through stock: open-market sales, shares withheld and shares sold to the company, less
    open-market purchases and what they paid to exercise options ("exercised": the shares at the exercise price).
    Shares withheld count because some companies have insiders sell on the market to cover the same taxes; counting
    both makes companies comparable. Shares withheld to pay an option's exercise price are offset by that price.

    Grants are not scored. For display, a grant is valued at the market value of the shares it covers: a stock
    award at the company's nearest reported price, an option at its exercise price. An option is worth less than
    the shares it covers, so this overstates option grants. A grant with no reported price near it is left out.

    A reported price far from the company's other reported prices is taken to be a filing error, and the transaction
    is left out. So is an exercise price above the share price: nobody pays more than the market to exercise. A
    transaction of a named company or partnership that two insiders both report is counted once.

    :param list(dict) transactions: The company's transactions
    :param int first_year: The first calendar year
    :param int last_year: The last calendar year
    :param dict thresholds: The thresholds
    :param list(dict) quarters: The company's buybacks by quarter. The insiders' open-market sales are totalled over
        the quarters wholly inside the calendar years, and over those of them that had a buyback.
    :returns: The summary dict, or None if no insider reported a transaction in those years
    """

    quarters = [
        {**quarter, 'sales': 0} for quarter in quarters
        if quarter['start'] >= f'{first_year}-01-01' and quarter['end'] <= f'{last_year}-12-31'
    ]
    quarter_starts = [quarter['start'] for quarter in quarters]
    years = {year: {'year': year, **dict.fromkeys(AMOUNTS, 0)} for year in range(first_year, last_year + 1)}
    series = price_series(transactions)
    people = {}
    holdings = {}
    for transaction in sorted(transactions, key=lambda transaction: (transaction['filed'] or '', transaction['accn'])):
        year = years.get(int(transaction['date'][:4]))
        if year is None:
            continue

        # Two insiders who share a company or partnership each report its transactions. Count each once: for the
        # insider who filed first.
        holding = transaction['holding']
        if holding is not None and holding[1] is not None:
            key = (transaction['kind'], transaction['date'], transaction['shares'], transaction['price'], *holding)
            if holdings.setdefault(key, transaction['owner']) != transaction['owner']:
                continue
        kind = transaction['kind']
        shares = transaction['shares']
        price = transaction['price']
        day = parse_date(transaction['date']).toordinal()
        person = people.setdefault(transaction['owner'], {
            'cik': transaction['owner'], 'name': transaction['name'], 'title': transaction['title'], 'filings': {},
            **dict.fromkeys(AMOUNTS, 0)
        })
        person['title'] = transaction['title']  # the title on the insider's latest filing

        # Value the transaction
        if kind in ('grant', 'option'):
            if kind == 'grant' or price is None:
                price = nearest_price(series, day, thresholds['grant_price_days'])
        elif kind == 'exercise':
            market = nearest_price(series, day, thresholds['grant_price_days'])
            if price is not None and market is not None and price > market:
                price = None
        elif price is not None and is_odd_price(series, day, price):
            price = None
        if price is None:
            # No price to value it at. Shares returned to the company for nothing are a forfeit, not a sale.
            continue

        # Add it to the year, the insider and the filing
        amount = _KIND_AMOUNTS[kind]
        value = shares * price
        year[amount] += value
        person[amount] += value
        filing = person['filings'].setdefault(transaction['accn'], {
            'accn': transaction['accn'], 'filed': transaction['filed'], **dict.fromkeys(AMOUNTS, 0)
        })
        filing[amount] += value

        # Add a sale to the quarter it fell in
        quarter = quarters[bisect.bisect_right(quarter_starts, transaction['date']) - 1] if quarters else None
        if kind == 'sale' and quarter and quarter['start'] <= transaction['date'] <= quarter['end']:
            quarter['sales'] += value

    if not people:
        return None

    # The totals, and what each year, insider and filing took out
    def cash_out(item):
        return item['sales'] + item['withheld'] + item['toIssuer'] - item['purchases'] - item['exercised']

    summary = {amount: sum(year[amount] for year in years.values()) for amount in AMOUNTS}
    filings = [filing for person in people.values() for filing in person['filings'].values()]
    for item in (summary, *years.values(), *people.values(), *filings):
        item['cashOut'] = cash_out(item)

    # The insiders who took out the most, with their filings
    sellers = sorted(
        (person for person in people.values() if person['cashOut'] > 0), key=lambda person: (-person['cashOut'], person['name'])
    )
    for person in sellers[:5]:
        person['filings'] = sorted(person['filings'].values(), key=lambda filing: (filing['filed'] or '', filing['accn']))
    return {
        **summary,
        'years': list(years.values()),
        'insiders': len(people),
        'sellers': len(sellers),
        'people': sellers[:5],
        'quarters': len(quarters),
        'buybacks': sum(quarter['buybacks'] for quarter in quarters),
        'buybackQuarters': sum(1 for quarter in quarters if quarter['buybacks'] > 0),
        'salesInQuarters': sum(quarter['sales'] for quarter in quarters),
        'salesInBuybackQuarters': sum(quarter['sales'] for quarter in quarters if quarter['buybacks'] > 0)
    }
