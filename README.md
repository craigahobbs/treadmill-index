# The Treadmill Index

A public index of large, growing companies whose revenue growth has not become meaningful cash for outside
owners, because the cash goes out as stock pay. It ranks how owners have been treated. It is not a short list,
a price forecast or investment advice, and it makes no statement about any company's intent.

The index is a statically hosted web application ([MarkdownUp](https://craigahobbs.github.io/markdown-up/) and
[BareScript](https://craigahobbs.github.io/bare-script/)) fed by data files built from SEC filings. Every
published figure links to the SEC filing it came from.

- [docs/index-definition.md](docs/index-definition.md) is the definition of the index.
- [docs/findings.md](docs/findings.md) is the record of the first whole-market run with the prototype.
- [docs/plan.md](docs/plan.md) is the plan for the web application.


## What is built

| Part | Where | State |
| --- | --- | --- |
| Build step: extract, screen, score, write data files | `src/treadmill_index/` | Stage 1 and the screen score (P1 and P2b) |
| Data files | `data/` | `index.json`, `index.csv`, `meta.json`, `company/<CIK>.json`, `archive/` |
| Web application | `index.html`, `treadmillIndex.md`, `treadmillIndex.bare` | Index, company pages, group totals, threshold explorer, methodology, data and limits, downloads |
| Full score (P2a, P3, P4) for the top 25 | | Not built. It needs insider-transaction data and hand-checked data. |


## Building the data

1. Download the SEC bulk file
   [companyfacts.zip](https://www.sec.gov/Archives/edgar/daily-index/xbrl/companyfacts.zip) (about 1.4 GB) to
   `data/raw/companyfacts.zip`. The SEC refuses bulk downloads from clients that do not identify themselves, so
   use a browser, or a client whose User-Agent names you and gives a contact address.
2. Run the build:

   ~~~
   make data
   ~~~

The build reads the zip directly (about 15 seconds on 12 cores, cached in `data/raw/` afterward), looks up
industry codes and tickers, screens and scores every company, checks the result, and writes `data/`. Each build
is also copied to `data/archive/<data date>/`.

Industry codes and tickers come from the SEC bulk file `submissions.zip` if it is in `data/raw/`, otherwise
from the SEC's per-company API, one request per company (about 1,300, cached in `data/raw/`). Set the
`SEC_USER_AGENT` environment variable to the User-Agent the SEC should see.

`data/raw/` and `*.zip` are git-ignored. Everything else in `data/` is published.


## Development

This is a [python-build](https://github.com/craigahobbs/python-build#readme) project.

~~~
make commit           # test, lint and coverage for the build step and the web application
make test             # the Python unit tests and the web application's unit tests
make cover            # Python coverage (100% required)
make test-app         # the web application's unit tests (100% coverage required)
make lint             # pylint, and static analysis of the web application
make data             # build the data files
make test-data        # remake the web application's test data, test/data/
make check-prototype  # check the build step reproduces the prototype's output
make run              # serve the application at http://localhost:8080/
~~~

The web application's test data, `test/data/`, is made by the build step itself from the made-up companies in
`test/makeTestData.py`. After a change to the content of the data files, run `make test-data` and update the
expected page renders in `test/testTreadmillIndexPages.bare`.
