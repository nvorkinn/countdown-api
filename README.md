# countdown-api

The contract between the countdown renderer ([pi-dashboard](https://github.com/nvorkinn/pi-dashboard)) and
[auth-broker](https://github.com/nvorkinn/auth-broker), as one OpenAPI file, [`openapi.yaml`](openapi.yaml), and the
code generated from it, published as an ordinary Python package.

## How it is built

This repository depends on [openapi-codegen](https://github.com/nvorkinn/openapi-codegen), as a **release** of it:
`pyproject.toml` points at the release's wheel and `uv.lock` records its hash. The workflows run its command line on
`openapi.yaml`, which writes the `countdown_api` package (the Pydantic models, a `requests` client and a registry for
the Flask server) into `src/`, and then build the wheel, `countdown_api-<version>-py3-none-any.whl`. The wheel also
carries the contract (`countdown_api/openapi.yaml`). `src/countdown_api` is committed too, so that a change to the
contract shows up as a change to the code; regenerate it with `python generate.py`. By hand:

    uv sync --frozen --no-install-project
    uv run --frozen --no-sync openapi-codegen openapi.yaml --out src/countdown_api --package countdown_api
    cp openapi.yaml src/countdown_api/
    uv build --wheel

All of it, generated code included, passes `ruff` with `select = ["ALL"]`.

## Using it

Depend on it like any package. Each side installs the extra it needs, so the renderer doesn't need Flask and the
broker doesn't need `requests`:

| side | dependency | imports |
| --- | --- | --- |
| the renderer | `countdown-api[client]` | `countdown_api.models`, `countdown_api.clients` |
| the broker | `countdown-api[server]` | `countdown_api.models`, `countdown_api.blueprints` |

`ConfigResponse.clock_format` is the application-wide format for user-facing clock times: `"12h"` or `"24h"`.
It is optional and defaults to `"24h"` when absent, so older brokers retain the existing behavior; explicit `null`
and other values are invalid. It does not change machine timestamps, durations, time zones or log formats.
Brokers should explicitly supply the saved value when constructing the response, since unset defaults are omitted
from the JSON response.

`ConfigResponse.language` (`"en"` or `"nb"`) is the language of everything the screen shows, and
`ConfigResponse.timezone` (an IANA name such as `"Europe/Oslo"`) is the screen's local time, for its clock and for what
counts as today. Both are optional, defaulting to `"en"` and `"Europe/London"`.

`ConfigResponse.departures` lists every stop the screen shows departures for, each with its `source` (`"tfl"` or
`"entur"`) and its `id` there, in the owner's order, plus the `style` they're drawn in. A renderer that reads it ignores
`tfl.stop_ids` and `tfl.style`; `tfl` keeps carrying the TfL stops alone, so a renderer that predates `departures` never
gets an id it can't look up. `NoticeBoard.country` (`"GB"` or `"NO"`) says whose postcode `notice_board.postcode` is;
without it, it is taken to be British.

`Tfl` carries no TfL key. The renderer reads the departures and TfL's disruptions from the store, and the providers
that fill it read TfL's key from their own environment. The `app_key` it used to carry is gone; the models ignore
fields they don't know, so a broker that still sends it is still read.

`ConfigResponse.style` (`"airy"`, `"hero"` or `"card"`) is the one look every panel is drawn in. A renderer that reads
it ignores the panels' own `style` fields (`tfl`, `departures`, `spotify`, `notice_board`), which a broker keeps
sending so older renderers still get a look they know (the shared `airy` is their `grouped` for the departures). It is
optional and defaults to null, which leaves the renderer on the panels' own fields.

`ConfigResponse.developer` switches the developer panel (GitHub pull requests and builds, AI plans) on with
`enabled`. It carries no token: the broker keeps the GitHub token, and its developer provider fills the store with the
panel's data, which the renderer reads. It is optional and defaults to null, which leaves the panel off.

`Glowmarkt.enabled` (required) switches the energy panel on. It carries no credentials: the broker's Glowmarkt
provider signs in and fills the store, which the renderer reads. The `username` and `password` it used to carry are
gone; the models ignore fields they don't know, so a broker that still sends them as null is still read.

`Weather.key` is the key the screen's weather is kept under in the store (the renderer reads `v1:weather:<key>`): for a
place picked on the settings page it is the place's name, country and Open-Meteo id (`london-gb-2643743`), so screens
that picked the same place share one forecast however its name was typed. `Weather.location` stays the place's name.
`key` is optional and defaults to null, which an older broker sends; a renderer then reads the weather under
`location`, as before `key`.

`Weather.api_key` is unused and on its way out: the renderer reads the weather from the store, and the weather
provider fills it from Open-Meteo, which needs no key. It is optional and defaults to `""`, so a renderer built on
this contract reads a broker that leaves it out. Renderers built before it was optional require it, so a broker keeps
sending it, empty and explicitly (an unset default is left out of the response), until none of those renderers is
left; then the broker stops and the field goes.

The server registers a handler for every operation and an authenticator for every security scheme; registering
checks that nothing is missing, so adding an operation to `openapi.yaml` fails the broker's startup (and its tests)
until it is implemented. The roles an operation allows are the scopes in its `security`:

```python
from countdown_api.blueprints import Api, ApiHTTPError

api = Api()


@api.authenticator("deviceSecret", provides=("device_id",))
def device_secret(context):  # context.credential: the bearer token; context.scopes: ("renderer",)
    ...  # look the device up; raise ApiHTTPError(401) or (403); return {"device_id": ...}


@api.get_config(decorators=[...])  # optional: filters that aren't part of the contract, outermost first
def get_config(*, device_id, x_device_name=None): ...


api.register(app)  # raises RegistrationError, naming everything that is missing or doesn't fit
```

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

The page also publishes `requirements.txt`, which is just the URL of the latest wheel
(`uv pip install -r https://nvorkinn.github.io/countdown-api/requirements.txt`), and `constraints.txt`, which pins only `countdown-api` to the latest release. Keep it ranged in
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

Edit `openapi.yaml` in a PR and run `python generate.py` to update the committed `src/countdown_api` (CI fails with "out of date" if you forget; it then builds the wheel and installs it with each extra). To publish, push a tag
`v<version>` on main; the release workflow stamps the version into the contract and the wheel, builds them and makes
that the latest release. Because devices in the field keep running older renderers, change the contract additively:
new optional fields and new operations are safe, removing or tightening something needs both sides released together.
