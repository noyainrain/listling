PYTHON=python3
PIP=pip3
NPM=npm

PIPFLAGS=$$([ -z "$$VIRTUAL_ENV" ] && echo --user) -U
NPMFLAGS=-C client --no-save --no-optional

.PHONY: test
test:
	$(PYTHON) -m unittest

.PHONY: test-ext
test-ext:
	$(PYTHON) -m unittest discover -p "ext_test*.py"

.PHONY: test-ui
test-ui:
	$(NPM) $(NPMFLAGS) run test-ui

.PHONY: test-perf
test-perf:
	$(PYTHON) -m listling.tests.perf

.PHONY: watch-test
watch-test:
	trap "exit 0" INT; $(PYTHON) -m tornado.autoreload -m unittest

.PHONY: lint
lint:
	pylint -j 0 listling
	$(NPM) $(NPMFLAGS) run lint

.PHONY: check
check: test test-ext test-ui lint

.PHONY: deps
deps:
	$(PIP) install $(PIPFLAGS) -r requirements.txt
	@# Work around npm 7 update modifying package.json (see https://github.com/npm/cli/issues/3044)
	$(NPM) $(NPMFLAGS) install --only=prod

.PHONY: deps-dev
deps-dev:
	$(PIP) install $(PIPFLAGS) -r requirements-dev.txt
	@# Work around npm 7 update modifying package.json (see https://github.com/npm/cli/issues/3044)
	$(NPM) $(NPMFLAGS) install

.PHONY: doc
doc:
	sphinx-build doc doc/build

.PHONY: show-deprecated
show-deprecated:
	git grep -in -C1 deprecate $$(git describe --tags $$(git rev-list -1 --first-parent \
	                                                     --until="6 months ago" master))

.PHONY: release
release:
	scripts/release.sh
	scripts/publish-doc.sh

.PHONY: micro-link
micro-link:
	$(PIP) install $(PIPFLAGS) -e "$(MICROPATH)"
	@# Work around npm 7 uninstalling local dependencies if outside package (see
	@# https://github.com/npm/cli/issues/2339)
	rm -r client/node_modules/@noyainrain/micro
	ln -sT "$(MICROPATH)/client" client/node_modules/@noyainrain/micro

.PHONY: clean
clean:
	rm -rf $$(find . -name __pycache__) doc/build doc/micro
	$(NPM) $(NPMFLAGS) run clean

.PHONY: help
help:
	@echo "test:            Run all unit tests"
	@echo "test-ext:        Run all extended/integration tests"
	@echo "test-ui:         Run all UI tests"
	@echo "                 BROWSER:       Browser to run the tests with. Defaults to"
	@echo '                                "firefox".'
	@echo "                 WEBDRIVER_URL: URL of the WebDriver server to use. If not set"
	@echo "                                (default), tests are run locally."
	@echo "                 TUNNEL_ID:     ID of the tunnel to use for remote tests"
	@echo "                 PLATFORM:      OS to run the remote tests on"
	@echo "                 SUBJECT:       Text included in subject of remote tests"
	@echo "test-perf:       Run all performance tests"
	@echo "watch-test:      Watch source files and run all unit tests on change"
	@echo "lint:            Lint and check the style of the code"
	@echo "check:           Run all code quality checks (test and lint)"
	@echo "deps:            Update the dependencies"
	@echo "deps-dev:        Update the development dependencies"
	@echo "doc:             Build the documentation"
	@echo "show-deprecated: Show deprecated code ready for removal (deprecated for at"
	@echo "                 least six months)"
	@echo "release:         Make a new release"
	@echo "                 FEATURE: Corresponding feature branch"
	@echo "                 VERSION: Version number"
	@echo "micro-link:      Link micro from a local repository. Useful when simultaneously"
	@echo "                 editing micro."
	@echo "                 MICROPATH: Location of local micro repository"
	@echo "clean:           Remove temporary files"
