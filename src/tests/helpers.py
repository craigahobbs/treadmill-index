# Licensed under the MIT License
# https://github.com/craigahobbs/treadmill-index/blob/main/LICENSE

# pylint: disable=missing-function-docstring, missing-module-docstring

import json
import os
import zipfile

from treadmill_index.extract import extract_company
from treadmill_index.insider import AMOUNTS


# The test data date and the baseline company's revenue, in millions, for fiscal 2019 to 2025
DATA_DATE = '2026-11-20'
REVENUE = (1000, 1100, 1250, 1400, 1600, 1800, 2000)


def unit(start, end, val, accn='0000000001-26-000001', filed='2026-02-15', form='10-K'):
    return {'start': start, 'end': end, 'val': val, 'accn': accn, 'filed': filed, 'form': form}


def annual(year, millions):
    return unit(f'{year}-01-01', f'{year}-12-31', millions * 1e6, accn=f'0000000001-{year + 1 - 2000}-000010', filed=f'{year + 1}-02-15')


def nine_months(year, millions):
    return unit(
        f'{year}-01-01', f'{year}-09-30', millions * 1e6, accn=f'0000000001-{year - 2000}-000030', filed=f'{year}-11-05', form='10-Q'
    )


def series(values, revenue):
    # A sequence is millions for each year; a number is a share of revenue
    return list(values) if isinstance(values, (list, tuple)) else [values * revenue_year for revenue_year in revenue]


def company_doc(cik=1, name='Test Co', revenue=REVENUE, ocf=0.12, capex=0.02, sbc=0.12, gross=0.6, operating=0.05, quarters=True,
                last_year=2025, tags=None):
    """
    Build a companyfacts document. By default: a company whose 10% free cash flow margin is more than used up by
    stock pay of 12% of revenue, with flat operating costs, and a 10-Q for the nine months after its latest year.
    """

    figures = {
        'RevenueFromContractWithCustomerExcludingAssessedTax': series(1, revenue),
        'NetCashProvidedByUsedInOperatingActivities': series(ocf, revenue),
        'PaymentsToAcquirePropertyPlantAndEquipment': series(capex, revenue),
        'ShareBasedCompensation': series(sbc, revenue),
        'GrossProfit': series(gross, revenue),
        'OperatingIncomeLoss': series(operating, revenue)
    }
    first_year = last_year - len(revenue) + 1
    gaap = {}
    for tag, values in figures.items():
        units = [annual(first_year + index, value) for index, value in enumerate(values)]
        if quarters and tag not in ('GrossProfit', 'OperatingIncomeLoss'):
            units.append(nine_months(last_year, 0.75 * values[-1]))
            units.append(nine_months(last_year + 1, 0.825 * values[-1]))
        gaap[tag] = {'units': {'USD': units}}
    for tag, units in (tags or {}).items():
        if units is None:
            del gaap[tag]
        else:
            gaap[tag] = {'units': {'USD': units}}
    return {'cik': cik, 'entityName': name, 'facts': {'us-gaap': gaap}}


def company_bytes(**kwargs):
    return json.dumps(company_doc(**kwargs)).encode('utf-8')


def company_record(**kwargs):
    return extract_company(company_bytes(**kwargs))


#
# Insider-transaction data sets
#


INSIDER_TABLES = {
    'SUBMISSION.tsv': ('ACCESSION_NUMBER', 'FILING_DATE', 'DOCUMENT_TYPE', 'ISSUERCIK'),
    'REPORTINGOWNER.tsv': ('ACCESSION_NUMBER', 'RPTOWNERCIK', 'RPTOWNERNAME', 'RPTOWNER_RELATIONSHIP', 'RPTOWNER_TITLE'),
    'NONDERIV_TRANS.tsv': (
        'ACCESSION_NUMBER', 'TRANS_DATE', 'TRANS_CODE', 'TRANS_ACQUIRED_DISP_CD', 'TRANS_SHARES', 'TRANS_PRICEPERSHARE',
        'DIRECT_INDIRECT_OWNERSHIP', 'NATURE_OF_OWNERSHIP', 'SHRS_OWND_FOLWNG_TRANS'
    ),
    'DERIV_TRANS.tsv': (
        'ACCESSION_NUMBER', 'TRANS_DATE', 'TRANS_CODE', 'TRANS_ACQUIRED_DISP_CD', 'TRANS_SHARES', 'TRANS_PRICEPERSHARE',
        'DIRECT_INDIRECT_OWNERSHIP', 'NATURE_OF_OWNERSHIP', 'SECURITY_TITLE', 'CONV_EXERCISE_PRICE', 'UNDLYNG_SEC_SHARES',
        'SHRS_OWND_FOLWNG_TRANS'
    )
}

CEO = ('0000001001', 'Doe Jane', 'Director,Officer', 'Chief Executive Officer')


def insider_fixture(sales, year=2025, **amounts):
    """
    Build an insider summary for the calendar years 2021 to 2025, with one year's amounts: its sales and any others
    """

    none = dict.fromkeys(('cashOut', *AMOUNTS), 0)
    totals = {**none, 'sales': sales, **amounts}
    totals['cashOut'] = totals['sales'] + totals['withheld'] + totals['toIssuer'] - totals['purchases'] - totals['exercised']
    return {
        **totals,
        'years': [{'year': other, **(totals if other == year else none)} for other in range(2021, 2026)],
        'insiders': 3, 'sellers': 2, 'people': [],
        'quarters': 2, 'buybackQuarters': 1, 'buybacks': 30000000, 'salesInQuarters': 90000000, 'salesInBuybackQuarters': 60000000
    }


def insider_filing(accn, cik=1, filed='18-MAR-2024', form='4', owners=(CEO,), nonderiv=(), deriv=()):
    """
    Build a filing for insider_zip. A "nonderiv" row is (date, code, acquired/disposed, shares, price, direct/indirect,
    nature, shares owned afterward); a "deriv" row is (date, code, acquired/disposed, shares, price, direct/indirect,
    nature, title, exercise price, underlying shares, shares owned afterward). Trailing values may be left off.
    """

    return {
        'SUBMISSION.tsv': [(accn, filed, form, f'{cik:010d}' if isinstance(cik, int) else cik)],
        'REPORTINGOWNER.tsv': [(accn, *owner) for owner in owners],
        'NONDERIV_TRANS.tsv': [(accn, *row) for row in nonderiv],
        'DERIV_TRANS.tsv': [(accn, *row) for row in deriv]
    }


def insider_zip(zip_path, filings):
    with zipfile.ZipFile(zip_path, 'w') as archive:
        for table, columns in INSIDER_TABLES.items():
            lines = ['\t'.join(columns)]
            for filing in filings:
                for row in filing[table]:
                    lines.append('\t'.join(str(value) for value in (*row, *([''] * (len(columns) - len(row))))))
            archive.writestr(table, '\n'.join(lines) + '\n')


def insider_zips(insider_dir, filings, first_year=2021, last_year=2025):
    """
    Write a data set for every quarter of some calendar years: the filings in the last, and none in the rest
    """

    names = [f'{year}q{quarter}_form345.zip' for year in range(first_year, last_year + 1) for quarter in range(1, 5)]
    for name in names:
        insider_zip(os.path.join(insider_dir, name), filings if name == names[-1] else [])
    return names
