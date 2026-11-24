"""
Generate the web application's page render tests, test/testTreadmillIndexPages.bare: render every page state below
against test/data/ and write each render log out as the test's expected value. Run it with "make test-pages" after a
change to what a page renders, then read the diff: the tests only say that the pages render what they rendered here.
"""

import json
import os
import subprocess
import sys


META = 'data/meta.json'
INDEX = 'data/index.json'
BUILDS = 'data/archive/builds.json'


def company(cik):
    return f'data/company/{cik}.json'


# The page states: the test name, the arguments (and other globals), the data URLs that load, a comment, and the
# test/data/ directory if it is not the default
SCENARIOS = [
    ('testMain_index', {}, [META, INDEX], 'The index page: the companies that pass the screen, in score order'),
    ('testMain_indexAll', {'vType': 'all', 'vSort': 'owner', 'tiRowLimit': 3}, [META, INDEX],
     'All types, sorted by owner-cash margin, with more rows than the row limit'),
    ('testMain_indexShowAll', {'vType': 'all', 'vSort': 'name', 'vAll': True, 'tiRowLimit': 3}, [META, INDEX],
     'All types, sorted by name, showing all rows'),
    ('testMain_indexFind', {'vType': 'all', 'vSort': 'costs', 'vSic': 7372, 'vFind': 'CO'}, [META, INDEX],
     'Find by name within an industry, sorted by the share of gross profit that costs take'),
    ('testMain_indexFindTicker', {'vFind': 'spay'}, [META, INDEX], 'Find by ticker'),
    ('testMain_indexNoMatch', {'vType': 'thin_margin', 'vFind': 'zzz'}, [META, INDEX], 'No companies match'),
    ('testMain_indexUnknownArgs', {'vType': 'bogus', 'vSort': 'bogus'}, [META, INDEX], 'An unknown type and sort'),
    ('testMain_indexInsiderSort', {'vType': 'all', 'vSort': 'insiders'}, [META, INDEX], 'All types, sorted by insider cash-out'),
    ('testMain_indexCapitalLed', {'vType': 'capital_led'}, [META, INDEX], 'The capital-led companies'),
    ('testMain_indexFailed', {}, [META], 'The index data failed to load'),
    ('testMain_metaFailed', {}, [INDEX], 'The meta data failed to load'),
    ('testMain_company', {'vPage': 'company', 'vCik': 1}, [META, company(1)], 'A ranked company with latest-12-month figures'),
    ('testMain_companyPerson', {'vPage': 'company', 'vCik': 1, 'vPerson': 1001}, [META, company(1)],
     "A company's page with one insider's filings"),
    ('testMain_companyOneOff', {'vPage': 'company', 'vCik': 6}, [META, company(6)],
     'One-off years, two capital spending tags, no latest 12 months, a share count jump'),
    ('testMain_companyCapitalLed', {'vPage': 'company', 'vCik': 2}, [META, company(2)],
     'Capital-led, no ticker, no insider filings, a name that needs escaping'),
    ('testMain_companyNoCostLine', {'vPage': 'company', 'vCik': 3}, [META, company(3)], 'No cost line, missing capital spending'),
    ('testMain_companyNoGrossProfit', {'vPage': 'company', 'vCik': 11}, [META, company(11)],
     'No gross profit for operating costs to take'),
    ('testMain_companyNoCashOut', {'vPage': 'company', 'vCik': 10}, [META, company(10)],
     'Insiders who bought and did not sell, and a falling share count'),
    ('testMain_companyCashGenerative', {'vPage': 'company', 'vCik': 4}, [META, company(4)],
     'Unranked with a score, former names, a share count change, cash returned'),
    ('testMain_companyExcluded', {'vPage': 'company', 'vCik': 5}, [META, company(5)], 'An excluded industry'),
    ('testMain_companyNoIndustryName', {'vPage': 'company', 'vCik': 7}, [META, company(7)], 'No industry description or exchange'),
    ('testMain_companyNoIndustry', {'vPage': 'company', 'vCik': 8}, [META, company(8)], 'No industry code'),
    ('testMain_companyUnknown', {'vPage': 'company', 'vCik': 99}, [META], 'An unknown company'),
    ('testMain_companyNoCik', {'vPage': 'company'}, [META], 'No company'),
    ('testMain_totals', {'vPage': 'totals'}, [META], 'The group totals page'),
    ('testMain_method', {'vPage': 'method'}, [META], 'The methodology page'),
    ('testMain_data', {'vPage': 'data'}, [META, BUILDS], 'The data and limits page'),
    ('testMain_dataNoBuilds', {'vPage': 'data'}, [META], 'The data and limits page when the list of builds failed to load'),
    ('testMain_indexNoInsider', {}, [META, INDEX], 'The index page of a build without the insider data sets', 'noinsider/'),
    ('testMain_companyNoInsider', {'vPage': 'company', 'vCik': 1}, [META, company(1)],
     "A company's page in a build without the insider data sets", 'noinsider/'),
    ('testMain_totalsNoInsider', {'vPage': 'totals'}, [META], 'The group totals page of a build without the insider data sets',
     'noinsider/'),
    ('testMain_dataNoInsider', {'vPage': 'data'}, [META, BUILDS], 'The data and limits page of a build without the insider data sets',
     'noinsider/')
]

# The globals that are not arguments, and the values the tests put back
DEFAULTS = {'tiRowLimit': 100}

HEADER = '''\
include <dataLineChart.bare>
include <unittest.bare>
include <unittestMock.bare>
include '../treadmillIndex.bare'
include 'testHelpers.bare'


# The page render tests. Each compares the whole render log of a page against the expected log.
#
# This file is generated: "make test-pages" renders the page states in test/makeTestPages.py against the test data,
# test/data/, which "make test-data" makes from the made-up companies in test/makeTestData.py.
'''


def string(text):
    """
    Write a BareScript string literal
    """

    return "'" + text.replace('\\', '\\\\').replace("'", "\\'").replace('\n', '\\n') + "'"


def literal(value, indent):
    """
    Write a BareScript literal for a JSON value, wrapped to the indent
    """

    pad = ' ' * indent
    if isinstance(value, str):
        return string(value)
    if isinstance(value, list) and value:
        flat = '[' + ', '.join(literal(item, 0) for item in value) + ']'
        if '\n' not in flat and len(flat) + indent <= 110 and not any(isinstance(item, (list, dict)) for item in value):
            return flat
        return '[ \\\n' + ', \\\n'.join(pad + '    ' + literal(item, indent + 4) for item in value) + ' \\\n' + pad + ']'
    if isinstance(value, dict) and value:
        flat = '{' + ', '.join(string(key) + ': ' + literal(item, 0) for key, item in value.items()) + '}'
        if '\n' not in flat and len(flat) + indent <= 110:
            return flat
        return '{ \\\n' + ', \\\n'.join(
            pad + '    ' + string(key) + ': ' + literal(item, indent + 4) for key, item in value.items()
        ) + ' \\\n' + pad + '}'
    return json.dumps(value)


def is_chart(call):
    """
    Test whether a logged call renders the yearly chart, which the tests check with a helper instead of a literal
    """

    model = call[1][0] if call[0] == 'elementModelRender' else None
    return isinstance(model, dict) and isinstance(model.get('elem'), dict) and model['elem'].get('svg') == 'svg'


def page_test(bare, test_dir, name, page_globals, urls, comment, data_dir=''):
    """
    Render a page state and write its test
    """

    command = [
        bare, '-m', os.path.join(test_dir, 'capturePage.bare'), '-v', 'vCapUrls', string(json.dumps(urls)),
        '-v', 'vCapGlobals', string(json.dumps(page_globals)), '-v', 'vCapDir', string(data_dir)
    ]
    output = subprocess.run(command, capture_output=True, text=True, check=True).stdout
    log = json.loads(next(line for line in output.splitlines() if line.startswith('[[')))
    calls = ', \\\n'.join(
        '        ' + (f'testChartCall(data, {string(urls[1])})' if is_chart(call) else literal(call, 8)) for call in log
    )
    sets = ''.join(f'    systemGlobalSet({string(key)}, {literal(value, 0)})\n' for key, value in page_globals.items())
    resets = ''.join(f'    systemGlobalSet({string(key)}, {literal(DEFAULTS.get(key), 0)})\n' for key in page_globals)
    return f'''
# {comment}
async function {name}():
    data = testData({literal(urls, 4)}{", " + string(data_dir) if data_dir else ""})
{sets}    unittestMockAll(data)
    tiMain()
    log = unittestMockEnd()
{resets}    unittestDeepEqual(log, [ \\
{calls} \\
    ])
endfunction
unittestRunTest('{name}')
'''


def main(bare):
    test_dir = os.path.dirname(__file__)
    tests = [page_test(bare, test_dir, *scenario) for scenario in SCENARIOS]
    with open(os.path.join(test_dir, 'testTreadmillIndexPages.bare'), 'w', encoding='utf-8') as tests_file:
        tests_file.write('\n'.join([HEADER, *tests]))
    print(f'Wrote {len(tests)} page render tests')


if __name__ == '__main__':
    main(sys.argv[1])
