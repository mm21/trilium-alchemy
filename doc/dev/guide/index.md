# Developer guide

Contributions are welcome, but please reach out first so work can be coordinated. This guide will walk you through setting up your environment and running tests.

## Setup

Ensure that [Poetry](https://python-poetry.org/) is installed before proceeding.

```bash
pip install poetry
```

### Installation

First, clone the repository:

```bash
git clone https://github.com/mm21/trilium-alchemy.git
cd trilium-alchemy
```

Install the dependencies:

```bash
poetry install --with=dev
```

And then activate a shell:

```bash
poetry shell
```

### Environment

From the root folder, copy `.env.example` to `.env` and fill in the variables. Not all tests require all of them, e.g. `TRILIUM_DATA_DIR` is only used to verify that backups were created. However it's encouraged to provide all of them so you can run all the tests.

## Command-line targets

There are a number of `doit` tasks to facilitate development workflows. Targets are generated in a corresponding folder under the top-level `__out__` folder (e.g. `__out__/doc/html`).

Simply run `doit` with the corresponding task name:

- `format`: Runs formatters: `autoflake`, `isort`, `black`, `toml-sort`
- `doc`: Builds HTML documentation
- `analysis`: Runs `mypy` and `pyright`
- `test`: Runs tests and generates coverage reports (HTML, XML, `.coverage`)
- `badges`: Parses test reports and updates pytest and coverage badges

For example, to run all tests and generate reports, run `doit test`.

## Running tests

```{warning}
Please use a separate, "disposable" Trilium instance to run the tests. Running the full suite creates and deletes 100+ notes within a short amount of time, cluttering your database. Additionally there is the potential to expose bugs (in either TriliumAlchemy or Trilium itself), however unlikely, which could corrupt your data.

The runner will detect existing notes and require you to pass `--clobber` if you want it to proceed running tests, acknowledging existing data may be inadvertently deleted if e.g. there is such a bug.
```

Run `pytest` followed by an optional path/test filter, e.g.:

```bash
pytest test/note/test_note.py::test_create
```

## Developing tests

### Fixtures

To get a new {obj}`Session` and a new {obj}`Note` for testing, simply create a test (function starting with `test`) which takes arguments called `session` and `note` respectively. For example:

```python
def test_create(session: Session, note: Note):
    ...
```

Here a new {obj}`Session` will be created, along with a new {obj}`Note`. The note is automatically deleted after the test exits.

Fixtures use ETAPI requests directly to avoid relying on the code under test.

### Markers

Markers are useful to configure certain things about the created {obj}`Note` under test, e.g. which attributes it has. For example, `test/attribute/test_accessors.py::test_index_del` uses such a marker to create an attribute in order to test deleting it.

```python
@mark.attribute("label1")
def test_index_del(session: Session, note: Note):
    assert note["label1"] == ""
    ...
```
