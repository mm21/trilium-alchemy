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

## Running tests

```{note}
Please use a separate, "disposable" Trilium instance to run the tests. Running the full suite creates and deletes over 70 notes, and one of the tests deletes any existing notes. The runner will detect existing notes and require you to pass `--clobber` if you want it to proceed running tests, acknowledging existing notes may be deleted.
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