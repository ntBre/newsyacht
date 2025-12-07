from dataclasses import dataclass
from typing import Callable, Self
from xml.etree import ElementTree


def then[T, U](x: T | None, f: Callable[[T], U | None]) -> U | None:
    """If the optional value `x` is some, return the result of applying `f`,
    else return `None`"""
    if x is None:
        return None
    return f(x)


@dataclass
class Item:
    """
    A entry in an RSS `Feed`.

    This is the deserialized representation from the XML document without any
    of the internal data tracked in the database.
    """

    title: str | None
    description: str | None
    link: str | None
    author: str | None
    date: str | None


@dataclass
class Feed:
    """
    A single RSS feed.

    This is the deserialized representation from the XML document without any
    of the internal data tracked in the database.
    """

    title: str | None
    link: str | None
    description: str | None
    items: list[Item]

    @classmethod
    def from_xml(cls, tree: ElementTree.ElementTree[ElementTree.Element[str]]) -> Self:
        """
        Deserialize a `Feed` from an XML document.
        """

        root = tree.getroot()
        assert root is not None and root.tag == "rss", "Expected root tag to be <rss>"

        channels = list(root.iter("channel"))
        assert len(channels) == 1, "Expected a single nested <channel>"

        channel = channels[0]

        title = then(channel.find("title"), lambda t: t.text)
        link = then(channel.find("link"), lambda t: t.text)
        description = then(channel.find("description"), lambda t: t.text)

        items = []
        for item in channel.iter("item"):
            title = then(item.find("title"), lambda t: t.text)
            link = then(item.find("link"), lambda t: t.text)
            description = then(item.find("description"), lambda t: t.text)
            author = then(item.find("dc:creator"), lambda t: t.text)
            date = then(item.find("pubDate"), lambda t: t.text)
            items.append(
                Item(
                    title=title,
                    link=link,
                    description=description,
                    author=author,
                    date=date,
                )
            )

        return cls(title=title, link=link, description=description, items=items)


def main() -> None:
    print("Hello from newsyacht!")

    tree = ElementTree.parse("tests/fixtures/arch.xml")
    feed = Feed.from_xml(tree)

    from pprint import pprint

    pprint(feed)
