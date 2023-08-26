(sessions)=
# Sessions

In TriliumAlchemy, the {obj}`Session` is the fundamental interface to interact with Trilium. It implements a [unit of work](https://martinfowler.com/eaaCatalog/unitOfWork.html) pattern, much like [SQLAlchemy's `Session`](https://docs.sqlalchemy.org/en/20/orm/session.html).

As you make changes to Trilium objects, their state is maintained in a {obj}`Session`. When you're done making changes and invoke {obj}`Session.flush`, the unit of work dependency solver determines the order in which to commit changes to Trilium and commits them. For example, new notes need to be created before their attributes.

```{note}
In Trilium, there are 3 kinds of objects:

- {obj}`Note`
- {obj}`Attribute`, divided into {obj}`Label` and {obj}`Relation`
- {obj}`Branch`

These are collectively referred to as "entities", both in 
Trilium's implementation and this project (see {obj}`Entity`).
```

By default, creating a {obj}`Session` registers it as the default (`default=True`{l=python}). Unless a default is registered, it's required to pass a {obj}`Session` when creating an entity.

```{warning}
One benefit of the unit of work pattern in databases is the fact that  changes can be committed in a [transaction](https://en.wikipedia.org/wiki/Database_transaction). As TriliumAlchemy uses the ETAPI interface provided by Trilium, it's currently not possible to commit changes within a transaction. This means if an error is encountered, it may leave your notes in an unexpected state with some changes committed and some not.

TriliumAlchemy does its best to validate that changes will be successful, and fail before making any changes if not.
```

## Authentication

Authentication is supported via token or password. If using a password, Trilium will create a token for you on the fly. This token will persist until {obj}`Session.logout` is invoked to delete it, or you exit a context.

## Basic usage

Instantiate a {obj}`Session` as follows:

```
from trilium_alchemy import Session

# your host here
HOST = "http://localhost"

# your token here
TOKEN = "YmcEF6jAWOSv_98jMiIoXEuFHofPqffmjrzS8zOOiLm7Q1DwjS8641YA="

session = Session(HOST, token=TOKEN)
```

You can then interact with Trilium in various ways as documented in the {ref}`API <trilium_alchemy>`. For example, perform a note search to get todos:

```
todo_list = session.search('#todo')
```

Then [clone](https://github.com/zadam/trilium/wiki/Cloning-notes) them to today's [Day note](https://github.com/zadam/trilium/wiki/Day-notes) using {obj}`Session.get_today_note`:

```
today = session.get_today_note()

today += todo_list
```

When you're done making changes, don't forget to call {obj}`Session.flush` to commit them:

```
session.flush()
```

## Context manager

The {obj}`Session` implements a context manager, providing a clean way to localize changes and automatically commit them.

For example:

```
with Session(HOST, token=TOKEN) as session:

    # create a new note under root
    note = Note(title="My note", parents={session.root})

    # session.flush() will be invoked automatically
```

This creates a new {obj}`Note` as a child of the root note, provided for convenience as {obj}`Session.root`.

Upon exiting the context, changes will automatically be committed via {obj}`Session.flush`.

If you had provided a `password` instead of `token`, exiting a context will additionally invoke {obj}`Session.logout` which would otherwise be required in order to delete your temporary token.

## Direct ETAPI access

TriliumAlchemy uses an [API client](https://github.com/mm21/trilium-client) generated by [OpenAPI Generator](https://openapi-generator.tech) to interface with Trilium. This provides [Pydantic](https://docs.pydantic.dev/latest/) models and a nice interface generated from Trilium's `etapi.openapi.yaml`.

The API object is provided as {obj}`Session.api` for direct ETAPI access, although TriliumAlchemy wraps all supported APIs.

## Roadmap

It's planned to generalize the {obj}`Session` to accommodate other types of note tree stores, namely {ref}`filesystems <fs-spec>` and possibly external databases like [CouchDB](https://couchdb.apache.org/).

The {obj}`Session` will then become the basis for synchronization capability. It's anticipated that you will be able to instantiate multiple {obj}`Session`s and synchronize them using a sync context, enabling sync between Trilium and a filesystem or even other Trilium instances.