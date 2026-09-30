# 1. Architecture

The system is a single-process vertical slice with four boundaries: a planner decides one action from an observation; a surface adapter perceives and acts on a live UI; a compiler turns successful decisions into a typed artifact; and the replay engine interprets only that artifact. Discovery and replay share the Playwright surface and policy layer, but replay has no planner dependency. That separation is the central production invariant: model behavior cannot leak into deterministic execution.

The target is a local server-rendered member console. It is intentionally table-heavy and has no test IDs, but retains labels and accessibility roles where a real legacy application might. A local app avoids third-party terms, credentials, rate limits, and real PII while still exercising navigation, form input, extraction, not-found behavior, session expiry, screenshots, and browser traces.

The live planner uses OpenAI structured output to produce one validated `AgentDecision` at a time from an accessibility snapshot. Stopping is bounded by `max_steps`; malformed output, policy rejection, explicit escalation, and exhausted steps stop discovery. `ScriptedDemoPlanner` exists only for repeatable offline development and labels its evidence `discovery-offline` so it cannot be mistaken for model evidence.

# 2. Artifact schema

`CapabilityArtifact` is a versioned Pydantic model. It contains an agent-facing name and description, semantic version, approval state, target and route constraint, typed inputs and outputs, ordered steps, one final checkpoint, and explicit business-outcome rules. Each step declares action, locator, parameterized value, output binding, risk, timeout, and retry bound. Artifacts are JSON, reviewable without code, and reject invalid shapes before execution.

Locators carry both mechanism and rationale. The preference is role/name, then label or visible text, with scoped CSS as a last resort. This example uses a CSS locator only for a cell in the legacy summary table because the field has no semantic control of its own. Concrete discovery values are replaced with `{{parameter}}` references, including values embedded in the artifact description. Input and output sensitivity is part of the contract rather than an undocumented logging convention.

The result union deliberately separates `success`, `business_outcome`, and `failure`. A missing member is returned as a known outcome. Failures carry code, step, expectation, observation, screenshot, and optional intervention ID. Callers therefore do not need to infer business meaning from exceptions or log strings.

# 3. Determinism & error handling

Replay validates parameters and policy before opening the flow, substitutes only declared templates, resolves recorded locators, uses bounded waits/retries, checks the allowlist again after every navigation-causing action, extracts declared outputs, and verifies the final checkpoint. No model client is constructed on this path.

Known business outcomes are checked after each successful step, before later steps can fail misleadingly. A session-expired heading is a hard runtime failure with a screenshot. Locator timeouts, policy violations, unresolved parameters, and checkpoint mismatches produce structured failures. Every replay records redacted JSONL events and a Playwright trace; failures add a full-page screenshot. Retries are intentionally limited to the same deterministic action and do not ask an LLM to reinterpret the page.

UI drift is secondary here but observable: a failed locator identifies the exact step and rationale, and the trace preserves the DOM snapshot. In production, repeated locator failures would lower artifact confidence and trigger review rather than silently introducing fuzzy behavior.

# 4. Heterogeneity & multi-tenant

The artifact describes intent in surface-neutral operations (`click`, `fill`, `extract`, `wait`) and typed locators. `PlaywrightSurface` is the current adapter. A desktop adapter could map role/name locators to Windows UI Automation or macOS Accessibility, while an image adapter could add an image/anchor locator strategy. The replay engine and result taxonomy would remain unchanged; only observation, locator resolution, and primitive execution belong to the surface.

For multi-tenant use, I would store a canonical artifact per vendor product/version plus a small tenant profile: origin, route prefix, branding aliases, and locator overrides keyed by step ID. Overrides would be reviewed data, not copied artifacts. A preflight fingerprint (landmark roles, titles, and selected visual hashes) would choose a compatible profile. Replay telemetry would track success by vendor version and tenant; correlated failures would quarantine the artifact, while isolated failures would suggest a tenant override. Sensitive runtime values would never enter the profile.

# 5. Escalation & handoff

Replay can pause before any configured step. `InterventionManager` saves a request containing capability, step, reason, screenshot, and explicit control owner. With `--headed --wait-for-human`, the Playwright process stays alive and cedes the same browser page to the operator. A small injected audit listener stores click/change metadata in session storage across same-origin navigation. The separate `resume` command writes a signal; replay reads it, records the manual events and operator note, changes ownership back to automation, and continues.

This is intentionally a minimal operator surface, but the control-transfer mechanism is real. A production console would replace filesystem signaling with an authenticated lease and websocket, stream the existing browser via CDP/WebRTC, enforce one active controller, expire leases, and bind every action to an operator identity. The runner's pause/resume boundary would not change.

# 6. Safety

Policy uses an explicit origin allowlist, route regexes, and action allowlist. It runs during discovery and replay and rechecks the resulting URL after every step. Steps classify risk; irreversible actions require confirmation and are blocked by default. The sample capability is read-only.

Logs pass through recursive redaction. Secret-like keys, member identifiers, and balances are masked; artifacts store parameter names and sensitivity metadata, not runtime member values. The target contains synthetic records only. Screenshots and traces can still contain screen-visible data, so a production evidence store must be encrypted, access-controlled, tenant-scoped, retention-limited, and processed by visual/DOM redaction before persistence. This prototype documents rather than implements that infrastructure.

# 7. Cuts

I did not build distributed queues, persistent browser workers, authentication, a real co-browsing console, desktop adapters, tenant override storage, or artifact promotion workflows. The artifact includes `draft/approved`, but replay approval gating is not enabled because it is a stretch goal. Recovery does not call an LLM; ambiguous states stop safely.

The checked-in evidence includes a genuine model-driven discovery and deterministic success and not-found replays. The offline planner remains available only as a reproducible development fallback. Next I would add authenticated operator leases, visual redaction, approval/signing, a vendor/tenant compatibility registry, and stability scoring across repeated replays.
