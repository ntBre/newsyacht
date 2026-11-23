import logging
import re
from pathlib import Path

from flask import Flask, abort, redirect, render_template, request, url_for

from newsyacht import models
from newsyacht.db import Db
from newsyacht.scoring import Model

logger = logging.getLogger(__name__)
logging.basicConfig()

HEX_COLOR = re.compile(r"#([a-zA-Z0-9]{6})")
PAGE_SIZE = 50


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

    def __init__(self, db_path: Path):
        self.db = db_path
        self.app = Flask(__name__)

        self.app.jinja_env.filters["label_text_color"] = label_text_color

        def updated_post(db: Db, item_id: int):
            if request.headers.get("X-Newsyacht-Fragment") == "post":
                return render_template("post_fragment.html", post=db.get_item(item_id))
            return redirect(request.referrer or url_for("index"))

        @self.app.route("/")
        def index():
            unread_only = request.args.get("unread") == "1"
            before = request.args.get("before", type=int)
            if "before" in request.args and (before is None or not 0 < before < 2**63):
                abort(400)

            with Db(self.db) as db:
                posts = db.get_posts(
                    read=False if unread_only else None,
                    limit=PAGE_SIZE + 1,
                    before=before,
                )
            has_more = len(posts) > PAGE_SIZE
            posts = posts[:PAGE_SIZE]
            more_url = (
                url_for("index", before=posts[-1].id, unread=1 if unread_only else None)
                if has_more
                else None
            )

            fragment = request.headers.get("X-Newsyacht-Fragment") == "posts"
            template = "posts_fragment.html" if fragment else "index.html"
            response = self.app.make_response(
                render_template(
                    template, posts=posts, unread_only=unread_only, more_url=more_url
                )
            )
            response.vary.add("X-Newsyacht-Fragment")
            if fragment and more_url:
                response.headers["X-Newsyacht-Next"] = more_url
            return response

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
                posts = db.get_posts_by_id(models.FeedId(feed_id))
            return render_template("feed.html", posts=posts, feed_title=feed_title)

        @self.app.route("/read/<int:item_id>")
        def read(item_id):
            with Db(self.db) as db:
                if request.args.get("mark") != "0":
                    db.set_read(item_id)
                link = db.get_link(item_id)
            return redirect(link)

        @self.app.route("/mark-read/<int:item_id>", methods=["POST"])
        def mark_read(item_id):
            with Db(self.db) as db:
                db.set_read(item_id)
                return updated_post(db, item_id)

        @self.app.route("/mark-unread/<int:item_id>", methods=["POST"])
        def mark_unread(item_id):
            with Db(self.db) as db:
                db.set_read(item_id, False)
                return updated_post(db, item_id)

        @self.app.route("/upvote/<int:item_id>", methods=["POST"])
        def upvote(item_id):
            with Db(self.db) as db:
                Model.change_vote(db, item_id, models.Vote.UP)
                return updated_post(db, item_id)

        @self.app.route("/downvote/<int:item_id>", methods=["POST"])
        def downvote(item_id):
            with Db(self.db) as db:
                Model.change_vote(db, item_id, models.Vote.DOWN)
                return updated_post(db, item_id)

    def run(self, *args, **kwargs):
        self.app.run(*args, **kwargs)
