# Anghel .lab Showcase

> A machine-readable showcase of how Anghel .lab thinks, builds, fails, validates, and improves.  
> Anghel .labの思考・実装・失敗・検証・改善を、AIにも読める形でまとめるショーケース。

## Start here

AI / tool-based inspection should start from [`showcase.json`](./showcase.json).

Human readers can use this README as a short orientation, but the structured files are the primary evidence map.

```text
showcase.json
  -> contracts/evidence-contract.json
  -> claims/index.json
  -> cases/index.json
  -> cases/*/case.json
  -> validation/validate_showcase.py
```

## Status

**Public distribution snapshot (v1).**

This repository is a public-safe, non-canonical Evidence Package curated from a private workbench. Repository visibility and release state are managed separately from the package contents.

## Boundary

- This repository is **non-canonical**.
- Production / research SSOT remains outside this Showcase.
- Public artifacts must not be reverse-imported as production semantics.
- Raw runtime state, private context, secrets, and current production control-plane internals are excluded by default.
- A public fixture can prove the behavior of the fixture. It does not automatically prove that private production code is identical to it.
- Private workbench history, Issues, Pull Requests, review history, runtime state, and raw telemetry are intentionally not included in this distribution snapshot.

## Activity record

Source development activity is tracked outside this public distribution snapshot. Raw Research / Runtime Telemetry is not stored here.
