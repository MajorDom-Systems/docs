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
pairing fails for any reason, the record is **kept unpaired**, with the name, room and icon the
user entered, and the error names it in `device_id`. The response schemas are in the
[reference](#reference) below.

| Status | When | `detail.type` |
|---|---|---|
| 422 | the integration raised [`MissingCredentialsError`](../device-integration/data_models.md#missing-hub-credentials); `credentials_type` says which (e.g. `wifi`, `thread`) | `missing_credentials` |
| 500 | any other pairing failure, e.g. the Thread border router is down or a USB radio is unplugged | `pairing_failed` |

Unpaired records are hidden from every device listing, room and automation, and are listed by
`GET /v1/api/device/unpaired` so the app can offer **finish pairing** without retyping anything.

To finish pairing:

1. After `missing_credentials`, ask the user for the credentials and save them on the Hub. For
   Wi-Fi, `POST /v1/api/set_wifi?connect=false` saves the network without switching the Hub's own
   connection.
2. `POST /v1/api/device/{device_id}` with a **live** `discovery_id` (the original discovery may have
   expired) and the credentials, if any. Repeating `POST /v1/api/device` for the same discovery
   retries the same record instead of returning 409.
3. Use the `id` of the returned device from then on: it can differ from `device_id`, since an
   integration may move the record to the device's own identity (ESPHome does after Improv).

The Hub deletes an unpaired record 24 hours after its last pairing attempt (each retry restarts
the timer), unpairing it from its integration first. `DELETE /v1/api/device/{device_id}` dismisses
it earlier.

## Reference

<swagger-ui src="hub-openapi-v1.json" supportedsubmitmethods="[]" />
