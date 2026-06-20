# Handoff Packet

## Goal / Branch

- Goal: UI-D1.4B-FIX automatically mount and render calibration diagnostics in Model Quality.
- Branch: `codex/ui-d1-4b-fix-calibration-render-trigger`
- Base: `dev` at merged UI-D1.4B milestone `7a18795`
- Risk: frontend render-trigger fix only; review before merge.

## Root Cause

- `renderModelQualitySection` created an anonymous loading mount but did not initiate its
  own load.
- The request was coupled to a later document-wide attribute lookup in
  `renderStructuredDetail`, and replacement was gated on `mount.isConnected`.
- This external selector/timing dependency allowed the visible Model Quality render path to
  miss the automatic trigger even though the fetch/render helpers were present in bundle.
- The prior asset stamp also needed a bump so browsers load the corrected module instance.

## Fix

- Model Quality now retains its own calibration mount/content references and directly calls
  `loadCalibrationDiagnostics()` with a non-blocking promise during section construction.
- The resolved payload replaces that exact retained content node with
  `renderCalibrationDiagnostics(payload)`; no global DOM lookup or connectivity gate remains.
- The outer section always includes `data-calibration-diagnostics`, the heading
  `Live calibration diagnostics`, `Read-only diagnostic`, and the loading state.
- Loading, `OK`, and safe unavailable states preserve the same outer QA hook and heading.
- Existing 60-second cache, shared in-flight promise, single all-timeframe endpoint request,
  safe failure copy, diagnostic cards, and decision isolation are unchanged.
- Asset stamp is `ui-d1-4b-fix-calibration-render-trigger`.

## Browser QA Expectations

- Opening Detail should automatically issue one `GET /v1/calibration` request.
- `[data-calibration-diagnostics]` count should be at least one.
- Body text should include `Live calibration diagnostics` immediately and
  `Top-label hit rate` after an `OK` response renders.
- Reopening Detail within 60 seconds should use cache/shared in-flight state rather than
  fan out requests.

## Boundaries / Verification

- Frontend-only; no backend, schema, endpoint, calibration, decision, permission, gate,
  probability, migration, or database change.
- No metric enters decision logic; hard gates remain authoritative.
- Frontend tests: PASS, 45 passed.
- Full pytest: PASS, 278 passed with 7 existing warnings.
- JavaScript syntax, Ruff, safeguards, schema validation, and manual smoke: PASS.
- Protected backend/schema/script/migration diffs: empty.
- Unsafe wording and direct database/secret greps: empty; accuracy is explicitly negated.
- `AI/03_CURRENT_STATE.md` was not edited because this fix's strict scope permits only
  `AI/05_HANDOFF.md` / `AI/08*` / changelog documentation.
- No merge, deploy, push, or migration performed.
- Next: Claude review, then deployment and live DOM/Network QA as a separate approved step.
