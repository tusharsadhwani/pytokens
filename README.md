# pytokens

A Fast, spec compliant Python 3.12+ tokenizer that runs on older Pythons.

## Installation

```bash
pip install pytokens
```

## Usage

```bash
python -m pytokens path/to/file.py
```

## Local Development / Testing

- Create and activate a virtual environment
- Run `pip install -r requirements-dev.txt` to do an editable install
- Run `pytest` to run tests

## Type Checking

Run `mypy .`

## Create and upload a package to PyPI

Make sure to bump the version in `setup.cfg`.

Then run the following commands:

```bash
rm -rf dist
python -m build
```

Then upload it to PyPI using [twine](https://twine.readthedocs.io/en/latest/#installation):

```bash
twine upload dist/*
```
