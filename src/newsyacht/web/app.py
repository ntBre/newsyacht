from operator import attrgetter
from pathlib import Path

from flask import Flask, redirect, render_template
from newsyacht import Db, DbItem


class App:
    app: Flask
    db: Path

    def __init__(self, db: Path):
        self.db = db
        self.app = Flask(__name__)

        @self.app.route("/")
        def index():
            with Db(self.db) as db:
                posts: list[DbItem] = sorted(
                    (post for post in db.get_posts() if post.link is not None),
                    key=attrgetter("date"),
                    reverse=True,
                )
                for post in posts:
                    if post.inner.author is None:
                        post.inner.author = db.get_feed_title(post.feed_id)
            unread_posts = [post for post in posts if not post.is_read]
            read_posts = [post for post in posts if post.is_read]
            return render_template(
                "index.html", unread_posts=unread_posts, read_posts=read_posts
            )

        @self.app.route("/read/<int:item_id>")
        def read(item_id):
            with Db(self.db) as db:
                db.set_read(item_id)
                link = db.get_link(item_id)
            return redirect(link)

        @self.app.route("/mark-read/<int:item_id>")
        def mark_read(item_id):
            "Like `App.read` but redirect to home without visiting the link"

            with Db(self.db) as db:
                db.set_read(item_id)

            return redirect("/")

    def run(self, *args, **kwargs):
        self.app.run(*args, **kwargs)
