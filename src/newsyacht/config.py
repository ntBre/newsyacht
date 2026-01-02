from dataclasses import dataclass
from pathlib import Path
from typing import NewType

Color = NewType("Color", str)


@dataclass
class Url:
    link: str
    color: Color | None = None


def load_urls(path: Path | str) -> list[Url]:
    """
    Load a sequence of URLs from `path`, one per line.

    Lines starting with `#` and empty lines are ignored.
    """

    urls = []
    for line in Path(path).read_text().splitlines():
        if line.startswith("#"):
            continue

        if len(stripped := line.strip()) == 0:
            continue

        match stripped.split():
            case [url]:
                urls.append(Url(url))
            case [url, color]:
                urls.append(Url(url, color))
            case line:
                msg = f"Unable to parse line: {line}"
                raise ValueError(msg)

    return urls
