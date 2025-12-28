import math
import re
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path

from newsyacht.db import Db

HTML_COMMENTS = re.compile(r"<!--.*?-->", re.DOTALL)
HTML_TAGS = re.compile(r"<[^>]+>")
TOKEN_RE = re.compile(r"[A-Za-z0-9-$']+")


@dataclass
class Model:
    db: Path

    up_docs: int
    "The number of documents with upvotes."

    down_docs: int
    "The number of documents with downvotes."

    up_total_tokens: int
    "The total number of tokens in upvoted documents."

    down_total_tokens: int
    "The total number of tokens in downvoted documents."

    tokens: dict[str, Token]

    @classmethod
    def from_db(cls, db_path):
        with Db(db_path) as db:
            model = db.conn.execute(
                """
                SELECT up_docs, down_docs, up_total_tokens, down_total_tokens
                FROM model
                """,
            ).fetchone()
            tokens = db.conn.execute(
                """
                SELECT text, up, down
                FROM model_tokens
                """
            )
            return cls(
                db=db_path,
                tokens={
                    token["text"]: Token(up=token["up"], down=token["down"])
                    for token in tokens
                },
                **model,
            )

    @property
    def vocabulary_size(self):
        return len(self.tokens)

    def score(
        self, tokens: Iterator[str], *, alpha: float = 1.0, beta: float = 1.0
    ) -> float:
        """
        Returns log P(UP|x) - log P(DOWN|x).
        Positive => prefer upvote, negative => prefer downvote.
        """
        V = max(self.vocabulary_size, 1)

        # Prior log-odds
        score = math.log((self.up_docs + beta) / (self.down_docs + beta))

        up_denom = self.up_total_tokens + alpha * V
        down_denom = self.down_total_tokens + alpha * V

        # Add token contributions
        tokens: Counter[str] = Counter(tokens)
        for text, count in tokens.items():
            if token := self.tokens.get(text):
                up, down = token.up, token.down
            else:
                up, down = 0, 0
            up_num = up + alpha
            down_num = down + alpha

            score += count * (
                math.log(up_num / up_denom) - math.log(down_num / down_denom)
            )

        return sigmoid(score)

    def add_item(self, document: str, vote: Vote):
        for token in tokenize(document):
            ...


@dataclass
class Token:
    """
    A scored token.

    `up` is the number of times this token appears in upvoted documents.
    """

    up: int = 0
    down: int = 0


class Vote(Enum):
    UP = auto()
    DOWN = auto()


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


def sigmoid(z: float) -> float:
    if z >= 0:
        ez = math.exp(-z)
        return 1 / (1 + ez)

    ez = math.exp(z)
    return ez / (1 + ez)
