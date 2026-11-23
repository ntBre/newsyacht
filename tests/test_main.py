import datetime
import re
from collections import Counter
from copy import deepcopy
from pathlib import Path
from xml.etree import ElementTree

import pytest

from newsyacht.cli import initial_score
from newsyacht.config import Color, Config, load_urls
from newsyacht.config import Feed as ConfigFeed
from newsyacht.db import Db
from newsyacht.models import Feed, FeedId, Item, Score, Vote
from newsyacht.scoring import Model, Token, tokenize
from newsyacht.web import App


@pytest.fixture
def hn_post() -> list[tuple[FeedId, Score, Item]]:
    tree = ElementTree.parse("tests/fixtures/hn.xml")
    feed = Feed._from_xml(tree)
    return [(FeedId(1), Score(0.9), feed.items[0])]


@pytest.fixture
def hn_feed() -> list[ConfigFeed]:
    return [ConfigFeed(link="https://news.ycombinator.com/rss", color=Color("#ff6600"))]


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "test.db"


@pytest.fixture
def db(db_path):
    with Db(db_path) as db:
        yield db


@pytest.fixture
def seeded_db(db, hn_feed, hn_post):
    db.insert_feeds(hn_feed)
    db.insert_items(hn_post)
    return db


@pytest.fixture
def arch_db(db):
    "Return a database seeded with all of the entries from the `arch.xml` fixture"

    db.insert_feeds([ConfigFeed(link="https://www.archlinux.org/feeds/news")])
    tree = ElementTree.parse("tests/fixtures/arch.xml")
    feed = Feed._from_xml(tree)
    db.insert_items([(FeedId(1), Score(1.0), item) for item in feed.items])
    return db


@pytest.fixture
def app(db_path):
    return App(db_path)


@pytest.fixture
def client(app):
    return app.app.test_client()


@pytest.mark.parametrize(
    "path",
    [
        "arch.xml",
        "atom.xml",
        "releases.xml",
        "hn.xml",
        "nodate.xml",
        "reddit.xml",
        "isodate.xml",
    ],
)
def test_feed_from_xml(path, snapshot):
    base = Path("tests/fixtures")
    tree = ElementTree.parse(base / path)
    assert Feed._from_xml(tree) == snapshot


def test_atom_article_link():
    api_url = "https://www.blogger.com/feeds/8520/posts/default/4555227175724144174"
    article_url = (
        "https://pyfound.blogspot.com/2026/11/"
        "python-is-for-everyone-join-in-psf-year.html"
    )
    feed = Feed.from_xml(
        f"""
        <feed xmlns="http://www.w3.org/2005/Atom">
            <link rel="self" href="https://www.blogger.com/feeds/8520/posts/default"/>
            <link rel="alternate" href="https://pyfound.blogspot.com/"/>
            <entry>
                <id>tag:blogger.com,1999:blog-8520.post-4555227175724144174</id>
                <link rel="edit" type="application/atom+xml" href="{api_url}"/>
                <link rel="self" type="application/atom+xml" href="{api_url}"/>
                <link rel="alternate" type="text/html" href="{article_url}"/>
            </entry>
        </feed>
        """
    )
    assert feed.link == "https://pyfound.blogspot.com/"
    assert feed.items[0].link == article_url


def test_load_urls(snapshot):
    assert load_urls("tests/fixtures/urls") == snapshot


def test_load_config(snapshot):
    assert Config.from_path("tests/fixtures/config.toml") == snapshot


def test_feed_config(seeded_db):
    config = Config.from_path("tests/fixtures/config.toml")
    seeded_db.insert_feeds(config.feeds)

    post = seeded_db.get_posts()[0]
    assert (post.author, post.color) == ("hackernews", "#ff6600")


def test_insert_comments(snapshot, seeded_db):
    posts = seeded_db.get_posts()

    assert len(posts) == 1
    assert posts[0].comments == snapshot


def test_ranked_index(snapshot, db, hn_feed, hn_post, client):
    db.insert_feeds(hn_feed)
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
    db.insert_feeds([ConfigFeed(link=url)])
    feed_id = db.get_feeds([url])[0].id
    tree = ElementTree.parse("tests/fixtures/nodate.xml")
    feed = Feed._from_xml(tree)
    db.insert_items([(FeedId(feed_id), Score(0.9), feed.items[0])])
    response = client.get("/?all=1")
    assert snapshot == response.text


def test_default_post_sorting(snapshot, db, hn_feed, hn_post, client):
    """The first page includes older posts when space remains."""
    db.insert_feeds(hn_feed)
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


def test_tokenize_hn(snapshot, seeded_db: Db):
    posts = []
    for post in seeded_db.get_posts():
        text = post.title + post.content
        posts.append(list(tokenize(text)))

    assert snapshot == posts


def test_tokenize_arch(snapshot, arch_db: Db):
    posts = []
    for post in arch_db.get_posts():
        text = post.title + post.content
        posts.append(list(tokenize(text)))

    assert snapshot == posts


def test_default_model(snapshot, db):
    model = Model.from_db(db)
    assert snapshot == model


def test_initial_score(snapshot, db, hn_post):
    "Test the decaying scores from an untrained model"

    model = Model.from_db(db)
    _feed_id, _score, item = next(iter(hn_post))
    scores = [f"{initial_score(model, item, i):.2f}" for i in range(5)]

    assert snapshot == scores


@pytest.mark.parametrize("vote", [Vote.UP, Vote.DOWN])
def test_reversible_votes(seeded_db, client, vote):
    post = seeded_db.get_posts()[0]
    counts = Counter(tokenize(post.text()))
    total = sum(counts.values())
    opposite = Vote.DOWN if vote == Vote.UP else Vote.UP

    for action, expected in [
        (vote, vote),
        (vote, Vote.NONE),
        (vote, vote),
        (opposite, opposite),
        (opposite, Vote.NONE),
    ]:
        endpoint = "upvote" if action == Vote.UP else "downvote"
        assert client.post(f"/{endpoint}/{post.id}").status_code == 302
        assert seeded_db.get_item(post.id).vote == expected

        model = Model.from_db(seeded_db)
        up, down = int(expected == Vote.UP), int(expected == Vote.DOWN)
        assert (model.up_docs, model.down_docs) == (up, down)
        assert (model.up_total_tokens, model.down_total_tokens) == (
            total * up,
            total * down,
        )
        assert model.tokens == {
            text: Token(up=count * up, down=count * down)
            for text, count in counts.items()
            if expected != Vote.NONE
        }


def test_read_posts_stay_visible(seeded_db, client):
    post = seeded_db.get_posts()[0]
    seeded_db.set_read(post.id)

    response = client.get("/?all=1")
    assert post.title in response.text
    assert 'class="post is-read"' in response.text

    unread = client.get("/?all=1&unread=1")
    assert post.title not in unread.text


def test_read_state_can_be_reversed(seeded_db, client):
    post = seeded_db.get_posts()[0]
    assert client.post(f"/mark-read/{post.id}").status_code == 302
    assert seeded_db.get_item(post.id).is_read

    assert client.post(f"/mark-unread/{post.id}").status_code == 302
    assert not seeded_db.get_item(post.id).is_read


def test_feed_includes_read_posts(seeded_db, client):
    post = seeded_db.get_posts()[0]
    seeded_db.set_read(post.id)
    assert post.title in client.get(f"/feed/{post.feed_id}").text


def test_async_read_response(seeded_db, client):
    post = seeded_db.get_posts()[0]
    response = client.post(
        f"/mark-read/{post.id}",
        headers={"X-Newsyacht-Fragment": "post"},
    )
    assert response.status_code == 200
    assert 'class="post is-read"' in response.text
    assert "Mark unread" in response.text

    response = client.post(
        f"/mark-unread/{post.id}",
        headers={"X-Newsyacht-Fragment": "post"},
    )
    assert response.status_code == 200
    assert "Mark read" in response.text
    assert 'class="post is-read"' not in response.text


def test_async_vote_response(seeded_db, client):
    post = seeded_db.get_posts()[0]
    response = client.post(
        f"/upvote/{post.id}",
        headers={"X-Newsyacht-Fragment": "post"},
    )
    assert response.status_code == 200
    assert "vote-up is-active" in response.text
    assert seeded_db.get_item(post.id).vote == Vote.UP

    reversed_vote = client.post(
        f"/upvote/{post.id}", headers={"X-Newsyacht-Fragment": "post"}
    )
    assert reversed_vote.status_code == 200
    assert "vote-up is-active" not in reversed_vote.text
    assert seeded_db.get_item(post.id).vote == Vote.NONE


def test_article_redirect_can_leave_read_state_unchanged(seeded_db, client):
    post = seeded_db.get_posts()[0]
    path = f"/read/{post.id}"

    response = client.get(path)
    assert response.location == post.inner.link
    assert seeded_db.get_item(post.id).is_read

    seeded_db.set_read(post.id, False)
    response = client.get(f"{path}?mark=0")
    assert response.location == post.inner.link
    assert not seeded_db.get_item(post.id).is_read


def test_paginated_posts(db, hn_feed, hn_post, client, monkeypatch):
    monkeypatch.setattr("newsyacht.web.app.PAGE_SIZE", 1)
    db.insert_feeds(hn_feed)
    feed_id, _score, item = hn_post[0]
    newer = deepcopy(item)
    newer.title = "A newer article"
    newer.guid = newer.title
    db.insert_items([*hn_post, (feed_id, Score(1.0), newer)])

    first = client.get("/?unread=1")
    assert "A newer article" in first.text
    assert item.title not in first.text
    assert "Show more" in first.text
    cursor_id = db.get_posts()[0].id

    # The keyset cursor still works after marking its article read.
    db.set_read(cursor_id)
    second = client.get(
        f"/?before={cursor_id}&unread=1",
        headers={"X-Newsyacht-Fragment": "posts"},
    )
    assert second.status_code == 200
    assert "<html" not in second.text
    assert "X-Newsyacht-Fragment" in second.vary
    assert item.title in client.get(f"/?before={cursor_id}&unread=1").text
    assert item.title in second.text
    assert "A newer article" not in second.text
    assert second.headers.get("X-Newsyacht-Next") is None


@pytest.mark.parametrize("before", ["bogus", "0", "9223372036854775808"])
def test_invalid_page_cursor(client, before):
    assert client.get(f"/?before={before}").status_code == 400
