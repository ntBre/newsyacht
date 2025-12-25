import argparse
import logging
import math
import os
import random
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, UTC
from email.utils import parsedate_to_datetime
from hashlib import sha256
from importlib.metadata import version
from operator import attrgetter
from pathlib import Path
from typing import NewType, Self
from collections.abc import Callable
from xml.etree import ElementTree
from xml.etree.ElementTree import Element

import httpx

logger = logging.getLogger(__name__)
logging.basicConfig()

FeedId = NewType("FeedId", int)
Color = NewType("Color", str)
Score = NewType("Score", float)


def then[T, U](x: T | None, f: Callable[[T], U]) -> U | None:
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
    comments: str | None
    "An optional link to a comments page"

    date: datetime | None = field(init=False)

    _raw_date: str | None = field(repr=False)

    _raw_guid: str | None = field(repr=False)
    "Input representation of the GUID, which could be missing."

    guid: str = field(init=False)
    "Final represenation of the GUID, which must be present."

    def __post_init__(self):
        """
        Try to find a fallback field for the GUID, if it's missing.

        Raises ValueError if no reasonable fallback can be found.
        """

        if self._raw_guid:
            self.guid = self._raw_guid
        elif self.link:
            self.guid = self.link
        elif self.content:
            m = sha256(usedforsecurity=False)
            m.update(self.content.encode())
            self.guid = m.hexdigest()
        else:
            msg = "Item doesn't include a GUID, link, or contents"
            raise ValueError(msg)

        if self._raw_date:
            self.date = datetime.fromisoformat(self._raw_date)

    def date_str(self):
        if self.date is None:
            return None
        return self.date.astimezone(UTC).isoformat()


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

    color: Color | None
    "Optional color to use when rendering the author names from this feed."

    inner: Item

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Self:
        return cls(
            id=row["id"],
            feed_id=row["feed_id"],
            is_read=row["is_read"],
            score=row["score"],
            color=row["color"],
            inner=Item(
                title=row["title"],
                content=row["content"],
                link=row["link"],
                author=row["author"],
                comments=row["comments"],
                _raw_date=row["date"],
                _raw_guid=row["guid"],
            ),
        )

    def __getattr__(self, attr):
        if hasattr(self.inner, attr):
            return getattr(self.inner, attr)
        return getattr(self, attr)

    @property
    def day(self) -> str:
        "Return the date in the form YYYY-MM-DD instead of the full timestamp"
        return self.date.strftime("%Y-%m-%d")


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

        if root is None:
            msg = "Feed missing root tag"
            raise ValueError(msg)
        if root.tag == "rss":
            return cls._from_rss(root)
        elif root.tag.endswith("feed"):
            return cls._from_atom(root)
        else:
            msg = f"Unexpected root tag: {root.tag}"
            raise ValueError(msg)

    @classmethod
    def _from_rss(cls, root: Element[str]) -> Self:
        channels: list[Element[str]] = list(root.iter("channel"))
        assert len(channels) == 1, "Expected a single nested <channel>"

        channel = channels[0]

        def get(item: Element[str], field: str) -> str | None:
            return then(item.find(field), attrgetter("text"))

        items = []
        for item in channel.iter("item"):
            pub_date = get(item, "pubDate")

            # TODO(brent) I'm pretty sure ty is doing something wrong here
            # related to https://github.com/astral-sh/ty/issues/1872. If I
            # change T and U in `then` to `str` and `datetime`, it type checks,
            # so this seems to be an issue with generic callables.
            rfc_date: datetime | None = then(pub_date, parsedate_to_datetime)  # ty: ignore [invalid-assignment, invalid-argument-type]
            if rfc_date:
                iso_date = rfc_date.astimezone(UTC).isoformat()
            items.append(
                Item(
                    title=get(item, "title"),
                    link=get(item, "link"),
                    content=get(item, "description"),
                    author=get(item, "dc:creator"),
                    comments=get(item, "comments"),
                    _raw_date=iso_date,
                    _raw_guid=get(item, "guid"),
                )
            )

        return cls(
            title=get(channel, "title"),
            link=get(channel, "link"),
            description=get(channel, "description"),
            items=items,
        )

    @classmethod
    def _from_atom(cls, root: Element[str]) -> Self:
        def get(element: Element[str], field: str) -> Element[str] | None:
            for item in element:
                if item.tag.endswith(field):
                    return item

        def find(
            element: Element[str], target: str, attr: str | None = None
        ) -> str | None:
            item = get(element, target)
            if item is not None:
                if attr is None:
                    return item.text
                else:
                    return item.attrib[attr]

        def author(element: Element[str]):
            author = get(element, "author")
            if author is None:
                return None

            name = get(author, "name")
            if name is None:
                return None

            return name.text

        items = [
            Item(
                title=find(item, "title"),
                link=find(item, "link", "href"),
                content=find(item, "content"),
                author=author(item),
                comments=find(item, "comments"),
                _raw_date=find(item, "published") or find(item, "updated"),
                _raw_guid=find(item, "id"),
            )
            for item in root
            if item.tag.endswith("entry")
        ]

        return cls(
            title=find(root, "title"),
            link=find(root, "link", "href"),
            description=find(root, "content"),
            items=items,
        )


@dataclass
class Url:
    link: str
    color: Color | None = None


def load_urls(path) -> list[Url]:
    """
    Load a sequence of URLs from `path`, one per line.

    Lines starting with `#` are ignored.
    """

    urls = []
    for line in Path(path).read_text().splitlines():
        if line.startswith("#"):
            continue

        match line.strip().split():
            case [url]:
                urls.append(Url(url))
            case [url, color]:
                urls.append(Url(url, color))
            case line:
                msg = f"Unable to parse line: {line}"
                raise ValueError(msg)

    return urls


def initial_score(count: int) -> float:
    """
    A rudimentary scoring function.

    All this does for now is return an exponentially decaying value as the
    number of items from the same source increases.

    We want the score to be bounded in [0, 1], so e^{-x} has the right
    properties: for the zeroth element it gives 1 and decreases from there. I
    think it might decrease a bit more quickly than we really want, but that's
    fine for now since every feed gets the same treatment.

    In other words, it doesn't matter if the score for every second post falls
    from 1.0 to 0.4 (~e^{-2}) or from 1.0 to 0.9 because every second post will
    fall by the same amount.

    However, we also throw in a small random variation just for fun.
    """
    eps = 0.1 * random.random()
    return math.exp(-(count + eps))


def update_feeds(feeds: list[DbFeed]) -> list[tuple[FeedId, Score, Item]]:
    """
    Fetch a list of feeds, update their metadata in place, and return a
    list of items.
    """

    items = []
    for feed in feeds:
        headers = {"user-agent": f"newsyacht/{version('newsyacht')}"}
        if feed.etag:
            headers["etag"] = feed.etag
        if feed.last_modified:
            headers["last-modified"] = feed.last_modified

        # this is the default, but set it explicitly to reuse in the log
        # message.
        timeout = 5.0
        try:
            response = httpx.get(
                feed.url, follow_redirects=True, headers=headers, timeout=timeout
            )
        except httpx.TimeoutException:
            logger.error(
                "Retrieving %s timed out after %.1f sec",
                feed.url,
                timeout,
                exc_info=False,  # very noisy and doesn't add any useful info
            )
            continue

        items_per_feed = Counter()
        if response.status_code == httpx.codes.OK:
            etag = response.headers.get("etag")
            last_modified = response.headers.get("last-modified")
            try:
                body = Feed.from_xml(response.text)
            except ValueError:
                logging.exception("Failed to parse %s", feed.url)
                raise
            feed.update(etag=etag, last_modified=last_modified, feed=body)
            for item in body.items:
                items.append((feed.id, initial_score(items_per_feed[feed.id]), item))
                items_per_feed[feed.id] += 1
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


class Db:
    path: Path

    def __init__(self, path):
        self.path = path

    def __enter__(self) -> Self:
        self.conn = sqlite3.connect(self.path)
        self._setup_connection()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.conn.close()

    def _setup_connection(self):
        self.conn.row_factory = sqlite3.Row

        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS feeds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL UNIQUE,
                color TEXT,
                title TEXT,
                description TEXT,
                etag TEXT,
                last_modified TEXT
            )
            """
        )

        self.conn.execute(
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
                comments      TEXT,
                date          TEXT,
                guid          TEXT NOT NULL,
                UNIQUE(feed_id, guid)
            )
            """
        )

    def get_posts(self) -> list[DbItem]:
        cur = self.conn.execute(
            """
            SELECT
                items.id,
                items.feed_id,
                items.is_read,
                items.score,
                items.title,
                items.content,
                items.link,
                items.author,
                items.comments,
                items.date,
                items.guid,
                feeds.color
            FROM items
            JOIN feeds
            ON feeds.id = items.feed_id
            """
        )

        posts = [DbItem.from_row(row) for row in cur.fetchall()]

        return posts

    def get_posts_by_id(self, feed_id: FeedId) -> list[DbItem]:
        cur = self.conn.execute(
            """
            SELECT
                items.id,
                items.feed_id,
                items.is_read,
                items.score,
                items.title,
                items.content,
                items.link,
                items.author,
                items.comments,
                items.date,
                items.guid,
                feeds.color
            FROM items
            JOIN feeds
            ON feeds.id = items.feed_id
            WHERE items.feed_id = ?
            """,
            (feed_id,),
        )

        posts = [DbItem.from_row(row) for row in cur.fetchall()]

        return posts

    def insert_urls(self, urls: list[Url]):
        with self.conn:
            self.conn.executemany(
                """
                INSERT INTO feeds (url, color)
                VALUES (?, ?)
                ON CONFLICT(url) DO UPDATE SET
                    color = excluded.color
                """,
                [(url.link, url.color) for url in urls],
            )

    def get_feeds(self, urls: list[str]):
        placeholders = ",".join("?" for _ in urls)
        cur = self.conn.execute(
            f"""
            SELECT id, url, title, description, etag, last_modified
            FROM feeds
            WHERE url IN ({placeholders})
            ORDER BY url;
            """,
            urls,
        )
        return [DbFeed(**row) for row in cur.fetchall()]

    def update_feeds(self, feeds):
        with self.conn:
            self.conn.executemany(
                """
                UPDATE feeds
                SET etag = ?, last_modified = ?, title = ?, description = ?
                WHERE id = ?
                """,
                [
                    (
                        feed.etag,
                        feed.last_modified,
                        feed.title,
                        feed.description,
                        feed.id,
                    )
                    for feed in feeds
                ],
            )

    def insert_items(self, items: list[tuple[FeedId, Score, Item]]):
        with self.conn:
            self.conn.executemany(
                """
                INSERT INTO items (feed_id, guid, title, content, link, author, date, comments, score)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(feed_id, guid) DO UPDATE SET
                    title = excluded.title,
                    content = excluded.content,
                    link = excluded.link,
                    author = excluded.author,
                    date = excluded.date,
                    comments = excluded.comments,
                    score = excluded.score
                """,
                [
                    (
                        feed_id,
                        item.guid,
                        item.title,
                        item.content,
                        item.link,
                        item.author,
                        item.date_str(),
                        item.comments,
                        score,
                    )
                    for feed_id, score, item in items
                ],
            )

    def get_feed_title(self, feed_id):
        cur = self.conn.execute(
            """
            SELECT title from feeds
            WHERE id = ?
            """,
            (feed_id,),
        )
        return cur.fetchone()["title"]

    def set_read(self, item_id):
        with self.conn:
            self.conn.execute(
                "UPDATE items SET is_read = 1 WHERE id = ?",
                (item_id,),
            )

    def get_link(self, item_id):
        return self.conn.execute(
            "SELECT link FROM items WHERE id = ?",
            (item_id,),
        ).fetchone()[0]


@dataclass
class App:
    config_dir: Path

    def load_urls(self) -> list[Url]:
        return load_urls(self.config_dir / "urls")

    def update(self, _args):
        with Db(self.config_dir / "cache.db") as db:
            urls = self.load_urls()
            db.insert_urls(urls)

            feeds = db.get_feeds([url.link for url in urls])

            items = update_feeds(feeds)

            db.update_feeds(feeds)

            db.insert_items(items)

    def list_(self, _args):
        with Db(self.config_dir / "cache.db") as db:
            posts = db.get_posts()

            grouped_posts = defaultdict(list)
            for post in posts:
                grouped_posts[post.feed_id].append(post.inner.title)

            for feed_id, posts in grouped_posts.items():
                feed_name = db.get_feed_title(feed_id)
                print(feed_name)
                for post in posts:
                    print(f"\t{post}")

    def serve(self, _args):
        from newsyacht.web import App

        app = App(self.config_dir / "cache.db")
        app.run("0.0.0.0", use_reloader=False)


def main() -> None:
    home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    config_dir = home / "newsyacht"

    app = App(config_dir)

    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(required=True)

    update = subparsers.add_parser(
        "update", description="Update the newsyacht database"
    )
    update.set_defaults(func=app.update)

    list_ = subparsers.add_parser("list", description="List available posts")
    list_.set_defaults(func=app.list_)

    serve = subparsers.add_parser("serve", description="Serve the web interface")
    serve.set_defaults(func=app.serve)

    args = parser.parse_args()
    args.func(args)
