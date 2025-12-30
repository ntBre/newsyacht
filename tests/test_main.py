import datetime
import re
from copy import deepcopy
from pathlib import Path
from xml.etree import ElementTree

import pytest

from newsyacht.config import Color, Url, load_urls
from newsyacht.db import Db
from newsyacht.models import Feed, FeedId, Item, Score
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
def seeded_db(db, hn_url, hn_post):
    db.insert_urls(hn_url)
    db.insert_items(hn_post)
    return db


@pytest.fixture
def app(db_path):
    return App(db_path)


@pytest.fixture
def client(app):
    return app.app.test_client()


@pytest.mark.parametrize(
    "path",
    ["arch.xml", "atom.xml", "releases.xml", "hn.xml", "nodate.xml", "reddit.xml"],
)
def test_feed_from_xml(path, snapshot):
    base = Path("tests/fixtures")
    tree = ElementTree.parse(base / path)
    assert Feed._from_xml(tree) == snapshot


def test_load_urls(snapshot):
    assert load_urls("tests/fixtures/urls") == snapshot


def test_insert_comments(snapshot, seeded_db):
    posts = seeded_db.get_posts()

    assert len(posts) == 1
    assert posts[0].comments == snapshot


def test_ranked_index(snapshot, db, hn_url, hn_post, client):
    db.insert_urls(hn_url)
    # append a second post with a higher score and test that it sorts
    # first
    feed_id, _score, item = hn_post[0]
    new_item = deepcopy(item)
    new_item.title = "Higher scoring post"
    new_item.guid = new_item.title
    posts = [*hn_post, (feed_id, Score(1.0), new_item)]
    db.insert_items(posts)

    response = client.get("/?all=1")

    assert snapshot == response.text


@pytest.mark.parametrize("endpoint", ["/?all=1", "/feed/1", "/archive"])
def test_endpoint(snapshot, seeded_db, client, endpoint):
    response = client.get(endpoint)
    assert snapshot == response.text


def test_index_missing_date(snapshot, db, client):
    url = "https://example.com/nodate.xml"
    db.insert_urls([Url(link=url)])
    feed_id = db.get_feeds([url])[0].id
    tree = ElementTree.parse("tests/fixtures/nodate.xml")
    feed = Feed._from_xml(tree)
    db.insert_items([(FeedId(feed_id), Score(0.9), feed.items[0])])
    response = client.get("/?all=1")
    assert snapshot == response.text


def test_default_post_sorting(snapshot, db, hn_url, hn_post, client):
    """
    The other `/` tests pass `?all=1` to avoid filtering out old posts.
    Here, we insert a new post with a generated date and test that it's shown
    while the others are filtered out.
    """
    db.insert_urls(hn_url)
    feed_id, score, item = hn_post[0]
    new_item = deepcopy(item)
    new_item.title = "Higher scoring post"
    new_item.guid = new_item.title
    new_item.date = datetime.datetime.now(datetime.UTC).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    posts = [*hn_post, (feed_id, score, new_item)]
    db.insert_items(posts)

    assert len(db.get_posts()) == 2

    response = client.get("/")

    response = re.sub(r"\d{4}-\d{2}-\d{2}", "<DATE>", response.text)
    assert snapshot == response


def test_thumbnail(snapshot, seeded_db: Db, client):
    tree = ElementTree.parse("tests/fixtures/reddit.xml")
    feed = Feed._from_xml(tree)
    seeded_db.insert_items([(FeedId(1), Score(1.0), feed.items[0])])

    response = client.get("/?all=1")
    assert snapshot == response.text
