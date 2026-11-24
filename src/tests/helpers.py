# pylint: disable=missing-function-docstring, missing-module-docstring

import json

from treadmill_index.extract import extract_company


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
