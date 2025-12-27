import argparse
import logging
import math
import os
import random
from collections import Counter, defaultdict
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path

import httpx

from newsyacht.config import Url, load_urls
from newsyacht.db import Db
from newsyacht.models import DbFeed, Feed, FeedId, Item, Score

logger = logging.getLogger(__name__)


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
            headers["if-none-match"] = feed.etag
        if feed.last_modified:
            headers["if-modified-since"] = feed.last_modified

        # this is the default, but set it explicitly to reuse in the log
        # message.
        timeout = 5.0
        try:
            response = httpx.get(
                feed.url, follow_redirects=True, headers=headers, timeout=timeout
            )
        except httpx.TimeoutException:
            logger.error(  # noqa: TRY400 exception is very noisy
                "Retrieving %s timed out after %.1f sec",
                feed.url,
                timeout,
                exc_info=False,
            )
            continue

        if response.status_code == httpx.codes.NOT_MODIFIED:
            logger.info("feed `%s` was up to date", feed.url)
            continue

        items_per_feed = Counter()
        if response.status_code == httpx.codes.OK:
            etag = response.headers.get("etag")
            last_modified = response.headers.get("last-modified")
            try:
                body = Feed.from_xml(response.text)
            except ValueError:
                logger.exception("Failed to parse %s", feed.url)
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


def main() -> None:
    logging.basicConfig()

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
