"""The governed automation domain (F1): one machine route, isolated from every human cohort.

Nothing in this package writes to the shared prediction tables, labels a run with a cohort origin
(USER_REQUESTED, CONTROLLED_SMOKE or SCHEDULED_SHADOW_EVIDENCE), reads protected section 5A
evidence, or feeds calibration and control. Automated runs live only in the automation ledger.
One module owns each contract:

- ``origin``: the server-stamped automation origin;
- ``config``: the kill switch, the credential registry and the quota bounds;
- ``credentials``: route-only machine authentication;
- ``contract``: the strict request, the pinned ``radar_evidence.v1`` response, errors and hashes;
- ``ledger``: idempotency and audit, isolated from the cohort tables;
- ``quota``: the per-credential rate bounds;
- ``service``: the fail-closed orchestration of one call.
"""
