"""
Extract the figures the index needs from the SEC "companyfacts" bulk file
"""

from concurrent.futures import ProcessPoolExecutor
import datetime
import json
import os
import zipfile


# The extract cache version - bump when the extracted record changes
EXTRACT_VERSION = 1

# Companies that never reported this much annual revenue are dropped at extraction. This is a speed filter that
# sits below the definition's $1B revenue test (and below that test moved down by a fifth).
PREFILTER_REVENUE = 5e8


# The XBRL tags behind each figure. For every figure but revenue the first tag that has the year wins.
# For revenue the largest value across the tags is used (companies changed revenue tags in 2018).
CONCEPTS = {
    'rev': [
        'Revenues',
        'RevenueFromContractWithCustomerExcludingAssessedTax',
        'RevenueFromContractWithCustomerIncludingAssessedTax',
        'SalesRevenueNet'
    ],
    'ocf': ['NetCashProvidedByUsedInOperatingActivities', 'NetCashProvidedByUsedInOperatingActivitiesContinuingOperations'],
    'ppe': ['PaymentsToAcquirePropertyPlantAndEquipment'],
    'prod': ['PaymentsToAcquireProductiveAssets'],
    'sw': ['PaymentsToDevelopSoftware'],
    'sbc': ['ShareBasedCompensation'],
    'sbc2': ['AllocatedShareBasedCompensationExpense'],
    'opex': ['OperatingExpenses'],
    'gp': ['GrossProfit'],
    'opinc': ['OperatingIncomeLoss'],
    'cae': ['CostsAndExpenses'],
    'cor': ['CostOfRevenue'],
    'cogs': ['CostOfGoodsAndServicesSold'],
    'bb': ['PaymentsForRepurchaseOfCommonStock'],
    'div': ['PaymentsOfDividends', 'PaymentsOfDividendsCommonStock'],
    'wh': ['PaymentsRelatedToTaxWithholdingForShareBasedCompensation'],
    'ni': ['NetIncomeLoss'],
    'sh': ['WeightedAverageNumberOfDilutedSharesOutstanding'],
    'inv': ['IncreaseDecreaseInInventories'],
    'disc': ['CashProvidedByUsedInOperatingActivitiesDiscontinuedOperations'],
    'loan_out': ['PaymentsForOriginationOfMortgageLoansHeldForSale', 'PaymentsForOriginationAndPurchasesOfLoansHeldForSale'],
    'loan_in': ['ProceedsFromSaleOfMortgageLoansHeldForSale', 'ProceedsFromSaleAndCollectionOfLoansHeldForsale'],
    'loan_chg': ['IncreaseDecreaseInLoansHeldForSale', 'IncreaseDecreaseInFinanceReceivables']
}

# The figures needed for the latest-12-month owner-cash margin
TTM_CONCEPTS = ('rev', 'ocf', 'ppe', 'prod', 'sw', 'sbc', 'sbc2')

# Fact array indexes: [value, accession number, date filed, form, period start, XBRL tag]
F_VAL, F_ACCN, F_FILED, F_FORM, F_START, F_TAG = range(6)


def parse_date(text):
    """
    Parse an ISO date

    :param str text: The ISO date
    :rtype: datetime.date
    """

    return datetime.date(int(text[:4]), int(text[5:7]), int(text[8:10]))


def period_facts(units, min_days, max_days):
    """
    Get the most recently filed fact for each period whose length is within a range of days

    :param list(dict) units: The XBRL facts for one tag and unit
    :param int min_days: The minimum period length, in days
    :param int max_days: The maximum period length, in days
    :returns: A dict of "start|end" to the fact, [value, accession number, date filed, form, period start]
    """

    best = {}
    for unit in units:
        start = unit.get('start')
        if start is None:
            continue
        end = unit['end']
        days = (parse_date(end) - parse_date(start)).days
        if days < min_days or days > max_days:
            continue
        key = start + '|' + end
        filed = unit.get('filed', '')
        if key not in best or filed > best[key][F_FILED]:
            best[key] = [unit['val'], unit.get('accn'), filed, unit.get('form'), start]
    return best


def annual_facts(units):
    """
    Get the most recently filed annual (350 to 380 day) fact for each period end date

    :param list(dict) units: The XBRL facts for one tag and unit
    :returns: A dict of period end date to the fact
    """

    best = {}
    for key, fact in period_facts(units, 350, 380).items():
        end = key.split('|')[1]
        if end not in best or fact[F_FILED] > best[end][F_FILED]:
            best[end] = fact
    return best


def extract_company(raw):
    """
    Extract a company's facts from its companyfacts JSON

    :param bytes raw: The company's JSON file content
    :returns: The company record, or None for a company that never reported PREFILTER_REVENUE of annual
        revenue or that has no stock-pay tags
    """

    # Fast reject before parsing
    if b'ShareBasedCompensation' not in raw:
        return None
    if b'"Revenues"' not in raw and b'RevenueFromContract' not in raw and b'SalesRevenueNet' not in raw:
        return None
    try:
        doc = json.loads(raw)
    except ValueError:
        return None
    gaap = doc.get('facts', {}).get('us-gaap', {})

    # The annual facts
    annual = {}
    for concept, tags in CONCEPTS.items():
        merged = {}
        for tag in tags:
            for unit, facts in gaap.get(tag, {}).get('units', {}).items():
                if unit not in ('USD', 'shares'):
                    continue
                for end, fact in annual_facts(facts).items():
                    if end not in merged or (concept == 'rev' and fact[F_VAL] > merged[end][F_VAL]):
                        merged[end] = fact + [tag]
        annual[concept] = merged
    revenue = annual['rev']
    if not revenue or max(fact[F_VAL] for fact in revenue.values()) < PREFILTER_REVENUE:
        return None

    # The recent part-year facts, by tag, for the latest-12-month figures
    cutoff = (parse_date(max(revenue)) - datetime.timedelta(days=800)).isoformat()
    recent = {}
    filed_max = max(fact[F_FILED] for fact in revenue.values())
    for concept in TTM_CONCEPTS:
        concept_recent = {}
        for tag in CONCEPTS[concept]:
            facts = gaap.get(tag, {}).get('units', {}).get('USD', [])
            tag_recent = {key: fact for key, fact in period_facts(facts, 60, 349).items() if key.split('|')[1] > cutoff}
            if tag_recent:
                concept_recent[tag] = tag_recent
                filed_max = max(filed_max, max(fact[F_FILED] for fact in tag_recent.values()))
        recent[concept] = concept_recent

    return {'cik': int(doc['cik']), 'name': doc.get('entityName'), 'annual': annual, 'recent': recent, 'filed_max': filed_max}


def extract_members(zip_path, names):
    """
    Extract the companies in some members of the companyfacts zip

    :param str zip_path: The companyfacts zip file path
    :param list(str) names: The zip member names
    :returns: The list of company records
    """

    records = []
    with zipfile.ZipFile(zip_path) as archive:
        for name in names:
            record = extract_company(archive.read(name))
            if record is not None:
                records.append(record)
    return records


def extract_all(zip_path, processes):
    """
    Extract every company in the companyfacts zip

    :param str zip_path: The companyfacts zip file path
    :param int processes: The number of worker processes
    :returns: The tuple of the company records, sorted by CIK, and the count of companies in the file
    """

    with zipfile.ZipFile(zip_path) as archive:
        names = sorted(name for name in archive.namelist() if name.endswith('.json'))
    chunks = [names[index:index + 64] for index in range(0, len(names), 64)]
    records = []
    with ProcessPoolExecutor(processes) as executor:
        for chunk_records in executor.map(extract_members, [zip_path] * len(chunks), chunks):
            records.extend(chunk_records)
    records.sort(key=lambda record: record['cik'])
    return records, len(names)


def load_records(zip_path, cache_path, processes, log=print):
    """
    Extract the companyfacts zip, or load the cached extract of the same file

    :param str zip_path: The companyfacts zip file path
    :param str cache_path: The extract cache file path
    :param int processes: The number of worker processes
    :param log: The log function
    :returns: The tuple of the company records, sorted by CIK, and the count of companies in the file
    """

    stat = os.stat(zip_path)
    stamp = f'{stat.st_size}-{int(stat.st_mtime)}-{EXTRACT_VERSION}'
    if os.path.exists(cache_path):
        with open(cache_path, 'r', encoding='utf-8') as cache_file:
            cache = json.load(cache_file)
        if cache['stamp'] == stamp:
            log(f'Using the cached extract of {zip_path}')
            return cache['records'], cache['inFile']
    log(f'Extracting {zip_path} ...')
    records, in_file = extract_all(zip_path, processes)
    with open(cache_path, 'w', encoding='utf-8') as cache_file:
        json.dump({'stamp': stamp, 'records': records, 'inFile': in_file}, cache_file)
    return records, in_file
