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

        return [DbItem.from_row(row) for row in cur.fetchall()]

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
