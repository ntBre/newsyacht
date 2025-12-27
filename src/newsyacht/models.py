import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from hashlib import sha256
from operator import attrgetter
from typing import NewType, Self
from xml.etree import ElementTree
from xml.etree.ElementTree import Element

from newsyacht.config import Color
from newsyacht.utils import then

FeedId = NewType("FeedId", int)
Score = NewType("Score", float)


@dataclass
class Item:
    """
    A entry in an RSS `Feed`.

    This is the deserialized representation from the XML document without any
    of the internal data tracked in the database.
    """

    title: str | None
    content: str | None
    link: str | None
    author: str | None
    comments: str | None
    "An optional link to a comments page"

    date: datetime | None = field(init=False)

    _raw_date: str | None = field(repr=False)

    _raw_guid: str | None = field(repr=False)
    "Input representation of the GUID, which could be missing."

    guid: str = field(init=False)
    "Final represenation of the GUID, which must be present."

    def __post_init__(self):
        """
        Try to find a fallback field for the GUID, if it's missing.

        Raises ValueError if no reasonable fallback can be found.
        """

        if self._raw_guid:
            self.guid = self._raw_guid
        elif self.link:
            self.guid = self.link
        elif self.content:
            m = sha256(usedforsecurity=False)
            m.update(self.content.encode())
            self.guid = m.hexdigest()
        else:
            msg = "Item doesn't include a GUID, link, or contents"
            raise ValueError(msg)

        self.date = datetime.fromisoformat(self._raw_date) if self._raw_date else None

    def date_str(self):
        if self.date is None:
            return None
        return self.date.astimezone(UTC).isoformat()


@dataclass
class DbItem:
    id: int
    "The ID in the database."

    feed_id: FeedId
    "The database ID of the parent feed."

    is_read: bool
    "Whether the item has been marked as read."

    score: float
    "Ranking score, currently unused."

    color: Color | None
    "Optional color to use when rendering the author names from this feed."

    inner: Item

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Self:
        return cls(
            id=row["id"],
            feed_id=row["feed_id"],
            is_read=row["is_read"],
            score=row["score"],
            color=row["color"],
            inner=Item(
                title=row["title"],
                content=row["content"],
                link=row["link"],
                author=row["author"],
                comments=row["comments"],
                _raw_date=row["date"],
                _raw_guid=row["guid"],
            ),
        )

    def __getattr__(self, attr):
        if hasattr(self.inner, attr):
            return getattr(self.inner, attr)
        return object.__getattribute__(self, attr)

    @property
    def day(self) -> str | None:
        "Return the date in the form YYYY-MM-DD instead of the full timestamp"
        if self.date is None:
            return None
        return self.date.strftime("%Y-%m-%d")


type XmlTree = (
    ElementTree.ElementTree[ElementTree.Element[str] | None]
    | ElementTree.ElementTree[ElementTree.Element[str]]
)


@dataclass
class Feed:
    """
    A single RSS feed.

    This is the deserialized representation from the XML document without any
    of the internal data tracked in the database.
    """

    title: str | None
    link: str | None
    description: str | None
    items: list[Item]

    @classmethod
    def from_xml(cls, xml: str) -> Self:
        tree = ElementTree.ElementTree(ElementTree.fromstring(xml))
        return cls._from_xml(tree)

    @classmethod
    def _from_xml(cls, tree: XmlTree) -> Self:
        """
        Deserialize a `Feed` from an XML document.
        """

        root = tree.getroot()

        if root is None:
            msg = "Feed missing root tag"
            raise ValueError(msg)

        if root.tag == "rss":
            return cls._from_rss(root)

        if root.tag.endswith("feed"):
            return cls._from_atom(root)

        msg = f"Unexpected root tag: {root.tag}"
        raise ValueError(msg)

    @classmethod
    def _from_rss(cls, root: Element[str]) -> Self:
        channels: list[Element[str]] = list(root.iter("channel"))
        assert len(channels) == 1, "Expected a single nested <channel>"

        channel = channels[0]

        def get(item: Element[str], field: str) -> str | None:
            return then(item.find(field), attrgetter("text"))

        items = []
        for item in channel.iter("item"):
            pub_date = get(item, "pubDate")

            # TODO(brent) I'm pretty sure ty is doing something wrong here
            # related to https://github.com/astral-sh/ty/issues/1872. If I
            # change T and U in `then` to `str` and `datetime`, it type checks,
            # so this seems to be an issue with generic callables.
            rfc_date: datetime | None = then(pub_date, parsedate_to_datetime)  # ty: ignore [invalid-assignment, invalid-argument-type]
            iso_date = rfc_date.astimezone(UTC).isoformat() if rfc_date else None
            items.append(
                Item(
                    title=get(item, "title"),
                    link=get(item, "link"),
                    content=get(item, "description"),
                    author=get(item, "dc:creator"),
                    comments=get(item, "comments"),
                    _raw_date=iso_date,
                    _raw_guid=get(item, "guid"),
                )
            )

        return cls(
            title=get(channel, "title"),
            link=get(channel, "link"),
            description=get(channel, "description"),
            items=items,
        )

    @classmethod
    def _from_atom(cls, root: Element[str]) -> Self:
        def get(element: Element[str], field: str) -> Element[str] | None:
            for item in element:
                if item.tag.endswith(field):
                    return item
            return None

        def find(
            element: Element[str], target: str, attr: str | None = None
        ) -> str | None:
            item = get(element, target)
            if item is not None:
                if attr is None:
                    return item.text
                return item.attrib.get(attr)
            return None

        def author(element: Element[str]):
            author = get(element, "author")
            if author is None:
                return None

            name = get(author, "name")
            if name is None:
                return None

            return name.text

        items = [
            Item(
                title=find(item, "title"),
                link=find(item, "link", "href"),
                content=find(item, "content"),
                author=author(item),
                comments=find(item, "comments"),
                _raw_date=find(item, "published") or find(item, "updated"),
                _raw_guid=find(item, "id"),
            )
            for item in root
            if item.tag.endswith("entry")
        ]

        return cls(
            title=find(root, "title"),
            link=find(root, "link", "href"),
            description=find(root, "content"),
            items=items,
        )


@dataclass
class DbFeed:
    """
    A feed in the database.

    TODO better name. This is basically the database model for a Feed, or really
    the primary feed type, but Feed is already taken above.
    """

    id: int
    "The ID in the database."

    url: str
    "The URL to fetch."

    title: str | None
    "The feed title."

    description: str | None
    "The feed description."

    etag: str | None
    "ETag header from the last server response, if provided."

    last_modified: str | None
    "Last-Modified header from the last server response, if provided."

    def update(self, *, etag, last_modified, feed: Feed):
        """
        Replace the provided fields of `self` if the values are not `None`.
        """
        self.title = feed.title or self.title
        self.description = feed.description or self.description
        self.etag = etag or self.etag
        self.last_modified = last_modified or self.last_modified
