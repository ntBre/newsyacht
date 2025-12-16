from pathlib import Path
from tempfile import TemporaryDirectory
from xml.etree import ElementTree

import pytest
from newsyacht import Db, DbItem, Feed, FeedId, load_urls


@pytest.mark.parametrize("path", ["arch.xml", "atom.xml", "releases.xml", "hn.xml"])
def test_feed_from_xml(path, snapshot):
    base = Path("tests/fixtures")
    tree = ElementTree.parse(base / path)
    assert Feed._from_xml(tree) == snapshot


def test_load_urls(snapshot):
    assert load_urls("tests/fixtures/urls") == snapshot


def test_insert_comments(snapshot):
    tree = ElementTree.parse("tests/fixtures/hn.xml")
    feed = Feed._from_xml(tree)
    items = [
        (
            0,
            DbItem(
                id=0,
                feed_id=FeedId(0),
                is_read=False,
                score=0.0,
                inner=feed.items[0],
            ),
        )
    ]
    with TemporaryDirectory() as d, Db(Path(d) / "test.db") as db:
        db.insert_items(items)
        posts = db.get_posts()

    assert len(posts) == 1
    assert posts[0].comments == snapshot
