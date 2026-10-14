# countdown-api

The contract between the countdown renderer ([pi-dashboard](https://github.com/nvorkinn/pi-dashboard)) and
[auth-broker](https://github.com/nvorkinn/auth-broker), as one OpenAPI file, [`openapi.yaml`](openapi.yaml), and the
code generated from it.

## How it is built

This repository depends on [openapi-codegen](https://github.com/nvorkinn/openapi-codegen), as a **release** of it:
`pyproject.toml` points at the release's wheel and `uv.lock` records its hash. `scripts/build.py` runs it on
`openapi.yaml` and archives what it generates:

| file | contains | for |
| --- | --- | --- |
| `countdown_api-client.tar.gz` | the Pydantic models and a `requests` client | the renderer |
| `countdown_api-server.tar.gz` | the Pydantic models and Flask views | the broker |

Each unpacks to a `countdown_api/` package. The archives are reproducible (same input, same bytes). To build them
yourself: `uv sync --frozen && uv run --frozen python scripts/build.py` (they land in `build/`).

## Using it

Always the latest release, whichever version of whichever repo is asking:

    https://github.com/nvorkinn/countdown-api/releases/latest/download/openapi.yaml
    https://github.com/nvorkinn/countdown-api/releases/latest/download/countdown_api-client.tar.gz
    https://github.com/nvorkinn/countdown-api/releases/latest/download/countdown_api-server.tar.gz
    https://github.com/nvorkinn/countdown-api/releases/latest/download/SHA256SUMS

Consumers download the archive for their side on every build and unpack it into their tree, so neither runs
the generator, and a build fails when its code no longer fits the contract.

The same release is published as a website, https://nvorkinn.github.io/countdown-api/: every file of it at fixed
addresses, `latest.json` (version, checksums, release link) and a page showing the current version. It needs
Settings > Pages > Source set to "GitHub Actions" and a `v*` tag rule on the `github-pages` environment
(Settings > Environments), since releases are deployed from tags.

## Changing it

Edit `openapi.yaml` in a PR (CI builds everything from it, checks it and imports the result). To publish, push a tag
`v<version>` on main; the release workflow stamps the version into the contract, builds the code from it and makes it
the latest release. Because devices in the field keep running older renderers, change the contract additively: new
optional fields and new operations are safe, removing or tightening something needs both sides released together.
