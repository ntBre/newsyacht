from pathlib import Path
from xml.etree import ElementTree

import pytest
from newsyacht import Feed, load_urls


@pytest.mark.parametrize("path", ["arch.xml", "atom.xml", "releases.xml"])
def test_feed_from_xml(path, snapshot):
    base = Path("tests/fixtures")
    tree = ElementTree.parse(base / path)
    assert Feed._from_xml(tree) == snapshot


def test_load_urls(snapshot):
    assert load_urls("tests/fixtures/urls") == snapshot
