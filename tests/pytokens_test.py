from pytokens import tokenize, Token, TokenType


def test_tokenize() -> None:
    source = "def foo():\n    7.e1\n"
    tokens = list(tokenize(source))
    assert tokens == [
        Token(
            TokenType.identifier, 0, 3, start_line=1, start_col=0, end_line=1, end_col=3
        ),
        Token(
            TokenType.whitespace, 3, 4, start_line=1, start_col=3, end_line=1, end_col=4
        ),
        Token(
            TokenType.identifier, 4, 7, start_line=1, start_col=4, end_line=1, end_col=7
        ),
        Token(TokenType.lparen, 7, 8, start_line=1, start_col=7, end_line=1, end_col=8),
        Token(TokenType.rparen, 8, 9, start_line=1, start_col=8, end_line=1, end_col=9),
        Token(TokenType.op, 9, 10, start_line=1, start_col=9, end_line=1, end_col=10),
        Token(
            TokenType.newline,
            10,
            11,
            start_line=1,
            start_col=10,
            end_line=1,
            end_col=11,
        ),
        Token(
            TokenType.indent, 11, 15, start_line=2, start_col=0, end_line=2, end_col=4
        ),
        Token(
            TokenType.number,
            15,
            19,
            start_line=2,
            start_col=4,
            end_line=2,
            end_col=8,
        ),
        Token(
            TokenType.newline, 19, 20, start_line=2, start_col=8, end_line=2, end_col=9
        ),
        Token(
            TokenType.dedent, 20, 20, start_line=3, start_col=0, end_line=3, end_col=0
        ),
        Token(
            TokenType.endmarker,
            20,
            20,
            start_line=3,
            start_col=0,
            end_line=3,
            end_col=0,
        ),
    ]

    # https://github.com/psf/black/issues/3700
    source = "{\r}"
    tokens = list(tokenize(source))
    assert tokens == [
        Token(TokenType.lbrace, 0, 1, start_line=1, start_col=0, end_line=1, end_col=1),
        Token(TokenType.rbrace, 1, 3, start_line=1, start_col=1, end_line=1, end_col=3),
        Token(
            TokenType.newline, 3, 4, start_line=1, start_col=3, end_line=1, end_col=4
        ),
        Token(
            TokenType.endmarker, 4, 4, start_line=2, start_col=0, end_line=2, end_col=0
        ),
    ]
