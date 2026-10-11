# LeRobot robotics uplink — development fix plan v1

Date: 2026-10-10

Version: 1.0

Status: implementation plan; no runtime changes or live qualification performed

## User Specs

Fix continuous-capture ingestion, durable delivery, spool reclamation, video-size compatibility, upload-lane independence, bounded shutdown, and duplicate/collision behavior. Qualify short-video indexing, per-collection distance thresholds, and end-to-end latency before a consumer uses cloud results for robot decisions.

The implementation must preserve native LeRobot bytes and episode/camera references, reuse the existing SQLite spool and transport seam, and keep cloud work outside the robot control loop. The fault-injection suite must cover more than 100 manifests, network loss, a full spool, and SIGTERM during upload.

## Scope

- Primary implementation: `uinterface/sdk_ros_robot/lerobot/`.
- Shared upload dependency: `uinterface/sdk_python/`, only where its existing contract prevents correct robotics uploads or recovery.
- Backend dependencies: `../vmx_avideo/infra/search_api_ui/routers/apionly_upload.py` for storage/finalization; upstream indexing/search implementations for sampling and score qualification. Backend changes require coordinated changes in that repository.
- Release coupling: `.github/workflows/sdk_robot_test_release.yml`, the robotics export filter, package tests, and generated API documentation.
- Reference design: `uinterface/sdk_ros_robot/docs/03_interface_rev3.md`, especially immutable handoff, duplicate-safe recovery, acknowledged-data cleanup, and cloud/control-loop separation. This is a proposed broader architecture; this fix does not implement its entire component skeleton.

No new queue service, database server, ROS dependency, LeRobot runtime dependency, transcoding pipeline, or general plugin framework is needed. Retain the current source layout and public package/import names.

## Findings checked against the current checkout

Paths in this table are relative to `uinterface/sdk_ros_robot/lerobot/` unless stated otherwise. “Confirmed” means source inspection, not a reproduced live incident.

| Issue | Evidence and current behavior | Priority / owner |
| --- | --- | --- |
| Discovery stops after 100 manifests | Confirmed: `LeRobotAdapter.discover()` in `src/vmodal_robot/adapters/lerobot.py` slices the sorted glob before checking `_seen`. The same first 100 retained manifests occupy every future batch. | P0 / robotics |
| Rejected handoffs stop retrying | Additional confirmed defect: discovery marks a manifest seen before `Runner.admit()` knows whether `Spool.accept()` succeeded. An unchanged handoff rejected for quota is not retried by the same adapter after capacity returns. | P0 / robotics |
| Built-in transport cannot complete a revision | Confirmed: every LeRobot revision requires metadata, but `VmodalTransport.from_env()` supplies no `artifact_api`; non-video delivery and revision publication raise `TransportBlocked`. `Spool.claim_revision()` requires all artifacts acknowledged. | P0 / robotics + backend |
| Daemon never reclaims spool payloads | Confirmed: `Spool.cleanup()` requires artifact ACK and all referencing revisions ACK; `run()` and `flush()` never call it. Even a fully capable custom transport eventually fills its spool without an external cleanup caller. | P0 / robotics |
| 100 MiB video cap | Confirmed: `SpoolConfig.max_video_bytes` is 104,857,600 bytes and is absent from CLI construction. The reference Python SDK also enforces `MAX_VIDEO_UPLOAD_BYTES = 100 * 1024 * 1024` before choosing multipart. A CLI-only cap increase cannot fix cloud delivery. | P1 / robotics + Python SDK + backend |
| Oversized video rejects telemetry too | Confirmed: `_accept()` checks every video and the whole revision quota before copying/inserting the revision. This is intentional atomic admission but makes producer chunk sizing critical. | P1 / producer contract |
| Upload lanes advance in lock step | Confirmed: `cycle()` gathers one video and one aux operation and awaits both before taking the next pair. Existing `tests/test_runner.py:test2()` exercises manual `run_once()` calls, not daemon scheduling, so it misses this defect. | P1 / robotics |
| SIGTERM exceeds drain budget | Confirmed: `stop()` only changes a flag; the active cycle can finish after a 120-second request wait. `_run()` then starts a separate flush budget. `flush()` starts its deadline after recovery and does not bound the awaited cycle or final publication loop. | P0 / robotics + transport |
| Interrupted/ambiguous uploads can repeat | Confirmed: stock `reconcile()` returns `None`; recovery treats that as remote absence and requeues the item. Revision recovery also blindly returns interrupted publication to READY. Stable local IDs alone do not make remote effects idempotent. | P0 / robotics + backend |
| Extended outages exhaust delivery attempts | Confirmed: `RunnerConfig.max_attempts=10`; ordinary network failures eventually become BLOCKED. Payloads remain durable, but reconnection alone will not resume them. This requires an explicit unattended-outage policy. | P0 / robotics |
| Same basename can replace an earlier video | Current upstream source selects `video_filename` as the final name and uses `os.replace(tmp_file, dest)`. For the same user, collection, modality, stream, and final filename, successful finalization replaces the earlier local raw file. The robot supplies no user timestamp, so the timestamp-change conflict check does not protect it. This does not establish the behavior of every deployed version or every R2 staging object. | P0 / robotics + backend qualification |
| Spool video filename may fail finalization | Additional integration defect: spooled files are named `payload`; the Python SDK derives the upload `filename` from `artifact.local_ref`. The robot passes a preferred `.mp4` name, while current upstream finalization requires matching upload/preferred filename extensions. The inspected path can therefore fail with 422 before collision behavior is reached. Existing fake clients do not exercise this check. | P0 / robotics + integration tests |
| README names an unavailable test script | `test.sh` exists in this monorepo. However, `public_release_filter.txt` excludes both it and `tests/`, and the release workflow explicitly asserts their absence. The README tells a public clone to run a root `test.sh`, although the package is under `lerobot/`. This is an export/documentation mismatch. | P1 / docs + packaging |
| Clips under a minute index as one frame | Tester report; this bridge does not extract frames, create indexes, or implement search. Reproduce against the deployed index configuration before changing the uploader. | Qualification / backend |
| Score is distance; top confidence is 1.0 | Tester report requiring wire/metric qualification. Python SDK search-hit models currently allow arbitrary extra fields; no robotics acceptance policy exists here. Treat normalized confidence as ranking/display information. | Qualification / search consumer + backend |
| Search takes 40–60 ms | Tester observation, not a measured robot-to-decision bound. Upload ACK, revision publication, index readiness, and searchability are separate events. | Qualification / benchmark |

LeRobot upstream currently defines a default video-file target of 200 in its MB setting and uses camera-specific paths with repeated `file-NNN.mp4` basenames. That target must not be mistaken for a guaranteed strict maximum; pin and inspect the producer version used in qualification. Sources: [LeRobot dataset utilities](https://github.com/huggingface/lerobot/blob/main/src/lerobot/datasets/utils.py) and [v3 format documentation](https://huggingface.co/docs/lerobot/lerobot-dataset-v3).

## Critical invariant

The producer owns mutable capture data. An immutable ready manifest declares finalized source bytes; successful spool admission is the local durable ownership boundary. SQLite state, checksums, IDs, and receipts are authoritative for accepted artifacts. Discovery caches, status summaries, and cloud search indexes are derived state.

1. Discovering or parsing a manifest is not durable acceptance. Capacity rejection must leave it eligible for a later attempt.
2. A revision is accepted atomically. Never pretend telemetry completed a revision whose video was discarded.
3. Unacknowledged, uncertain, or blocked payloads are retained. Cleanup may remove only spool-owned payloads whose complete set of referencing revisions is durably published and whose retention period has expired.
4. A transport ACK must establish durable storage of the expected identity and bytes. HTTP success, an R2 key allocation, or indexing job submission alone is insufficient.
5. The same artifact/revision identity must have one logical remote effect across timeout, retry, process death, and lost response.
6. A shutdown deadline bounds the entire stop sequence from receipt of the signal, including in-flight requests, recovery, publication, and client close.
7. An aux worker must advance while a video upload is still in flight. Admission/copy work must not monopolize that worker's event loop.
8. Upload completion does not imply indexing completion or freshness. Cloud retrieval remains asynchronous robot memory; this plan introduces no synchronous cloud dependency into actuation.

## Data Contract

### Manifest discovery and local handoff

- Keep manifest `contract_version=1`, `source_format=lerobot`, and supported source version `v3`.
- `discover(limit)` limits eligible new/changed manifests after filtering, not the directory's first `limit` filenames. A non-positive limit returns no items.
- Keep producer files and ready manifests untouched by default. An optional producer-side archive policy may move a manifest only after confirmed local admission; uploader deletion is unnecessary for the discovery fix.
- Add explicit handoff feedback for the built-in adapter. Confirmation happens after `Spool.accept()` commits. Deferred capacity/I/O failures receive retry eligibility; malformed immutable inputs receive a recorded permanent rejection until their content changes.
- Preserve custom adapters that implement only `discover()` using an optional feedback hook, consistent with the runner's existing optional `drain_errors()` seam. Document this extension rather than requiring a breaking protocol change.
- Bound and rotate deferred discovery work so an unchanged oversized or quota-deferred manifest cannot monopolize the first batch. A restart may rescan old manifests; existing durable revision/artifact IDs make this safe without a second accepted-item database.
- Persist classified rejection/defer reasons using the existing spool rejection bookkeeping, with additive fields if required for CLI status. Report deferred capacity separately from malformed input and delivery BLOCKED states. Avoid appending the same rejection every poll.

### Artifact identity and remote naming

- Preserve existing dataset and artifact IDs for existing spools. Artifact IDs currently derive from persisted dataset ID, relative path, and checksum; revision IDs include the source revision and artifact IDs.
- Use the full existing artifact ID plus `.mp4` as the video storage name. Camera/chunk/source paths remain in `rel_path` and `source_refs`, and a revision maps those paths to remote receipts.
- The remote contract is scoped by destination and artifact identity: same ID + same checksum returns the same durable receipt; same ID + different checksum is a conflict. Retries may repair an incomplete transfer but must not enqueue duplicate indexing work or replace another artifact.
- Same basename in different cameras, chunks, datasets, or changed content must yield distinct final names. Do not flatten only the basename or use a random name per attempt.
- Keep source-relative clocks separate from UTC. Do not synthesize `start_datetime_user` from LeRobot episode-relative timestamps just to access CCTV behavior.
- Persisted dataset IDs survive ordinary restart, but are currently generated randomly on first admission. Exactly-once replay after deletion of the spool database is not guaranteed. Spool database loss requires a documented restore/reconciliation procedure, not silent fresh admission.

### Generic storage, revision publication, and recovery

- A qualified transport must durably deliver video, telemetry, metadata, and opaque artifacts without transforming original bytes.
- Reuse `deliver_artifact`, `reconcile_artifact`, and `publish_revision` at the existing `artifact_api` seam. Resolve original artifact references/checksums when publishing a revision; the current `DatasetRevision` carries IDs, so the receiving service must already know their descriptors or the publisher must supply them through the qualified API.
- Artifact receipts retain `artifact_id`, stable `remote_ref`, ACK status, and checksum evidence. Qualification must distinguish a remotely verified checksum from the current `_receipt()` fallback that merely echoes the expected local checksum.
- Reconciliation must distinguish confirmed stored, confirmed absent, and unknown/unavailable. `None` may mean confirmed absence only for a transport capable of making that check. Unsupported reconciliation is not evidence of absence.
- Revision publication is idempotent by `revision_id`. A lost publication receipt is recovered by lookup or repeat-idempotent publish, never by creating another logical revision.
- Classify failures at the transport boundary. For the unattended robot daemon, transient network/timeouts/service-unavailable failures remain retryable with capped exponential backoff and jitter while durable capacity is available; a routine outage must not become permanent solely after ten attempts. Preserve a finite attempt policy for callers that explicitly select it. Invalid inputs, unsupported operations, authorization/configuration errors, and checksum conflicts become visible operator-action states rather than endless upload loops.
- Additive schema changes preserve current WAL/FULL durability, existing rows, IDs, and receipts. Back up and test migrations on representative existing spools.

### Limits, retained bytes, and status

- Byte limits are integer bytes; documentation distinguishes MiB (`1024**2`) from decimal MB. Effective upload limit is the minimum of configured admission limit and qualified transport/backend limits.
- Expose `max_video_bytes` in `run`, `flush`, and `status` through shared spool construction; map a new variable in `env.sh` only because this value cannot be derived from total spool capacity.
- Validate the selected transport's supported size before admission. Do not accept a large backlog that the chosen transport can never deliver.
- Preserve all-or-nothing revision admission. For a deliberately independent telemetry stream, the producer can emit a separate complete manifest containing telemetry and its metadata snapshot; this is a producer contract change, not partial acceptance of the old revision.
- Retain receipt and identity records after payload cleanup for deduplication. Define `max_records` as the existing locally retained payload-record quota and expose total historical database records separately; document database-history growth rather than silently deleting replay evidence.
- Status includes artifact and revision counts by state, deferred handoffs/reasons, retained bytes, cleanup eligibility/last cleanup, and transport qualification. An empty runnable queue with blocked revisions or deferred handoffs must not look healthy.

### Search acceptance and freshness

- Qualify the raw distance field, metric, embedding model/version, preprocessing, collection/index version, and score direction before configuring a threshold. Do not rename or reinterpret SDK wire fields.
- A collection calibration profile records that scope, a version, held-out evaluation evidence, a chosen false-accept budget, and a maximum allowed distance `d_max`. Different models/modalities cannot share a threshold without qualification.
- A candidate is eligible only when its distance is finite, its calibration scope matches, `distance <= d_max`, and its observed age is within the consumer's explicit freshness budget. Missing calibration/metric/time evidence produces UNKNOWN; an empty result set is not proof that an object is absent.
- Result-relative `confidence=1.0` cannot override this ceiling. Do not publish a calibrated probability unless labeled evaluation actually supports one.
- This is a retrieval acceptance decision, not a safety-rated presence detector. Actuation continues to rely on local sensing/control.

## List of potential failures issues

| Failure | Required behavior / mitigation |
| --- | --- |
| Accepted manifests remain in ready directory | Continue past them to newer manifests; never require deletion for progress. |
| Capacity returns after a rejection | Retry the unchanged handoff fairly; no recorder rewrite/restart required. |
| Manifest disappears during a directory scan | Record/skip the per-file race and continue discovering others. |
| Admission hits ENOSPC or a checksum change | Roll back the whole revision, remove only incomplete spool copies, retain all producer bytes, and classify the failure. |
| Network drops before remote storage | Persist retry state and exact immutable bytes; bounded backoff avoids a hot loop and extended outages remain eligible after reconnection. |
| Network drops after remote storage | Reconcile or repeat an idempotent operation; preserve uncertain state until resolved. |
| Unsupported built-in generic transport | Fail capability validation before daemon admission, with an actionable error; do not gradually fill the disk with permanently blocked revisions. |
| Large video is admitted but SDK rejects it | Prevent using validated effective size limits and test the real SDK call path. Multipart does not bypass its preflight size cap. |
| Telemetry reserve exists but bundled video does not fit | Defer the whole manifest and report why; use bounded producer chunks or explicitly independent aux manifests. |
| Slow video, publication, or local copy | Other delivery workers continue; cap concurrency and move filesystem copying off the network event loop without sharing the SQLite connection across threads. |
| Cleanup runs while another revision still needs an artifact | Keep the payload until every reference qualifies; retain receipts and deduplication identity. |
| SIGTERM during recovery, upload, publication, or close | One absolute deadline; cancel outstanding tasks, retain uncertain claims, and exit within the tested bound. |
| Finalizer sees repeated `file-000.mp4` or `payload` names | Unique stable video names at staging and final storage; verify two different bytes remain retrievable. |
| Index has one sample despite several relevant events | Explicit sampling/window policy and short-clip regression fixtures; preserve event-time mapping. |
| Unrelated top search hit has confidence 1.0 | Reject beyond the calibrated raw-distance ceiling; keep stale/unqualified results UNKNOWN. |

## List of files to be changed

All robotics paths below are relative to `uinterface/sdk_ros_robot/lerobot/`. Add new files only in the phase that needs them.

| File | Planned responsibility |
| --- | --- |
| `src/vmodal_robot/adapters/lerobot.py` | Eligible-item batching, admission feedback, deferred fairness, per-manifest scan errors. |
| `src/vmodal_robot/runner.py` | Independent workers, single recovery pass, uncertain outcome handling, bounded shutdown, publication accounting, scheduled cleanup. |
| `src/vmodal_robot/spool.py` | Classified admission outcomes/status, compatible video object names, cleanup/recovery coupling, additive migrations where needed. |
| `src/vmodal_robot/contracts.py` | Document transport capabilities, receipt/reconciliation semantics, and optional adapter feedback; preserve current contract version unless wire incompatibility is unavoidable. |
| `src/vmodal_robot/transports/vmodal.py` | Qualified generic API wiring, stable remote names, capability validation, truthful receipts and reconciliation, close lifecycle. |
| `src/vmodal_robot/cli.py` | Shared video-size/retention settings, lifecycle in one event loop, one signal-time deadline, meaningful flush/exit outcome. |
| `src/vmodal_robot/utils.py` | Reuse existing hashing, stable-ID, and durable-copy helpers; add only needed reusable migration/timing/policy utilities. |
| `src/vmodal_robot/__init__.py` | Update exports only if a deliberate public contract addition is introduced. No automatic export of internal workers. |
| `env.sh` | Centralized mappings for new deployment controls that cannot be derived. |
| `tests/utils_datafake.py` | Multi-manifest/camera/chunk generators and deterministic fault hooks; count remote side effects, not just dictionary keys. |
| `tests/test_lerobot.py`, `tests/test_spool.py`, `tests/test_runner.py`, `tests/test_vmodal.py` | Expand existing regression/contract tests. |
| `tests/test_cli.py` (new) | Actual CLI option propagation and subprocess signal/deadline tests. |
| `tests/test_artifacts.py` | Export/documentation consistency and clean installation; retain current packaging boundaries. |
| `README.md`, `docs.py`, generated `docs_sdk/` | Correct capability claims, quickstart/testing paths, controls, recovery, and timing limits; regenerate HTML from source. |
| `docs/transport_contract.md` (new) | Qualified generic transport, idempotency, size/ACK guarantees, and operational recovery procedure. |
| `docs/search_qualification.md` (new) | Sampling/window decision, calibration schema/evidence, freshness budgets, and benchmark results. |
| `examples/measure_cloud_latency.py` (new) | Explicit live benchmark reusing public Python SDK upload/index/search operations. |
| `examples/search_acceptance.py` (new, after score qualification) | Small consumer example applying a collection profile and absolute ceiling; no robotics search facade. |
| `tests/test_measure_cloud_latency.py`, `tests/test_search_acceptance.py` (new) | Offline assertions for timing accounting and acceptance policy. |
| `pyproject.toml`, `MANIFEST.in`, `public_release_filter.txt` | Update only when qualified dependency versions or new public guides/examples require it. Keep internal tests and environment scripts out of runtime distributions. |
| `.github/workflows/sdk_robot_test_release.yml` (repository root) | Validate supported public docs/examples and existing offline/package gates without weakening secret detection. |
| `uinterface/sdk_python/src/vmodal/resources/collections.py` and its existing upload tests/docs | Conditional shared size/recovery changes; keep all SDK consumers compatible and qualify the published dependency, not just an editable monorepo copy. |
| `../vmx_avideo/infra/search_api_ui/routers/apionly_upload.py` and its existing tests | Conditional idempotent finalization/storage qualification and generic artifact/revision support. |

## Implementation step

### P0-A — Discovery progress and retryable admission

**Files:** adapter, runner admission, spool rejection/status bookkeeping, `tests/test_lerobot.py`, `tests/test_runner.py`, fake-data helpers.

1. Move the batch bound after seen/deferred filtering. Count selected eligible manifests rather than raw directory entries. Cover `limit=0` explicitly.
2. Add optional adapter admission feedback. Confirm accepted manifests only after the spool transaction succeeds. Treat `SpoolFull` as deferred capacity, not as successful discovery consumption; distinguish per-video deployment limits from temporary byte/record pressure.
3. Use fair rotation and retry eligibility for deferred candidates, so permanently oversized manifests do not repeatedly occupy every batch. Preserve unchanged accepted-manifest skipping during one process lifetime.
4. Keep durable deduplication in the existing spool. On restart, repeated manifests return existing revisions without recopying accepted objects or adding remote effects. Do not create another accepted-item ledger unless this proves insufficient.
5. Handle `stat`/load races per file. Retain invalid-manifest reasons without letting one bad file abort discovery or flooding the rejection table.

**Existing tests touched:** adapter valid/version/path/metadata checks; runner quota and oversized handoff checks.

**Test Cases:**

- 250 distinct immutable manifests, batch 100: subsequent polls admit all 250 while old files remain. Add a 251st file whose name sorts before earlier files and verify it is found.
- Accepted first 100 plus invalid/deferred candidates: later valid candidates still progress.
- Fill spool, defer an unchanged manifest, free eligible capacity, retry and admit it without rewriting or restarting the producer.
- Restart halfway through discovery: same revision/artifact IDs, no duplicate upload effects.
- `limit=0`, a removed manifest between glob and stat, and a corrected rejected manifest.

**How to test:** plain-assert adapter/runner tests via existing Fire entry points; no network.

### P0-B — Stable video names and duplicate-safe cloud delivery

**Files:** spool object naming/recovery, transport, contracts, existing spool/transport tests; upstream upload tests and Python SDK upload integration tests where needed.

1. Resolve the local filename-extension mismatch before treating current fake uploads as representative. Store new video spool objects under `<artifact_id>.mp4` and use that same stable name as `video_filename`; auxiliary payload naming can stay unchanged.
2. Migrate existing video `local_ref` values safely. Preserve IDs/states, verify checksum, durably materialize the new same-byte path, commit the new reference, then remove the old spool-owned path. Prefer a verified same-filesystem hard link and directory fsync so migration does not require a second payload's free space; if linking is unavailable, defer a copy migration until headroom exists. Recover crashes at each step without deleting the only accepted copy. Reuse existing durable-copy helpers for the fallback; a full spool must remain usable rather than starting an unsafe migration.
3. Update `os_recover()` to recognize both legacy `payload` and the new owned video names, remove only verified orphans, and clean interrupted migration artifacts. Cleanup must delete the persisted reference and leave no naming aliases consuming space.
4. Qualify current backend behavior with two camera files both named `file-000.mp4` and different checksums. Check both R2 staging identity and final raw paths; a unique final name alone is insufficient if both requests overwrite one staging object named `payload`.
5. Specify idempotent finalize/index side effects by artifact ID/checksum. The same request after remote success must return the same receipt without another logical index job. A checksum conflict blocks the item and preserves local evidence.
6. Make reconciliation outcomes explicit. Stock transport must not report unsupported lookup as confirmed absence. If neither reconciliation nor idempotent replay is available, fail capability validation or block an uncertain outcome with a precise recovery reason; do not blindly resend.
7. Qualify revision publication the same way. Persist its remote receipt and use lookup or idempotent publish after interruption.

**Existing tests touched:** `tests/test_vmodal.py:test1()` must assert stable naming and exercise real SDK serialization; fake lost-ACK/restart tests must count delivery/finalization/index side effects.

**Test Cases:**

- Two cameras and two chunks with identical basenames: four distinct final objects, bytes and original path mappings preserved.
- Different content at the same source-relative path: new artifact identity and no overwrite of the old artifact.
- Lost ACK during a running process and SIGKILL followed by restart: one logical remote artifact/revision and one indexing effect.
- Confirmed absence retries; unavailable/unsupported lookup retains uncertainty; conflicting checksum becomes BLOCKED.
- Existing spool migration crashes before/after local-ref commit; old pending objects remain deliverable and cleanup reclaims all owned payload bytes.
- Actual SDK `filename` and preferred name extensions agree; test cannot pass solely through `FakeCollections` accepting arbitrary keywords.

**How to test:** offline HTTP/storage stubs through the public SDK path, then an explicit disposable live collection qualification. Record deployed backend and installed SDK versions.

### P0-C — Complete the transport path and reclaim published payloads

**Files:** transport, contracts, runner, spool/status, CLI, transport contract guide, existing tests.

1. Qualify or implement the generic artifact and revision backend operations behind the existing `artifact_api` seam. `from_env()` must actually construct the qualified implementation used by the stock CLI; constructor injection in a unit test is not a production fix.
2. If a qualified generic API is unavailable, make the stock CLI fail before admitting LeRobot revisions, with the exact missing capabilities. Keep a custom qualified transport supported. Do not ACK metadata locally or weaken publication rules to make the spool appear drained.
3. Verify immutable metadata snapshots and original Parquet/opaque bytes are remotely retrievable by receipt. Publish revisions only after every member is acknowledged.
4. Invoke the existing `cleanup()` periodically in normal operation and after successful publication/drain, and before deferring admission for capacity. Add one explicit retention control; choose/document zero post-publication delay as the v1 deployment default only for a qualified durable backend.
5. Preserve the current all-referencing-revisions predicate. An artifact reused by an unpublished revision stays local even if an earlier revision is published. Keep cleanup idempotent and recoverable if a process dies between filesystem removal and database update.
6. Correct flush completion/status accounting to include revision states. Currently `pending_count()`/`blocked_count()` count only artifacts, so a failed revision publish can still produce an apparent successful flush.
7. Add revision/deferred/cleanup/capability status fields without removing existing JSON keys. Report healthy-idle, deferred-capacity, blocked-delivery, and uncertain-outcome distinctly.
8. Document an explicit audited requeue procedure for existing BLOCKED items after the missing capability is fixed. Reconcile first, requeue only applicable unsupported-capability items, and preserve corruption/checksum conflicts and receipts.
9. Implement the classified transient-outage retry policy for unattended operation and persist attempts/next retry time across restart. Keep finite-policy callers compatible. Expose operator-action failures and do not exhaust a normal network outage into permanent BLOCKED state.

**Test Cases:**

- Qualified stock construction uploads every kind, publishes the revision, and reclaims payloads automatically. Repeat enough revisions to exceed cumulative `max_bytes` while retained live bytes stay bounded.
- Unqualified stock construction rejects startup before data admission; existing accepted spool data remains intact.
- Metadata/video/revision ACK missing: no unsafe cleanup. Shared artifact referenced by an unfinished revision: no cleanup.
- Publication retry/failure keeps flush incomplete; blocked revision makes flush fail visibly even when artifact pending count is zero.
- Cleanup interruption, retention not yet expired, and disk-full rejection followed by automatic reclamation/re-admission.
- More than ten consecutive transient failures, restart while offline, then reconnection: the original bytes/identity deliver automatically. Invalid/auth/checksum failures stop appropriately and remain visible.

**How to test:** existing fake transport plus real generic API contract stub; live byte-for-byte retrieval only after backend capability qualification.

### P0-D — One bounded shutdown lifecycle

**Files:** runner, CLI, transport close behavior, `tests/test_runner.py`, new `tests/test_cli.py`.

1. Start one monotonic absolute deadline when SIGINT/SIGTERM arrives. Stop admission immediately and wake sleeping workers. Include the currently executing requests in that same drain budget.
2. Bound recovery, delivery, publication, worker joining, and transport close by remaining time. Cap each request timeout by the remaining budget, cancel in-flight tasks at expiry, and gather their completion before closing SQLite.
3. Preserve cancellation as an uncertain persisted SENDING claim unless a durable receipt was committed. Do not catch cancellation as an ordinary terminal transport error or reset to READY without reconciliation/idempotency.
4. Recover once before normal workers start. Avoid concurrent startup recovery from two lane workers and avoid re-running recovery against active claims during shutdown flush.
5. Keep client construction/use/close inside one `asyncio.run()` lifecycle. The current separate event loops for run/flush and `transport.close()` must be removed.
6. A second stop signal forces cancellation through the same durable-state rules. Emit whether the drain completed; use a meaningful CLI exit outcome for incomplete/blocked flush.
7. Document a service-specific stop-timeout setting with a small tested teardown margin above the SDK deadline. Do not rely on an assumed universal systemd default.
8. Account for admission-copy cancellation as well as network tasks. Cancelling an await of thread work does not stop its underlying file copy, and `asyncio.run()` can wait for executor shutdown. Give copy work cooperative stop checks between bounded blocks and test the actual process exit. Document the process manager's final hard-stop behavior for pathological blocking disk/transport code; restart must recover any incomplete objects without losing accepted data.

**Test Cases:**

- Subprocess SIGTERM mid-video, mid-aux, mid-recovery, mid-publication, idle sleep, and client close. With a 1-second test budget and 120-second configured request timeout, exit within budget plus a documented small test margin; no new admission after the signal.
- Zero drain budget exits promptly; future retry times do not extend the deadline; a blocked revision does not cause a false successful drain.
- A claimed artifact survives cancellation/restart with identical bytes and ID; ambiguous remote success is reconciled before further delivery.
- SIGKILL after remote storage but before local ACK exercises crash recovery independently of cooperative cancellation.
- SIGTERM during a large admission copy: no new committed revision after stop, no executor wait beyond the tested budget, source untouched, incomplete spool copy recovered on restart.

**How to test:** event-gated deterministic transports and Linux subprocess signal tests. A simple flag-only `stop()` unit test does not establish this behavior.

### P1-A — Support producer video sizes end to end

**Files:** shared spool CLI construction, `SpoolConfig`, `env.sh`, README, CLI/spool tests; reference SDK/backend limit handling where qualification requires it.

1. Expose `--max_video_bytes` and `VMODAL_ROBOT_MAX_VIDEO_BYTES` with positive-integer validation and consistent CLI-over-env precedence. Preserve existing positional API use by appending optional parameters rather than inserting them into published call signatures.
2. Treat 100 MiB as the current stock cloud limit until the reference SDK and backend qualify a larger value. For the LeRobot v3 deployment, target at least 256 MiB admission for typical 200-setting shards only after the chosen transport can deliver them; oversized single-episode shards still need an explicit policy.
3. Qualify an intact approximately 200-MB/MiB producer shard through upload, finalization, retrieval, and indexing. If larger native shards are supported, update the shared SDK/backend contract first and require a published compatible `vmodal` version in the robotics optional dependency.
4. If the cloud retains its smaller limit, configure producer shard rotation below it and fail incompatible deployment configuration early. Changing `multipart_threshold_bytes` or enabling lossy reduction is not a solution to the current preflight cap or native-byte contract.
5. Keep atomic admission and auxiliary reserve behavior explicit. A reserve protects independent aux revisions, not a mixed manifest containing an inadmissible video. Document separate aux handoffs only when the producer needs that independence.

**Test Cases:**

- Exact effective limit accepted, limit + 1 rejected/deferred with producer bytes intact; approximately 200-MB shard accepted only on a qualified larger transport.
- CLI/env/default propagation through run/status/flush; zero/negative configured values and incompatible transport limits fail clearly.
- Mixed oversized revision has no partial spool state; independent telemetry revision can use the reserved capacity.
- Large upload test traverses the reference SDK preflight and backend limits. Small fake fixtures use injected limits; do not allocate hundreds of MB for every unit test.

### P1-B — Truly independent video, aux, and publication workers

**Files:** runner, CLI lifecycle, any admission copy split in spool/utils, runner/CLI tests and README.

1. Keep one video worker and one aux worker alive independently. Each claims its next eligible item as soon as its previous operation finishes; do not rendezvous through `gather()` after every pair.
2. Keep revision publication in its own bounded worker so a slow publish does not stall either upload lane. Reuse `run_once()`/`publish_once()` and the existing state transitions instead of introducing a second scheduler.
3. Run discovery/admission coordination independently of network workers. Large hashing/copying must not block the network event loop. Split filesystem copy from short SQLite commit work and offload only the filesystem portion, with the cooperative stop checks required by P0-D; do not simply send `Spool.accept()` to a thread using the existing thread-bound SQLite connection.
4. Keep one SQLite owner and bounded in-flight work. Respect existing multipart concurrency=1 initially; more requests are not required to prove lane independence.
5. Sleep/wake on lane-specific retry eligibility or new work without hot polling. Do not let worker recovery see claims owned by another active worker. Keep `cycle()` usable for existing tests/callers, but make daemon progress independent of its batch barrier.
6. Ensure admission/cleanup/publication cannot delete an object currently referenced by an active delivery; acknowledged-state and reference gates remain authoritative.

**Test Cases:**

- Start the actual `run()` path, block the first video indefinitely with an event, admit several aux artifacts, and assert multiple aux ACKs before releasing video. Use synchronization events rather than long arbitrary sleeps.
- Repeat with blocked publication, video retry backoff, and a deliberately slow local file copy. Aux progress and signal handling continue.
- Concurrent workers claim each artifact once, preserve revision-before-cleanup ordering, stop together, and leave no background tasks after close.

### Q0 — Reproduce short-clip indexing and decide temporal sampling

**Files:** new search qualification guide and benchmark; conditional upstream indexing code/config/tests. The robotics adapter remains a finalized-artifact uploader.

1. Reproduce with decodable 5-, 15-, 30-, 59-, 60-, and 61-second videos containing known events near the beginning, middle, and end, across two cameras. Record actual indexed frame count, timestamps, event recall, and the selected embedding/index configuration.
2. Trace the existing indexer's duration-to-sampling rule and index configuration using the upstream graph/source. Record exact functions/files before opening the backend implementation change; do not assume splitting a video fixes a one-frame default.
3. Separate three controls: producer shard/finalization length, indexing frame-sampling interval, and semantic retrieval window length/overlap. A finalized LeRobot storage shard can contain many semantic windows; preserve original MP4 bytes and store window references rather than copying overlapping videos by default.
4. Benchmark explicit candidate windows of 2, 5, and 10 seconds with 0%, 25%, and 50% overlap. Select frame interval from the shortest event that must be detected and verify recall, queue volume, cloud cost, and freshness. These are experimental candidates, not a new production default.
5. Record the chosen policy per collection/index and its version. Require positive window length, `0 <= overlap < window_length`, monotonically mapped timestamps, terminal-window coverage, and a declared boundary policy for episodes and shard transitions.
6. Keep camera/episode/time mappings from LeRobot metadata. Never join another camera's offsets by basename, compare unrelated episode-relative clocks, or count duplicate overlapping hits as independent evidence.

**Test Cases:** multiple events recovered from a short clip, event across a window/shard boundary, final partial window, multiple episodes per file, variable frame rate, two cameras, and no-event clips. Count indexed samples and source-time references as well as search hits.

**Exit criterion:** the guide names the selected length/overlap/sampling policy, upstream configuration/patch, pinned versions, coverage/recall evidence, and tradeoff. No “under a minute means one frame” behavior may remain undocumented or unqualified.

### Q1 — Per-collection calibration and an absolute distance ceiling

**Files:** search qualification guide, minimal consumer example, `tests/test_search_acceptance.py`; conditional backend/Python SDK changes only if required score metadata is unavailable.

1. Capture actual search wire responses for text/image queries, including raw distance and normalized confidence. Verify metric/direction for every supported model and identify any combined-score transformation. Do not copy display thresholds into a robot policy.
2. Build labeled calibration/evaluation sets per collection using representative positives, hard negatives, empty scenes, lighting/camera variations, and stale captures. Split by episode/session to avoid overlap/frame leakage between calibration and held-out evaluation.
3. Choose the false-accept budget with the consumer owner, derive the maximum distance threshold from calibration, and report held-out false accepts/misses and sample counts. No universal numerical threshold or reliability claim is justified by the tester's top-hit score.
4. Implement one small example acceptance function after field qualification. Reject non-finite distances, wrong scope/model/index, distances beyond the ceiling, and stale timestamps. Return accepted/rejected/unknown plus raw evidence and calibration version; normalized confidence cannot promote a rejection.
5. Recalibrate when model, preprocessing, camera domain, segmentation/sampling policy, or collection/index version changes. Overlapping hits are correlated; do not multiply confidence or treat repeats as independent observations.
6. Keep the core robotics upload package free of a new search service/facade and ML dependencies. Use the reference Python SDK and a small versioned JSON profile at the consumer boundary.

**Test Cases:** unrelated single hit with confidence 1.0 rejected by distance; exact ceiling boundary; NaN/infinite/missing score; wrong model/collection/index; stale/missing timestamps; empty results; profile invalidation after policy/model change; top-k changes do not alter acceptance of an unchanged raw distance.

**Exit criterion:** each qualified collection has held-out evidence and an explicit absolute ceiling/freshness budget. Unqualified scope returns UNKNOWN and cannot drive actuation.

### Q2 — Measure capture-to-searchable latency before integration

**Files:** `examples/measure_cloud_latency.py`, its offline accounting tests, search qualification guide; reuse Python SDK index/search operations and existing transport receipts.

Measure the full chain and report both per-stage and end-to-end results:

| Stage | Required measurement |
| --- | --- |
| Capture buffering | Event/source capture to producer finalization; includes waiting for shard/window closure. |
| Handoff/admission | Finalized file to durable manifest and spool acceptance; include hashing/copy time. |
| Queue residence | Acceptance to first delivery attempt, including offline backlog and retries. |
| Upload | Request start through durable storage/finalization ACK; include transfer size and effective throughput. |
| Revision publication | Last artifact ACK to durable published revision. |
| Index processing | Submit/trigger to documented index-ready state; include backend queue time. |
| Search visibility | First verified retrieval of the known event from the new index; index job completion alone is insufficient. |
| Query/decision | Robot-client wall time for request, response, and acceptance evaluation; compare with server execution time separately. |
| Freshness | Event capture to accepted result/consumer decision, with explicit clock mapping. |

1. Use monotonic time for local elapsed intervals and correlated IDs for cross-service stages. Synchronize clocks or record bounded offset uncertainty; LeRobot source-relative clocks need an explicit wall-time anchor before reporting absolute freshness.
2. Exercise short clips and native larger shards, warm/cold indexes, one/multiple cameras, healthy Wi-Fi, bandwidth restriction, an outage/reconnect, and a pre-existing backlog. Fix window/sampling policy for each run.
3. Report sample count, p50/p95/p99, observed maximum, timeout/failure rate, bytes, retry counts, environment, and SDK/backend/model versions. Do not silently omit failed requests or add stage percentiles to manufacture an end-to-end percentile.
4. Use a disposable collection and explicit live invocation. Keep offline timing/policy checks in the ordinary suite; no hidden cloud uploads during `bash test.sh test`.
5. Compare measured freshness and tail latency with a consumer-defined deadline before integration. The reported 40–60 ms search time is only a query-stage observation. Until a budget and failure behavior are qualified, use cloud retrieval asynchronously for memory/review/planning and keep the local control loop independent.

**Test Cases:** fake clock/stage timestamps, missing index readiness, indexing failure, successful upload followed by delayed search visibility, outage queue residence, clock uncertainty, and results too stale for acceptance.

**Exit criterion:** checked-in results and a concrete suitability decision for the specified use case. This benchmark does not certify deterministic latency or safety of cloud control.

### P1-C — Correct public instructions and release validation

**Files:** robotics README, transport/search guides, generated docs, package/export tests and workflow as needed.

1. Keep private tests/test tooling out of the public runtime export, consistent with existing release assertions. Change the public README to explain the package-under-`lerobot/` layout and that the fake-data suite is maintained/run in the development repository.
2. Document the working monorepo command `cd uinterface/sdk_ros_robot/lerobot && bash test.sh test` separately from public installation/CLI examples. Do not advertise a public-clone `bash test.sh test` while the export intentionally omits it.
3. Correct the “independent lanes,” “restart reconciliation,” and “graceful drain” claims to match the qualified stock transport and daemon behavior. Include effective upload limits, capacity defer/retry, cleanup retention, uncertain recovery, and cloud latency boundaries.
4. Explicitly allow new public guides/examples in `public_release_filter.txt` only when they are intended for consumers. Keep `docs/todo/`, internal fixtures, env files, and private tooling excluded. Update staged-export checks so every documented public local path exists.
5. If an SDK/backend contract extension requires new routes, first compare against `../vmx_avideo/infra/search_api_ui/routers/apionly_routes.py`; never treat an SDK doc mirror as authoritative. Run parsed upstream/mirror/constants comparisons and required SDK route checks for route/path edits.
6. Generate docs with the existing `docs.py` rather than editing HTML, and preserve release secret-detection/offline/package dependencies. Validate locally/staged without triggering publication.

## Test Critical List

Paths relative to the repository root:

| Test file | Critical coverage |
| --- | --- |
| `uinterface/sdk_ros_robot/lerobot/tests/test_lerobot.py` | 250+ retained manifests, eligible batch limit, changing/invalid manifests, directory races. |
| `uinterface/sdk_ros_robot/lerobot/tests/test_spool.py` | Atomic admission, capacity reclaim, shared revision references, old spool migration, payload naming and orphan recovery. |
| `uinterface/sdk_ros_robot/lerobot/tests/test_runner.py` | Actual daemon lane independence, continuous deferred re-admission, transient outage, lost ACK, revision failures, automatic cleanup, bounded flush. |
| `uinterface/sdk_ros_robot/lerobot/tests/test_vmodal.py` | Qualified stock construction, real SDK wire behavior, unsupported capability rejection, naming, idempotency, receipts/reconciliation. |
| `uinterface/sdk_ros_robot/lerobot/tests/test_cli.py` | CLI/env size settings and signal-driven process shutdown during each awaited phase. |
| `uinterface/sdk_ros_robot/lerobot/tests/test_artifacts.py` | Package/install/export compatibility and truthful public instructions. |
| `uinterface/sdk_ros_robot/lerobot/tests/test_measure_cloud_latency.py` | End-to-end timing/freshness accounting and failures retained in reports. |
| `uinterface/sdk_ros_robot/lerobot/tests/test_search_acceptance.py` | Raw-distance ceiling, scope invalidation, non-finite scores, top-hit normalization, stale/unknown handling. |

Extend `tests/utils_datafake.py` and current tests first. Tests use plain assertions and Fire (`test1()` through `test9()`, `test_all()`), repository-required imports, and `dirtest="ztmp/ztests"` for generated output only. Keep committed `ztmptest/` read-only and never scan real `ztmp/` data. Use events/fake clocks for deterministic faults; subprocess signals cover actual process shutdown. Do not mask unexpected errors with broad try/except.

Fake MP4/Parquet byte strings are sufficient for transport/storage assertions, but not for decoding, indexing, frame counts, or presence calibration. Those qualifications require small real decodable test media and representative robot observations, isolated from the routine offline suite.

## Test for Data Contract List

| Contract | Verification |
| --- | --- |
| Native byte preservation | Remote retrieved bytes SHA-256 equals manifest/spool checksum for every artifact kind. |
| Path/camera/episode identity | Identical basenames remain distinct; revision receipts reconstruct original relative paths, cameras, row ranges, and time offsets. |
| Durable ownership | Crash before/after copy, admission transaction, ACK, publication, cleanup, and naming migration; exactly one recoverable accepted copy remains until safe deletion. |
| Receipt truth | Reject wrong ID, missing remote reference, conflicting checksum, non-durable acceptance, and unsupported reconciliation masquerading as absence. |
| Duplicate effects | Count remote creation, finalization, and index jobs across lost responses/restart, not just unique keys in an idempotent fake dictionary. |
| Revision completeness | Every referenced artifact ACK required; missing metadata, blocked member, or failed publication prevents completion/cleanup. |
| Capacity accounting | Retained payload bytes/records and deferred handoffs match actual storage; cleanup frees space automatically and historical identities remain usable. |
| Effective size | CLI/spool/reference SDK/backend agree; approximately 200-size native producer shards cannot be accepted and then permanently rejected downstream. |
| Shutdown state | Signal-time budget bounds all awaited phases; cancellation preserves uncertainty and restarts reconcile safely. |
| Search meaning | Raw metric, calibration version/scope, absolute ceiling, indexed temporal coverage, and freshness evidence determine eligibility. |

## Verification commands for implementation

These are future implementation checks, not evidence that fixes have already passed. From the repository root, initialize the existing environment; do not create a virtualenv/Conda environment:

```bash
source ./isetup_env.sh
export PYTHONPATH="$(pwd)"
cd uinterface/sdk_ros_robot/lerobot
bash test.sh test
bash test.sh package
python docs.py generate
python docs.py check
```

Register new offline test modules in the existing `test.sh` dispatcher. Run direct `python tests/test_<module>.py test_all` commands while iterating. Run signal tests on Linux, including the workflow's existing Python 3.10–3.13 matrix. The docs command requires the existing docs extra; do not silently add a new runtime dependency.

For any shared Python SDK upload change, run its upload-focused checks and `bash test.sh test` from `uinterface/sdk_python`. For route/path changes specifically, also run `python tests/test_routes.py test_all`, the parsed upstream route comparison, and the root-required full SDK checks. Use existing backend test entry points for coordinated changes; identify their exact names during backend implementation instead of inventing commands here.

Live qualification is a separate explicit operation. Record backend/build versions, published `vmodal` version, collection/model configuration, fault profile, all receipts, and latency/calibration evidence under the robotics `docs/`. Do not publish a release or trigger a live workflow merely to validate this plan.

## Implementation Order

1. **P0-A first:** recover discovery progress and capacity-deferred handoffs with regressions that fail on current behavior.
2. **P0-B and P0-C next:** agree on backend generic storage/idempotency capabilities, fix video naming, wire a genuinely usable stock transport, then activate safe automatic cleanup. Capability failure remains explicit until backend qualification passes.
3. **P0-D:** bound shutdown and preserve uncertain remote outcomes. Complete this before long-running deployment.
4. **P1-A and P1-B:** qualify effective video sizes and independent daemon workers; ensure the scheduler refactor preserves the shutdown and recovery tests.
5. **Q0 and Q2:** reproduce sampling and measure the entire latency chain before selecting a production temporal policy or use-case budget.
6. **Q1:** calibrate against the selected sampling/model/index policy, then implement the small consumer acceptance example.
7. **P1-C:** synchronize docs, staged exports, dependency versions, and release checks for the final behavior.

Local reliability fixes can be reviewed in separate changes, but stock transport completion, large-file compatibility, and duplicate-safe finalization are cross-repository contracts. Do not mark them complete from fake-only tests.

## Completion gates and rollout

- **Reliable local daemon:** more than 100 retained manifests progress; full-spool handoffs retry after reclamation; several aux deliveries finish during one blocked video; signal deadline is enforced; no unsafe payload deletion.
- **Qualified stock cloud path:** native bytes of every kind are retrievable; revision publication works; stable naming preserves cameras/chunks; lost responses/restarts create one logical remote effect; automatic cleanup keeps continuous operation bounded.
- **Producer compatibility:** a pinned actual LeRobot v3 shard layout/size is deliverable end to end, and original camera/episode/time references survive.
- **Qualified retrieval:** short-clip temporal coverage, per-collection absolute distance ceiling, held-out error evidence, and end-to-end freshness budget are recorded. Cloud retrieval remains outside actuation.
- **Reviewable release:** existing tests plus fault cases pass, old spool migration is verified, public instructions match staged artifacts, generated docs validate, and secret-detection/release gates remain intact.

Roll out first against copied old spool state and a disposable destination, then one robot with bounded production traffic. Preserve producer originals and a spool database/payload backup before migrations. Never run two daemon versions against the same spool. If rollback becomes necessary, stop the new daemon and verify old-schema/local-ref compatibility before restarting an older version; do not delete pending data to reclaim space.

## Planning limitations

This document is based on the current local source, existing tests, release/export rules, and cited LeRobot upstream references. No fault suite, cloud request, deployed-backend collision test, real robot calibration, or latency measurement was run while writing it. Reported short-clip sampling and score semantics remain explicit qualification items; deployed backend behavior and all numerical production thresholds must be verified before claiming support.
