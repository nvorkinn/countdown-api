# countdown-api

The contract between the countdown renderer ([pi-dashboard](https://github.com/nvorkinn/pi-dashboard)) and
[auth-broker](https://github.com/nvorkinn/auth-broker), as one OpenAPI file: [`openapi.yaml`](openapi.yaml).
Both projects generate their side of it with [openapi-codegen](https://github.com/nvorkinn/openapi-codegen) on every
build, so neither keeps a copy and neither can drift from the other.

## Using it

Always the latest release, whichever version of whichever repo is asking:

    https://github.com/nvorkinn/countdown-api/releases/latest/download/openapi.yaml

- the renderer generates the client and models: `openapi-codegen <file> --only clients,models`
- the broker generates the blueprints and models: `openapi-codegen <file> --only blueprints,models`

A build fails when its code no longer fits the contract.

## Changing it

Edit `openapi.yaml` in a PR (CI checks that every part still generates and imports). Merging it to main is the
release: the release workflow works out the next version itself (the latest release's patch number plus one, v1.0.0
for the first), stamps it into the published file and makes it the latest release. Keep `info.version` as
`0.0.0-dev` in the repo. Because devices in the field keep running older renderers, change the contract additively:
new optional fields and new operations are safe, removing or tightening something needs both sides released
together.
