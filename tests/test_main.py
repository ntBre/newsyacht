from xml.etree import ElementTree

from newsyacht import Feed, main


def test_feed_from_xml(snapshot):
    tree = ElementTree.parse("tests/fixtures/arch.xml")
    assert Feed.from_xml(tree) == snapshot


def test_main():
    main()
