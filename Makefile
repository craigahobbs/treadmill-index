# Download python-build
PYTHON_BUILD_DIR ?= ../python-build
define WGET
ifeq '$$(wildcard $(notdir $(1)))' ''
$$(info Downloading $(notdir $(1)))
$$(shell [ -f $(PYTHON_BUILD_DIR)/$(notdir $(1)) ] && cp $(PYTHON_BUILD_DIR)/$(notdir $(1)) . || $(call WGET_CMD, $(1)))
endif
endef
WGET_CMD = if command -v wget >/dev/null 2>&1; then wget -q -c $(1); else curl -f -Os $(1); fi
$(eval $(call WGET, https://craigahobbs.github.io/python-build/Makefile.base))
$(eval $(call WGET, https://craigahobbs.github.io/python-build/pylintrc))


# Include python-build
include Makefile.base


# Development dependencies - bare-script provides the "bare" CLI for the web application's tests and lint
TESTS_REQUIRE := bare-script


help:
	@echo "            [data|insider-data|lint-app|run|test-app|test-data|test-pages]"


clean:
	rm -rf Makefile.base pylintrc


# Run the web application's unit tests (TEST_APP="testName" runs one test); -d surfaces builtin debug logs
.PHONY: test-app
test: test-app
test-app: $(DEFAULT_VENV_BUILD)
	$(DEFAULT_VENV_BIN)/bare -d -m test/runTests.bare$(if $(TEST_APP), -v vUnittestTest "'$(TEST_APP)'")


# Lint the web application's scripts standalone. -x lints and executes (the scripts and the test files);
# -s lints the test runner and the page capture script without executing them.
.PHONY: lint-app
lint: lint-app
lint-app: $(DEFAULT_VENV_BUILD)
	$(DEFAULT_VENV_BIN)/bare -x -m *.bare test/test*.bare
	$(DEFAULT_VENV_BIN)/bare -s -m test/runTests.bare test/capturePage.bare


# Build the web application's data files from the SEC bulk files in data/raw/. Python runs isolated (-I)
# because it reads downloaded files. If a company's industry code is not cached yet, SEC_USER_AGENT is required.
.PHONY: data
data: $(DEFAULT_VENV_BUILD)
	$(DEFAULT_VENV_PYTHON) -I -m treadmill_index


# Download the SEC insider-transaction data sets (Forms 3, 4 and 5) to data/raw/insider/. SEC_USER_AGENT is
# required - your name and a contact address. It is read from the environment and never stored:
#     SEC_USER_AGENT="Your Name you@example.com" make insider-data
.PHONY: insider-data
insider-data: $(DEFAULT_VENV_BUILD)
	$(DEFAULT_VENV_PYTHON) -I -m treadmill_index --download-insider


# Make the web application's unit test data, test/data/, from the made-up companies in test/makeTestData.py
.PHONY: test-data
test-data: $(DEFAULT_VENV_BUILD)
	PYTHONPATH=src $(DEFAULT_VENV_PYTHON) test/makeTestData.py


# Make the web application's page render tests, test/testTreadmillIndexPages.bare, from the pages as they render now.
# Run it after "make test-data", or after a change to what a page renders, and read the diff.
.PHONY: test-pages
test-pages: $(DEFAULT_VENV_BUILD)
	$(DEFAULT_VENV_PYTHON) test/makeTestPages.py $(DEFAULT_VENV_BIN)/bare


# Run the web application locally
.PHONY: run
run:
	python3 -m http.server 8080
