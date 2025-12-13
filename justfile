run *args:
	uv run -- newsyacht {{args}}

test:
	uv run -- pytest tests

accept:
	uv run -- pytest tests --snapshot-update

check:
	uv run -- ruff check
	uv run -- ruff format --check
	uv run -- ty check

format:
	uv run -- ruff format
