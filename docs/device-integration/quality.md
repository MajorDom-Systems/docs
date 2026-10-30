# Quality Checklist

The [Implementation Checklist](index.md#implementation-checklist) gets your integration **functional** — it launches, pairs, controls, and reports. This checklist gets it **reliable and maintainable**: it's the bar an integration must clear before it's released.

Items are ordered from **vital** (never ship without them) to **nice-to-have**.

!!! tip "Track it in your repo, not here"
    The [integration template](https://github.com/MajorDom-Systems/integration-template#progress)
    README ships **both checklists as a fillable copy** — tick items there as you implement them
    and your CI goes green. This page is the reference that explains the *why* behind each item.

---

## Reliability — vital

An integration must never take the Hub down, and never spam the logs. The Hub isolates a crashing integration where it can, but a quality integration doesn't rely on that.

- [ ] **Recovers automatically.** Connection loss, an offline device, or a restarted backend/radio must recover on their own — no manual restart. Reconnection is retried with backoff, not a tight loop.
- [ ] **No exception escapes the controller.** Every background task, subscription loop, and callback catches its own errors. An unhandled exception in a background task dies silently; one raised inside a `self.dependencies.output.*` call propagates back into the Hub. Neither is acceptable.
- [ ] **Failures are surfaced, not raised.** An expected/transient failure (device offline, bad reading, timeout) is logged **once** (no repeated spam) and reflected on the device — `device.available = False` and a human-readable `last_error` — then cleared on recovery. It does not bubble up as an exception.
- [ ] **Re-authenticates automatically** when credentials expire or are rejected (if the protocol uses credentials).
- [ ] **Fully asynchronous.** No blocking I/O on the event loop; blocking or CPU-heavy work runs off-loop (a thread/executor) so it can't stall the Hub.
- [ ] **Availability is live.** Offline/online is detected while the Hub is running, not only on reboot (this also appears on the implementation checklist — it's a reliability requirement, so it's repeated here).
- [ ] **Stable identity.** Device and parameter UUIDs are derived through the SDK helpers, so they stay identical across restarts and re-pairs — state and automations survive.

## Tested — vital

- [ ] **End-to-end automated tests** drive the controller through pair → command → fetch → events → `unpair` against a **virtual/simulated device** (the SDK's `majordom_integration_sdk.testing` doubles), with no physical hardware required.
- [ ] **Failure paths are tested** — offline device, transport error, rejected credentials — asserting the integration degrades gracefully (sets `available`/`last_error`, does not raise).
- [ ] **Broad device coverage** where the protocol has many device/parameter types — exercise the full mapping surface, not one happy-path device. (A protocol-provided virtual-device catalogue, run in CI, is the ideal.)

## Maintainable — important

- [ ] **Fully typed** — passes `ty` with no package-wide ignore blocks; any exceptions are file/rule-scoped and commented with why.
- [ ] **Clean** — passes the full `poe check` (ruff lint + format, `ty`, tests, build) with no warnings.
- [ ] **Readable & structured** — clear names, comments where the intent isn't obvious; conversion logic lives in a mapper and models are separated, per the template layout.
- [ ] **Efficient** — prefer event subscriptions over polling; batch or chunk reads; avoid redundant network and CPU work.
- [ ] **Diagnosable** — logging at the right levels, enough to debug a device problem from the logs alone. A device-state diagnostic dump is a bonus.
- [ ] **Owned** — a listed maintainer who keeps it working as the protocol and the upstream library evolve.

## User experience — important

- [ ] **Rich parameter metadata.** Every parameter has the correct **visibility** (`user` / `setting` / `system`) and the device's **main parameter** is set — so the app can present a clean control-center action, a sensible on-tap parameter list, a settings page, and hidden system internals. Getting this right is what makes a device feel native rather than a raw dump of protocol attributes; a poorly-mapped device is a poor device, however reliable it is.

## Extras — nice-to-have

- [ ] **Logical, localizable naming** — device and parameter names read well to a non-technical user and can be translated.
- [ ] **Firmware/software updates** — device firmware can be updated through the Hub, where supported. *(The update API is still WIP.)*
- [ ] **User documentation** — a supported-device list, setup notes, and troubleshooting aimed at non-technical users.

---

## Reporting errors

The reliability rules above hinge on one habit: **catch errors at the edges and turn them into state, not exceptions.**

- Inside a background task or subscription loop, wrap the body in a `try/except`. On a per-device failure, set that device's `available`/`last_error` and keep the loop alive.
- Never let an exception cross into a `self.dependencies.output.*` call — the Hub treats those callbacks as trusted and an exception there can disrupt Hub-side handling.
- Log an expected failure once at the appropriate level; don't re-log the same condition every poll.

For controller-level problems that aren't tied to a single device (e.g. the backend/radio went away entirely), call `controller_did_encounter_error` — it surfaces a plain-language message to the user, and `still_running=False` marks the whole integration as failed. See [Reporting errors to the user](controller.md#controller_did_encounter_error).
