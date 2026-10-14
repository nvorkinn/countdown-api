# countdown-api

The contract between the countdown renderer ([pi-dashboard](https://github.com/nvorkinn/pi-dashboard)) and
[auth-broker](https://github.com/nvorkinn/auth-broker), as one OpenAPI file, [`openapi.yaml`](openapi.yaml), and the
code generated from it, published as an ordinary Python package.

## How it is built

This repository depends on [openapi-codegen](https://github.com/nvorkinn/openapi-codegen), as a **release** of it:
`pyproject.toml` points at the release's wheel and `uv.lock` records its hash. The workflows run its command line on
`openapi.yaml`, which writes the `countdown_api` package (the Pydantic models, a `requests` client and Flask views)
into `src/`, and then build the wheel, `countdown_api-<version>-py3-none-any.whl`. The wheel also carries the contract
(`countdown_api/openapi.yaml`). `src/` isn't committed. By hand:

    uv sync --frozen --no-install-project
    uv run --frozen --no-sync openapi-codegen openapi.yaml --out src/countdown_api
    cp openapi.yaml src/countdown_api/
    uv build --wheel

## Using it

Depend on it like any package. Each side installs the extra it needs, so the renderer doesn't need Flask and the
broker doesn't need `requests`:

| side | dependency | imports |
| --- | --- | --- |
| the renderer | `countdown-api[client]` | `countdown_api.models`, `countdown_api.clients` |
| the broker | `countdown-api[server]` | `countdown_api.models`, `countdown_api.blueprints` |

The package isn't on PyPI. Its **latest page**, https://nvorkinn.github.io/countdown-api/, is a flat package index
that always lists the latest release's wheel, so a project finds the current version there. In `pyproject.toml`:

```toml
[project]
dependencies = ["countdown-api[client]"]

[[tool.uv.index]]
name = "countdown-api"
url = "https://nvorkinn.github.io/countdown-api/"
format = "flat"
explicit = true            # only for the packages that name it below: nothing else is looked up here

[tool.uv.sources]
countdown-api = { index = "countdown-api" }
```

`uv lock --upgrade-package countdown-api` reads the page and records the latest version, with the wheel's hash, in
`uv.lock`; `uv sync --frozen` then installs exactly that. The page links the wheel at its address on the release,
which stays valid after the next release replaces the page, so an older lockfile keeps working until you upgrade.

The page also publishes `constraints.txt`, which pins only `countdown-api` to the latest release. Keep it ranged in
`pyproject.toml` and let this file choose the version:

```
uv sync --constraints https://nvorkinn.github.io/countdown-api/constraints.txt
uv pip install -r pyproject.toml -c https://nvorkinn.github.io/countdown-api/constraints.txt
export UV_CONSTRAINT=https://nvorkinn.github.io/countdown-api/constraints.txt   # applies to every uv command
```

`UV_OVERRIDE` / `--override` works the same way, and also overrides what transitive dependencies require.

The same page has `latest.json` (version, checksums, release link), `openapi.yaml` and `SHA256SUMS`. It needs
Settings > Pages > Source set to "GitHub Actions" and a `v*` tag rule on the `github-pages` environment
(Settings > Environments), since releases are deployed from tags.

## Changing it

Edit `openapi.yaml` in a PR (CI builds the wheel from it and installs it with each extra). To publish, push a tag
`v<version>` on main; the release workflow stamps the version into the contract and the wheel, builds them and makes
that the latest release. Because devices in the field keep running older renderers, change the contract additively:
new optional fields and new operations are safe, removing or tightening something needs both sides released together.
