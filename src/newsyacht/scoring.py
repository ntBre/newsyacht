import math
import re
from collections import Counter, defaultdict
from collections.abc import Iterator
from dataclasses import dataclass

from newsyacht.db import Db
from newsyacht.models import Vote

HTML_COMMENTS = re.compile(r"<!--.*?-->", re.DOTALL)
HTML_TAGS = re.compile(r"<[^>]+>")
TOKEN_RE = re.compile(r"[A-Za-z0-9-$']+")


@dataclass
class Model:
    up_docs: int
    "The number of documents with upvotes."

    down_docs: int
    "The number of documents with downvotes."

    up_total_tokens: int
    "The total number of tokens in upvoted documents."

    down_total_tokens: int
    "The total number of tokens in downvoted documents."

    tokens: defaultdict[str, Token]

    @classmethod
    def from_db(cls, db):
        model = db.conn.execute(
            """
            SELECT up_docs, down_docs, up_total_tokens, down_total_tokens
            FROM model
            WHERE id = 1
            """,
        ).fetchone()
        tokens = db.conn.execute(
            """
            SELECT text, up, down
            FROM model_tokens
            """
        )
        return cls(
            tokens=defaultdict(
                Token,
                {
                    token["text"]: Token(up=token["up"], down=token["down"])
                    for token in tokens
                },
            ),
            **model,
        )

    @property
    def vocabulary_size(self):
        return len(self.tokens)

    def score(
        self, tokens: Iterator[str], *, alpha: float = 1.0, beta: float = 1.0
    ) -> float:
        """
        Returns the model's score in [0, 1] for `tokens`.
        """
        vocabulary_size = max(self.vocabulary_size, 1)

        # Prior log-odds
        score = math.log((self.up_docs + beta) / (self.down_docs + beta))

        up_denom = self.up_total_tokens + alpha * vocabulary_size
        down_denom = self.down_total_tokens + alpha * vocabulary_size

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

    @classmethod
    def change_vote(cls, db: Db, item_id: int, vote: Vote) -> None:
        """Toggle or replace a vote and its training data atomically."""
        with db.conn:
            # Lock before reading the vote and model to avoid concurrent updates.
            db.conn.execute("BEGIN IMMEDIATE")
            item = db.get_item(item_id)
            new_vote = Vote.NONE if item.vote == vote else vote

            model = cls.from_db(db)
            document = item.text()
            if item.vote != Vote.NONE:
                model._adjust_item(db, document, item.vote, delta=-1)
            if new_vote != Vote.NONE:
                model._adjust_item(db, document, new_vote, delta=1)

            db.conn.execute(
                "UPDATE items SET vote = ? WHERE id = ?", (new_vote.value, item_id)
            )
            # A removed vote may leave tokens with no remaining occurrences.
            db.conn.execute("DELETE FROM model_tokens WHERE up = 0 AND down = 0")

    def _adjust_item(self, db: Db, document: str, vote: Vote, *, delta: int) -> None:
        """Apply or reverse a document's contribution inside a transaction."""
        counts = Counter(tokenize(document))
        total_tokens = sum(counts.values()) * delta
        updated = defaultdict(Token)
        for text, count in counts.items():
            count *= delta
            match vote:
                case Vote.UP:
                    self.tokens[text].up += count
                    updated[text].up += count
                case Vote.DOWN:
                    self.tokens[text].down += count
                    updated[text].down += count

        match vote:
            case Vote.UP:
                self.up_docs += delta
                self.up_total_tokens += total_tokens
            case Vote.DOWN:
                self.down_docs += delta
                self.down_total_tokens += total_tokens

        db.conn.execute(
            """
            UPDATE model
            SET up_docs = ?, down_docs = ?, up_total_tokens = ?, down_total_tokens = ?
            WHERE id = 1
            """,
            (
                self.up_docs,
                self.down_docs,
                self.up_total_tokens,
                self.down_total_tokens,
            ),
        )
        db.conn.executemany(
            """
            INSERT INTO model_tokens (text, up, down)
            VALUES (?, ?, ?)
            ON CONFLICT(text) DO UPDATE SET
                up = up + excluded.up,
                down = down + excluded.down
            """,
            [(text, token.up, token.down) for text, token in updated.items()],
        )


@dataclass
class Token:
    """
    A scored token.

    `up` is the number of times this token appears in upvoted documents.
    """

    up: int = 0
    down: int = 0


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
