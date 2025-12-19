from copy import deepcopy
from pathlib import Path
from xml.etree import ElementTree

import pytest
from newsyacht import Color, Db, Feed, FeedId, Item, Score, Url, load_urls
from newsyacht.web import App


@pytest.fixture
def hn_post() -> list[tuple[FeedId, Score, Item]]:
    tree = ElementTree.parse("tests/fixtures/hn.xml")
    feed = Feed._from_xml(tree)
    return [(FeedId(1), Score(0.9), feed.items[0])]


@pytest.fixture
def hn_url() -> list[Url]:
    return [Url(link="https://news.ycombinator.com/rss", color=Color("#ff6600"))]


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "test.db"


@pytest.fixture
def db(db_path):
    with Db(db_path) as db:
        yield db


@pytest.fixture
def app(db_path):
    return App(db_path)


@pytest.fixture
def client(app):
    return app.app.test_client()


@pytest.mark.parametrize("path", ["arch.xml", "atom.xml", "releases.xml", "hn.xml"])
def test_feed_from_xml(path, snapshot):
    base = Path("tests/fixtures")
    tree = ElementTree.parse(base / path)
    assert Feed._from_xml(tree) == snapshot


def test_load_urls(snapshot):
    assert load_urls("tests/fixtures/urls") == snapshot


def test_insert_comments(snapshot, db, hn_url, hn_post):
    db.insert_urls(hn_url)
    db.insert_items(hn_post)
    posts = db.get_posts()

    assert len(posts) == 1
    assert posts[0].comments == snapshot


def test_index(snapshot, db, hn_url, hn_post, client):
    db.insert_urls(hn_url)
    db.insert_items(hn_post)
    response = client.get("/")
    assert snapshot == response.text


def test_ranked_index(snapshot, db, hn_url, hn_post, client):
    db.insert_urls(hn_url)
    # append a second post with a higher score and test that it sorts
    # first
    feed_id, score, item = hn_post[0]
    new_item = deepcopy(item)
    new_item.title = "Higher scoring post"
    new_item.guid = new_item.title
    hn_post.append((feed_id, Score(1.0), new_item))
    db.insert_items(hn_post)

    response = client.get("/")

    assert snapshot == response.text


def test_feed(snapshot, db, hn_url, hn_post, client):
    db.insert_urls(hn_url)
    db.insert_items(hn_post)
    response = client.get("/feed/1")
    assert snapshot == response.text
