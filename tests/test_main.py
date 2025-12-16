from pathlib import Path
from tempfile import TemporaryDirectory
from xml.etree import ElementTree

import pytest
from newsyacht import Color, Db, Feed, FeedId, Item, Url, load_urls
from newsyacht.web import App


@pytest.fixture
def hn_post() -> list[tuple[FeedId, Item]]:
    tree = ElementTree.parse("tests/fixtures/hn.xml")
    feed = Feed._from_xml(tree)
    return [(FeedId(1), feed.items[0])]


@pytest.fixture
def hn_url() -> list[Url]:
    return [Url(link="https://news.ycombinator.com/rss", color=Color("#ff6600"))]


@pytest.mark.parametrize("path", ["arch.xml", "atom.xml", "releases.xml", "hn.xml"])
def test_feed_from_xml(path, snapshot):
    base = Path("tests/fixtures")
    tree = ElementTree.parse(base / path)
    assert Feed._from_xml(tree) == snapshot


def test_load_urls(snapshot):
    assert load_urls("tests/fixtures/urls") == snapshot


def test_insert_comments(snapshot, hn_url, hn_post):
    with TemporaryDirectory() as d, Db(Path(d) / "test.db") as db:
        db.insert_urls(hn_url)
        db.insert_items(hn_post)
        posts = db.get_posts()

    assert len(posts) == 1
    assert posts[0].comments == snapshot


def test_index(snapshot, hn_url, hn_post):
    with TemporaryDirectory() as d:
        path = Path(d) / "test.db"
        with Db(path) as db:
            db.insert_urls(hn_url)
            db.insert_items(hn_post)

        app = App(path)
        client = app.app.test_client()
        response = client.get("/")

        assert snapshot == response.text
