.DEFAULT_GOAL := help

UV ?= uv
UV_CACHE_DIR ?= $(CURDIR)/.uv-cache
export UV_CACHE_DIR
RUN := $(UV) run --locked --no-sync
COVERAGE_FLAGS := $(if $(filter 1,$(COVERAGE)),--cov=receipt_ocr --cov-report=term-missing)
BACKEND ?= scikit-image
APPROACHES ?= tests/prepare_approaches.json
OBSERVE_APPROACHES ?= tests/observe_approaches.json
FEATURED := setup check test build help help-verbose

define show_help
	@LC_ALL=C sort -t: -k1,1 $(MAKEFILE_LIST) | awk -v featured="$(FEATURED)" -v verbose="$(1)" '\
		/^[[:alnum:]_.-]+:.*## / { \
			target = $$0; sub(/:.*/, "", target); \
			description = $$0; sub(/^[^:]+:.*## /, "", description); \
			targets[++count] = target; descriptions[target] = description; \
		} \
		END { \
			print "Make targets:"; \
			printf "  \033[1mFeatured\033[0m\n"; \
			featured_count = split(featured, names, " "); \
			for (i = 1; i <= featured_count; i++) { \
				print_target(names[i]); featured_targets[names[i]] = 1; \
			} \
			if (verbose) { \
				printf "\n  \033[1mEverything else\033[0m\n"; \
				for (i = 1; i <= count; i++) { \
					if (!(targets[i] in featured_targets)) print_target(targets[i]); \
				} \
			} \
		} \
		function print_target(name) { \
			printf "    \033[36m%-24s\033[0m %s\n", name, descriptions[name]; \
		}'
endef

.PHONY: help help-verbose setup prepare-dev prepare-image evaluate-prepare evaluate-observe hooks build deps-lock format format-check lint typecheck test check
help: ## Show featured commands
	$(call show_help,0)

help-verbose: ## Show all commands
	$(call show_help,1)

setup: ## Install the locked development environment, optionally with OBSERVE=1
	$(UV) sync --locked $(if $(filter 1,$(OBSERVE)),--extra observe)

prepare-dev: ## Prepare private test fixtures with ARCHIVE=... BOOK=...
	$(RUN) python -m tests.fixture_corpus --archive "$(ARCHIVE)" --book "$(BOOK)"

prepare-image: ## Prepare INPUT=... in OUTPUT_DIR=..., optionally with BACKEND=opencv
	$(RUN) receipt-prepare-image "$(INPUT)" --output-dir "$(OUTPUT_DIR)" --backend "$(BACKEND)"

evaluate-prepare: ## Compare image fixtures with optional APPROACHES=<JSON config>
	$(RUN) python -m tests.evaluate_prepare --approaches "$(APPROACHES)"

evaluate-observe: ## Compare OCR engines with optional OBSERVE_FIXTURE=<image ID> and OBSERVE_APPROACHES=<JSON config>
	$(RUN) python -m tests.evaluate_observe --approaches "$(OBSERVE_APPROACHES)" $(if $(OBSERVE_FIXTURE),--fixture "$(OBSERVE_FIXTURE)")

hooks: ## Install the fixture pre-push guard
	git config --local core.hooksPath .githooks

build: ## Build the source distribution and wheel
	$(UV) build --no-sources

deps-lock: ## Resolve the declared dependency constraints
	$(UV) lock

format: ## Format Python source and apply lint fixes
	$(RUN) ruff check --fix src tests
	$(RUN) ruff format src tests

format-check: ## Check Python formatting
	$(RUN) ruff format --check src tests

lint: ## Check Python lint rules
	$(RUN) ruff check src tests

typecheck: ## Check Python types
	$(RUN) mypy src tests

test: ## Run tests with optional COVERAGE=1 and PREPARE_FIXTURE=<image ID>
	$(RUN) pytest $(COVERAGE_FLAGS) $(if $(PREPARE_FIXTURE),--prepare-fixture "$(PREPARE_FIXTURE)")

check: ## Run formatting, lint, type checks, and tests with coverage
	$(MAKE) format-check
	$(MAKE) lint
	$(MAKE) typecheck
	$(MAKE) test COVERAGE=1
