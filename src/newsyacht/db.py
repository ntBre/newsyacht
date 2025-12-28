import sqlite3
from pathlib import Path
from typing import Self

from newsyacht.config import Url
from newsyacht.models import DbFeed, DbItem, FeedId, Item, Score


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

        with self.conn:
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
                    thumbnail     TEXT,
                    date          TEXT,
                    guid          TEXT NOT NULL,
                    UNIQUE(feed_id, guid)
                )
                """
            )

            # Initialize the scoring model with zeros if it doesn't exist
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS model (
                    id                  INTEGER PRIMARY KEY CHECK (id = 1),
                    up_docs             INTEGER NOT NULL,
                    down_docs           INTEGER NOT NULL,
                    up_total_tokens     INTEGER NOT NULL,
                    down_total_tokens   INTEGER NOT NULL
                )
                """
            )

            self.conn.execute(
                """
                INSERT OR IGNORE INTO model (
                id, up_docs, down_docs, up_total_tokens, down_total_tokens
                )
                VALUES (1, 0, 0, 0, 0)
                """
            )

            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS model_tokens (
                    text                TEXT PRIMARY KEY,
                    up                  INTEGER NOT NULL,
                    down                INTEGER NOT NULL
                )
                """
            )

    def get_posts(
        self, days: int | None = None, read: bool | None = None
    ) -> list[DbItem]:
        """
        Get posts from the database, optionally filtered by `days` and `read`.

        `days` controls the number of previous days to consider, while `read`
        determines whether posts that have already been marked read are
        included. When both of these are `None`, all posts are included.

        TODO(brent) `read` should probably be an enum with three variants:
        - `True` means return only read posts
        - `False` means return only unread posts
        - `None` means return both read and unread posts
        """
        date_filter = (
            f"datetime(items.date) >= datetime('now', '-{days} day')"
            if days is not None
            else ""
        )

        match read:
            case None:
                read_filter = ""
            case True:
                read_filter = "items.is_read = 1"
            case False:
                read_filter = "items.is_read = 0"

        link_filter = "items.link IS NOT NULL"

        return self._get_posts(link_filter, date_filter, read_filter)

    def get_posts_by_id(self, feed_id: FeedId) -> list[DbItem]:
        return self._get_posts("items.feed_id = ?", params=(feed_id,))

    def _get_posts(self, *filters, params=()):
        filters = [f for f in filters if f]
        filter_clause = f"WHERE {' AND '.join(filters)}" if filters else ""

        cur = self.conn.execute(
            f"""
            SELECT
                items.id,
                items.feed_id,
                items.is_read,
                items.score,
                items.title,
                items.content,
                items.link,
                items.thumbnail,
                COALESCE(items.author, feeds.title) AS author,
                items.comments,
                items.date,
                items.guid,
                feeds.color
            FROM items
            JOIN feeds
            ON feeds.id = items.feed_id
            {filter_clause}
            ORDER BY substr(items.date, 1, 10) DESC, items.score DESC
            """,
            params,
        )

        return [DbItem.from_row(row) for row in cur.fetchall()]

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
                INSERT INTO items (
                    feed_id,
                    guid,
                    title,
                    content,
                    link,
                    author,
                    date,
                    comments,
                    thumbnail,
                    score
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(feed_id, guid) DO UPDATE SET
                    title = excluded.title,
                    content = excluded.content,
                    link = excluded.link,
                    author = excluded.author,
                    date = excluded.date,
                    comments = excluded.comments,
                    thumbnail = excluded.thumbnail,
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
                        item.thumbnail,
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
