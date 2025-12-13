from flask import Flask, render_template
from newsyacht import DbItem


class App:
    app: Flask
    posts: list[DbItem]

    def __init__(self, posts: list[DbItem]):
        self.posts = posts
        self.app = Flask(__name__)

        @self.app.route("/")
        def index():
            return render_template("index.html", posts=posts)

    def run(self, *args, **kwargs):
        self.app.run(*args, **kwargs)
