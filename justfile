# Run the CLI
run *args:
	uv run -- newsyacht {{args}}

# Run the tests
test *args:
	uv run -- pytest tests -vv {{args}}

# Run the tests and accept any snapshot changes
accept:
	uv run -- pytest tests --snapshot-update

# Lint with Ruff
lint *args:
	uv run -- ruff check {{args}}

isort:
	uv run -- ruff check --select I,F401 --fix

check: isort format lint
	uv run -- ty check --no-progress

format:
	uv run -- ruff format
	prettier src/newsyacht/web/static -w

all: format lint check test

install:
	uv tool install --reinstall .
