import re
from collections.abc import Iterator

HTML_COMMENTS = re.compile(r"<!--.*?-->", re.DOTALL)
HTML_TAGS = re.compile(r"<[^>]+>")
TOKEN_RE = re.compile(r"[A-Za-z0-9-$']+")


def tokenize(text: str) -> Iterator[str]:
    """
    Tokenize `text` into a normalized sequence of tokens.

    The normalization involves:
    - stripping HTML comments
    - stripping HTML tags
    - converting the text to lowercase

    Additionally, any tokens that consist entirely of digits after these
    changes are filtered out.
    """

    text = HTML_COMMENTS.sub(" ", text)
    text = HTML_TAGS.sub(" ", text)
    tokens = TOKEN_RE.findall(text.lower())
    yield from (t for t in tokens if not t.isdigit())
