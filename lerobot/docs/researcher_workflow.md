# Offline researcher workflow and recovery contract

The local package now provides deterministic temporal reconciliation, an offline
native contract validator, immutable sidecar handoff, receipt-bound descriptors,
and recovery from an independent artifact reader. Capture/control loops do not
call these operations. Stock cloud transport remains unqualified; this feature
does not invent a generic storage endpoint or claim deployed search visibility.

Run the acceptance example from a source checkout:

```bash
export PYTHONPATH="$PWD:$PWD/src"
python examples/researcher_workflow.py run --name=researcher_demo
python tests/test_dataset.py test_all
python tests/test_temporal.py test_all
```

Outputs remain under `ztmp/ztests/<name>/workstation-staging/`. The example uses
fake MP4/Parquet/audio bytes and a normalized mock scanner, freezes a separate
in-memory remote archive, deletes the producer and ready directory, and then
recovers every original and sidecar. It proves offline contract handling and
remote-only byte recovery. It does not prove actual LeRobot decoding, training
reader compatibility, a deployed backend, or semantic retrieval.

## Producer boundary

Call the pinned producer's actual finalization API first. For LeRobot v3 this
means closing/finalizing the dataset before inventorying it. Never snapshot
open Parquet writers or recording media. The producer supplies a complete closed
`RevisionInput` using existing contracts; hashes, paths and all required metadata
must describe the final immutable bytes.

`dataset_prepare(root, item, native, bundles, paths)` validates the supplied
normalized scanner output against the inventory and actual `meta/info.json`,
calls the same `temporal_bundle` function used at the workstation, and writes
four immutable sidecars. `paths` must explicitly name `native`, `temporal`,
`alignment`, and `quality`; names are caller-owned conventions, with no hidden
backend path definition. The existing metadata artifact kind carries these
JSON sidecars. Existing audio originals use `opaque`; no new audio upload kind
or endpoint is assumed.

The returned `RevisionInput` includes every original and sidecar. Its artifact
`source_refs` include the explicit sidecar paths. Original timing fields
`source_clock`, `start`, and `end` survive `dataset_ready(root, prepared,
ready_path)`, which writes an existing-format ready manifest atomically and last.
Use that handoff with the existing adapter, spool, runner and qualified transport.
The uploader does not recompute joins or mutate native timestamps during retry.

Immutable writes permit identical replay. Same path/different bytes fails; no
published mapping is overwritten. A failed preparation can leave closed
sidecars but never emits a ready manifest implicitly, so callers can inspect and
rerun the exact inputs safely.

## Native scanner contract

`native` is a versioned dictionary prepared by a pinned native scanner. It is
normalized evidence, not a claim that this package parses arbitrary LeRobot
Parquet or decodes MP4. Real deployments must supply and qualify that scanner.
The mock generator in `tests/utils_dataset_fake.py` demonstrates the complete
schema.

- `schema_version=1`, stable producer `dataset_id`, immutable `source_revision`, `producer_version`,
  `scanner_version`, `feature_profile_id`, and explicit `source_kind` of `real`,
  `simulation`, or `synthetic` identify inputs and semantics.
- `info_path` and a nonempty `metadata_paths` list name exact inventoried native
  metadata dependencies, including the producer's actual task, episode and stats
  paths. Inventory closure is explicit; filenames are not guessed.
- `features` must equal the actual `meta/info.json` feature declarations. State
  and action declare dtype, shape, component names, units and semantics. Camera
  keys use exact native video feature keys.
- `fps` must match metadata, `timestamp_tolerance_ns` must be explicit, and
  native `total_frames`/`total_episodes` must equal the closed normalized inventory.
  Native integer timestamps and sample spacing are validated without widening
  the pinned tolerance or repairing rows.
- `task_indices` enumerate unique metadata task IDs. Every row must resolve its
  task; missing state/action vectors, changed feature keys, NaN, or shape mismatch
  fail validation.
- Every `episodes` entry contains `episode_index`, `length`, `data_path`, physical
  half-open `row_start`/`row_end`, `start_index`, `reference_clock`,
  `reference_epoch`, `reference_start_ns`, and `video_bounds` for every camera.
  Each camera bound declares original path, integer `start_pts`/`end_pts`, and
  rational `time_base_num`/`time_base_den`. Shared-shard intervals may have capture
  gaps but cannot overlap ownership.
- Every `rows` entry contains episode/frame/dataset `index`, `timestamp_ns`,
  `task_index`, exact data shard `data_path`, physical `row_ordinal`, and feature
  values. Dataset-wide index is never substituted for a physical ordinal.

Simulation requires complete `simulation_provenance` with engine/version, seed,
scene/config hashes, robot model/calibration, control settings and positive step
duration. `utc_anchored` must be false and `simulation_destination` must equal the
explicit handoff destination. This preserves isolation intent, not a deployed
source-kind filter guarantee. Search qualification remains blocked until actual
isolation/filtering is proven.

## Temporal bundle contract

Each native sample needs exactly one persisted bundle. It contains `request`,
`profile`, `clocks`, `sources`, and `native_sample`. The first four fields are
passed directly to `vmodal_robot.reconciliation.temporal.temporal_bundle` on both
producer and workstation. Fractions serialize as numerator/denominator objects;
large integer nanoseconds are never converted to floating absolute timestamps.

`native_sample` contains `dataset_id`, immutable capture `source_revision`,
numeric `episode_index`, `frame_index`, original `timestamp_ns`, `data_path` and
physical `row_ordinal`. `request.sample_id` is the compact JSON encoding of
`[dataset_id, source_revision, episode_index, frame_index]`. Temporal request and
source episode IDs are strings, so native episode 0 uses `"0"`. The request's
reference clock/epoch must equal the episode contract and target time must be
exactly `reference_start_ns + timestamp_ns`. A changed canonical grid is a
derived dataset requiring a separately qualified writer/reader.

Every source path/checksum must occur in the immutable inventory. Video sources
must lie within that episode/camera's half-open PTS interval with the same time
base. Native telemetry/action ordinals must lie within the exact episode shard
range. Profiles must require every native camera, state and action; extra required
modalities such as audio remain explicit. Policies, per-modality budgets,
maximum ages/gaps, guaranteed uncertainties and pairwise budgets are defined by
the temporal component. Unanchored relative clocks can support training alignment
without claiming UTC or wall-clock search.

Failures remain structured in alignment/quality sidecars. Archive preparation
can retain invalid joins; `alignment_valid` is false and training/search remain
unqualified. There is no zero filling, cross-episode interpolation, silent audio
silence, or tolerance expansion.

For already-aligned native input, selected video PTS/path and state/action physical
rows must equal the canonical native row's original references. A bounded nearby
match cannot silently replace them; the result becomes unresolved with a native
reference mismatch reason. Additional ROS interpolation/conversion requires a
separately validated derived dataset rather than retiming this native layout.

## Publication and remote-only reconstruction

After all original and sidecar dependencies obtain qualified durable receipts,
`dataset_descriptor(handoff, revision, artifacts, receipts)` binds inventory
paths, kinds, content types, sizes, SHA256, artifact IDs, stable remote references,
source refs, destination and revision identity. Each dependency needs an
ACKNOWLEDGED receipt whose identity/checksum are verified. Reused immutable
artifacts remain explicit dependencies; current handoff source refs are
authoritative even when the original artifact's earlier refs mention an older
alignment sidecar.

The descriptor still needs durable publication through the qualified transport
implementation. Constructing a dictionary is not proof of publication. Persist
its checksum in an authenticated publication/discovery receipt. Neither producer
paths nor uploader spool payloads are recovery dependencies.

The descriptor explicitly preserves `native_dataset_id` beside the uploader's
`dataset_id`. The existing spool allocates its own persistent dataset UUID;
canonical native sample identities retain the producer's stable dataset ID.
Recovery verifies both mappings and never silently substitutes one for the other.

The reader seam is deliberately small:

```python
class ArtifactReader:
    def open_artifact(self, stable_remote_ref):
        # Return a binary context manager using the qualified SDK integration.
        # Resolve renewed download access while retaining exact immutable identity.
        ...

report = dataset_recover(reader, descriptor_ref, expected_descriptor_sha256,
                         "ztmp/ztests/recovered-revision")
```

The caller supplies a trusted descriptor digest and a staging directory. Recovery
checks that digest, enumerates the exact closure, restores original relative
paths, and validates every length/SHA256 before replacing a downloaded file.
Complete verified files resume without another artifact download; corrupt cached
files must be downloaded again and verified. Interrupted/truncated transfers,
invalid paths, symlinks, duplicate identities, foreign revision members, missing
sidecars or mismatched persisted joins fail closed. No completion is returned
until the entire closure and native contract pass. Expose the staging directory
to consumers only after `archive_valid` is returned; keep separate staging roots
for different descriptor revisions.

Recovery reloads normalized native inputs, reuses the persisted clocks/profile
and temporal component, and byte-compares canonical recomputed results with the
alignment sidecar. Ordinary inspection does not create uploads or pick a looser
matching policy.

## Late corrections and independent gates

A mapping-only correction supplies a new handoff `item.source_revision`, new
sidecar paths, `parent_descriptor_sha256`, and a nonempty `correction_reason`.
`native.source_revision` and canonical native sample identity remain the original
capture revision. Native bytes can be reused; the published descriptor/alignment
revision is new. Existing mappings stay immutable. Retimed rows or media instead
require a separately validated derived dataset.

Recovery reports `archive_valid` and `alignment_valid` independently. It always
leaves `training_loadable=False` and `search_resolvable=False`, with exact pending
reasons. A mock scanner or byte store cannot promote these flags. Production
qualification still needs all of the following evidence:

- A pinned real LeRobot reader reads every acceptance sample, required camera,
  task, state and action, then consumes the intended policy-shaped batch and
  bounded temporal windows. This checks compatibility, not policy performance.
- A deployed generic artifact implementation stores and renewably retrieves the
  complete descriptor closure, including reused dependencies, after cleanup.
- Qualified search asset/native PTS maps, capture clock anchors where required,
  index operation reconciliation, exact index version and known-event visibility
  resolve each hit against a published descriptor allowlist.
- Deployed sampling retains labeled short/terminal events within its coverage
  budget, and held-out semantic retrieval satisfies its distinct recall budget.
- Real derived subset exports regenerate episode/row/task/statistics metadata
  using pinned writer tooling. Local exclusions do not claim remote tombstones,
  shared-shard physical deletion or a valid arbitrary-frame training dataset.

The plain acceptance suite covers two cameras, two episodes sharing shards with a
real reference-time gap, non-file-local dataset indices, original sound windows,
remote-only recovery, verified resume/repair, corrupt/truncated bytes, tampered
persisted selections, invalid ordinals/features/tasks/timestamps, immutable replay,
versioned corrections, incomplete closure, receipt verification and simulation
provenance. Temporal tests separately exercise clock drift, resets, ambiguity,
causality, interpolation and action/audio uncertainty.
