from pytokens import tokenize, Token, TokenType as T


def test_tokenize() -> None:
    source = "def foo():\n    7.e1\n"
    tokens = list(tokenize(source))
    assert tokens == [
        Token(T.identifier, 0, 3, start_line=1, start_col=0, end_line=1, end_col=3),
        Token(T.whitespace, 3, 4, start_line=1, start_col=3, end_line=1, end_col=4),
        Token(T.identifier, 4, 7, start_line=1, start_col=4, end_line=1, end_col=7),
        Token(T.lparen, 7, 8, start_line=1, start_col=7, end_line=1, end_col=8),
        Token(T.rparen, 8, 9, start_line=1, start_col=8, end_line=1, end_col=9),
        Token(T.op, 9, 10, start_line=1, start_col=9, end_line=1, end_col=10),
        Token(T.newline, 10, 11, start_line=1, start_col=10, end_line=1, end_col=11),
        Token(T.indent, 11, 15, start_line=2, start_col=0, end_line=2, end_col=4),
        Token(T.number, 15, 19, start_line=2, start_col=4, end_line=2, end_col=8),
        Token(T.newline, 19, 20, start_line=2, start_col=8, end_line=2, end_col=9),
        Token(T.dedent, 20, 20, start_line=3, start_col=0, end_line=3, end_col=0),
        Token(T.endmarker, 20, 20, start_line=3, start_col=0, end_line=3, end_col=0),
    ]

    # https://github.com/psf/black/issues/3700
    source = "{\r}"
    tokens = list(tokenize(source))
    assert tokens == [
        Token(T.lbrace, 0, 1, start_line=1, start_col=0, end_line=1, end_col=1),
        Token(T.whitespace, 1, 2, start_line=1, start_col=1, end_line=1, end_col=2),
        Token(T.rbrace, 2, 3, start_line=1, start_col=2, end_line=1, end_col=3),
        Token(T.newline, 3, 4, start_line=1, start_col=3, end_line=1, end_col=4),
        Token(T.endmarker, 4, 4, start_line=2, start_col=0, end_line=2, end_col=0),
    ]

    source = "€€, x🐍y = 1, 2"
    tokens = list(tokenize(source))
    assert tokens == [
        Token(T.identifier, 0, 2, start_line=1, start_col=0, end_line=1, end_col=2),
        Token(T.op, 2, 3, start_line=1, start_col=2, end_line=1, end_col=3),
        Token(T.whitespace, 3, 4, start_line=1, start_col=3, end_line=1, end_col=4),
        Token(T.identifier, 4, 7, start_line=1, start_col=4, end_line=1, end_col=7),
        Token(T.whitespace, 7, 8, start_line=1, start_col=7, end_line=1, end_col=8),
        Token(T.op, 8, 9, start_line=1, start_col=8, end_line=1, end_col=9),
        Token(T.whitespace, 9, 10, start_line=1, start_col=9, end_line=1, end_col=10),
        Token(T.number, 10, 11, start_line=1, start_col=10, end_line=1, end_col=11),
        Token(T.op, 11, 12, start_line=1, start_col=11, end_line=1, end_col=12),
        Token(T.whitespace, 12, 13, start_line=1, start_col=12, end_line=1, end_col=13),
        Token(T.number, 13, 14, start_line=1, start_col=13, end_line=1, end_col=14),
        Token(T.newline, 14, 15, start_line=1, start_col=14, end_line=1, end_col=15),
        Token(T.endmarker, 15, 15, start_line=2, start_col=0, end_line=2, end_col=0),
    ]

    source = r'''rf"\N{42}"'''
    tokens = list(tokenize(source))
    assert tokens == [
        Token(T.fstring_start, 0, 3, start_line=1, start_col=0, end_line=1, end_col=3),
        Token(T.fstring_middle, 3, 5, start_line=1, start_col=3, end_line=1, end_col=5),
        Token(T.lbrace, 5, 6, start_line=1, start_col=5, end_line=1, end_col=6),
        Token(T.number, 6, 8, start_line=1, start_col=6, end_line=1, end_col=8),
        Token(T.rbrace, 8, 9, start_line=1, start_col=8, end_line=1, end_col=9),
        Token(T.fstring_end, 9, 10, start_line=1, start_col=9, end_line=1, end_col=10),
        Token(T.newline, 10, 11, start_line=1, start_col=10, end_line=1, end_col=11),
        Token(T.endmarker, 11, 11, start_line=2, start_col=0, end_line=2, end_col=0),
    ]


def test_weird_op_case() -> None:
    source = "\n#\r0"
    tokens = list(tokenize(source))
    assert tokens == [
        Token(T.nl, 0, 1, start_line=1, start_col=0, end_line=1, end_col=1),
        Token(T.comment, 1, 4, start_line=2, start_col=0, end_line=2, end_col=3),
        Token(T.nl, 4, 5, start_line=2, start_col=3, end_line=2, end_col=4),
        Token(T.endmarker, 5, 5, start_line=3, start_col=0, end_line=3, end_col=0),
    ]

    source = "\n\r0"
    tokens = list(tokenize(source))
    assert tokens == [
        Token(T.nl, 0, 1, start_line=1, start_col=0, end_line=1, end_col=1),
        Token(T.whitespace, 1, 2, start_line=2, start_col=0, end_line=2, end_col=1),
        Token(T.number, 2, 3, start_line=2, start_col=1, end_line=2, end_col=2),
        Token(T.newline, 3, 4, start_line=2, start_col=2, end_line=2, end_col=3),
        Token(T.endmarker, 4, 4, start_line=3, start_col=0, end_line=3, end_col=0),
    ]


def test_nested_f_tstrings() -> None:
    source = '''t"foo {f'bar'} baz"'''
    tokens = list(tokenize(source))
    assert tokens == [
        Token(T.tstring_start, 0, 2, start_line=1, start_col=0, end_line=1, end_col=2),
        Token(T.tstring_middle, 2, 6, start_line=1, start_col=2, end_line=1, end_col=6),
        Token(T.lbrace, 6, 7, start_line=1, start_col=6, end_line=1, end_col=7),
        Token(T.fstring_start, 7, 9, start_line=1, start_col=7, end_line=1, end_col=9),
        Token(
            T.fstring_middle, 9, 12, start_line=1, start_col=9, end_line=1, end_col=12
        ),
        Token(
            T.fstring_end, 12, 13, start_line=1, start_col=12, end_line=1, end_col=13
        ),
        Token(T.rbrace, 13, 14, start_line=1, start_col=13, end_line=1, end_col=14),
        Token(
            T.tstring_middle, 14, 18, start_line=1, start_col=14, end_line=1, end_col=18
        ),
        Token(
            T.tstring_end, 18, 19, start_line=1, start_col=18, end_line=1, end_col=19
        ),
        Token(T.newline, 19, 20, start_line=1, start_col=19, end_line=1, end_col=20),
        Token(T.endmarker, 20, 20, start_line=2, start_col=0, end_line=2, end_col=0),
    ]


def test_dedent_after_escaped_nl() -> None:
    source = "if True:\n    if \\\nTrue:\n        pass\n    pass\npass"
    tokens = list(tokenize(source))
    assert tokens == [
        Token(T.identifier, 0, 2, start_line=1, start_col=0, end_line=1, end_col=2),
        Token(T.whitespace, 2, 3, start_line=1, start_col=2, end_line=1, end_col=3),
        Token(T.identifier, 3, 7, start_line=1, start_col=3, end_line=1, end_col=7),
        Token(T.op, 7, 8, start_line=1, start_col=7, end_line=1, end_col=8),
        Token(T.newline, 8, 9, start_line=1, start_col=8, end_line=1, end_col=9),
        Token(T.indent, 9, 13, start_line=2, start_col=0, end_line=2, end_col=4),
        Token(T.identifier, 13, 15, start_line=2, start_col=4, end_line=2, end_col=6),
        Token(T.whitespace, 15, 16, start_line=2, start_col=6, end_line=2, end_col=7),
        Token(T.whitespace, 16, 18, start_line=2, start_col=7, end_line=3, end_col=0),
        Token(T.identifier, 18, 22, start_line=3, start_col=0, end_line=3, end_col=4),
        Token(T.op, 22, 23, start_line=3, start_col=4, end_line=3, end_col=5),
        Token(T.newline, 23, 24, start_line=3, start_col=5, end_line=3, end_col=6),
        Token(T.indent, 24, 32, start_line=4, start_col=0, end_line=4, end_col=8),
        Token(T.identifier, 32, 36, start_line=4, start_col=8, end_line=4, end_col=12),
        Token(T.newline, 36, 37, start_line=4, start_col=12, end_line=4, end_col=13),
        Token(T.whitespace, 37, 41, start_line=5, start_col=0, end_line=5, end_col=4),
        Token(T.dedent, 41, 41, start_line=5, start_col=4, end_line=5, end_col=4),
        Token(T.identifier, 41, 45, start_line=5, start_col=4, end_line=5, end_col=8),
        Token(T.newline, 45, 46, start_line=5, start_col=8, end_line=5, end_col=9),
        Token(T.whitespace, 46, 46, start_line=6, start_col=0, end_line=6, end_col=0),
        Token(T.dedent, 46, 46, start_line=6, start_col=0, end_line=6, end_col=0),
        Token(T.identifier, 46, 50, start_line=6, start_col=0, end_line=6, end_col=4),
        Token(T.newline, 50, 51, start_line=6, start_col=4, end_line=6, end_col=5),
        Token(T.endmarker, 51, 51, start_line=7, start_col=0, end_line=7, end_col=0),
    ]

    source = "if True:\n    if \\\nTrue:\n        pass\n    pass"
    tokens = list(tokenize(source))
    assert tokens == [
        Token(T.identifier, 0, 2, start_line=1, start_col=0, end_line=1, end_col=2),
        Token(T.whitespace, 2, 3, start_line=1, start_col=2, end_line=1, end_col=3),
        Token(T.identifier, 3, 7, start_line=1, start_col=3, end_line=1, end_col=7),
        Token(T.op, 7, 8, start_line=1, start_col=7, end_line=1, end_col=8),
        Token(T.newline, 8, 9, start_line=1, start_col=8, end_line=1, end_col=9),
        Token(T.indent, 9, 13, start_line=2, start_col=0, end_line=2, end_col=4),
        Token(T.identifier, 13, 15, start_line=2, start_col=4, end_line=2, end_col=6),
        Token(T.whitespace, 15, 16, start_line=2, start_col=6, end_line=2, end_col=7),
        Token(T.whitespace, 16, 18, start_line=2, start_col=7, end_line=3, end_col=0),
        Token(T.identifier, 18, 22, start_line=3, start_col=0, end_line=3, end_col=4),
        Token(T.op, 22, 23, start_line=3, start_col=4, end_line=3, end_col=5),
        Token(T.newline, 23, 24, start_line=3, start_col=5, end_line=3, end_col=6),
        Token(T.indent, 24, 32, start_line=4, start_col=0, end_line=4, end_col=8),
        Token(T.identifier, 32, 36, start_line=4, start_col=8, end_line=4, end_col=12),
        Token(T.newline, 36, 37, start_line=4, start_col=12, end_line=4, end_col=13),
        Token(T.whitespace, 37, 41, start_line=5, start_col=0, end_line=5, end_col=4),
        Token(T.dedent, 41, 41, start_line=5, start_col=4, end_line=5, end_col=4),
        Token(T.identifier, 41, 45, start_line=5, start_col=4, end_line=5, end_col=8),
        Token(T.newline, 45, 46, start_line=5, start_col=8, end_line=5, end_col=9),
        Token(T.dedent, 46, 46, start_line=6, start_col=0, end_line=6, end_col=0),
        Token(T.endmarker, 46, 46, start_line=6, start_col=0, end_line=6, end_col=0),
    ]

    source = "if True:\n    if \\\nTrue:\n        pass\npass"
    tokens = list(tokenize(source))
    assert tokens == [
        Token(T.identifier, 0, 2, start_line=1, start_col=0, end_line=1, end_col=2),
        Token(T.whitespace, 2, 3, start_line=1, start_col=2, end_line=1, end_col=3),
        Token(T.identifier, 3, 7, start_line=1, start_col=3, end_line=1, end_col=7),
        Token(T.op, 7, 8, start_line=1, start_col=7, end_line=1, end_col=8),
        Token(T.newline, 8, 9, start_line=1, start_col=8, end_line=1, end_col=9),
        Token(T.indent, 9, 13, start_line=2, start_col=0, end_line=2, end_col=4),
        Token(T.identifier, 13, 15, start_line=2, start_col=4, end_line=2, end_col=6),
        Token(T.whitespace, 15, 16, start_line=2, start_col=6, end_line=2, end_col=7),
        Token(T.whitespace, 16, 18, start_line=2, start_col=7, end_line=3, end_col=0),
        Token(T.identifier, 18, 22, start_line=3, start_col=0, end_line=3, end_col=4),
        Token(T.op, 22, 23, start_line=3, start_col=4, end_line=3, end_col=5),
        Token(T.newline, 23, 24, start_line=3, start_col=5, end_line=3, end_col=6),
        Token(T.indent, 24, 32, start_line=4, start_col=0, end_line=4, end_col=8),
        Token(T.identifier, 32, 36, start_line=4, start_col=8, end_line=4, end_col=12),
        Token(T.newline, 36, 37, start_line=4, start_col=12, end_line=4, end_col=13),
        Token(T.whitespace, 37, 37, start_line=5, start_col=0, end_line=5, end_col=0),
        Token(T.dedent, 37, 37, start_line=5, start_col=0, end_line=5, end_col=0),
        Token(T.dedent, 37, 37, start_line=5, start_col=0, end_line=5, end_col=0),
        Token(T.identifier, 37, 41, start_line=5, start_col=0, end_line=5, end_col=4),
        Token(T.newline, 41, 42, start_line=5, start_col=4, end_line=5, end_col=5),
        Token(T.endmarker, 42, 42, start_line=6, start_col=0, end_line=6, end_col=0),
    ]

    source = "if True:\n    if \\\nTrue:\n        pass\n"
    tokens = list(tokenize(source))
    assert tokens == [
        Token(T.identifier, 0, 2, start_line=1, start_col=0, end_line=1, end_col=2),
        Token(T.whitespace, 2, 3, start_line=1, start_col=2, end_line=1, end_col=3),
        Token(T.identifier, 3, 7, start_line=1, start_col=3, end_line=1, end_col=7),
        Token(T.op, 7, 8, start_line=1, start_col=7, end_line=1, end_col=8),
        Token(T.newline, 8, 9, start_line=1, start_col=8, end_line=1, end_col=9),
        Token(T.indent, 9, 13, start_line=2, start_col=0, end_line=2, end_col=4),
        Token(T.identifier, 13, 15, start_line=2, start_col=4, end_line=2, end_col=6),
        Token(T.whitespace, 15, 16, start_line=2, start_col=6, end_line=2, end_col=7),
        Token(T.whitespace, 16, 18, start_line=2, start_col=7, end_line=3, end_col=0),
        Token(T.identifier, 18, 22, start_line=3, start_col=0, end_line=3, end_col=4),
        Token(T.op, 22, 23, start_line=3, start_col=4, end_line=3, end_col=5),
        Token(T.newline, 23, 24, start_line=3, start_col=5, end_line=3, end_col=6),
        Token(T.indent, 24, 32, start_line=4, start_col=0, end_line=4, end_col=8),
        Token(T.identifier, 32, 36, start_line=4, start_col=8, end_line=4, end_col=12),
        Token(T.newline, 36, 37, start_line=4, start_col=12, end_line=4, end_col=13),
        Token(T.dedent, 37, 37, start_line=5, start_col=0, end_line=5, end_col=0),
        Token(T.dedent, 37, 37, start_line=5, start_col=0, end_line=5, end_col=0),
        Token(T.endmarker, 37, 37, start_line=5, start_col=0, end_line=5, end_col=0),
    ]
