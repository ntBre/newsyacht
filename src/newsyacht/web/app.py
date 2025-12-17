from operator import attrgetter
from pathlib import Path

from flask import Flask, redirect, render_template
from newsyacht import Db, DbItem


def label_text_color(bg_hex: str) -> str:
    """
    Return '#fff' or '#111' depending on the background color brightness.
    Accepts '#RRGGBB' or 'RRGGBB'.
    """
    h = bg_hex.lstrip("#")
    if len(h) != 6:
        return "#fff"  # safe fallback

    r = int(h[0:2], 16)
    g = int(h[2:4], 16)
    b = int(h[4:6], 16)

    # WCAG-ish relative luminance (sRGB -> linear -> luminance)
    def lin(c: int) -> float:
        x = c / 255.0
        return x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4

    L = 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)

    # Tune threshold to taste. ~0.45–0.55 is a common range.
    return "#111" if L > 0.5 else "#fff"


class App:
    app: Flask
    db: Path

    def __init__(self, db: Path):
        self.db = db
        self.app = Flask(__name__)

        self.app.jinja_env.filters["label_text_color"] = label_text_color

        @self.app.route("/")
        def index():
            with Db(self.db) as db:
                posts: list[DbItem] = sorted(
                    (post for post in db.get_posts() if post.link is not None),
                    key=attrgetter("day", "score"),
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
