.PHONY: up down test backend-test frontend-build lint format coverage quality-report e2e

up:
	docker compose up --build

down:
	docker compose down

test:
	python3 -m pytest -q

backend-test:
	python3 -m compileall services tests
	python3 -m pytest -q

lint:
	python3 -m ruff check services tests

format:
	python3 -m ruff format services tests

frontend-build:
	cd frontend && npm run build

# Покрытие тестами по engine/. Падает, если ниже порога.
coverage:
	python3 -m pytest --cov --cov-report=term --cov-report=json:reports/coverage.json --cov-fail-under=50 tests/unit/ tests/integration/

# Полный отчёт качества: coverage + F1 по violations + бенчмарк производительности + сводка.
# CORPUS — путь до корпуса с .docx (по умолчанию tests/fixtures для smoke).
CORPUS ?= tests/fixtures
ANNOTATIONS ?= tests/quality/violation_annotations.json
HEADING_ANNOTATIONS ?= tests/quality/corpus_annotations.json
REPORTS ?= reports

quality-report:
	mkdir -p $(REPORTS)
	python3 -m pytest --cov --cov-report=json:$(REPORTS)/coverage.json -q tests/unit/ tests/integration/ || true
	@if [ -f $(HEADING_ANNOTATIONS) ]; then \
		python3 -m tests.quality.measure_heading_detection --corpus $(CORPUS) --annotations $(HEADING_ANNOTATIONS) --output $(REPORTS)/heading_quality.json || true; \
	else echo "skip heading: $(HEADING_ANNOTATIONS) not found"; fi
	@if [ -f $(ANNOTATIONS) ]; then \
		python3 -m tests.quality.measure_violations --corpus $(CORPUS) --annotations $(ANNOTATIONS) --output $(REPORTS)/violations_quality.json || true; \
	else echo "skip violations: $(ANNOTATIONS) not found"; fi
	python3 -m tests.quality.measure_pipeline_performance --corpus $(CORPUS) --output $(REPORTS)/performance.json --runs 3 --warmup 1 --mode check || true
	python3 -m tests.quality.aggregate_report --reports $(REPORTS) --output $(REPORTS)/quality_summary.json

# E2E через docker compose. Требует поднятого стека (make up в другом терминале).
e2e:
	python3 -m pytest -q tests/e2e/ -m e2e
