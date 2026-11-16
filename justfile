# Run the CLI
run *args:
	uv run -- newsyacht {{args}}

# Run the tests
[arg("update", short="u", value="--snapshot-update")]
test update="" *args:
	uv run -- pytest tests -vv {{args}} {{update}}

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
