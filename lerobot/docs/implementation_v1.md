# Fixes v1 implementation and qualification status

Date: 2026-10-10. This record accompanies the private
[implementation plan](todo/fixes_v1.md). It is excluded from the public runtime
export. The implementation preserves the existing package layout and native
LeRobot bytes; no new queue service, database server, runtime dependency,
search service, or synchronous cloud control-loop dependency was introduced.

The ten blocks have local implementation or qualification tooling. **Local
completion does not establish qualified stock cloud support or production
retrieval suitability.** Stock `VmodalTransport.from_env()` intentionally fails
before spool construction because no generic backend has been qualified/wired.
A qualified Python custom-transport seam remains available. No release, live
workflow, hidden cloud upload, or deployed backend change is part of validation.

| Block | Local implementation/evidence | Remaining qualification gate |
| --- | --- | --- |
| P0-A discovery/handoff | Eligible-manifest batching, post-commit feedback, fair deferred retries, classified rejection status; `tests/test_lerobot.py`, `tests/test_spool.py`, `tests/test_runner.py`. | Representative sustained producer capture on robot. |
| P0-B stable names/idempotency | Full-ID MP4 naming, additive backup/migration, verified receipts, idempotent generic seam; `tests/test_vmodal.py`, `tests/test_spool.py`. | Stable deployed names; count remote effects/index jobs across lost-response/restart faults. |
| P0-C transport/retention | Capability validation before admission, generic transport seam, automatic cleanup only after artifact and all-reference publication ACKs; retained/history accounting; `tests/test_vmodal.py`, `tests/test_spool.py`, `tests/test_runner.py`. | Deployed generic byte storage/revision publication; retrieve every artifact kind; continuous qualified destination and bounded production traffic. |
| P0-D shutdown/recovery/outages | One absolute drain budget, signal cancellation, uncertain lookup/idempotent replay, unlimited transient retries by default; `tests/test_cli.py`, `tests/test_runner.py`. | Linux Python 3.10–3.13 workflow and robot/supervisor behavior; arbitrary stuck kernel I/O needs hard stop. |
| P1-A effective size | CLI/env/shared construction exposes positive integer admission cap; qualified transport limits checked before admission; real SDK preflight regression coverage. | Pin actual LeRobot shard layout/size and deploy backend support; SDK remains independently capped at 100 MiB. |
| P1-B independent workers | Video/aux/publication/admission workers; filesystem work off event loop, SQLite owner retained; daemon fault assertions in `tests/test_runner.py`. | Production storage and network fault profiles. |
| Q0 short-clip sampling | Upstream sampler traced; 12 decodable 5/15/30/59/60/61-second two-view clips exercised; beginning/middle samples retained, terminal events all filtered; [guide](search_qualification.md). | Deployed indexed counts/event recall, all candidate window policies, variable FPS/episode/shard boundaries, selected collection policy and cost/freshness evidence. |
| Q1 collection acceptance | Minimal raw-distance/freshness example, explicit UNKNOWN unqualified profile, scoped held-out evidence contract; `tests/test_search_acceptance.py`. | Actual wire metric/model/index provenance, representative labels, consumer-approved error/freshness budget, held-out ceiling per collection. |
| Q2 latency accounting | Explicit benchmark and offline tests retain missing/failure stages, report stages separately from observed end-to-end times; `tests/test_measure_cloud_latency.py`. | Disposable live collection, full clock-correlated capture-to-decision trace across network/backlog scenarios, pinned builds and concrete consumer suitability decision. |
| P1-C docs/release | Correct package-under-`lerobot/` installation, separate monorepo suite, transport/recovery guide, explicit public guide/example whitelist, staged install/local-link checks; `tests/test_artifacts.py`. | Local suite/package/generated-doc checks passed; existing secret/offline/package release gates remain required for publication. |

Q0's observed 24/36 labeled intervals with retained samples is temporal coverage,
not semantic retrieval recall. No production window/sampling policy is selected.
Q1's [profile](search_profile.json) remains unqualified with no production
numerical ceiling. Q2 must report a partial trace as partial; missing capture,
publication, or acceptance observations prevent a full-chain latency claim.

## Validation record

Final integration validation is run from the development `lerobot/` directory,
using the existing Python environment (no new environment):

```bash
bash test.sh test
bash test.sh package
python docs.py generate
python docs.py check
```

The root `isetup_env.sh` is absent in this checkout; local work uses the existing
Python 3.11 environment with the repository on `PYTHONPATH`. Focused assertion
checks were performed during implementation. Final integration on macOS with
Python 3.11.13 passed all nine test modules through `bash test.sh test`, then
`bash test.sh package`, `python docs.py generate`, and `python docs.py check`.
The staged export installs and both public examples run directly with isolated
installed-package paths. Shell syntax and authored-file whitespace checks passed.
Existing Linux workflow matrix execution is separate from local verification
and was not triggered.

Integration review additionally verified real SIGKILL after fake remote storage
but before local ACK, persistent creation/finalization/index-effect counters,
receipt-insert rollback, post-commit admission errors without payload deletion,
and legacy unverified ACK reconciliation before automatic reclamation. These
are local fault tests, not qualification of a deployed cloud receiver.

The public staged export intentionally excludes `tests/`, `test.sh`, env files,
private todo/implementation records, and fixtures. Consumer guides/examples are
explicitly included in the export and source distribution. Generated API HTML
must be produced by `docs.py`; hand-edited HTML is not validation evidence.
SDK route constants and API paths were not changed; route-sync checks are not
required for this diff. No shared upload cap was silently raised.

## Rollout and limits

Before migration, preserve producer originals and a complete consistent
database/payload backup; test a copied old spool against a disposable destination.
The automatic pre-migration database snapshot is not a payload backup. IDs remain
stable across ordinary restart, but database deletion can generate new dataset
IDs and loses exactly-once replay evidence. Retained legacy echoed receipts need
remote requalification before cleanup. Do not reset checksum conflicts or run
two versions on one spool. Review the [transport recovery procedure](transport_contract.md)
before selective audited operator requeue or rollback.

Deployment gates remain: qualified generic stock backend, actual producer
compatibility, short-clip indexed temporal coverage, held-out collection distance
ceilings, and measured capture-to-decision freshness with an explicit consumer
deadline. Cloud retrieval remains asynchronous memory/review/planning pending
those gates and outside the local actuation loop throughout.
