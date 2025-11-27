.PHONY: test test-cov test-unit test-integration

test:
	pytest tests/

test-cov:
	pytest tests/ --cov=bot/handlers/game --cov-report=term-missing --cov-report=html

test-unit:
	pytest tests/ -m unit

test-integration:
	pytest tests/ -m integration

test-watch:
	pytest-watch tests/