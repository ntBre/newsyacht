import argparse
import os
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from newsyacht import Db, update_feeds
from newsyacht.config import Url, load_urls


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
