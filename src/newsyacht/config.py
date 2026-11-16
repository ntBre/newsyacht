import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import NewType, Self

Color = NewType("Color", str)


@dataclass
class Feed:
    link: str
    "The link to the feed."

    tags: list[str] = field(default_factory=list)
    "Any tags to associate with the feed."

    color: Color | None = None
    "The color to use for the label, if any."

    label: str | None = None
    "The label to use instead of the author, if any."


@dataclass
class Config:
    feeds: list[Feed]

    @classmethod
    def from_path(cls, path: Path | str) -> Self:
        """
        Try to load a config file from `path` as TOML, falling back to the
        legacy URL format if that fails.
        """
        path = Path(path)
        try:
            data = tomllib.loads(path.read_text())
            if feeds := data.get("feed"):
                return cls([Feed(**feed) for feed in feeds])
        except tomllib.TOMLDecodeError:
            urls = load_urls(path)
            feeds = [Feed(link=url.link, color=url.color) for url in urls]
            return cls(feeds)

        raise ValueError(f"Failed to load config from {path}")


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
                urls.append(Url(url, Color(color)))
            case line:
                msg = f"Unable to parse line: {line}"
                raise ValueError(msg)

    return urls
