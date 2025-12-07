run:
	uv run newsyacht

test:
	uv run -- pytest tests

check:
	uv run -- ruff check
	uv run -- ruff format --check
	uv run -- ty check
