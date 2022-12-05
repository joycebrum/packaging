import contextlib
import re
from dataclasses import dataclass
from typing import Dict, Iterator, NoReturn, Optional, Tuple, Union

from .specifiers import Specifier


@dataclass
class Token:
    name: str
    text: str
    position: int


class ParserSyntaxError(Exception):
    """The provided source text could not be parsed correctly."""

    def __init__(
        self,
        message: str,
        *,
        source: str,
        span: Tuple[int, int],
    ) -> None:
        self.span = span
        self.message = message
        self.source = source

        super().__init__()

    def __str__(self) -> str:
        marker = " " * self.span[0] + "^" * (self.span[1] - self.span[0] + 1)
        return "\n    ".join([self.message, self.source, marker])


DEFAULT_RULES: "Dict[str, Union[str, re.Pattern[str]]]" = {
    "LPAREN": r"\s*\(",
    "LEFT_PARENTHESIS": r"\(",
    "RIGHT_PARENTHESIS": r"\)",
    "LEFT_BRACKET": r"\[",
    "RIGHT_BRACKET": r"\]",
    "SEMICOLON": r";",
    "COMMA": r",",
    "QUOTED_STRING": re.compile(
        r"""
            (
                ('[^']*')
                |
                ("[^"]*")
            )
        """,
        re.VERBOSE,
    ),
    "OP": r"(===|==|~=|!=|<=|>=|<|>)",
    "BOOLOP": r"(or|and)",
    "IN": r"in",
    "NOT": r"not",
    "VARIABLE": re.compile(
        r"""
            (
                python_version
                |python_full_version
                |os[._]name
                |sys[._]platform
                |platform_(release|system)
                |platform[._](version|machine|python_implementation)
                |python_implementation
                |implementation_(name|version)
                |extra
            )
        """,
        re.VERBOSE,
    ),
    "VERSION": re.compile(Specifier._version_regex_str, re.VERBOSE | re.IGNORECASE),
    "AT": r"\@",
    "URL": r"[^ ]+",
    "IDENTIFIER": r"[a-zA-Z0-9._-]+",
    "WS": r"[ \t]+",
    "END": r"$",
}


class Tokenizer:
    """Context-sensitive token parsing.

    Provides methods to examine the input stream to check whether the next token
    matches.
    """

    def __init__(
        self,
        source: str,
        *,
        rules: "Dict[str, Union[str, re.Pattern[str]]]",
    ) -> None:
        self.source = source
        self.rules: Dict[str, re.Pattern[str]] = {
            name: re.compile(pattern) for name, pattern in rules.items()
        }
        self.next_token: Optional[Token] = None
        self.position = 0

    def consume(self, name: str) -> None:
        """Move beyond provided token name, if at current position."""
        if self.check(name):
            self.read()

    def check(self, name: str, *, peek: bool = False) -> bool:
        """Check whether the next token has the provided name.

        By default, if the check succeeds, the token *must* be read before
        another check. If `peek` is set to `True`, the token is not loaded and
        would need to be checked again.
        """
        assert (
            self.next_token is None
        ), f"Cannot check for {name!r}, already have {self.next_token!r}"
        assert name in self.rules, f"Unknown token name: {name!r}"

        expression = self.rules[name]

        match = expression.match(self.source, self.position)
        if match is None:
            return False
        if not peek:
            self.next_token = Token(name, match[0], self.position)
        return True

    def expect(self, name: str, *, expected: str) -> Token:
        """Expect a certain token name next, failing with a syntax error otherwise.

        The token is *not* read.
        """
        if not self.check(name):
            raise self.raise_syntax_error(f"Expected {expected}")
        return self.read()

    def read(self) -> Token:
        """Consume the next token and return it."""
        token = self.next_token
        assert token is not None

        self.position += len(token.text)
        self.next_token = None

        return token

    def raise_syntax_error(
        self,
        message: str,
        *,
        span_start: Optional[int] = None,
        span_end: Optional[int] = None,
    ) -> NoReturn:
        """Raise ParserSyntaxError at the given position."""
        span = (
            self.position if span_start is None else span_start,
            self.position if span_end is None else span_end,
        )
        raise ParserSyntaxError(
            message,
            source=self.source,
            span=span,
        )

    @contextlib.contextmanager
    def enclosing_tokens(self, open_token: str, close_token: str) -> Iterator[bool]:
        if self.check(open_token):
            open_position = self.position
            self.read()
        else:
            open_position = None

        yield open_position is not None

        if open_position is None:
            return

        if not self.check(close_token):
            self.raise_syntax_error(
                f"Expected closing {close_token}",
                span_start=open_position,
            )

        self.read()
