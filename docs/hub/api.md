# Hub API

!!! warning "Under active development"
    MajorDom is still under development.  
    The API surface is stabilizing, but endpoints and message schemas are still subject to change.

!!! info "Reference only — interactive testing is disabled"
    These schemas are valid and are kept in sync with the Hub automatically (regenerated on
    every `develop` build), but they are published here for **learning and reference only** —
    "Try it out" is disabled for both REST and WebSocket operations.

    The Hub itself serves fully interactive API + WebSocket docs, used by Hub developers;
    a publicly hosted interactive version is more involved and currently a work in progress.

## Pairing errors

`POST /v1/api/device` and `POST /v1/api/device/{id}` save the device record first, then pair. If
pairing fails, the record is **kept (unpaired)** and the error names it in `device_id`. Other API
errors keep the plain `{"type", "msg"}` body.

| Status | When | `detail` |
|---|---|---|
| 422 | the integration raised [`MissingCredentialsError`](../device-integration/data_models.md#missing-hub-credentials) | `{"type": "missing_credentials", "msg": "Missing credentials: wifi", "device_id": "<uuid>", "credentials_type": "wifi"}` |
| 500 | any other pairing failure | `{"type": "unexpected_error", "msg": "Pairing failed", "device_id": "<uuid>"}` |

Retry after `missing_credentials`:

1. Ask the user for the missing credentials and save them on the Hub. For Wi-Fi:
   `POST /v1/api/set_wifi?connect=false` saves the network without switching the Hub's own connection.
2. `POST /v1/api/device/{device_id}` with `{"device_id": "<device_id>", "discovery_id": "<discovery_id>", "credentials": ...}`.
3. Use the `id` of the returned device from then on: it can differ from `device_id`, since an
   integration may move the record to the device's own identity (ESPHome does after Improv).

Unpaired records left behind by abandoned retries are not cleaned up yet.

## Reference

<swagger-ui src="hub-openapi-v1.json" supportedsubmitmethods="[]" />
