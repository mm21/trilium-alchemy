# Developer guide

Contributions are welcome, but please reach out first so work can be coordinated. This guide will walk you through setting up your environment and running tests.

## Setup

### Installation

Install the dependencies by activating a shell:

```bash
poetry shell
```

And then running:

```bash
poetry install --with=dev
```

### Environment

From the root folder, copy `.env.example` to `.env` and fill in the variables. Not all tests require all of them, e.g. `TRILIUM_DATA_DIR` is only used to verify that backups were created. However it's encouraged to provide all of them so you can run all the tests.

## Command-line targets

There are a number of scons aliases to facilitate development workflows. Targets are generated in a corresponding folder under the top-level `build` folder (e.g. `build/doc/html`).

- `test`: Runs tests and generates coverage reports (HTML, XML, `.coverage`)
- `badges`: Parses test reports and updates pytest/coverage badges
- `mypy`: Runs mypy and generates reports (HTML, XML)
- `pyright`: Runs pyright and generates JSON report
    - Note: since pyright outputs JSON to stdout rather than writing to a file, it's suggested to run `pyright` manually to see individual errors
- `analysis`: Alias for `mypy pyright`
- `doc`: Builds HTML documentation
- `format`: Runs `black` and `toml-sort` (for pyproject.toml)

For example, to run all tests and generate reports, run `scons test`.

## Running tests

```{note}
Please use a separate, "disposable" Trilium instance to run the tests. Running the full suite creates and deletes over 70 notes within a short amount of time.

The runner will detect existing notes and require you to pass `--clobber` if you want it to proceed running tests, acknowledging existing data may be inadvertently deleted if e.g. there is a bug. Such bugs may, in the worst case, put Trilium into an unexpected state or corrupt data.
```

Run `pytest` followed by an optional path/test filter, e.g.:

```bash
pytest test/note/test_attributes.py::test_create
```

## Developing tests

### Fixtures

To get a new {obj}`Session` and a new {obj}`Note` for testing, simply create a test (function starting with `test`) which takes arguments called `session` and `note` respectively. For example:

```python
def test_create(session: Session, note: Note):
    ...
```

Here a new {obj}`Session` will be created, along with a new {obj}`Note`. The note is automatically deleted after the test exits.

### Markers

Markers are useful to configure certain things about the created {obj}`Note` under test, e.g. which attributes it has. For example, `test/attribute/test_helpers.py::test_index_del` uses such a marker to create an attribute in order to test deleting it.

```python
@mark.attribute("label1")
def test_index_del(session: Session, note: Note):
    assert note["label1"] == ""
    ...
```
