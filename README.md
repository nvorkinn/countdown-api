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
| `v1:parcels:<device id>` | string, JSON | `ParcelList` | 43,200 s | the parcel provider | the parcels panel and notices, the broker's `getNotices` |
| `v1:parcels-status:<device id>` | string | `ParcelsLinkStatus` | 86,400 s | the parcel provider | the broker |
| `v1:pace:<source>:<id>` | string | `Pace` (seconds) | 60 s | any bursty provider | the broker |
| `v1:departures:<stop id>` | string, JSON | `StopDepartures` | 120 s | countdown's TfL and Entur providers | the arrivals panels, the broker's `getArrivals` |
| `v1:weather:<weather key>` | string, JSON | `StoredForecast` | 1,800 s | countdown's weather provider | the weather panel, the broker's `getWeather` |
| `v1:background:<weather key>` | string, JSON | `StoredBackground` | 172,800 s | countdown's background provider | the broker's `getWeather` |
| `v1:background-image:<sha256>` | string, bytes | `BackgroundImage` | 172,800 s | countdown's background provider | the broker's `getBackgroundImage` |
| `v1:background-place:<weather key>` | string, JSON | `BackgroundPlace` | none | the broker, with the subscriptions | countdown's background provider |
| `v1:notices:tfl-lines:<stop id>` | string, JSON | `StoredLineStatus` | 600 s | countdown's TfL notices provider | the notice board, the broker's `getNotices` |
| `v1:notices:tfl-stations:<stop id>` | string, JSON | `StoredStationDisruptions` | 1,800 s | countdown's TfL notices provider | the notice board, the broker's `getNotices` |
| `v1:notices:tfl-roads:<place>` | string, JSON | `StoredRoadDisruptions` | 1,800 s | countdown's TfL notices provider | the notice board, the broker's `getNotices` |
| `v1:notices:tfl-network` | string, JSON | `StoredNetworkStatus` | 600 s | countdown's TfL notices provider | the broker's `getNotices` |
| `v1:notices:met-office:<place>` | string, JSON | `StoredMetOfficeWarnings` | 1,800 s | countdown's Met Office provider | the notice board, the broker's `getNotices` |
| `v1:notices:bank-holidays` | string, JSON | `StoredBankHolidays` | 604,800 s | countdown's bank holidays provider | the notice board, the broker's `getNotices` |

`store.yaml` says more about each (its `keys`), and about the subscription sources (`sources`). The schemas (its
`$defs`) are JSON Schema 2020-12. The values that are the upstream service's own answer (Glowmarkt's readings,
Spotify's queue and top lists, the GitHub summary) are pinned as their wrapper, with the answer itself left open: the
renderer reads those with its own models of the service's answers; so are TfL's answers in the TfL notices and
Open-Meteo's forecast in the weather. A `<place>` is a postcode without its space, in capitals (`SE173LL`): the key
builders take the postcode as the broker writes it (`SE17 3LL`) and make the place themselves. Keys only one side
uses (the render lease, and countdown's other providers' data: floods, Entur's situations, MET Norway's warnings, the
postcodes' places) aren't here: they are that side's own, until the other side reads them too.

The enqueue script, [`lua/enqueue.lua`](lua/enqueue.lua), is the one way anything queues a render: `SET` the queued
flag `NX` with its TTL, and only if that set it, `LPUSH` the device id. Every consumer runs it from here, byte for byte, so
its SHA1 (what `EVALSHA` calls it by) is the same everywhere.

### The devices' routes

| route | takes | answers | what it is |
| --- | --- | --- | --- |
| `POST /api/devices/register` | `DeviceRegistration` | `DeviceRegistered` (201 new, 200 again) | a device's identity, from a secret it keeps, and its size; an e-paper screen's also says its frame format |
| `GET /api/devices/config` | | `ConfigResponse`, its version as `ETag` | the device's config: for an e-paper screen, the pairing value (`pairing_code` set) until it's paired |
| `PUT /api/devices/config` | `ConfigResponse` | `ConfigResponse` | save it whole, from a device's own settings panel; its read-only fields sent as they came; `If-Match` optional |
| `PUT /api/devices/config/{section}` | a section (`ConfigSection` names it), `If-Match` | `ConfigResponse`, its new `ETag` | save one section whole; 409 when `If-Match` is stale, so the caller reloads instead of overwriting |
| `GET /api/stops/search` | `q` | `StopSearchResult[]` | London's and Norway's stops, for a stop picker |
| `GET /api/places/search` | `q` | `PlaceSearchResult[]` | towns and cities (Open-Meteo), for the weather picker |
| `GET /api/devices/spotify/token` | | `SpotifyAccessToken` | a touchscreen's short-lived access token for its owner's Spotify; the refresh token stays on the server |
| `GET /api/devices/weather` | | `DeviceWeather` | the forecast for the device's weather place, as the store has it (`v1:weather:<key>`), and its backgrounds so far (`v1:background:<key>`) |
| `GET /api/backgrounds/{digest}` | | a JPEG (`BackgroundImage`), cached immutably | a weather panel background by its SHA-256, with no secret, as a screen loads it as a plain image |
| `GET /api/devices/arrivals` | | `DeviceArrivals` | the departures from each of the device's stops, in its order, as the store has them (`v1:departures:<stop id>`) |
| `GET /api/devices/notices` | | `DeviceNotices` | what the store has for the device's notice board (TfL, the Met Office, bank holidays, and its owner's parcels when switched on) and every Tube line's status, as each provider stored it |
| `GET /register` (and `POST`) | `TouchscreenRegistration` | a page, or a 303 to `return_to` | on the settings site, behind the login: registers a touchscreen from its secret's hash and makes the person signed in its owner, then sends it back to its app with `device_id` |
| `GET /device/{device_id}` | `embed=1` (optional) | a page, or 404 | on the settings site, behind the login: a device's settings for its owner; with `embed=1`, without the site around it, for a frame in the device's own settings (a touchscreen's Settings tab) |

All but the registrations and the backgrounds take the device's secret as `Authorization: Bearer <secret>`
(`securitySchemes.deviceSecret`);
`/register` takes the person's login instead, on the settings site rather than the devices' API.
The config and search routes also work on the settings site with the person's login instead of a secret, the config
ones for the device their `device_id` query names. Both searches answer the same result shape (`SearchResult`: `id`,
`name`, `subtitle`, `indent`) with a `value` that is what picking it saves, in the config's own shape.
The routes are an OpenAPI 3.1 paths object in `store.yaml` (its `paths`), so `store.d.ts` types each route as well as
its schemas (`paths["/api/devices/config"]["get"]`, `operations["getConfig"]`), and the reference lists them.
`touchscreen.json`, `config_store.json` and `device_panels.json` are their examples.

For TypeScript, `client.ts` has a function per route, named by its `operationId`, so a caller never writes a path:
`getConfig(client)`, `putConfig(client, config, { headers: { "If-Match": etag } })` and so on for the devices' API
(each answers `{ data, response }` for a 2xx and `{ error, response }` otherwise, and sends `client.secret` as the
bearer where the route takes it), and a URL builder for each page a device sends a browser to,
`registerTouchscreenUrl(server, { secret_hash, width, height, return_to })` and `deviceSettingsPageUrl(server, {
device_id })`. It's plain `fetch`, typed by `store.d.ts`, with nothing to install; `generate.py` writes it with the
rest, so a new route gets its function in the same PR.

### A device's config

`ConfigResponse` is a device's config as a few flat fields and a section per panel, each section its own schema
(`config.weather.location`, not `config.weather_location`):

- every type's flat fields: `device_id`, `type`, `width` and `height`, all read-only (`readOnly: true`: the server's,
  or what the device said at registration), then `clock_format`;
- every type's sections: `arrivals`, `weather` and `notice_board`;
- `style`, on every type, but its type's own schema: an e-paper screen's (`EpaperStyle`: orientation, drawing style,
  weather design, layout) or a touchscreen's (`TouchscreenStyle`: skin and colour);
- an e-paper screen's own: its read-only `pairing_code` and frame `format`, its `interval`, `language` and `timezone`,
  and the sections `spotify`, `apple_music`, `glowmarkt`, `developer` and `parcels`;
- a touchscreen's own: `display` (when its screen sleeps), `lyrics` (the synced lyrics' size and alignment; a config
  from before it has none, which a touchscreen shows as medium, on the left) and `parcels` (whether its notice board
  has its owner's parcels). That is all of it: a touchscreen is English only, keeps its own time, plays music itself
  and has no other integrations. Every setting a device has lives here on the server, but for its Wi-Fi, which stays
  on the device.

It's a `oneOf` of `EpaperConfig` and `TouchscreenConfig` with a `discriminator` on `type`, so both languages get a
tagged union: `models.ConfigResponse` is a Pydantic discriminated union (read it with `TypeAdapter(ConfigResponse)`),
and `ConfigResponse` in `store.d.ts` a union narrowed by `type`. It never has a secret: logins and keys (Spotify's link
among them) are the owner's account's, held on the server. It's the value of `v1:config:<device id>` (and, with an
e-paper screen's `pairing_code` set, of `v1:pairing:<device id>`) as well as what the routes answer, so the render pool
and a device read the same config.

### The words

What a screen says about a stored value is worded where it's shown: by the render pool for an e-paper screen, by the
touchscreen's own app for a touchscreen. So that both say the same thing, the strings they word it with are here, in
`countdown_api/messages`: [ICU MessageFormat](https://unicode-org.github.io/icu/userguide/format_parse/messages/) by
id, each with a description and its string in English and Norwegian (`notices.json`: the notice board's line
statuses, weather warnings and bank holidays). Each side formats them with its own ICU formatter, so a string keeps to
what every formatter does alike: named arguments, `select`, and `plural` with `one` and `other`. Dates and times are
formatted by the caller and passed in as text. Only what more than one kind of screen says is here.

A provider's own prose (TfL's reason for a line's status) can't be worded from a string, and is too long for a
touchscreen's row. The provider that fetches it has a model shorten it, and stores the short form beside it
(`shorts`, each a `NoticeShort`: the text, a title and a summary), so it's data like the text itself and nothing that
shows a notice asks a model.

## The package

    from countdown_api import fixtures, keys, models, scripts

| module | what it is |
| --- | --- |
| `countdown_api.keys` | a builder per key (`keys.config(device_id)`), or a constant for one with no parameter (`keys.RENDER_JOBS`), each TTL (`keys.PAIRING_TTL_S`, `keys.RENDER_QUEUED_TTL_MS`), each key's prefix for a SCAN (`keys.CONFIG_PREFIX`), and the subscription sources (`keys.SOURCES`) |
| `countdown_api.models` | a Pydantic model (or a type alias) of every schema: `ConfigResponse`, `EpaperConfig`, `FrameRecord`, ... |
| `countdown_api.scripts` | the Lua scripts: `scripts.ENQUEUE.source`, `.sha1`, and what its `keys` and `args` are |
| `countdown_api.messages` | the words: `messages.catalog("en")["notice.line.title"]`, `messages.load("notices.json")`, `messages.LANGUAGES` |
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
