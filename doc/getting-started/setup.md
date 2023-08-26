# Setup

## ETAPI

To use TriliumAlchemy, you need to connect to Trilium through its ETAPI interface. See Trilium's documentation for details: <https://github.com/zadam/trilium/wiki/ETAPI>

```{note}
For SDK use, once you've selected a method, create a {obj}`Session` and pass the appropriate argument: either `token` or `password`. See {ref}`sessions` for details.
```

### Token

This is the recommended mechanism. Create a new token in the UI from Options &rarr; ETAPI.

### Password

If you provide a password, a temporary token is created for you. This token is deleted when you invoke {obj}`Session.logout` or exit a context using `with`{l=python}.

## Tool config (coming soon)

There will be a config file format and .env file support for configuring CLI tools.
