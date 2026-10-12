# Robot data analysis — Python and MCP endpoint backlog

Updated: 2026-10-11. Status: proposal / backlog. Robot-aware endpoints below
are **proposed**, not implemented. Existing SDK and MCP operations are listed
separately. Example method names describe intended interfaces, not runnable APIs.

Goal: search uploaded robot data, resolve moments to episodes and frames,
inspect aligned telemetry, and build datasets for training and evaluation
through Python APIs or MCP tools.

**P0** = required for usable results, **P1** = core analysis,
**P2** = productivity / scale, **P3** = later. Retained feature IDs match the
original backlog.

## 1. Existing operations and API contract

Reuse `uinterface/sdk_python` and `uinterface/mcp_python`:

- Search: Python `search_video` with text, base64 image, metadata, date,
  pagination, and `version_lancedb` parameters. MCP `find` also accepts image
  paths / URLs and can save matching frames.
- Collection discovery: `collection_groups_list`,
  `collection_subcollections_list`.
- Frame retrieval: `image_get_url(_bulk)`, `image_get_from_url`,
  `image_download_from_records`.
- Label persistence: `collection_upload_metadata` with JSONL,
  `write_mode`, and `allow_overlap`.
- Index inspection: `index_status`, `index_jobs_list`.

`uinterface/sdk_python` is the reference API contract. Proposed analysis APIs
reuse the `vmodal` client for VModal calls. MCP wrappers reuse the same analysis
logic and follow `mcp_python` parameter conventions: `collection_name`,
`sub_collection_name`, and `version_id`. Translate these to SDK parameters at
the interface boundary; do not introduce separate HTTP implementations.

Existing raw search hits include `score`, `mode`, `group_name`, `stream_name`,
`filename`, `source_path`, `ts_unix_13digits`, and `text_snippet`. They are not
resolved robot frame references.

## 2. Analysis inputs and outputs

- Inputs: already published collections, retained manifests, source revisions,
  video artifacts, telemetry artifacts, and optional event labels. Capture and
  upload are owned by the [robot backlog](../../todo/inside_ros/00_new_researcher.md).
- Manifest index: `artifact_id`, `dataset_key`, `source_revision`,
  `relative_path`, `camera_key`, episodes, video offsets, row ranges,
  `capture_start_unix_ms`, FPS, and remote reference. Analysis consumes an
  exported index without requiring access to the robot spool database.
- `RobotFrameRef`: dataset, source revision, artifact, episode, camera,
  frame index, episode-relative time, capture timestamp, and remote reference.
  Missing or ambiguous mappings must remain explicitly unresolved.
- Segment: source revision, episode, start / end times, cameras, best score,
  and hit count. Never merge across source revisions or episodes.
- Python returns typed records, pandas DataFrames, or artifact paths as
  appropriate. MCP returns JSON-serializable records, summaries, and artifact
  references using the same field names and timestamp units.
- Provenance: query, collection scope, filters, requested index version,
  source revisions, references, and scores accompany analysis outputs.

Clock anchors and artifact availability are upstream input requirements.
Remote manifest / telemetry retrieval remains blocked until a supported
artifact retrieval API is available. Source datasets remain read-only.

## 3. Proposed Python endpoints

### Search and retrieval

| Feature | Proposed Python interface | Behavior and acceptance |
| --- | --- | --- |
| F-12 (P0) Hit resolution | `vmodal_robot.resolve(hit, manifest_index)` and batch form | Return `RobotFrameRef` plus raw hit; flag missing / ambiguous mappings. Known hits must resolve to correct episode, camera, and frame, with matching pixels within a defined hash tolerance. |
| F-13 (P0) Manifest consumption | `vmodal_robot.load_manifest_index(path)` | Load a retained Parquet index keyed by `artifact_id`. Entries are append-only; remote reconstruction must match the export checksum. Manifest production / publication stays upstream. |
| F-14 (P1) Robot search | `RobotSearch.search(...)` | Wrap `search_video` for text, image examples, metadata, dates, collection scope, and index version. Convert local episode / frame / camera examples to base64. Return raw hits, references, scores, and version provenance; support pagination and all-results deduplication. |
| F-15 (P1) Moment grouping | `RobotSearch.group(hits, gap_s=1.0, per_episode=None)` | Merge nearby resolved hits within a source revision / episode across cameras. Rank segments by best score; `per_episode=1` selects one per episode. Keep unresolved hits separate. |
| F-16 (P1) Telemetry context | `RobotSearch.context(ref, before_s=2, after_s=2)` | Return aligned telemetry rows: joint states, actions, forces where available. Use local data first; remote data requires artifact retrieval. Report missing rows or clock alignment. |
| F-17 (P1) Media retrieval | `RobotSearch.frames(refs, out_dir)`; `RobotSearch.clips(segments, out_dir)` | Reuse SDK frame download operations; extract clips from available local video with optional ffmpeg. Return paths and source references. |
| F-18 (P2) Camera synchronization | `RobotSearch.camera_frames(ref, tolerance_ms)` | Return the nearest frame from each camera at the same capture timestamp, with offsets. Require clock anchors and flag cameras outside tolerance. |
| F-19 (P2) Search replay | `RobotSearch.replay(receipt)` | Rerun a recorded query and return a result diff. Receipts include SDK version and timestamp; actual index / model identity depends on backend exposure. |

### Analysis and curation

| Feature | Proposed Python interface | Behavior and acceptance |
| --- | --- | --- |
| F-20 (P1) Dataset export | `RobotSearch.export(refs, out_dir, unit)` | Export whole episodes or trimmed segments with re-indexed frames using optional LeRobot tooling. Refuse a non-empty output; preserve source data. Include revisions, artifact IDs, checksums, and search receipt. |
| F-22 (P1) Analysis tables | `vmodal_robot.pd_hits(hits)`; `vmodal_robot.pd_segments(segments)` | Return tidy DataFrames of references, timestamps, scores, and provenance. Keep pandas optional. |
| F-23 (P1) Label persistence | `RobotSearch.label(refs, labels, label_source)` | Store relevance / scenario labels with revision and segment references. Save locally; expose explicit metadata publication using the existing SDK operation and upstream metadata schema. |
| F-24 (P1) Retrieval evaluation | `RobotSearch.evaluate(events, collection_name, k)` | Return recall@k, first-hit rank, temporal coverage, and unresolved hits for labeled events. Distinguish sampling / ranking misses only with supporting evidence; otherwise use unknown. |
| F-25 (P2) Dataset metrics | `RobotSearch.report(source_revision=None)` | Return episode count, duration, cameras, FPS, success rate, event counts, indexed versus expected frames, and unresolved hits. Include upload / index lag only when timestamps exist; identify unavailable metrics. |
| F-26 (P2) Policy comparison | `RobotSearch.compare_policies(query, policy_versions)` | Search a shared scenario with policy metadata filters and group by episode. Return failure examples and success rates with outcome labels and explicit denominators. |
| F-27 (P2) Similar failures | `RobotSearch.similar_failures(ref, filters)` | Use image queries and group related moments by robot, policy, and scene. Embedding clustering depends on backend support. |
| F-28 (P3) Dataset hygiene | `RobotSearch.hygiene(dataset)` | Flag frozen cameras, black frames, and near-duplicate episodes using local hashes. Return source references without modifying data; cross-dataset embedding analysis depends on backend support. |

## 4. F-29 (P1) Proposed MCP endpoints

Robot-aware tools wrap the Python endpoints above. Existing MCP `find` remains
the baseline for raw search results.

| Proposed MCP tool | Python behavior | Feature IDs |
| --- | --- | --- |
| `robot_find` | Search, resolve, and group moments | F-12–F-15 |
| `robot_context` | Telemetry window summary and source references | F-16 |
| `robot_frames` | Retrieve frames or local clips | F-17 |
| `robot_camera_frames` | Retrieve synchronized camera frames | F-18 |
| `robot_replay` | Replay a receipt and return differences | F-19 |
| `robot_export` | Export an episode or segment dataset | F-20 |
| `robot_label` | Persist labels; explicitly request metadata publication | F-23 |
| `robot_evaluate` | Measure retrieval against labeled events | F-24 |
| `robot_report` | Return dataset quality metrics | F-25 |
| `robot_compare_policies` | Compare labeled scenario results | F-26 |
| `robot_similar_failures` | Search from a failure frame | F-27 |
| `robot_hygiene` | Return local dataset hygiene findings | F-28 |

Schemas must specify collection scope, source revision, timestamp units,
pagination, output paths, and local versus published label writes. Reuse the
Python contracts for missing data, unresolved references, provenance, and
export overwrite behavior. Large telemetry tables and media outputs should be
returned as artifact references with bounded summaries. Decide plugin entrypoint
versus separate server before implementation using existing registry conventions.

## 5. Use-case flows

Each flow uses the proposed endpoints above. Existing SDK search and frame
retrieval can supply raw hits today; robot resolution and aligned analysis
remain planned.

### A. Investigate a failed grasp

Input: collection `lab_pick_place`, robot/session scope, query "gripper drops
the red cube", and a manifest for the selected source revision.

1. Load the manifest and call `RobotSearch.search` with collection, metadata,
   time range, and an index version when supported.
2. Resolve hits and group adjacent frames with `RobotSearch.group`, keeping
   separate episodes distinct and combining cameras for the same moment.
3. Retrieve representative frames and call `RobotSearch.context` for two
   seconds before / after the hit; compare grip actions, joint states, and
   forces against the visible event.
4. Use `RobotSearch.camera_frames` when another camera can clarify the event;
   show its timestamp offset before treating views as synchronized.
5. Record a relevance judgment and failure label through `RobotSearch.label`.

Output: verified segment references, frame paths, aligned telemetry, labels,
and the search receipt. An unresolved hit or missing telemetry stays marked
as such; visual evidence alone cannot establish a force or action history.

### B. Build a training or evaluation dataset

Input: a scenario query such as "failed grasps on transparent objects",
collection scope, and accessible source datasets.

1. Search all requested pages, deduplicate hits, resolve them, and group them
   into segments. Retain the query and scope in a receipt.
2. Inspect frames / telemetry and label accepted or rejected candidates.
   Select references from accepted results only.
3. Call `RobotSearch.export` with `unit="episode"` to retain full context, or
   `unit="segment"` to produce trimmed, re-indexed episodes.
4. Return the new dataset location and export manifest with source revisions,
   artifact IDs, checksums, selected boundaries, and label provenance.

Output: a new dataset with traceable source membership. Stop export if source
artifacts are unavailable or the output directory is non-empty. Keep separate
source revisions distinct even when episode numbers match.

### C. Measure whether search finds known events

Input: labeled events containing source revision, episode, time interval,
and query; a collection; and a chosen `k` / index version.

1. Call `RobotSearch.evaluate` to search each event's query with the same
   scope and version, then resolve and group the returned hits.
2. Match results to labeled event intervals within the correct revision and
   episode; count each labeled event once when computing recall@k.
3. Return first-hit rank, temporal coverage, and missed / unresolved events
   with the evidence used for each diagnosis.
4. Use `RobotSearch.replay` after an index change to compare retrieved
   references and rerun evaluation against the same event set.

Output: an evaluation table and reproducible search receipts. An empty result
is not proof that an event never happened. The earlier
[search qualification](../../lerobot/docs/search_qualification.md)
reported all 12 terminal events missed by the default sampler in short clips;
measure this collection before claiming completeness.

### D. Compare policy versions on the same scenario

Input: one scenario query, policy versions, collection scope, and outcome
labels for the comparison population.

1. Call `RobotSearch.compare_policies` with the same scenario and search
   settings for every version; resolve results and group by episode.
2. Attach outcome labels and report episode counts, label coverage, and
   success rates per version. Describe whether denominators cover retrieved
   episodes or the full labeled scenario population.
3. Retrieve representative failure frames / telemetry per version, preserving
   their source references for follow-up investigation.

Output: comparison metrics and concrete failure examples. Missing outcomes
remain unknown. Search-selected episodes alone cannot establish an overall
policy success rate because retrieval may omit relevant episodes.

### E. Expand one failure into a failure family

Input: a verified failure frame reference and optional robot / scene / policy
filters.

1. Retrieve the example frame and call `RobotSearch.similar_failures` using
   an image query under the requested collection scope.
2. Resolve and group returned moments by robot, policy, and scene.
3. Inspect candidate frames and telemetry before assigning a shared failure
   label; publish confirmed labels only when explicitly requested.
4. Export accepted references or convert results with `pd_segments` for
   further Python analysis.

Output: reviewed related moments and label provenance. Visual similarity is
candidate evidence, not confirmation of the same physical failure cause.
Embedding clustering remains deferred until vectors are exposed by the API.

### F. Answer an analysis question through MCP

Input: "Find cube-drop failures in lab_pick_place and show what the gripper
was doing around each event."

1. `robot_find` searches within explicit collection / session scope and
   returns resolved segments, scores, pagination state, and a receipt.
2. `robot_frames` retrieves visual evidence; `robot_context` returns bounded
   telemetry summaries and references to full context tables.
3. `robot_camera_frames` supplies additional views when needed and available.
4. Return episode, camera, time, evidence references, and any unresolved or
   missing context. Separate observed evidence from inferred causes.
5. If requested, `robot_label` persists judgments or `robot_export` creates
   a dataset from selected references using the same Python contracts.

Output: a traceable answer backed by frames and telemetry. With only existing
MCP `find`, report raw filenames / timestamps and frame evidence; do not claim
robot-aware resolution or telemetry access exists yet.

### G. Check a dataset before downstream training

Input: a retained source revision and locally accessible dataset artifacts.

1. Call `RobotSearch.report` for episode / camera coverage, outcome label
   coverage, indexed frame counts, and unresolved mappings.
2. Call `RobotSearch.hygiene` to identify frozen, black, or duplicate frames
   and episodes with their source references.
3. Retrieve representative flagged frames and record reviewed exclusions as
   labels. Export a selected dataset only as an explicit subsequent operation.

Output: structured findings and reviewed exclusion references. Missing index
counts or lag timestamps remain unavailable metrics; source data stays intact.

## 6. Endpoint delivery order and open questions

- M1: F-12–F-14. Search a prepared collection by text and metadata, resolve
  known hits with a portable manifest, and verify frame pixels.
- M2: F-15–F-17, F-20, F-22–F-24. Fetch aligned telemetry, export failure
  segments, persist labels, and measure recall against labeled events.
- M3: F-29. Expose implemented Python analysis behavior through MCP with
  matching schemas and results.
- M4: F-18, F-19, F-25–F-28. Add synchronization, reproducibility, comparative
  analysis, and dataset quality endpoints.

Verify before implementing:

- Which metadata operators are supported, and how are metadata rows joined to
  frames: exact filename / timestamp or nearest timestamp?
- Are clock anchors sufficient to map search timestamps to episode frames and
  telemetry rows across cameras?
- How can workstations retrieve published manifests and telemetry artifacts?
- Does search expose the actual index version and model identity?
- Which metadata fields support policy, revision, outcome, and label filters?
- Should robot MCP tools use a plugin entrypoint or a separate server?

CLI commands, notebook UI, agent skills, capture, upload orchestration, ROS
adapters, and fleet operations are outside this backlog. Analysis runs outside
the robot control and recording loops. Search completeness must be measured
through F-24 for each collection.
