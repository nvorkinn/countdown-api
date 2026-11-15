# countdown-api: the countdown store contract

This is a shared contract project. The broker (the config site) and the renderers (the providers and the render
pool) don't talk to each other over HTTP: they share a Redis, and that is all they share. This repository is the
contract for it: every key and channel that crosses between them, what each holds, its TTL, who writes it and who reads
it, the Lua script they run, and the canonical examples every consumer's tests check against. It is one file,
[`store.yaml`](store.yaml), and the model code generated from it for Python (the `countdown_api` package, Pydantic
models) and TypeScript (`store.d.ts`).

It also has the broker's HTTP routes for its devices (see [The devices' routes](#the-devices-routes)): registering a
device, and reading and saving a device's config. A device is an e-paper screen (`epaper`) or a touchscreen
(`touchscreen`), its config's `type`. So the contract covers both: the Redis keys, and the devices' HTTP API.

## What's in the contract

| key | Redis type | value (schema) | TTL | written by | read by |
| --- | --- | --- | --- | --- | --- |
| `v1:sub:<source>` | set | `Subscription` | none | the broker, on every config save | the providers |
| `v1:sub:changed` | channel | `SubChanged` (empty) | | the broker, after the sets | every provider |
| `v1:config:<device id>` | string, JSON | `ConfigResponse` | none | the broker | the render pool |
| `v1:pairing:<device id>` | string, JSON | `ConfigResponse` (`pairing_code` set) | 600 s, the code's own | the broker | the render pool |
| `v1:render:screens` | hash | `RenderScreens` (device id to slug) | none | the broker | the render pool |
| `v1:render:jobs` | list | `RenderJobs` (device ids) | none | the enqueue script | the render workers |
| `v1:render:queued:<device id>` | string | `RenderQueuedFlag` | 60,000 ms | the enqueue script | the claim script |
| `v1:frame:<device id>` | hash, bytes | `FrameRecord` | 86,400 s | the render pool | the broker |
| `v1:energy:<device id>` | string, JSON | `StoredEnergy` | 86,400 s | the broker's glow provider | the energy panel |
| `v1:spotify:<device id>` | string, JSON | `StoredPlayer` | 180 s | the broker's music provider | the Spotify area |
| `v1:spotify-top:<device id>` | string, JSON | `StoredTop` | 7,200 s | the broker's music provider | the Spotify area |
| `v1:art:<sha1 of the URL>` | string, bytes | `AlbumArt` | 300 s | the broker's music provider | the Spotify area |
| `v1:developer:<device id>` | string, JSON | `StoredDeveloper` | 900 s | the broker's developer provider | the developer panel |
| `v1:parcels:<device id>` | string, JSON | `ParcelList` | 43,200 s | the parcel provider | the parcels panel and notices |
| `v1:parcels-status:<device id>` | string | `ParcelsLinkStatus` | 86,400 s | the parcel provider | the broker |
| `v1:pace:<source>:<id>` | string | `Pace` (seconds) | 60 s | any bursty provider | the broker |

`store.yaml` says more about each (its `keys`), and about the subscription sources (`sources`). The schemas (its
`$defs`) are JSON Schema 2020-12. The values that are the upstream service's own answer (Glowmarkt's readings,
Spotify's queue and top lists, the GitHub summary) are pinned as their wrapper, with the answer itself left open: the
renderer reads those with its own models of the service's answers. Keys only one side uses (the providers' data for
the renderers, the render lease) aren't here: they are that side's own.

The enqueue script, [`lua/enqueue.lua`](lua/enqueue.lua), is the one way anything queues a render: `SET` the queued
flag `NX` with its TTL, and only if that set it, `LPUSH` the device id. Every consumer runs it from here, byte for byte, so
its SHA1 (what `EVALSHA` calls it by) is the same everywhere.

### The devices' routes

| route | takes | answers | what it is |
| --- | --- | --- | --- |
| `POST /api/devices/register` | `DeviceRegistration` | `DeviceRegistered` (201 new, 200 again) | a device's identity, from a secret it keeps, and its size; an e-paper screen's also says its frame format |
| `GET /api/devices/config` | | `ConfigResponse` | the device's config: the pairing value (`pairing_code` set) until it's paired |
| `PUT /api/devices/config` | `ConfigResponse` | `ConfigResponse` | save it whole, from a device's own settings panel; its read-only fields sent as they came |
| `GET /api/devices/spotify/token` | | `SpotifyAccessToken` | a touchscreen's short-lived access token for its owner's Spotify; the refresh token stays on the server |
| `GET /register` (and `POST`) | `TouchscreenRegistration` | a page, or a 303 to `return_to` | on the settings site, behind the login: registers a touchscreen from its secret's hash and makes the person signed in its owner, then sends it back to its app with `device_id` |

All but the registrations take the device's secret as `Authorization: Bearer <secret>` (`securitySchemes.deviceSecret`);
`/register` takes the person's login instead, on the settings site rather than the devices' API.
The routes are an OpenAPI 3.1 paths object in `store.yaml` (its `paths`), so `store.d.ts` types each route as well as
its schemas (`paths["/api/devices/config"]["get"]`, `operations["getConfig"]`), and the reference lists them.
`touchscreen.json` and `config_store.json` are their examples.

### A device's config

`ConfigResponse` is a device's config as a few flat fields and a section per panel, each section its own schema
(`config.weather.location`, not `config.weather_location`):

- flat: `device_id`, `type`, `width`, `height` and `pairing_code`, all read-only (`readOnly: true`: the server's, or
  what the device said at registration), then `interval`, `clock_format`, `language` and `timezone`;
- every type's sections: `arrivals`, `weather`, `notice_board`, `spotify`, `apple_music`, `glowmarkt`, `developer`
  and `parcels`;
- `style`, on every type, but its type's own schema: an e-paper screen's (`EpaperStyle`: orientation, drawing style,
  weather design, layout) or a touchscreen's (`TouchscreenStyle`: skin and colour). An e-paper screen also has its
  read-only frame `format`, a touchscreen its `display` (when its screen sleeps).

It's a `oneOf` of `EpaperConfig` and `TouchscreenConfig` with a `discriminator` on `type`, so both languages get a
tagged union: `models.ConfigResponse` is a Pydantic discriminated union (read it with `TypeAdapter(ConfigResponse)`),
and `ConfigResponse` in `store.d.ts` a union narrowed by `type`. It never has a secret: logins and keys (Spotify's link
among them) are the owner's account's, held on the server. It's the value of `v1:config:<device id>` (and, with
`pairing_code` set, of `v1:pairing:<device id>`) as well as what the routes answer, so the render pool and a device
read the same config.

## The package

    from countdown_api import fixtures, keys, models, scripts

| module | what it is |
| --- | --- |
| `countdown_api.keys` | a builder per key (`keys.config(device_id)`), or a constant for one with no parameter (`keys.RENDER_JOBS`), each TTL (`keys.PAIRING_TTL_S`, `keys.RENDER_QUEUED_TTL_MS`), each key's prefix for a SCAN (`keys.CONFIG_PREFIX`), and the subscription sources (`keys.SOURCES`) |
| `countdown_api.models` | a Pydantic model (or a type alias) of every schema: `ConfigResponse`, `EpaperConfig`, `FrameRecord`, ... |
| `countdown_api.scripts` | the Lua scripts: `scripts.ENQUEUE.source`, `.sha1`, and what its `keys` and `args` are |
| `countdown_api.fixtures` | the canonical examples: `fixtures.load("config_store.json")`, `fixtures.read_bytes("frame_record.bin")`, `fixtures.DIRECTORY` |

There are TypeScript types of the schemas too, `src/countdown_api/store.d.ts`, written by
[openapi-typescript](https://openapi-ts.dev/) from the same schemas as the models. Each schema is exported by its own
name, and as `components["schemas"][name]`:

```ts
import type { ConfigResponse, FrameRecord, TouchscreenConfig } from "<this repository>/src/countdown_api/store";
```

Every generated file starts with an `@generated` line, which most tools and reviews read as "don't edit".

The package also carries the contract itself as `countdown_api/store.json`. It needs only pydantic.

Running the enqueue script with redis-py:

```python
from countdown_api import keys, scripts

enqueue = client.register_script(scripts.ENQUEUE.source)
enqueue(keys=[keys.render_queued(device_id), keys.RENDER_JOBS], args=[device_id, keys.RENDER_QUEUED_TTL_MS])
```

### The examples

`src/countdown_api/fixtures` is the one copy of the examples every consumer tests against (each key's `examples` in
`store.yaml` names its own). A writer checks that what it writes is what they show, a reader that it reads what they
show, and this repository's tests (`tests/`) that each is what the schemas allow, under its key and TTL. So a change
to the stored shape is a PR here first: change the example and the schema together, and the consumers' tests then say
what has to follow. Nothing in them is real: no real device, code, token or password.

## Using it

Consumers use the repository as a git submodule, some pinned to a commit and some building against this
repository's main. Because of the latter, **change the contract additively**: a new key, schema, field with a default
or example is safe; removing or tightening one needs every consumer to have stopped using it first, which means a
later PR here.

The schema reference is at https://nvorkinn.github.io/countdown-api/: the keys, the sources, the scripts and every
schema, shown with [Scalar](https://scalar.com). The Pages workflow publishes it on every push to main, so it is
main's contract. It needs Settings > Pages > Source set to "GitHub Actions", and the `github-pages` environment to
allow the branch `main`.

## Changing it

Edit `store.yaml` (and `lua/`), then regenerate the committed `src/countdown_api`:

    uv sync --frozen
    npm ci
    uv run --frozen python generate.py

[`generate.py`](generate.py) writes `models.py` with
[openapi-codegen](https://github.com/nvorkinn/openapi-codegen) (a release of it, whose hash `uv.lock` records), handed
the contract's schemas as an OpenAPI document's components: JSON Schema 2020-12 is what OpenAPI 3.1's schemas are, so
the models are the same classes they were when the contract was an HTTP API. `store.d.ts` comes from
openapi-typescript (pinned in `package.json`/`package-lock.json`), from the same OpenAPI document. It writes `keys.py`,
`scripts.py`, `store.json` and `__init__.py` itself, from the same file, and runs `ruff check --fix` and `ruff format`
on the Python and `biome check --write` on `store.d.ts` and `store.json`. It writes each tagged union (a `oneOf` with a
`discriminator`) in `models.py` itself, after its members, as a Pydantic discriminated union: openapi-codegen would
write a plain union, and can put it before its members.
The models check the schemas' `pattern`s too, and the tests check every example against the schemas with jsonschema.

CI checks it's up to date (`python generate.py --check`), type-checks `store.d.ts` with `tsc` (`tsconfig.json`: strict,
`noUncheckedIndexedAccess` and `exactOptionalPropertyTypes`), runs [Biome](https://biomejs.dev/) on the TypeScript and
JSON (`biome.json`; lint and format, the fixtures included), runs ruff (`select = ["ALL"]`, generated code included) and
the tests (`uv run --frozen pytest`), and builds the wheel. A PR that changes `store.yaml` gets the regenerated code
pushed to it. There is no release: the project isn't released on its own, and a consumer builds what it needs from
its submodule.
