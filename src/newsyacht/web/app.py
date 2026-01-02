import logging
import re
from pathlib import Path

from flask import Flask, redirect, render_template, request, url_for

from newsyacht.db import Db
from newsyacht.models import FeedId

logger = logging.getLogger(__name__)
logging.basicConfig()

HEX_COLOR = re.compile(r"#([a-zA-Z0-9]{6})")


def label_text_color(color: str) -> str:
    """
    Return '#fff' or '#111' depending on the background color brightness.
    """

    if not (m := HEX_COLOR.fullmatch(color)):
        logger.warning("Failed to parse %s as a hex color, falling back to #fff", color)
        return "#fff"

    digits = m[1]

    r = int(digits[0:2], 16)
    g = int(digits[2:4], 16)
    b = int(digits[4:6], 16)

    # WCAG-ish relative luminance (sRGB -> linear -> luminance)
    def lin(c: int) -> float:
        x = c / 255.0
        return x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4

    luminance = 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)

    # Tune threshold to taste. ~0.45-0.55 is a common range.
    return "#111" if luminance > 0.5 else "#fff"


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
                posts = (
                    db.get_posts()
                    if request.args.get("all")
                    else db.get_posts(days=3, read=False)
                )
            return render_template("index.html", posts=posts)

        @self.app.route("/archive")
        def archive():
            """
            Return all previously read posts

            I probably would have called this `/read` if that weren't already
            taken.
            """
            with Db(self.db) as db:
                posts = db.get_posts(read=True)
            return render_template("archive.html", posts=posts)

        @self.app.route("/feed/<int:feed_id>")
        def feed(feed_id):
            with Db(self.db) as db:
                feed_title = db.get_feed_title(feed_id)
                posts = db.get_posts_by_id(FeedId(feed_id))
            posts = [post for post in posts if not post.is_read]
            return render_template("feed.html", posts=posts, feed_title=feed_title)

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

            return redirect(request.referrer or url_for("index"))

    def run(self, *args, **kwargs):
        self.app.run(*args, **kwargs)
