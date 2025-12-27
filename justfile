run *args:
	uv run -- newsyacht {{args}}

test *args:
	uv run -- pytest tests {{args}}

accept:
	uv run -- pytest tests --snapshot-update

lint *args:
	uv run -- ruff check {{args}}

check: format lint
	uv run -- ty check --no-progress

format:
	uv run -- ruff format
