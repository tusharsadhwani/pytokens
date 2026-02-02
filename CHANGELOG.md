# Changelog

## v0.4.1

- Avoid emitting dedents after an escaped new line
- Add `--json` support to the CLI
- Fix quiet mode in the CLI

## v0.4.0

- Improve performance by removing slicing in `TokenIterator.name` that can cause quadratic behaviour
- Use mypyc for compilation for a 2.5x performance improvement
- Various packaging improvements
