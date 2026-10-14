# countdown-api

The contract between the countdown renderer ([pi-dashboard](https://github.com/nvorkinn/pi-dashboard)) and
[auth-broker](https://github.com/nvorkinn/auth-broker), as one OpenAPI file, [`openapi.yaml`](openapi.yaml), and the
code generated from it.

## How it is built

This repository depends on [openapi-codegen](https://github.com/nvorkinn/openapi-codegen), as a **release** of it:
`pyproject.toml` points at the release's wheel and `uv.lock` records its hash. The workflows run its command line on
`openapi.yaml` and archive what it generates:

`countdown_api.tar.gz` holds the whole generated `countdown_api/` package: the Pydantic models (`models.py`), the
`requests` client (`clients/`) and the Flask views (`blueprints/`). Each side imports only what it needs, so the
renderer doesn't need Flask and the broker doesn't need `requests`; unpack it and use your half.

The archive is reproducible (same input, same bytes). The commands
are in `.github/workflows/ci.yml`; `uv sync --frozen`, then `uv run --frozen openapi-codegen openapi.yaml --out
some/countdown_api` does it by hand.

## Using it

Always the latest release, whichever version of whichever repo is asking:

    https://github.com/nvorkinn/countdown-api/releases/latest/download/openapi.yaml
    https://github.com/nvorkinn/countdown-api/releases/latest/download/countdown_api.tar.gz
    https://github.com/nvorkinn/countdown-api/releases/latest/download/SHA256SUMS

Consumers download the archive on every build and unpack it into their tree, so neither runs
the generator, and a build fails when its code no longer fits the contract.

The same release is published as a website, https://nvorkinn.github.io/countdown-api/: every file of it at fixed
addresses, `latest.json` (version, checksums, release link) and a page showing the current version. It needs
Settings > Pages > Source set to "GitHub Actions" and a `v*` tag rule on the `github-pages` environment
(Settings > Environments), since releases are deployed from tags.

## Changing it

Edit `openapi.yaml` in a PR (CI builds the code from it and imports the result). To publish, push a tag
`v<version>` on main; the release workflow stamps the version into the contract, builds the code from it and makes it
the latest release. Because devices in the field keep running older renderers, change the contract additively: new
optional fields and new operations are safe, removing or tightening something needs both sides released together.
