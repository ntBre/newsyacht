import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Self
from xml.etree import ElementTree

import httpx

logger = logging.getLogger(__name__)
logging.basicConfig()


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
    def from_xml(cls, xml: str) -> Self:
        tree = ElementTree.ElementTree(ElementTree.fromstring(xml))
        return cls._from_xml(tree)

    @classmethod
    def _from_xml(cls, tree: ElementTree.ElementTree[ElementTree.Element[str]]) -> Self:
        """
        Deserialize a `Feed` from an XML document.
        """

        root = tree.getroot()
        assert root is not None and root.tag == "rss", "Expected root tag to be <rss>"

        channels = list(root.iter("channel"))
        assert len(channels) == 1, "Expected a single nested <channel>"

        channel = channels[0]

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

        title = then(channel.find("title"), lambda t: t.text)
        link = then(channel.find("link"), lambda t: t.text)
        description = then(channel.find("description"), lambda t: t.text)

        return cls(title=title, link=link, description=description, items=items)


def load_urls(path) -> list[str]:
    """
    Load a sequence of URLs from `path`, one per line.
    """
    return [url.strip() for url in Path(path).read_text().splitlines()]


def update_feeds(feeds: list[DbFeed]):
    """
    Fetch a list of feeds and update them in place.
    """
    for feed in feeds:
        # TODO include etag and last_modified, extracted from ETag and
        # Last-Modified headers.
        #
        # I think it's actually okay always to use the URLs from the file, but
        # we'll need to get the header values from the database, so we'll just
        # need to query for whatever URLs before we actually fetch.
        response = httpx.get(feed.url, follow_redirects=True)
        if response.status_code == httpx.codes.OK:
            etag = response.headers.get("etag")
            last_modified = response.headers.get("last-modified")
            body = Feed.from_xml(response.text)
            feed.update(etag=etag, last_modified=last_modified, feed=body)
        else:
            logger.error(
                "failed to retrieve %s with %s", feed.url, response.status_code
            )

    return feeds


@dataclass
class DbFeed:
    """
    A feed in the database.

    TODO better name. This is basically the database model for a Feed, or really
    the primary feed type, but Feed is already taken above.
    """

    url: str
    "The URL to fetch."

    etag: str | None
    "ETag header from the last server response, if provided."

    last_modified: str | None
    "Last-Modified header from the last server response, if provided."

    feed: Feed | None
    "The deserialized feed result, if the response was okay."

    def __init__(self, url):
        self.url = url
        self.etag = None
        self.last_modified = None
        self.feed = None

    def update(self, *, etag, last_modified, feed):
        """
        Replace the provided fields of `self` if the values are not `None`.
        """
        self.etag = etag or self.etag
        self.last_modified = last_modified or self.last_modified
        self.feed = feed or self.feed


def main() -> None:
    urls = load_urls("tests/fixtures/urls")
    feeds = [DbFeed(url) for url in urls]

    update_feeds(feeds)

    # tree = ElementTree.parse("tests/fixtures/arch.xml")
    # feed = Feed.from_xml(tree)

    # from pprint import pprint

    # pprint(feed)
