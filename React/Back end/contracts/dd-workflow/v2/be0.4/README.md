# DD workflow v2 — BE0.4 read-fixture freeze

This directory is the isolated, synthetic contract pack for `dd-workflow.v2-be0.4`.
It defines read shapes and examples only. It does **not** register FastAPI routes,
change database schemas, alter persistence, schedule work, or authorize mutations.

## Status and compatibility

- Contract: `dd-workflow.v2`
- Fixture version: `dd-workflow.v2-be0.4`
- Status: `read_fixture_frozen`
- Error envelope: existing `fs-compliance.v1`
- Investigation source compatibility: existing Source contract `1.0`
- Runtime behavior changed: **false**

All identities, identifiers, sources, evidence and timestamps are synthetic. Display
strings deliberately say “Synthetic” and the Georgian examples use `სატესტო`
(test). No runtime record was copied into this pack.

## Frozen read surface

The standalone OpenAPI document describes these proposed read contracts:

- workflow vocabulary, case detail/list/queue and authoritative workflow read;
- connector state/list and immutable connector-run list/detail reads;
- live-computed assessment read tied to `workflowVersion`;
- case-scoped report snapshot list/detail reads;
- standard errors, masking metadata, pagination and safe deep-link types.

The transition POST is present only to attach a version-conflict example. It is
marked `draft-be1+`, `x-executable: false`, has no approved request body, and must
not be called. Connector/report mutation action codes in examples are display-only
capability hints for later milestones. Unknown actions are ignored by clients;
actions are never authorization.

## Contract invariants

- Unit intervals are `number|null` in `0..1`; deprecated triage is
  `object|null` with `score` in `0..100|null`.
- `resultCount: 0` means an affirmative, completed `zero_results` run.
  Unavailable, permission-required and error runs use `resultCount: null`.
- Connector execution outcome and freshness are independent. A `partial` run may
  also be stale. `partialReason` is coverage metadata; `failure` is error-only.
- A selected/required never-run connector reduces coverage and has a start action,
  never a retry action. Eligible unselected connectors are excluded from the
  coverage denominator.
- Masking is a strict three-state model: visible, masked, or omitted. Queue subjects
  are display-only and never include a hidden raw value.
- All dictionary success envelopes include `_access`. Existing response middleware
  may additionally send `X-FS-Masked-Fields`.
- Report snapshots are immutable reads. Legacy null timestamps sort after non-null
  timestamps, with `snapshotId` as the stable tie-breaker.
- Safe routes are same-app absolute paths without query/fragment. Validation occurs
  after repeated percent-decoding and rejects schemes, protocol-relative paths,
  traversal, controls and backslashes.

## Deferred decisions

Retention periods, coverage thresholds, final outcome vocabulary, reviewer rules,
archive restoration policy, private-note policy and deletion execution remain
provisional product/counsel decisions. The schema exposes provisional policy IDs;
frontend code must not hard-code their durations or effects.

Every mutation family is listed in `manifest.json` as `draft-be1+` or later and
non-executable. No BE1+ request schema is frozen here.

## Validation and freeze

From this directory, after installing the isolated test dependency:

```powershell
python -m pip install -r tests/requirements.txt
python -m unittest discover -s tests -p "test_*.py" -v
```

`FREEZE.sha256` is the aggregate SHA-256 of every path in `manifest.freezeFiles`.
For each lexically sorted relative path, hash the file bytes and append
`path + NUL + lowercase_file_digest + LF` to the aggregate input. The contract test
recomputes and verifies this value.
