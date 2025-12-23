run *args:
	uv run -- newsyacht {{args}}

test *args:
	uv run -- pytest tests {{args}}

accept:
	uv run -- pytest tests --snapshot-update

lint *args:
	uv run -- ruff check {{args}}

check: lint
	uv run -- ruff format --check
	uv run -- ty check

format:
	uv run -- ruff format
