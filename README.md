# countdown-api: the countdown store contract

This is a shared contract project. The broker (the config site) and the renderers (the providers and the render
pool) don't talk to each other over HTTP: they share a Redis, and that is all they share. This repository is the
contract for it: every key and channel that crosses between them, what each holds, its TTL, who writes it and who reads
it, the Lua script they run, and the canonical examples every consumer's tests check against. It is one file,
[`store.yaml`](store.yaml), and the model code generated from it for Python (the `countdown_api` package, Pydantic
models), TypeScript (`store.d.ts`) and, for the routes an e-paper screen's firmware calls, C++ (`cpp/countdown_api`).

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
| `v1:notices:entur:<stop id>` | string, JSON | `StoredEnturSituations` | 900 s | countdown's Entur situations provider | the notice board, the broker's `getNotices` |
| `v1:notices:met-office:<place>` | string, JSON | `StoredMetOfficeWarnings` | 1,800 s | countdown's Met Office provider | the notice board, the broker's `getNotices` |
| `v1:notices:bank-holidays` | string, JSON | `StoredBankHolidays` | 604,800 s | countdown's bank holidays provider | the notice board, the broker's `getNotices` |
| `v1:location:<place>` | string, JSON | `StoredLocation` | 604,800 s | countdown's locations provider | the notice board and countdown's providers of notices about a place, the broker's `getNotices` |
| `v1:notices:floods:<place>` | string, JSON | `StoredFloods` | 1,800 s | countdown's floods provider | the notice board, the broker's `getNotices` |
| `v1:notices:metalerts` | string, JSON | `StoredMetAlerts` | 1,800 s | countdown's MetAlerts provider | the notice board, the broker's `getNotices` |
| `v1:bins:<sha1 of the address>` | string, JSON | `StoredBinCollections` | 129,600 s | countdown's bins provider | the notice board, the broker's `getNotices` |

`store.yaml` says more about each (its `keys`), and about the subscription sources (`sources`). The schemas (its
`$defs`) are JSON Schema 2020-12. The values that are the upstream service's own answer (Glowmarkt's readings,
Spotify's queue and top lists, the GitHub summary) are pinned as their wrapper, with the answer itself left open: the
renderer reads those with its own models of the service's answers; so are TfL's answers in the TfL notices, Entur's in
its situations, MET Norway's in its warnings, and Open-Meteo's forecast in the weather. A `<place>` is a postcode without its space, in capitals (`SE173LL`): the key
builders take the postcode as the broker writes it (`SE17 3LL`) and make the place themselves. Keys only one side
uses (the render lease, countdown's TfL timetables and notices' short forms, and the channel the locations provider
nudges its readers on) aren't here: they are that side's own, until the other side reads them too.

The enqueue script, [`lua/enqueue.lua`](lua/enqueue.lua), is the one way anything queues a render: `SET` the queued
flag `NX` with its TTL, and only if that set it, `LPUSH` the device id. Every consumer runs it from here, byte for byte, so
its SHA1 (what `EVALSHA` calls it by) is the same everywhere.

### The devices' routes

| route | takes | answers | what it is |
| --- | --- | --- | --- |
| `POST /api/devices/register` | `DeviceRegistration` | `DeviceRegistered` (201 new, 200 again) | a device's identity, from a secret it keeps, and its size; an e-paper screen's also says its frame format |
| `POST /api/frame` | `FrameReport`, `If-None-Match` | the frame's bytes with its `ETag` (200), or 304, 404, 409; `Retry-After` | an e-paper screen's poll for its frame, in a loop, sleeping `Retry-After` between; its body is what it measured and logged since the last |
| `GET /api/devices/config` | | `ConfigResponse`, its version as `ETag` | the device's config: for an e-paper screen, the pairing value (`pairing_code` set) until it's paired |
| `PUT /api/devices/config` | `ConfigResponse` | `ConfigResponse` | save it whole, from a device's own settings panel; its read-only fields sent as they came; `If-Match` optional |
| `PUT /api/devices/config/{section}` | a section (`ConfigSection` names it), `If-Match` | `ConfigResponse`, its new `ETag` | save one section whole; 409 when `If-Match` is stale, so the caller reloads instead of overwriting |
| `GET /api/stops/search` | `q` | `StopSearchResult[]` | London's and Norway's stops, for a stop picker |
| `GET /api/places/search` | `q` | `PlaceSearchResult[]` | towns and cities (Open-Meteo), for the weather picker |
| `GET /api/places/here` | `latitude`, `longitude` (optional) | `PlaceSearchResult[]` (at most one) | the town or city at the position sent, or with none where the caller's IP places it, for the weather picker's current location |
| `GET /api/postcodes/lookup` | `postcode` | `Postcode`, in its canonical form; 400, 404, 502 | where a UK or Norwegian postcode the owner typed is |
| `POST /api/postcodes/near` | `NearPostcodesRequest` (a position, and how sure it is) | `NearbyPostcode[]` (at most 10); 400, 502 | the UK postcodes nearest a position, nearest first, for a setup's location step on the owner's phone, which finds the position itself; a device's secret or, on the settings site, a login |
| `GET /api/stops/near` | `latitude`, `longitude` | `NearbyStopResult[]` (at most 20) | TfL's stations and bus stops nearest a position, nearest first, each a `StopSearchResult` with its `distance` in metres; none outside TfL's area |
| `GET /api/devices/spotify/token` | | `SpotifyAccessToken` | a touchscreen's short-lived access token for its owner's Spotify; the refresh token stays on the server |
| `POST /api/devices/soloist/codes` | `SoloistKeyCodeRequest` | `SoloistKeyCode` (201) | a code one of a touchscreen's people saves their own Spotify Soloist API key with, shown as a link to `/soloist`; ten minutes, one use |
| `GET /api/devices/soloist/keys` | | `SoloistKeys` | which of the touchscreen's people have a key saved; never a key |
| `GET /api/devices/soloist/key` | `person` | `SoloistApiKey` | the key saved for one of the touchscreen's people, which it starts its Soloist daemon with for them; `Cache-Control: no-store`, and never answered cross-origin |
| `DELETE /api/devices/soloist/keys/{person}` | | 204 | forget the key saved for one of the touchscreen's people |
| `POST /api/devices/spotify/sign-ins` | `SpotifySignInRequest` | `SpotifySignIn` (201) | a Spotify sign-in a touchscreen shows as a code to scan: the phone signs in at Spotify through the settings site's `/spotify/sign-in`, with the touchscreen's PKCE challenge; ten minutes |
| `GET /api/devices/spotify/sign-ins/{id}` | | `SpotifySignInResult` | `waiting`, or once the phone is back Spotify's code (`done`) or error (`failed`), answered once; the touchscreen exchanges the code with its own verifier |
| `GET /api/devices/setup` | `device_id` (the settings site only) | `SetupStatus`; 404 for a touchscreen that has reported nothing | which step a touchscreen's setup is at, for it and its owner's phone to show the same one; with it, while the step is `spotify`, the sign-in the server made for the phone |
| `PUT /api/devices/setup` | `SetupReport` | `SetupStatus` | what only the touchscreen knows of its setup: its first Spotify sign-in's PKCE challenge (sent before it is paired), its Soloist's name and sign-in, its phone paired, and that it has finished |
| `GET /api/devices/account` | | `DeviceAccount` | which services the owner's account has linked (Parcel, Spotify), so a device can tell one that's switched off from one never set up; never a login or key |
| `GET /api/devices/weather` | | `DeviceWeather` | the forecast for the device's weather place, as the store has it (`v1:weather:<key>`), and its backgrounds so far (`v1:background:<key>`) |
| `GET /api/backgrounds/{digest}` | | a WebP (`BackgroundImage`), cached immutably | a weather panel background by its SHA-256, with no secret, as a screen loads it as a plain image |
| `GET /api/devices/arrivals` | | `DeviceArrivals` | the departures from each of the device's stops, in its order, as the store has them (`v1:departures:<stop id>`) |
| `GET /api/devices/notices` | | `DeviceNotices` | what the store has for the device's notice board (TfL, the Met Office, the Environment Agency's flood warnings, bank holidays, MET Norway's warnings covering a Norwegian postcode, and its owner's parcels when switched on) and every Tube line's status, as each provider stored it |
| `GET /register` (and `POST`) | `TouchscreenRegistration` | a page, or a 303 to `return_to` | on the settings site, behind the login: registers a touchscreen from its secret's hash and makes the person signed in its owner, then sends it back to its app with `device_id` |
| `GET /device/{device_id}` | `embed=1` (optional) | a page, or 404 | on the settings site, behind the login: a device's settings for its owner; with `embed=1`, without the site around it, for a frame in the device's own settings (a touchscreen's Settings tab) |
| `GET /soloist` | `code` | a page | on the settings site, with no login: where a person pastes their Spotify Soloist API key for the touchscreen and person the code names |
| `GET /spotify/sign-in` | `id` | a redirect to Spotify, or a page | on the settings site, with no login: where the phone that scanned a touchscreen's Spotify sign-in starts |
| `GET /spotify/sign-in/callback` | `state`, `code` or `error` | a page | on the settings site, with no login: Spotify's redirect address for those sign-ins, which keeps Spotify's answer for the touchscreen |
| `GET /account/parcel` | | a page | on the settings site, behind the login: where the person finds their Parcel API key and pastes it, for a device to send a phone to while its owner's account has none |

All but the registrations and the backgrounds take the device's secret as `Authorization: Bearer <secret>`
(`securitySchemes.deviceSecret`);
`/register` takes the person's login instead, on the settings site rather than the devices' API.
The config and search routes also work on the settings site with the person's login instead of a secret, the config
ones for the device their `device_id` query names. Both searches answer the same result shape (`SearchResult`: `id`,
`name`, `subtitle`, `indent`) with a `value` that is what picking it saves, in the config's own shape.
The routes are an OpenAPI 3.1 paths object in `store.yaml` (its `paths`), so `store.d.ts` types each route as well as
its schemas (`paths["/api/devices/config"]["get"]`, `operations["getConfig"]`), and the reference lists them.
`touchscreen.json`, `config_store.json`, `device_panels.json` and `frame_poll.json` are their examples.

For TypeScript, `client.ts` has a function per route, named by its `operationId`, so a caller never writes a path:
`getConfig(client)`, `putConfig(client, config, { headers: { "If-Match": etag } })` and so on for the devices' API
(each answers `{ data, response }` for a 2xx and `{ error, response }` otherwise, and sends `client.secret` as the
bearer where the route takes it), and a URL builder for each page a device sends a browser to,
`registerTouchscreenUrl(server, { secret_hash, width, height, brightness_control, return_to })`,
`deviceSettingsPageUrl(server, { device_id })` and `connectParcelPageUrl(server)`. It's plain `fetch`, typed by
`store.d.ts`, with nothing to install; `generate.py` writes it with the rest, so a new route gets its function in the
same PR.

For C++ (countdown-esp32's firmware), `cpp/countdown_api` has the same for the two routes an e-paper screen calls,
as headers of plain C++17 with nothing to install: `api.h` has a function per route, `registerDevice(registration)`
and `pollFrame(report)`, and there is a header per schema they take (`DeviceRegistration.h`, `FrameReport.h`, ...),
each a struct with `toJson()`. A function answers the request to send as data (`Request`: its method, path, JSON
body and whether it takes the secret) and sends nothing itself, so it builds for the host as for a board, and the
firmware sends it with the HTTP client it already has:

```cpp
#include "countdown_api/api.h"  // with -I <this repository>/cpp

countdown_api::DeviceRegistration registration;
registration.secret = secret;
registration.width = 800;
registration.height = 480;
registration.format = countdown_api::DeviceRegistration::FormatEnum::Mono1bppPacked;
const countdown_api::Request request = countdown_api::registerDevice(registration);
http.request(request.method, brokerUrl + request.path, request.body, secret, "");
```

A field that isn't set (an empty `std::optional`) is left out of the JSON, so an e-paper screen sends no `type` and
a touchscreen no `format`. The headers only write JSON: a screen reads an answer's status and headers, never a JSON
body, so there is no model of an answer and no JSON library. Which routes get a function is `CPP_OPERATIONS` in
`generate.py`.

### A device's config

`ConfigResponse` is a device's config as a few flat fields and a section per panel, each section its own schema
(`config.weather.location`, not `config.weather_location`):

- every type's flat fields: `device_id`, `type`, `width` and `height`, all read-only (`readOnly: true`: the server's,
  or what the device said at registration), then `clock_format`;
- every type's sections: `arrivals`, `weather` and `notice_board`;
- `style`, on every type, but its type's own schema: an e-paper screen's (`EpaperStyle`: orientation, drawing style,
  weather design, layout) or a touchscreen's (`TouchscreenStyle`: skin, colour and Dynamic, on unless turned off);
- `language` (en or nb), on every type; a touchscreen's config from before it has none, which reads as en;
- an e-paper screen's own: its read-only `pairing_code` and frame `format`, its `interval` and `timezone`, and the
  sections `spotify`, `apple_music`, `glowmarkt`, `developer` and `parcels`;
- a touchscreen's own: `display` (when its screen sleeps, how bright it is and its quiet hours), `lyrics` (the synced
  lyrics' size and alignment; a config from before it has none, which a touchscreen shows as medium, on the left),
  `holidays` (how many days ahead its notice board mentions the next holiday; none reads as a week) and
  `parcels` (whether its notice board has its owner's parcels). That is all of it: a touchscreen keeps its own time, plays music itself and has no other
  integrations. Every setting a device has lives here on the server, but for its Wi-Fi, which stays
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
statuses, TfL's station and road disruptions, flood warnings, the Met Office's and MET Norway's weather warnings, the
clocks changing, and the UK's bank holidays and Norway's public holidays). Each side formats them with its own ICU formatter, so a string keeps to
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
main's contract. Every push to main also sends a `countdown-api-main`
[repository_dispatch](.github/workflows/dispatch-submodule-bumps.yml) to countdown, countdown-server and the-max-mix,
whose "Bump countdown-api" workflow points their submodule at main on the branch `chore/bump-countdown-api` and opens
a PR for it, or updates the one already open. Both ends use the `COUNTDOWN_API_BUMP_TOKEN` secret, a fine-grained PAT
with Contents and Pull requests read and write on the three consumers.

Pages needs Settings > Pages > Source set to "GitHub Actions", and the `github-pages` environment to
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
on the Python and `biome check --write` on `store.d.ts` and `store.json`. The C++ headers in `cpp/countdown_api` come
from [openapi-generator](https://github.com/OpenAPITools/openapi-generator) (its command pinned in `package.json`,
its own version in `openapitools.json`; it needs Java), given only the routes `CPP_OPERATIONS` names and the schemas
they take. It runs its `cpp-tiny` generator, the one for a microcontroller, for the C++ types and names, but with the
templates in [`templates/cpp`](templates/cpp) instead of its own, whose output needs Arduino's HTTP client and a JSON
library and sends every optional field. It writes each tagged union (a `oneOf` with a
`discriminator`) in `models.py` itself, after its members, as a Pydantic discriminated union: openapi-codegen would
write a plain union, and can put it before its members.
The models check the schemas' `pattern`s too, and the tests check every example against the schemas with jsonschema.

CI checks it's up to date (`python generate.py --check`), type-checks `store.d.ts` with `tsc` (`tsconfig.json`: strict,
`noUncheckedIndexedAccess` and `exactOptionalPropertyTypes`), runs [Biome](https://biomejs.dev/) on the TypeScript and
JSON (`biome.json`; lint and format, the fixtures included), runs ruff (`select = ["ALL"]`, generated code included) and
the tests (`uv run --frozen pytest`, which also build the C++ headers with the host's compiler, warnings as errors,
and check they write the examples), and builds the wheel. A PR that changes `store.yaml` gets the regenerated code
pushed to it. There is no release: the project isn't released on its own, and a consumer builds what it needs from
its submodule.
