# The Treadmill Index

[The Treadmill Index](https://craigahobbs.github.io/treadmill-index/)
is a public index of large, growing companies whose revenue growth has not become meaningful cash for outside
owners, because the cash goes out as stock pay. It scores three signs together: owner cash that stays near
zero, operating costs that take all of gross profit, and insiders who take cash out through stock. It ranks
how owners have been treated. It is not a short list, a price forecast or investment advice, and it makes no
finding about any one company's intent.

The index is a statically hosted web application ([MarkdownUp](https://craigahobbs.github.io/markdown-up/) and
[BareScript](https://craigahobbs.github.io/bare-script/)) fed by data files built from SEC filings. Every
published figure links to the SEC filing it came from.

- [docs/index-definition.md](docs/index-definition.md) is the definition of the index. Its amendment of
  2026-11-24 is what is built.
- [docs/findings.md](docs/findings.md) is the record of the first whole-market run with the prototype.
- [docs/plan.md](docs/plan.md) is the original plan for the web application.


## What Is Built

| Part | Where | State |
| --- | --- | --- |
| Build step: extract, screen, score, write data files | `src/treadmill_index/` | The screen, and one score (75) on three signs: owner cash, costs as a share of gross profit, insider cash-out as a share of revenue |
| Data files | `data/` | `index.json`, `index.csv`, `meta.json`, `company/<CIK>.json`, `archive/` |
| Web application | `index.html`, `treadmillIndex.md`, `treadmillIndex.bare` | Index, company pages with insider filings, group totals, methodology and glossary, data and limits with downloads |


## Building the Data

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
is also copied to `data/archive/<data date>/<method version>/`.

Industry codes and tickers come from the SEC bulk file `submissions.zip` if it is in `data/raw/`, otherwise
from the SEC's per-company API, one request per company (about 1,300, cached in `data/raw/`). The cache is not
refreshed: delete `data/raw/submissions-cache.json` to pick up a company's new ticker or industry code.

Any step that makes a request to the SEC requires the `SEC_USER_AGENT` environment variable: your name and a
contact address, as the SEC asks of automated clients. There is no default, and it is never written to a
file. Set it for the one command:

~~~
SEC_USER_AGENT="Your Name you@example.com" make data
SEC_USER_AGENT="Your Name you@example.com" make insider-data
~~~

`make insider-data` downloads the SEC's quarterly insider-transaction data sets to `data/raw/insider/`. `make data`
needs them: what each company's insiders took out through stock is one of the three signs. The build stops, and
names the quarters, if a data set of the latest five calendar years is missing.

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
make insider-data     # download the SEC insider-transaction data sets
make test-data        # remake the web application's test data, test/data/
make test-pages       # remake the web application's page render tests from the pages as they render now
make run              # serve the application at http://localhost:8080/
~~~

The web application's test data, `test/data/`, is made by the build step itself from the made-up companies in
`test/makeTestData.py`. The page render tests, `test/testTreadmillIndexPages.bare`, are generated from the page
states listed in `test/makeTestPages.py`. After a change to the content of the data files, or to what a page
renders, run `make test-data` and `make test-pages`, and read the diff before committing it.


## License

The code is under the [MIT License](LICENSE). The figures in `data/` are computed from public SEC filings; each
one links to the filing it came from.
