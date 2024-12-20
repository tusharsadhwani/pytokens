"""CLI interface for pytokens."""

from __future__ import annotations

import argparse
import io
import os.path
import tokenize
from typing import NamedTuple
import warnings

import pytokens


class CLIArgs:
    filepath: str
    validate: bool


def cli(argv: list[str] | None = None) -> int:
    """CLI interface."""
    parser = argparse.ArgumentParser()
    parser.add_argument("filepath")
    parser.add_argument("--validate", action="store_true")
    args = parser.parse_args(argv, namespace=CLIArgs)

    if os.path.isdir(args.filepath):
        files = find_all_python_files(args.filepath)
        verbose = False
    else:
        files = [args.filepath]
        verbose = True

    for filepath in files:
        with open(filepath, "rb") as file:
            encoding, read_bytes = tokenize.detect_encoding(file.readline)
            source = b"".join(read_bytes) + file.read()

        if args.validate:
            validate(filepath, source, encoding, verbose=verbose)

        else:
            for token in pytokens.tokenize(source.decode(encoding)):
                print(token)

    return 0


class TokenTuple(NamedTuple):
    type: str
    start: tuple[int, int]
    end: tuple[int, int]


def validate(filepath: str, source: bytes, encoding: str, verbose: bool = True) -> None:
    """Validate the source code."""
    warnings.simplefilter("ignore")

    # Ensure all line endings have newline as a valid index
    if len(source) == 0 or source[-1:] != b"\n":
        source = source + b"\n"

    # Same as .splitlines(keepends=True), but doesn't split on linefeeds i.e. \x0c
    sourcelines = [line + b"\n" for line in source.split(b"\n")]
    # For that last newline token that exists on an imaginary line sometimes
    sourcelines.append(b"\n")

    source_file = io.BytesIO(source)
    builtin_tokens = tokenize.tokenize(source_file.readline)
    # drop the encoding token
    next(builtin_tokens)

    expected_tokens_unprocessed = [
        TokenTuple(tokenize.tok_name[token.type], token.start, token.end)
        for token in builtin_tokens
    ]
    expected_tokens = [expected_tokens_unprocessed[0]]
    for index, token in enumerate(expected_tokens_unprocessed[1:], start=1):
        last_token = expected_tokens[-1]

        current_token = token
        # Merge consecutive FSTRING_MIDDLE tokens. it's weird cpython has it like that.
        if current_token.type == last_token.type == "FSTRING_MIDDLE":
            expected_tokens.pop()
            current_token = TokenTuple(
                current_token.type,
                last_token.start,
                current_token.end,
            )

        if index + 1 < len(expected_tokens_unprocessed):
            # When an FSTRING_MIDDLE ends with a `{{{` like f'x{{{1}', Python eats
            # the last { char as well as its end index, so we get a `x{` token
            # instead of the expected `x{{` token. This fixes that case. Pretty
            # much always there should be no gap between an fstring-middle ending
            # and the { op after it.
            # Same deal for `}}}"`
            next_token = expected_tokens_unprocessed[index + 1]
            if (
                (current_token.type == "FSTRING_MIDDLE" and next_token.type == "OP")
                or (
                    current_token.type == "FSTRING_MIDDLE"
                    and next_token.type == "FSTRING_END"
                )
                and next_token.start[0] == current_token.end[0]
                and next_token.start[1] > current_token.end[1]
            ):
                expected_tokens.append(
                    TokenTuple(
                        current_token.type,
                        current_token.start,
                        next_token.start,
                    )
                )
                continue

        expected_tokens.append(current_token)

    source_string = source.decode(encoding)
    our_tokens = (
        TokenTuple(
            token.type.to_python_token(),
            (token.start_line, token.start_col),
            (token.end_line, token.end_col),
        )
        for token in pytokens.tokenize(source_string)
        if token.type != pytokens.TokenType.whitespace
    )

    for builtin_token, our_token in zip(expected_tokens, our_tokens):
        mismatch = builtin_token != our_token
        if mismatch or verbose:
            print("EXPECTED", builtin_token)
            print("---- GOT", our_token)

        if mismatch:
            if verbose:
                print("Filepath:", filepath)
            else:
                print("\033[1;31mF\033[0m", end="", flush=True)
            raise AssertionError("Tokens do not match")

    print("\033[1;32m.\033[0m", end="", flush=True)


def find_all_python_files(directory: str) -> list[str]:
    """Recursively find all Python files in the given directory."""
    python_files = []
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith(".py"):
                python_files.append(os.path.join(root, file))
    return python_files