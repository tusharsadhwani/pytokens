"""pytokens - A Fast, spec compliant Python 3.12+ tokenizer that runs on older Pythons."""

from __future__ import annotations

from dataclasses import dataclass, field
import enum
import string
from typing import Iterator, NewType


class Underflow(Exception): ...


class NotAnIndent(Exception): ...


class InconsistentUseOfTabsAndSpaces(Exception): ...


class DedentDoesNotMatchAnyOuterIndent(Exception): ...


class UnterminatedString(Exception): ...


class UnexpectedEOF(Exception): ...


class UnexpectedCharacterAfterBackslash(Exception): ...


class UnexpectedCharacter(Exception): ...


class TokenType(enum.IntEnum):
    whitespace = 1
    indent = 2
    dedent = 3
    newline = 4  # semantically meaningful newline
    nl = 5  # non meaningful newline
    comment = 6

    _op_start = 7  # marker used to check if a token is an operator
    semicolon = 8
    lparen = 9
    rparen = 10
    lbracket = 11
    rbracket = 12
    lbrace = 13
    rbrace = 14
    colon = 15
    op = 16
    _op_end = 17  # marker used to check if a token is an operator

    identifier = 18
    number = 19
    string = 20
    fstring_start = 21
    fstring_middle = 22
    fstring_end = 23

    endmarker = 24

    def __repr__(self) -> str:
        return f"TokenType.{self.name}"

    def to_python_token(self) -> str:
        if self.name == "identifier":
            return "NAME"

        if self.is_operator(self):
            return "OP"

        return self.name.upper()

    @staticmethod
    def is_operator(value: int) -> bool:
        return TokenType._op_start < value < TokenType._op_end


@dataclass
class Token:
    type: TokenType
    # Byte offsets in the file
    start_index: int
    end_index: int
    start_line: int
    # 0-indexed offset from start of line
    start_col: int
    end_line: int
    end_col: int

    def to_byte_slice(self, source: str) -> str:
        # Newline at end of file may not exist in the file
        if (
            (self.type == TokenType.newline or self.type == TokenType.nl)
            and self.start_index == len(source)
            and self.end_index == len(source) + 1
        ):
            return ""

        # Dedents at end of file also may not exist in the file
        if (
            self.type == TokenType.dedent
            and self.start_index == len(source) + 1
            and self.end_index == len(source) + 1
        ):
            return ""

        # Endmarkers are out of bound too
        if self.type == TokenType.endmarker:
            return ""

        return source[self.start_index : self.end_index]


def is_whitespace(char: str) -> bool:
    return char == " " or char == "\t" or char == "\x0b" or char == "\x0c"


class FStringState:
    State = NewType("State", int)

    not_fstring = State(1)
    at_fstring_middle = State(2)
    at_fstring_lbrace = State(3)
    in_fstring_expr = State(4)
    in_fstring_expr_modifier = State(5)
    at_fstring_end = State(6)

    def __init__(self) -> None:
        self.state = FStringState.not_fstring
        self.stack: list[FStringState.State] = []

    def enter_fstring(self) -> None:
        self.stack.append(self.state)
        self.state = FStringState.at_fstring_middle

    def leave_fstring(self) -> None:
        assert self.state == FStringState.at_fstring_end
        self.state = self.stack.pop()

    def consume_fstring_middle_for_lbrace(self) -> None:
        if self.state == FStringState.in_fstring_expr_modifier:
            self.stack.append(self.state)

        self.state = FStringState.at_fstring_lbrace

    def consume_fstring_middle_for_end(self) -> None:
        self.state = FStringState.at_fstring_end

    def consume_lbrace(self) -> None:
        self.state = FStringState.in_fstring_expr

    def consume_rbrace(self) -> None:
        assert (
            self.state == FStringState.in_fstring_expr
            or self.state == FStringState.in_fstring_expr_modifier
        )

        if (
            len(self.stack) > 0
            and self.stack[-1] == FStringState.in_fstring_expr_modifier
        ):
            self.state = self.stack.pop()
        else:
            self.state = FStringState.at_fstring_middle

    def consume_colon(self) -> None:
        assert self.state == FStringState.in_fstring_expr
        self.state = FStringState.in_fstring_expr_modifier


@dataclass
class TokenIterator:
    source: str
    current_index: int = 0
    prev_index: int = 0
    line_number: int = 1
    prev_line_number: int = 1
    byte_offset: int = 0
    prev_byte_offset: int = 0
    all_whitespace_on_this_line: bool = True

    bracket_level: int = 0
    bracket_level_stack: list[int] = field(default_factory=list)
    prev_token: Token | None = None

    indent_stack: list[str] = field(default_factory=list)
    dedent_counter: int = 0

    # f-string state
    fstring_state: FStringState = field(default_factory=FStringState)
    fstring_quote_stack: list[str] = field(default_factory=list)
    fstring_quote: str | None = None

    def is_in_bounds(self) -> bool:
        return self.current_index < len(self.source)

    def peek(self) -> str:
        assert self.is_in_bounds()
        return self.source[self.current_index]

    def peek_next(self) -> str:
        assert self.current_index + 1 < len(self.source)
        return self.source[self.current_index + 1]

    def advance(self) -> None:
        self.current_index += 1
        self.byte_offset += 1

    def advance_by(self, count: int) -> None:
        self.current_index += count
        self.byte_offset += count

    def next_line(self) -> None:
        self.line_number += 1
        self.byte_offset = 0
        self.all_whitespace_on_this_line = True

    def advance_check_newline(self) -> None:
        if self.source[self.current_index] == "\n":
            self.current_index += 1
            self.next_line()
        else:
            self.advance()

    def match(self, *options: str, ignore_case: bool = False) -> bool:
        for option in options:
            if self.current_index + len(option) > len(self.source):
                continue
            snippet = self.source[self.current_index : self.current_index + len(option)]
            if ignore_case:
                option = option.lower()
                snippet = snippet.lower()

            if option == snippet:
                return True

        return False

    def make_token(self, tok_type: TokenType) -> Token:
        token = Token(
            type=tok_type,
            start_index=self.prev_index,
            end_index=self.current_index,
            start_line=self.prev_line_number,
            start_col=self.prev_byte_offset,
            end_line=self.line_number,
            end_col=self.byte_offset,
        )
        if tok_type == TokenType.newline or tok_type == TokenType.nl:
            self.next_line()
        elif tok_type == TokenType.whitespace or tok_type == TokenType.comment:
            pass
        else:
            self.all_whitespace_on_this_line = False

        self.prev_token = token
        self.prev_index = self.current_index
        self.prev_line_number = self.line_number
        self.prev_byte_offset = self.byte_offset
        return token

    def push_fstring_quote(self, quote: str) -> None:
        if self.fstring_quote is not None:
            self.fstring_quote_stack.append(self.fstring_quote)

        self.fstring_quote = quote

    def pop_fstring_quote(self) -> None:
        if self.fstring_quote is None:
            raise Underflow
        self.fstring_quote = (
            None
            if len(self.fstring_quote_stack) == 0
            else self.fstring_quote_stack.pop()
        )

    def newline(self) -> Token:
        if self.is_in_bounds() and self.source[self.current_index] == "\r":
            self.advance()
        self.advance()
        in_brackets = self.bracket_level > 0
        token_type = (
            TokenType.nl
            if (
                in_brackets
                or self.fstring_state.state == FStringState.in_fstring_expr
                or self.all_whitespace_on_this_line
            )
            else TokenType.newline
        )
        token = self.make_token(token_type)
        return token

    def endmarker(self) -> Token:
        if len(self.indent_stack) > 0:
            _ = self.indent_stack.pop()
            return self.make_token(TokenType.dedent)

        return self.make_token(TokenType.endmarker)

    def decimal(self) -> Token:
        digit_before_decimal = False
        if self.source[self.current_index].isdigit():
            digit_before_decimal = True
            self.advance()

        # TODO: this is too lax; 1__2 tokenizes successfully
        while self.is_in_bounds() and (
            self.source[self.current_index].isdigit()
            or self.source[self.current_index] == "_"
        ):
            self.advance()

        if self.is_in_bounds() and self.source[self.current_index] == ".":
            self.advance()

        while self.is_in_bounds() and (
            self.source[self.current_index].isdigit()
            or (
                self.source[self.current_index] == "_"
                and self.source[self.current_index - 1].isdigit()
            )
        ):
            self.advance()
        # Before advancing over the 'e', ensure that there has been at least 1 digit before the 'e'
        if self.current_index + 1 < len(self.source) and (
            (digit_before_decimal or self.source[self.current_index - 1].isdigit())
            and (
                self.source[self.current_index] == "e"
                or self.source[self.current_index] == "E"
            )
            and (
                self.source[self.current_index + 1].isdigit()
                or (
                    self.current_index + 2 < len(self.source)
                    and (
                        self.source[self.current_index + 1] == "+"
                        or self.source[self.current_index + 1] == "-"
                    )
                    and self.source[self.current_index + 2].isdigit()
                )
            )
        ):
            self.advance()
            self.advance()
            # optional third advance not necessary as itll get advanced just below

        # TODO: this is too lax; 1__2 tokenizes successfully
        while self.is_in_bounds() and (
            self.source[self.current_index].isdigit()
            or (
                (digit_before_decimal or self.source[self.current_index - 1].isdigit())
                and self.source[self.current_index] == "_"
            )
        ):
            self.advance()

        # Complex numbers end in a `j`. But ensure at least 1 digit before it
        if self.is_in_bounds() and (
            (digit_before_decimal or self.source[self.current_index - 1].isdigit())
            and (
                self.source[self.current_index] == "j"
                or self.source[self.current_index] == "J"
            )
        ):
            self.advance()
        # If all of this resulted in just a dot, return an operator
        if (
            self.current_index - self.prev_index == 1
            and self.source[self.current_index - 1] == "."
        ):
            # Ellipsis check
            if (
                self.current_index + 2 <= len(self.source)
                and self.source[self.current_index : self.current_index + 2] == ".."
            ):
                self.advance()
                self.advance()

            return self.make_token(TokenType.op)

        return self.make_token(TokenType.number)

    def binary(self) -> Token:
        # jump over `0b`
        self.advance()
        self.advance()
        while (
            self.is_in_bounds()
            and self.source[self.current_index] == "0"
            or self.source[self.current_index] == "1"
        ):
            self.advance()
        if self.is_in_bounds() and (
            self.source[self.current_index] == "e"
            or self.source[self.current_index] == "E"
        ):
            self.advance()
            if self.is_in_bounds() and self.source[self.current_index] == "-":
                self.advance()

        while (
            self.is_in_bounds()
            and self.source[self.current_index] == "0"
            or self.source[self.current_index] == "1"
        ):
            self.advance()
        return self.make_token(TokenType.number)

    def octal(self) -> Token:
        # jump over `0o`
        self.advance()
        self.advance()
        while (
            self.is_in_bounds()
            and self.source[self.current_index] >= "0"
            and self.source[self.current_index] <= "7"
        ):
            self.advance()
        if self.is_in_bounds() and (
            self.source[self.current_index] == "e"
            or self.source[self.current_index] == "E"
        ):
            self.advance()
            if self.is_in_bounds() and self.source[self.current_index] == "-":
                self.advance()

        while (
            self.is_in_bounds()
            and self.source[self.current_index] >= "0"
            and self.source[self.current_index] <= "7"
        ):
            self.advance()
        return self.make_token(TokenType.number)

    def hexadecimal(self) -> Token:
        # jump over `0x`
        self.advance()
        self.advance()
        while (
            self.is_in_bounds() and self.source[self.current_index] in string.hexdigits
        ):
            self.advance()
        if self.is_in_bounds() and (
            self.source[self.current_index] == "e"
            or self.source[self.current_index] == "E"
        ):
            self.advance()
            if self.is_in_bounds() and self.source[self.current_index] == "-":
                self.advance()

        while (
            self.is_in_bounds() and self.source[self.current_index] in string.hexdigits
        ):
            self.advance()
        return self.make_token(TokenType.number)

    def find_opening_quote(self) -> int:
        # Quotes should always be within 3 chars of the beginning of the string token
        for offset in range(3):
            char = self.source[self.current_index + offset]
            if char == '"' or char == "'":
                return self.current_index + offset

        raise AssertionError("Quote not found somehow")

    def string_prefix_and_quotes(self) -> tuple[str, str]:
        quote_index = self.find_opening_quote()
        prefix = self.source[self.current_index : quote_index]
        quote_char = self.source[quote_index]

        # Check for triple quotes
        quote = (
            self.source[quote_index : quote_index + 3]
            if (
                quote_index + 3 <= len(self.source)
                and self.source[quote_index + 1] == quote_char
                and self.source[quote_index + 2] == quote_char
            )
            else self.source[quote_index : quote_index + 1]
        )
        return prefix, quote

    def fstring(self) -> Token:
        if self.fstring_state.state in (
            FStringState.not_fstring,
            FStringState.in_fstring_expr,
        ):
            prefix, quote = self.string_prefix_and_quotes()
            self.push_fstring_quote(quote)
            for _ in range(len(prefix)):
                self.advance()
            for _ in range(len(quote)):
                self.advance()
            self.fstring_state.enter_fstring()
            return self.make_token(TokenType.fstring_start)

        if self.fstring_state.state == FStringState.at_fstring_middle:
            assert self.fstring_quote is not None
            is_single_quote = len(self.fstring_quote) == 1
            start_index = self.current_index
            while self.is_in_bounds():
                char = self.source[self.current_index]
                # For single quotes, bail on newlines
                if char == "\n" and is_single_quote:
                    raise UnterminatedString

                # Handle escapes
                if char == "\\":
                    self.advance()
                    # But don't escape a `\{` or `\}` in f-strings
                    # but DO escape `\N{` in f-strings, that's for unicode characters
                    if (
                        self.current_index + 1 < len(self.source)
                        and self.peek() == "N"
                        and self.peek_next() == "{"
                    ):
                        self.advance()
                        self.advance()

                    if self.is_in_bounds() and not (
                        self.peek() == "{" or self.peek() == "}"
                    ):
                        self.advance_check_newline()

                    continue

                # Find opening / closing quote
                if char == "{":
                    if self.peek_next() == "{":
                        self.advance()
                        self.advance()
                        continue
                    else:
                        self.fstring_state.consume_fstring_middle_for_lbrace()
                        # If fstring-middle is empty, skip it by returning the next step token
                        if self.current_index == start_index:
                            return self.fstring()

                        return self.make_token(TokenType.fstring_middle)

                assert self.fstring_quote is not None
                if self.match(self.fstring_quote):
                    self.fstring_state.consume_fstring_middle_for_end()
                    # If fstring-middle is empty, skip it by returning the next step token
                    if self.current_index == start_index:
                        return self.fstring()

                    return self.make_token(TokenType.fstring_middle)

                self.advance_check_newline()

            raise UnexpectedEOF

        if self.fstring_state.state == FStringState.at_fstring_lbrace:
            self.advance()
            self.bracket_level_stack.append(self.bracket_level)
            self.bracket_level = 0
            self.fstring_state.consume_lbrace()
            return self.make_token(TokenType.lbrace)

        if self.fstring_state.state == FStringState.at_fstring_end:
            assert self.fstring_quote is not None
            for _ in range(len(self.fstring_quote)):
                self.advance()
            self.pop_fstring_quote()
            self.fstring_state.leave_fstring()
            return self.make_token(TokenType.fstring_end)

        if self.fstring_state.state == FStringState.in_fstring_expr_modifier:
            start_index = self.current_index
            while self.is_in_bounds():
                char = self.source[self.current_index]
                assert self.fstring_quote is not None
                if (char == "\n" or char == "{") and len(self.fstring_quote) == 1:
                    if char == "{":
                        self.fstring_state.consume_fstring_middle_for_lbrace()
                    else:
                        # TODO: why?
                        self.fstring_state.state = FStringState.in_fstring_expr

                    # If fstring-middle is empty, skip it by returning the next step token
                    if self.current_index == start_index:
                        return self.fstring()

                    return self.make_token(TokenType.fstring_middle)
                elif char == "}":
                    self.fstring_state.state = FStringState.in_fstring_expr
                    return self.make_token(TokenType.fstring_middle)

                self.advance_check_newline()

            raise UnexpectedEOF

        raise AssertionError("Unhandled f-string state")

    def string(self) -> Token:
        prefix, quote = self.string_prefix_and_quotes()
        for char in prefix:
            if char == "f" or char == "F":
                return self.fstring()

        for _ in range(len(prefix)):
            self.advance()
        for _ in range(len(quote)):
            self.advance()

        is_single_quote = len(quote) == 1

        while self.is_in_bounds():
            char = self.source[self.current_index]
            # For single quotes, bail on newlines
            if char == "\n" and is_single_quote:
                raise UnterminatedString

            # Handle escapes
            if char == "\\":
                self.advance()
                self.advance_check_newline()
                continue

            # Find closing quote
            if self.match(quote):
                for _ in range(len(quote)):
                    self.advance()
                return self.make_token(TokenType.string)

            self.advance_check_newline()

        raise UnexpectedEOF

    def indent(self) -> Token:
        start_index = self.current_index
        saw_whitespace = False
        saw_tab_or_space = False
        while self.is_in_bounds():
            char = self.source[self.current_index]
            if is_whitespace(char):
                self.advance()
                saw_whitespace = True
                if char == " " or char == "\t":
                    saw_tab_or_space = True
            else:
                break

        if not self.is_in_bounds():
            # File ends with no whitespace after newline, don't return indent
            if self.current_index == start_index:
                raise NotAnIndent
            # If reached the end of the file, don't return an indent
            return self.make_token(TokenType.whitespace)

        # If the line is preceded by just linefeeds/CR/etc.,
        # ignore that leading whitespace entirely.
        if saw_whitespace and not saw_tab_or_space:
            start_index = self.current_index

        # For lines that are just leading whitespace and a slash or a comment,
        # don't return indents
        next_char = self.peek()
        if (
            next_char == "#"
            or next_char == "\\"
            or next_char == "\r"
            or next_char == "\n"
        ):
            return self.make_token(TokenType.whitespace)

        new_indent = self.source[start_index : self.current_index]
        current_indent = "" if len(self.indent_stack) == 0 else self.indent_stack[-1]

        if len(new_indent) == len(current_indent):
            if len(new_indent) == 0:
                raise NotAnIndent

            if new_indent != current_indent:
                raise InconsistentUseOfTabsAndSpaces
            return self.make_token(TokenType.whitespace)
        elif len(new_indent) > len(current_indent):
            if len(current_indent) > 0 and current_indent not in new_indent:
                raise InconsistentUseOfTabsAndSpaces
            self.indent_stack.append(new_indent)
            return self.make_token(TokenType.indent)
        else:
            while len(self.indent_stack) > 0:
                top_indent = self.indent_stack[-1]
                if len(top_indent) < len(new_indent):
                    raise DedentDoesNotMatchAnyOuterIndent

                if len(top_indent) == len(new_indent):
                    break

                _ = self.indent_stack.pop()
                self.dedent_counter += 1

            # Let the dedent counter make the dedents. They must be length zero
            return self.make_token(TokenType.whitespace)

    def is_newline(self) -> bool:
        if self.source[self.current_index] == "\n":
            return True
        if (
            self.source[self.current_index] == "\r"
            and self.current_index + 1 < len(self.source)
            and self.source[self.current_index + 1] == "\n"
        ):
            self.advance()
            return True

        return False

    def name(self) -> Token:
        remaining = self.source[self.current_index :]
        if not str.isidentifier(remaining[0]):
            raise UnexpectedCharacter

        for i in range(1, len(remaining) + 1):
            identifier = remaining[:i]
            if not str.isidentifier(identifier):
                length = i - 1
                break
        else:
            length = len(remaining)

        self.advance_by(length)
        return self.make_token(TokenType.identifier)

    def __iter__(self) -> TokenIterator:
        return self

    def __next__(self) -> Token:
        if self.prev_token is not None and self.prev_token.type == TokenType.endmarker:
            raise StopIteration

        # EOF checks
        if self.current_index == len(self.source):
            if self.prev_token is None:
                return self.endmarker()

            if self.prev_token.type in {
                TokenType.newline,
                TokenType.nl,
                TokenType.dedent,
            }:
                return self.endmarker()
            else:
                return self.newline()

        if self.current_index > len(self.source):
            return self.endmarker()

        # f-string check
        if (
            self.fstring_state.state != FStringState.not_fstring
            and self.fstring_state.state != FStringState.in_fstring_expr
        ):
            return self.fstring()

        current_char = self.source[self.current_index]

        # Comment check
        if current_char == "#":
            while self.is_in_bounds() and self.peek() != "\n" and self.peek() != "\r":
                self.advance()
            return self.make_token(TokenType.comment)

        # Empty the dedent counter
        if self.dedent_counter > 0:
            self.dedent_counter -= 1
            return self.make_token(TokenType.dedent)

        # Newline check
        if self.is_newline():
            return self.newline()

        # \<newline> check
        if current_char == "\\":
            self.advance()
            if not self.is_in_bounds():
                raise UnexpectedEOF

            # Consume all whitespace on this line and the next.
            found_whitespace = False
            while self.is_in_bounds():
                char = self.source[self.current_index]
                if is_whitespace(char):
                    self.advance()
                    found_whitespace = True
                elif char == "\n" or (
                    char == "\r"
                    and self.current_index + 1 < len(self.source)
                    and self.source[self.current_index + 1] == "\n"
                ):
                    if char == "\r":
                        self.advance()
                    self.advance()
                    found_whitespace = True
                    # Move to next line without creating a newline token. But,
                    # if the previous line was all whitespace, whitespace on
                    # the next line is still valid indentation. Avoid consuming
                    if self.all_whitespace_on_this_line:
                        self.next_line()
                        break
                    else:
                        self.next_line()
                        # Preserve this boolean, we're on the same line semantically
                        self.all_whitespace_on_this_line = False

                else:
                    break

            if not found_whitespace:
                raise UnexpectedCharacterAfterBackslash

            return self.make_token(TokenType.whitespace)

        # \r on its own without a \n following, becomes an op along with the next char
        if current_char == "\r":
            self.advance()
            if self.is_in_bounds():
                assert self.source[self.current_index] != "\n"
                self.advance()
                return self.make_token(TokenType.op)

            return self.newline()

        # Indent / dedent checks
        if (
            self.byte_offset == 0
            and self.bracket_level == 0
            and self.fstring_state.state == FStringState.not_fstring
        ):
            try:
                indent_token = self.indent()
            except NotAnIndent:
                indent_token = None

            if indent_token is not None:
                return indent_token

        if current_char in (" ", "\r", "\t", "\x0b", "\x0c"):
            while self.is_in_bounds() and is_whitespace(
                self.source[self.current_index]
            ):
                self.advance()
            return self.make_token(TokenType.whitespace)

        if current_char in ("+", "&", "|", ",", "^", "@", "%", "=", "!", "~"):
            self.advance()
            if self.peek() == "=":
                self.advance()
            return self.make_token(TokenType.op)

        if current_char == "<":
            self.advance()
            if self.peek() == ">":
                # Barry as FLUFL easter egg
                self.advance()
                return self.make_token(TokenType.op)

            if self.peek() == "<":
                self.advance()
            if self.peek() == "=":
                self.advance()
            return self.make_token(TokenType.op)

        if current_char == ">":
            self.advance()
            if self.peek() == ">":
                self.advance()
            if self.peek() == "=":
                self.advance()
            return self.make_token(TokenType.op)

        if current_char == "/":
            self.advance()
            if self.peek() == "/":
                self.advance()
            if self.peek() == "=":
                self.advance()
            return self.make_token(TokenType.op)

        if current_char == "*":
            self.advance()
            if self.peek() == "*":
                self.advance()
            if self.peek() == "=":
                self.advance()
            return self.make_token(TokenType.op)

        if current_char == "-":
            self.advance()
            # -> operator
            if self.peek() == ">":
                self.advance()
                return self.make_token(TokenType.op)

            # -= operator
            if self.peek() == "=":
                self.advance()
            return self.make_token(TokenType.op)

        if current_char in (",", ";"):
            self.advance()
            return self.make_token(TokenType.op)

        # This guy is not used in Python3, but still exists
        # for backwards compatibility i guess.
        if current_char == "`":
            self.advance()
            return self.make_token(TokenType.op)

        if current_char == "(":
            self.advance()
            self.bracket_level += 1
            return self.make_token(TokenType.lparen)

        if current_char == ")":
            self.advance()
            self.bracket_level -= 1
            if self.bracket_level < 0:
                self.bracket_level = 0
            return self.make_token(TokenType.rparen)

        if current_char == "[":
            self.advance()
            self.bracket_level += 1
            return self.make_token(TokenType.lbracket)

        if current_char == "]":
            self.advance()
            self.bracket_level -= 1
            if self.bracket_level < 0:
                self.bracket_level = 0
            return self.make_token(TokenType.rbracket)

        if current_char == "{":
            self.advance()
            self.bracket_level += 1
            return self.make_token(TokenType.lbrace)

        if current_char == "}":
            self.advance()
            if (
                self.bracket_level == 0
                and self.fstring_state.state == FStringState.in_fstring_expr
            ):
                self.fstring_state.consume_rbrace()
                self.bracket_level = self.bracket_level_stack.pop()
            else:
                self.bracket_level -= 1
                if self.bracket_level < 0:
                    self.bracket_level = 0

            return self.make_token(TokenType.rbrace)

        if current_char == ":":
            self.advance()
            if (
                self.bracket_level == 0
                and self.fstring_state.state == FStringState.in_fstring_expr
            ):
                self.fstring_state.state = FStringState.in_fstring_expr_modifier
                return self.make_token(TokenType.op)
            else:
                if self.peek() == "=":
                    self.advance()
                return self.make_token(TokenType.op)

        if current_char in ".0123456789":
            if self.current_index + 2 <= len(self.source) and self.source[
                self.current_index : self.current_index + 2
            ] in ("0b", "0B"):
                return self.binary()
            elif self.current_index + 2 <= len(self.source) and self.source[
                self.current_index : self.current_index + 2
            ] in ("0o", "0O"):
                return self.octal()
            elif self.current_index + 2 <= len(self.source) and self.source[
                self.current_index : self.current_index + 2
            ] in ("0x", "0X"):
                return self.hexadecimal()
            else:
                return self.decimal()

        if (
            (self.current_index + 1 <= len(self.source) and self.match('"', "'"))
            or (
                self.current_index + 2 <= len(self.source)
                and self.match(
                    'b"',
                    "b'",
                    'r"',
                    "r'",
                    'f"',
                    "f'",
                    'u"',
                    "u'",
                    ignore_case=True,
                )
            )
            or (
                self.current_index + 3 <= len(self.source)
                and self.match(
                    'br"',
                    "br'",
                    'rb"',
                    "rb'",
                    'fr"',
                    "fr'",
                    'rf"',
                    "rf'",
                    ignore_case=True,
                )
            )
        ):
            return self.string()

        return self.name()


def tokenize(source: str) -> Iterator[Token]:
    token_iterator = TokenIterator(source)
    return iter(token_iterator)
