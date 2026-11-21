.DEFAULT_GOAL := help

UV ?= uv
UV_CACHE_DIR ?= $(CURDIR)/.uv-cache
export UV_CACHE_DIR
RUN := $(UV) run --locked --no-sync
COVERAGE_FLAGS := $(if $(filter 1,$(COVERAGE)),--cov=receipt_ocr --cov-report=term-missing)

.PHONY: help setup build deps-lock format format-check lint typecheck test check
help:
	@printf '%s\n' \
	  'setup                            Install the locked development environment' \
	  'build                            Build the source distribution and wheel' \
	  'deps-lock                        Resolve the declared dependency constraints' \
	  'format                           Format Python source' \
	  'format-check                     Check Python formatting' \
	  'lint                             Check Python lint rules' \
	  'typecheck                        Check Python types' \
	  'test [COVERAGE=1]                Run tests, optionally enforcing coverage' \
	  'check                            Run formatting, lint, type checks, and tests with coverage'

setup:
	$(UV) sync --locked

build:
	$(UV) build --no-sources

deps-lock:
	$(UV) lock

format:
	$(RUN) ruff check --fix src tests
	$(RUN) ruff format src tests

format-check:
	$(RUN) ruff format --check src tests

lint:
	$(RUN) ruff check src tests

typecheck:
	$(RUN) mypy src tests

test:
	$(RUN) pytest $(COVERAGE_FLAGS)

check:
	$(MAKE) format-check
	$(MAKE) lint
	$(MAKE) typecheck
	$(MAKE) test COVERAGE=1
