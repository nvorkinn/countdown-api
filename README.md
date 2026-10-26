# countdown-api: the countdown store contract

[auth-broker](https://github.com/nvorkinn/auth-broker) (the config site) and
[countdown](https://github.com/nvorkinn/countdown) (the providers and the render pool) don't talk to each other
over HTTP. They share a Redis, and that is all they share. This repository is the contract for it: every key and
channel that crosses between them, what each holds, its TTL, who writes it and who reads it, the Lua script both run,
and the canonical examples both sides' tests check against. It is one file, [`store.yaml`](store.yaml), and the
Python package generated from it, `countdown_api`. (The repository keeps its old name; the HTTP API it was named for
is gone.)

## What's in the contract

| key | Redis type | value (schema) | TTL | written by | read by |
| --- | --- | --- | --- | --- | --- |
| `v1:sub:<source>` | set | `Subscription` | none | auth-broker, on every config save | countdown's providers |
| `v1:sub:changed` | channel | `SubChanged` (empty) | | auth-broker, after the sets | every provider |
| `v1:config:<device id>` | string, JSON | `ConfigResponse` | none | auth-broker | the render pool |
| `v1:pairing:<device id>` | string, JSON | `PairingConfig` | 600 s, the code's own | auth-broker | the render pool |
| `v1:render:screens` | hash | `RenderScreens` (device id to slug) | none | auth-broker | the render pool |
| `v1:render:jobs` | list | `RenderJobs` (device ids) | none | the enqueue script | the render workers |
| `v1:render:queued:<device id>` | string | `RenderQueuedFlag` | 60,000 ms | the enqueue script | the claim script |
| `v1:frame:<device id>` | hash, bytes | `FrameRecord` | 86,400 s | the render pool | auth-broker |
| `v1:energy:<device id>` | string, JSON | `StoredEnergy` | 86,400 s | auth-broker's glow provider | the energy panel |
| `v1:spotify:<device id>` | string, JSON | `StoredPlayer` | 180 s | auth-broker's music provider | the Spotify area |
| `v1:spotify-top:<device id>` | string, JSON | `StoredTop` | 7,200 s | auth-broker's music provider | the Spotify area |
| `v1:art:<sha1 of the URL>` | string, bytes | `AlbumArt` | 300 s | auth-broker's music provider | the Spotify area |
| `v1:developer:<device id>` | string, JSON | `StoredDeveloper` | 900 s | auth-broker's developer provider | the developer panel |
| `v1:pace:<source>:<id>` | string | `Pace` (seconds) | 60 s | any bursty provider | auth-broker |

`store.yaml` says more about each (its `keys`), and about the subscription sources (`sources`). The schemas (its
`$defs`) are JSON Schema 2020-12. The values that are the upstream service's own answer (Glowmarkt's readings,
Spotify's queue and top lists, the GitHub summary) are pinned as their wrapper, with the answer itself left open: the
renderer reads those with its own models of the service's answers. Keys only one side uses (the providers' data for
the renderers, the render lease) are countdown's own, in its `countdown_core/store/keys.py`.

The enqueue script, [`lua/enqueue.lua`](lua/enqueue.lua), is the one way anything queues a render: `SET` the queued
flag `NX` with its TTL, and only if that set it, `LPUSH` the device id. Both sides run it from here, byte for byte, so
its SHA1 (what `EVALSHA` calls it by) is the same everywhere.

## The package

    from countdown_api import fixtures, keys, models, scripts

| module | what it is |
| --- | --- |
| `countdown_api.keys` | a builder per key (`keys.config(device_id)`), or a constant for one with no parameter (`keys.RENDER_JOBS`), each TTL (`keys.PAIRING_TTL_S`, `keys.RENDER_QUEUED_TTL_MS`), each key's prefix for a SCAN (`keys.CONFIG_PREFIX`), and the subscription sources (`keys.SOURCES`) |
| `countdown_api.models` | a Pydantic model (or a type alias) of every schema: `ConfigResponse`, `PairingConfig`, `FrameRecord`, ... |
| `countdown_api.scripts` | the Lua scripts: `scripts.ENQUEUE.source`, `.sha1`, and what its `keys` and `args` are |
| `countdown_api.fixtures` | the canonical examples: `fixtures.load("config_store.json")`, `fixtures.read_bytes("frame_record.bin")`, `fixtures.DIRECTORY` |

The wheel also carries the contract itself as `countdown_api/store.json`. It needs only pydantic.

Running the enqueue script with redis-py:

```python
from countdown_api import keys, scripts

enqueue = client.register_script(scripts.ENQUEUE.source)
enqueue(keys=[keys.render_queued(device_id), keys.RENDER_JOBS], args=[device_id, keys.RENDER_QUEUED_TTL_MS])
```

### The examples

`src/countdown_api/fixtures` is the one copy of the examples both repositories test against (each key's `examples` in
`store.yaml` names its own). auth-broker checks that what it writes is what they show and that it reads what they show,
countdown the same for its side, and this repository's tests (`tests/`) that each is what the schemas allow, under
its key and TTL. So a change to the stored shape is a PR here first: change the example and the schema together, and
the two sides' tests then say what has to follow. Nothing in them is real: no real device, code, token or password.

## Using it

Both sides use the repository as a git submodule: countdown at `api`, building against this repository's
main (its CI runs `git submodule update --init --remote`), and auth-broker at `vendor/countdown-api`, pinned to a
commit. Because countdown builds against main, **change the contract additively**: a new key, schema, field with a
default or example is safe; removing or tightening one needs both sides to have stopped using it first, which means a
later PR here.

The package isn't on PyPI. Each release is also published to https://nvorkinn.github.io/countdown-api/, a flat package
index that lists the latest release's wheel (`[[tool.uv.index]] url = "https://nvorkinn.github.io/countdown-api/"
format = "flat" explicit = true`, then `uv lock --upgrade-package countdown-api`), with `requirements.txt` (the wheel's
URL), `constraints.txt` (pins only countdown-api to the latest release), `latest.json`, `store.yaml` and `SHA256SUMS`.
It needs Settings > Pages > Source set to "GitHub Actions" and a `v*` tag rule on the `github-pages` environment.

## Changing it

Edit `store.yaml` (and `lua/`), then regenerate the committed `src/countdown_api`:

    uv sync --frozen
    uv run --frozen python generate.py

[`generate.py`](generate.py) writes `models.py` with
[openapi-codegen](https://github.com/nvorkinn/openapi-codegen) (a release of it, whose hash `uv.lock` records), handed
the contract's schemas as an OpenAPI document's components: JSON Schema 2020-12 is what OpenAPI 3.1's schemas are, so
the models are the same classes they were when the contract was an HTTP API. It writes `keys.py`, `scripts.py`,
`store.json` and `__init__.py` itself, from the same file, and runs `ruff check --fix` and `ruff format` on all of it.
The models check the schemas' `pattern`s too, and the tests check every example against the schemas with jsonschema.

CI checks it's up to date (`python generate.py --check`), runs ruff (`select = ["ALL"]`, generated code included) and
the tests (`uv run --frozen pytest`), and builds the wheel. A PR that changes `store.yaml` gets the regenerated code
pushed to it. To publish, push a tag `v<version>` on main: the release workflow stamps the version into the contract
and the wheel, builds them and makes that the latest release.
