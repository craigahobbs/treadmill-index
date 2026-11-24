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
	@echo "            [check-prototype|data|insider-data|lint-app|run|test-app|test-data]"


clean:
	rm -rf Makefile.base pylintrc


# Run the web application's unit tests (TEST_APP="testName" runs one test); -d surfaces builtin debug logs
.PHONY: test-app
test: test-app
test-app: $(DEFAULT_VENV_BUILD)
	$(DEFAULT_VENV_BIN)/bare -d -m test/runTests.bare$(if $(TEST_APP), -v vUnittestTest "'$(TEST_APP)'")


# Lint the web application's scripts standalone. -x lints and executes (the scripts and the test files);
# -s lints the test runner without executing it (that's the test-app target).
.PHONY: lint-app
lint: lint-app
lint-app: $(DEFAULT_VENV_BUILD)
	$(DEFAULT_VENV_BIN)/bare -x -m *.bare test/test*.bare
	$(DEFAULT_VENV_BIN)/bare -s -m test/runTests.bare


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


# Check that the build step, with the prototype's options, reproduces prototype/treadmill_market_screen.csv.
# This only holds against the SEC companyfacts.zip of 2026-11-23.
.PHONY: check-prototype
check-prototype: $(DEFAULT_VENV_BUILD)
	$(DEFAULT_VENV_PYTHON) prototype/compare.py


# Make the web application's unit test data, test/data/, from the made-up companies in test/makeTestData.py
.PHONY: test-data
test-data: $(DEFAULT_VENV_BUILD)
	PYTHONPATH=src $(DEFAULT_VENV_PYTHON) test/makeTestData.py


# Run the web application locally
.PHONY: run
run:
	python3 -m http.server 8080
