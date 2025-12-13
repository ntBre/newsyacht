import logging
import sqlite3
from dataclasses import dataclass
from operator import attrgetter
from pathlib import Path
from typing import Callable, NewType, Self
from xml.etree import ElementTree

import httpx

logger = logging.getLogger(__name__)
logging.basicConfig()

FeedId = NewType("FeedId", int)


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
    content: str | None
    link: str | None
    author: str | None
    date: str | None
    guid: str


@dataclass
class DbItem:
    id: int
    "The ID in the database."

    feed_id: FeedId
    "The database ID of the parent feed."

    is_read: bool
    "Whether the item has been marked as read."

    score: float
    "Ranking score, currently unused."

    inner: Item

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Self:
        return cls(
            id=row["id"],
            feed_id=row["feed_id"],
            is_read=row["is_read"],
            score=row["score"],
            inner=Item(
                title=row["title"],
                content=row["content"],
                link=row["link"],
                author=row["author"],
                date=row["date"],
                guid=row["guid"],
            ),
        )


type XmlTree = (
    ElementTree.ElementTree[ElementTree.Element[str] | None]
    | ElementTree.ElementTree[ElementTree.Element[str]]
)


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
    def _from_xml(cls, tree: XmlTree) -> Self:
        """
        Deserialize a `Feed` from an XML document.
        """

        root = tree.getroot()
        assert root is not None and root.tag == "rss", "Expected root tag to be <rss>"

        channels = list(root.iter("channel"))
        assert len(channels) == 1, "Expected a single nested <channel>"

        channel = channels[0]

        def get(item, field):
            return then(item.find(field), attrgetter("text"))

        items = []
        for item in channel.iter("item"):
            items.append(
                Item(
                    title=get(item, "title"),
                    link=get(item, "link"),
                    content=get(item, "description"),
                    author=get(item, "dc:creator"),
                    date=get(item, "pubDate"),
                    guid=get(item, "guid"),
                )
            )

        return cls(
            title=get(channel, "title"),
            link=get(channel, "link"),
            description=get(channel, "description"),
            items=items,
        )


def load_urls(path) -> list[str]:
    """
    Load a sequence of URLs from `path`, one per line.
    """
    return [url.strip() for url in Path(path).read_text().splitlines()]


def update_feeds(feeds: list[DbFeed]) -> list[tuple[FeedId, Item]]:
    """
    Fetch a list of feeds, update their metadata in place, and return a
    list of items.
    """

    items = []
    for feed in feeds:
        headers = {}
        if feed.etag:
            headers["etag"] = feed.etag
        if feed.last_modified:
            headers["last-modified"] = feed.last_modified

        response = httpx.get(feed.url, follow_redirects=True, headers=headers)
        if response.status_code == httpx.codes.OK:
            etag = response.headers.get("etag")
            last_modified = response.headers.get("last-modified")
            body = Feed.from_xml(response.text)
            feed.update(etag=etag, last_modified=last_modified, feed=body)
            items.extend((feed.id, item) for item in body.items)
        else:
            logger.error(
                "failed to retrieve %s with %s", feed.url, response.status_code
            )

    return items


@dataclass
class DbFeed:
    """
    A feed in the database.

    TODO better name. This is basically the database model for a Feed, or really
    the primary feed type, but Feed is already taken above.
    """

    id: int
    "The ID in the database."

    url: str
    "The URL to fetch."

    title: str | None
    "The feed title."

    description: str | None
    "The feed description."

    etag: str | None
    "ETag header from the last server response, if provided."

    last_modified: str | None
    "Last-Modified header from the last server response, if provided."

    def update(self, *, etag, last_modified, feed: Feed):
        """
        Replace the provided fields of `self` if the values are not `None`.
        """
        self.title = feed.title or self.title
        self.description = feed.description or self.description
        self.etag = etag or self.etag
        self.last_modified = last_modified or self.last_modified


def main() -> None:
    urls = load_urls("tests/fixtures/urls")

    conn = sqlite3.connect("cache.db")
    conn.row_factory = sqlite3.Row

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS feeds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT NOT NULL UNIQUE,
            title TEXT,
            description TEXT,
            etag TEXT,
            last_modified TEXT
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS items (
            id            INTEGER PRIMARY KEY,
            feed_id       INTEGER NOT NULL REFERENCES feeds(id),
            is_read       INTEGER NOT NULL DEFAULT 0,
            score         REAL NOT NULL DEFAULT 0.0,
            title         TEXT,
            content       TEXT,
            link          TEXT,
            author        TEXT,
            date          TEXT,
            guid          TEXT NOT NULL,
            UNIQUE(feed_id, guid)
        )
        """
    )

    with conn:
        conn.executemany(
            """
            INSERT INTO feeds (url)
            VALUES (?)
            ON CONFLICT(url) DO NOTHING;
            """,
            [(u,) for u in urls],
        )

    placeholders = ",".join("?" for _ in urls)
    cur = conn.execute(
        f"""
        SELECT id, url, title, description, etag, last_modified
        FROM feeds
        WHERE url IN ({placeholders})
        ORDER BY url;
        """,
        urls,
    )

    feeds = [DbFeed(*row) for row in cur.fetchall()]

    items = update_feeds(feeds)

    with conn:
        conn.executemany(
            """
            UPDATE feeds
            SET etag = ?, last_modified = ?
            WHERE id = ?
            """,
            [(feed.etag, feed.last_modified, feed.id) for feed in feeds],
        )

    with conn:
        conn.executemany(
            """
            INSERT INTO items (feed_id, guid, title, content, link, author, date)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(feed_id, guid) DO UPDATE SET
                title = excluded.title,
                content = excluded.content,
                link = excluded.link,
                author = excluded.author,
                date = excluded.date
            """,
            [
                (
                    feed_id,
                    item.guid,
                    item.title,
                    item.content,
                    item.link,
                    item.author,
                    item.date,
                )
                for feed_id, item in items
            ],
        )

    cur = conn.execute(
        """
        SELECT id, feed_id, is_read, score, title, content, link, author, date, guid
        FROM items
        """
    )

    posts = [DbItem.from_row(row) for row in cur.fetchall()]

    for post in posts:
        print(post.inner.title)
