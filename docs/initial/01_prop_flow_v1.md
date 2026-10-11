# ROS Robot Video Upload SDK — Flow Diagrams v1

Date: 2026-09-05
Status: Proposed architecture companion
Source of truth: [`01_prop_v1.md`](01_prop_v1.md)

## 1. Purpose and diagram index

This document turns the architecture proposal into focused implementation and maintenance flows. It describes the target design; it does not claim that the Rust crates or C++ compatibility shims already exist.

Conventions:

- Solid arrows carry data or required control.
- Dashed arrows show optional paths, references, or fallback integration.
- `RawVideoFrame`, `EncodedVideoPacket`, and `MediaObject` are the only media payload contracts inside the Rust core.
- Non-video ROS data remains serialized in the rosbag2/MCAP sidecar.
- In dependency diagrams, `A --> B` means **A depends on B**.
- Every video source selects exactly one ingestion mode: `mini_batch` or `stream`.
- `mini_batch` writes five-minute local files and asynchronously uploads only closed files through the spool.
- `stream` sends continuously through a bounded handoff and does not create local batch files on its normal path.

| Area | Diagrams |
|---|---|
| Interface with input data | System context, input routing, ROS image mapping, source activation and mode selection |
| Internal component flow | Runtime failure domains, public lifecycle, observability correlation |
| Data transformation | Media-path selection, canonical transformations, original/normalized lanes |
| Code dependencies | Rust crate graph, external libraries, C/C++ compatibility boundary |
| Reliability | Mini-batch spool/upload, stream sessions, crash recovery, pressure handling, format changes |
| Maintenance | Change-impact routing, new-adapter workflow, verification gates |

## 2. Interface with input data

### 2.1 System context

```mermaid
flowchart LR
    subgraph Inputs[Robot and file inputs]
        ROSIMG[ROS 2 Image and CompressedImage]
        ROSTEL[CameraInfo TF IMU LiDAR odometry and custom topics]
        DEVICE[V4L2 libcamera and C API devices]
        NETWORK[RTSP RTP SRT RTMP and WebRTC]
        OBJECT[Closed files MCAP and packaged rosbag2]
        VENDOR[C++ only vendor SDK]
    end

    subgraph Robot[Robot SDK]
        ROSADAPT[vmodal-ros adapters]
        CAPTURE[vmodal-capture]
        MCAP[vmodal-mcap sidecar control]
        FFI[vmodal-ffi safe wrapper]
        MODE{mini_batch or stream}
        SPOOL[(Ready files and SQLite WAL)]
        UPLOAD[vmodal-upload]
        SENDER[vmodal stream sender]
    end

    CPP[C++ compatibility shim]
    API[Upload control API]
    STORE[Object storage data plane]
    LIVE[Continuous stream endpoint]
    LIFECYCLE[Remote lifecycle processing]

    ROSIMG --> ROSADAPT --> CAPTURE
    ROSTEL --> MCAP
    DEVICE --> CAPTURE
    NETWORK --> CAPTURE
    OBJECT --> CAPTURE
    VENDOR --> CPP --> FFI --> CAPTURE
    CAPTURE --> MODE
    MODE -->|mini_batch 5-minute file| SPOOL
    MODE -->|stream bounded packet handoff| SENDER
    MCAP --> SPOOL
    SPOOL --> UPLOAD
    UPLOAD -->|create status sign complete done| API
    UPLOAD -->|signed multipart bytes| STORE
    SENDER -->|continuous encoded video| LIVE
    API --> LIFECYCLE
```

Maintenance rule: media inputs terminate at `vmodal-capture`, then the configured mode routes them either to the mini-batch spool or continuous stream sender. Telemetry terminates at MCAP. Capture adapters do not call upstream APIs directly.

### 2.2 Input routing into canonical contracts

```mermaid
flowchart TD
    INPUT[Configured source] --> KIND{Input class}

    KIND -->|ROS Image| RIMG[rclrs raw image adapter]
    KIND -->|ROS CompressedImage| CIMG[rclrs transport-aware adapter]
    KIND -->|custom encoded ROS topic| RENC[typed Rust adapter]
    KIND -->|V4L2 libcamera or network| GST[gstreamer-rs source adapter]
    KIND -->|closed immutable file| FILE[file object adapter]
    KIND -->|C++ only SDK| CABI[C ABI adapter or isolated sidecar]
    KIND -->|non-video ROS topic| BAG[rosbag2 MCAP recorder]

    RIMG --> RAW[RawVideoFrame]
    CIMG --> CFMT{Payload meaning proven?}
    CFMT -->|JPEG still frames| ENCODED[EncodedVideoPacket or lossless bundle]
    CFMT -->|PNG TIFF depth or unknown| RAWOBJ[Raw bundle or serialized original]
    RENC --> ENCODED
    GST --> GOUT{Probed payload kind}
    GOUT --> RAW
    GOUT --> ENCODED
    GOUT --> MEDIA[MediaObject]
    FILE --> MEDIA
    CABI --> FOUT{Adapter payload kind}
    FOUT --> RAW
    FOUT --> ENCODED
    FOUT --> MEDIA
    BAG --> SIDECAR[Closed MCAP MediaObject]

    RAW --> PLANNER[Media planner]
    ENCODED --> PLANNER
    MEDIA --> PLANNER
    RAWOBJ --> PLANNER
    PLANNER --> MODE{Configured ingestion mode}
    MODE -->|mini_batch batch_duration 5m| SPOOL[Durable spool]
    MODE -->|stream| SEND[Bounded continuous sender]
    SIDECAR --> SPOOL
```

The adapter must reject an input if it cannot prove frame, packet, or complete-object boundaries. An unknown format name alone is not a reason to reject a safely bounded original object. `stream` additionally requires a continuously sendable frame/packet contract; complete objects and MCAP sidecars use `mini_batch`.

### 2.3 ROS image and calibration mapping

```mermaid
flowchart LR
    subgraph ROS[ROS messages]
        IMG[sensor_msgs Image]
        CIMG[sensor_msgs CompressedImage]
        INFO[sensor_msgs CameraInfo]
    end

    IMG -->|height width encoding endianness step| DESC[MediaDescriptor]
    IMG -->|header stamp| CTIME[capture_time_ns]
    IMG -->|header frame_id| FRAME[coordinate_frame_id]
    IMG -->|data and ownership| PLANES[plane buffers]
    DESC --> RAW[RawVideoFrame]
    CTIME --> RAW
    FRAME --> RAW
    PLANES --> RAW

    CIMG -->|complete format string| PARSE[transport-specific parser]
    CIMG -->|header| CHEADER[timestamp and coordinate frame]
    PARSE --> CPAYLOAD[encoded packet or lossless bundle]
    CHEADER --> CPAYLOAD

    INFO -->|original changing calibration| MCAP[MCAP sidecar]
    RAW --> ASSOC[associate by source time and frame]
    CPAYLOAD --> ASSOC
    MCAP --> ASSOC
    ASSOC --> SESSION[Session manifest correlation]
```

The coordinate `frame_id` is never reused as an image sequence number. `CameraInfo` remains time-varying ROS data rather than a single frozen field in the media descriptor.

### 2.4 Source configuration and atomic activation

```mermaid
sequenceDiagram
    actor Operator
    participant SDK as vmodal-sdk
    participant Registry as Adapter registry
    participant Source as SourceAdapter
    participant Endpoint as Endpoint capabilities
    participant Planner as Media planner
    participant Admission as Capacity admission
    participant Pipeline as Isolated pipeline
    participant Manifest as SQLite manifest

    Operator->>SDK: configure source with mode
    SDK->>SDK: validate mini_batch plus 5m duration or stream
    SDK->>Registry: resolve kind and ABI version
    Registry-->>SDK: one adapter or typed error
    SDK->>Source: probe with deadline
    Source-->>SDK: factual SourceCapabilities
    SDK->>Endpoint: load live cached or static capabilities
    Endpoint-->>SDK: file-upload and live-stream capabilities
    SDK->>Planner: choose semantics-preserving path
    Planner-->>SDK: immutable MediaPlan
    SDK->>Admission: reserve mode-specific encoder disk spool or uplink budget
    Admission-->>SDK: admitted or quantitative rejection
    SDK->>Pipeline: open and preroll in isolation
    Pipeline-->>SDK: descriptor timing and keyframe validation
    alt mode is mini_batch
        SDK->>Manifest: persist source instance and timeline
        Manifest-->>SDK: committed
    else mode is stream
        SDK->>Endpoint: establish continuous stream session
        Endpoint-->>SDK: session ready
    end
    SDK->>Pipeline: atomically activate
    SDK-->>Operator: ACTIVE with negotiated plan
```

Any failure before activation destroys the candidate pipeline, releases its reservation, and leaves existing sources running.

## 3. Internal flow between components

### 3.1 Runtime processes and failure domains

```mermaid
flowchart LR
    subgraph CaptureProcess[Capture process]
        ROS[rclrs executor]
        CONTROL[SDK control loop]
        SRC1[Source worker A]
        SRC2[Source worker B]
        GST1[GStreamer pipeline A]
        GST2[GStreamer pipeline B]
        MODE{Per-source mode router}
        FINALIZE[5-minute file finalizer]

        ROS -->|bounded handoff| SRC1
        ROS -->|bounded handoff| SRC2
        CONTROL --> SRC1
        CONTROL --> SRC2
        SRC1 --> GST1 --> MODE
        SRC2 --> GST2 --> MODE
    end

    subgraph DurableBoundary[Durable boundary]
        FILES[Partial and ready files]
        DB[(SQLite WAL manifest)]
    end

    subgraph UploadProcess[Upload process]
        READER[Ready-object reader]
        SCHED[Fair scheduler]
        TASKS[Bounded Tokio transfer tasks]
        VERIFY[Verify and commit]

        READER --> SCHED --> TASKS --> VERIFY
    end

    subgraph StreamProcess[Continuous stream process]
        SQUEUE[Bounded packet queue]
        SENDER[Stream sender and reconnect]
        REMOTE[Upstream stream endpoint]

        SQUEUE --> SENDER --> REMOTE
    end

    subgraph SidecarProcess[Optional telemetry process]
        BAG[rosbag2 MCAP recorder]
    end

    MODE -->|mini_batch batch_duration 5m| FINALIZE
    MODE -->|stream| SQUEUE
    FINALIZE -->|atomic rename| FILES
    FINALIZE -->|transaction| DB
    BAG -->|closed MCAP| FILES
    BAG -->|object record| DB
    FILES --> READER
    DB --> READER
    VERIFY --> DB
```

In `mini_batch`, only immutable files and manifest state cross into upload processing, so restarting the uploader does not interrupt capture. In `stream`, the bounded packet handoff is intentionally non-durable: sender/network stalls invoke the configured drop-or-stop policy instead of growing memory or writing an implicit batch file.

### 3.2 Public SDK lifecycle

```mermaid
stateDiagram-v2
    [*] --> Created
    Created --> Configured: configure
    Configured --> Starting: start
    Starting --> Running: sources admitted and active
    Starting --> Failed: startup contract failure
    Running --> Running: status or reload_sources
    Running --> Paused: pause one or all sources
    Paused --> Running: resume
    Running --> Flushing: flush
    Flushing --> Running: backlog committed
    Running --> Stopping: graceful stop
    Paused --> Stopping: graceful stop
    Stopping --> Stopped: mini-batch files finalized and streams closed
    Failed --> Stopping: cleanup
    Stopped --> [*]
```

The C/C++ lifecycle facade forwards these operations to the Rust API. It does not create a second lifecycle implementation.

### 3.3 Observability and correlation

```mermaid
flowchart LR
    SOURCE[Source adapter] --> SMETRIC[Source metrics]
    PIPE[Media pipeline] --> PMETRIC[Queue codec and timing metrics]
    SPOOL[Spool and SQLite] --> DMETRIC[Mini-batch file and backlog metrics]
    UPLOAD[Upload and stream transports] --> UMETRIC[Goodput retry reconnect and loss metrics]

    SMETRIC --> LABELS[robot session source timeline object IDs]
    PMETRIC --> LABELS
    DMETRIC --> LABELS
    UMETRIC --> LABELS

    LABELS --> ROSDIAG[ROS diagnostics]
    LABELS --> OPENMETRICS[OpenMetrics or textfile]
    LABELS --> LOGS[Structured logs]
    LABELS --> STATUS[SDK status]
```

Every alert includes source, timeline, and ingestion mode. Mini-batch alerts also correlate to a spool/remote object ID; stream alerts correlate to the upstream session and lost time interval.

## 4. Data transformation flows

### 4.1 Media-path selection

```mermaid
flowchart TD
    START[Probed source descriptor] --> COMPLETE{Complete immutable object?}
    COMPLETE -->|yes and endpoint accepts original| OBJECT[Object passthrough]
    COMPLETE -->|no| ENCODED{Safely framed encoded packets?}
    COMPLETE -->|yes but original rejected| ENCODED

    ENCODED -->|codec profile and framing accepted| PASS[Packet passthrough and remux]
    ENCODED -->|codec accepted container rejected| TRANSMUX[Transmux without decode]
    ENCODED -->|normalization required| HTRANS{Hardware transcode available?}

    HTRANS -->|yes| HWTRANS[Hardware decode convert encode]
    HTRANS -->|no| PRESERVE{Original or raw preservation allowed?}

    ENCODED -->|no| RAW{Representable raw frames?}
    RAW -->|yes| LOSSLESS{Lossless semantics required?}
    LOSSLESS -->|yes| BUNDLE[Lossless raw bundle]
    LOSSLESS -->|no| HWENC{Hardware encode available?}
    HWENC -->|yes| ENCODE[Hardware encode]
    HWENC -->|no| SW{Explicit software policy admitted?}

    PRESERVE -->|yes| ORIGINAL[Original-only object]
    PRESERVE -->|no| SW
    SW -->|yes| SOFTWARE[Software normalize]
    SW -->|no| REJECT[NO_SAFE_MEDIA_PATH]
    RAW -->|no but bounded original exists| ORIGINAL
    RAW -->|no boundary or unsafe layout| REJECT

    OBJECT --> ADMIT[Capacity admission]
    PASS --> ADMIT
    TRANSMUX --> ADMIT
    HWTRANS --> ADMIT
    BUNDLE --> ADMIT
    ENCODE --> ADMIT
    ORIGINAL --> ADMIT
    SOFTWARE --> ADMIT
```

Semantic preservation is evaluated before cost. Among semantically valid choices, prefer object passthrough, packet passthrough, zero-copy hardware, bounded-copy hardware, raw bundle, then software processing.

### 4.2 Ingestion mode routing

```mermaid
flowchart LR
    MEDIA[Planned encoded media] --> MODE{Source mode}

    MODE -->|mini_batch| FILE[Write local file for batch_duration 5m]
    FILE --> CLOSE[Close flush checksum and mark READY]
    CLOSE --> ASYNC[Asynchronous upload]
    ASYNC --> UPSTREAM[Upstream object ingestion]
    CLOSE --> NEXT[Immediately record next five-minute file]

    MODE -->|stream| QUEUE[Bounded stream queue]
    QUEUE --> SEND[Continuous upstream sender]
    SEND --> LIVE[Upstream stream ingestion]
    SEND -->|disconnect| RECONNECT[Bounded reconnect and report gap]
    RECONNECT --> SEND
```

The modes are mutually exclusive for one source pipeline. `mini_batch` never uploads a growing file; `stream` never waits for a five-minute boundary. An automatic, silent fallback between modes is forbidden.

### 4.3 Canonical transformation paths

```mermaid
flowchart LR
    subgraph RawPath[Raw frame path]
        RAW[RawVideoFrame] --> CAPS[validate planes stride color and time]
        CAPS --> CONVERT[minimal permitted conversion]
        CONVERT --> HWE[hardware encoder]
        HWE --> PARSER1[codec parser]
        PARSER1 --> PACKETS1[Mode-ready encoded packets]
    end

    subgraph EncodedPath[Encoded packet path]
        ENC[EncodedVideoPacket] --> DEPAY[depay or demux]
        DEPAY --> PARSER2[codec parser]
        PARSER2 --> PACKETS2[Mode-ready encoded packets]
    end

    subgraph ObjectPath[Object path]
        OBJ[MediaObject] --> IMMUTABLE[validate immutable and complete]
        IMMUTABLE --> STAGE[reflink hard-link when safe or copy]
        STAGE --> HASH[checksum]
    end

    subgraph SensorPath[Lossless robotics path]
        SENSOR[Depth Bayer thermal or ROS telemetry] --> BUNDLE[raw bundle or MCAP]
        BUNDLE --> HASH2[checksum]
    end

    PACKETS1 --> MODE[Ingestion mode routing]
    PACKETS2 --> MODE
    HASH --> READY
    HASH2 --> READY
```

The encoded path never inserts a decoder unless the selected immutable `MediaPlan` explicitly names a transcode path. Frame/packet outputs proceed to the mode router: `mini_batch` muxes them into a five-minute file, while `stream` forwards them continuously. Complete objects and sensor bundles proceed directly to the mini-batch spool.

### 4.4 Original and normalized derivative lanes

```mermaid
flowchart TD
    ASSET[One source asset] --> POLICY{Requested preservation policy}
    POLICY -->|original only| ORIGINAL[Original object]
    POLICY -->|normalized only| NORMAL[Normalized derivative]
    POLICY -->|both| BOTH[Create both objects]
    BOTH --> ORIGINAL
    BOTH --> NORMAL

    ORIGINAL --> OREC[Spool record with source_asset_id]
    NORMAL --> NREC[Spool record with source_asset_id and derivation_id]
    OREC --> OCOMMIT[Commit original lane]
    NREC --> NCOMMIT[Commit normalized lane]

    OCOMMIT --> COMPLETE{All requested lanes committed?}
    NCOMMIT --> COMPLETE
    COMPLETE -->|yes| ASSETDONE[Asset complete]
    COMPLETE -->|no| WAIT[Remain retryable]
```

This object-commit flow applies to `mini_batch`. Committing a normalized derivative must never mark the original lane complete when both were requested; `stream` uses its live session state instead.

## 5. Code structure dependencies

### 5.1 Rust crate dependency graph

```mermaid
flowchart TD
    CLI[vmodal-cli] --> SDK[vmodal-sdk]
    FFI[vmodal-ffi] --> SDK
    FFI --> CAPTURE[vmodal-capture]
    FFI --> CONTRACTS[vmodal-contracts]

    SDK --> ROS[vmodal-ros]
    SDK --> CAPTURE
    SDK --> SPOOL[vmodal-spool]
    SDK --> UPLOAD[vmodal-upload]
    SDK --> MCAP[vmodal-mcap]
    SDK --> CONTRACTS

    ROS --> CAPTURE
    ROS --> CONTRACTS
    CAPTURE --> CONTRACTS
    SPOOL --> CONTRACTS
    UPLOAD --> SPOOL
    UPLOAD --> CONTRACTS
    MCAP --> SPOOL
    MCAP --> CONTRACTS
```

Required rules:

- `vmodal-contracts` is the dependency leaf and owns no ROS, GStreamer, database, network, or C++ types.
- `vmodal-sdk` is the orchestration facade; lower crates never depend back on it.
- `vmodal-ffi` depends on the Rust core. The Rust core never depends on the compatibility facade.
- `vmodal-ros` implements source adapters against the trait owned by `vmodal-capture`; `vmodal-capture` does not depend on ROS.
- A dependency cycle is an architecture failure, not something to resolve with global state.

### 5.2 External library containment

```mermaid
flowchart LR
    ROS[vmodal-ros only] --> RCLRS[rclrs and generated ROS messages]
    CAPTURE[vmodal-capture only] --> GST[gstreamer-rs]
    SPOOL[vmodal-spool only] --> SQLITE[rusqlite and SQLite]
    UPLOAD[vmodal-upload only] --> HTTP[reqwest and hyper]
    UPLOAD --> TOKIO[Tokio]
    MCAP[vmodal-mcap only] --> ROSBAG[rosbag2 process and MCAP storage]
    FFI[vmodal-ffi only] --> CABI[C ABI and unsafe FFI]

    ROS --> TYPES[framework-owned contracts]
    CAPTURE --> TYPES
    SPOOL --> TYPES
    UPLOAD --> TYPES
    MCAP --> TYPES
    FFI --> TYPES
```

This containment allows an external library to be replaced without changing `vmodal-sdk` signatures or persisted media contracts.

### 5.3 Repository and service coupling

```mermaid
flowchart LR
    ROBOT[uinterface sdk_ros_robot Rust crates] --> UPLOAD
    UPLOAD[vmodal-upload] -. contract reference .-> SDKPY[uinterface sdk_python multipart implementation]
    UPLOAD -. optional TUS calls .-> STREAM[infra api_stream]
    UPLOAD -->|create status sign complete done| CONTROL[Existing upload control API]
    UPLOAD -->|signed URL PUT| STORE[Object storage]
    UPLOAD -->|continuous stream session| LIVE[Streaming endpoint]

    TESTS[Robot SDK contract fixtures] -->|compare| SDKPY
    TESTS -->|verify| CONTROL
```

`sdk_python` is the mini-batch upload-contract reference, not a runtime dependency. Route or payload changes must update the Rust file transport and its fixtures in the same change. Stream-session contracts are validated independently against the selected streaming endpoint.

### 5.4 C/C++ compatibility boundary

```mermaid
flowchart LR
    subgraph Consumers[Compatibility consumers]
        CAPP[Existing C or C++ application]
        VSDK[C++ only vendor SDK]
        RCLCPP[Optional rclcpp image_transport fallback]
    end

    HEADER[vmodal_ffi_v1.h]
    FACADE[Rust C lifecycle facade]
    CSHIM[Minimal C++ source shim]
    SAFE[vmodal-ffi safe Rust wrapper]
    TRAIT[Rust SourceAdapter trait]
    SDK[Rust RobotSdk]

    CAPP --> HEADER --> FACADE --> SDK
    VSDK --> CSHIM
    RCLCPP --> CSHIM
    CSHIM -->|one exported function table| HEADER
    HEADER --> SAFE --> TRAIT
```

Only opaque handles, fixed-width fields, byte slices, explicit lengths, synchronization handles, typed status codes, and release callbacks cross the boundary. No C++ exception or Rust panic may unwind across it.

### 5.5 FFI buffer ownership

```mermaid
sequenceDiagram
    participant Rust as vmodal-ffi
    participant Shim as C++ source shim
    participant Vendor as Vendor SDK
    participant Queue as Bounded Rust queue

    Rust->>Shim: start registered callbacks
    Shim->>Vendor: acquire frame
    Vendor-->>Shim: vendor buffer and lifetime token
    Shim-->>Rust: callback descriptor pointer length release_fn
    Rust->>Rust: validate ABI sizes descriptor and bounds
    alt queue has capacity
        Rust->>Queue: enqueue owned handle or bounded copy
        Queue-->>Rust: consumed
        Rust->>Shim: release_fn exactly once
        Shim->>Vendor: release vendor buffer
    else queue is full
        Rust->>Shim: release_fn immediately
        Shim->>Vendor: release vendor buffer
        Rust->>Rust: apply declared overflow policy and metric
    end
```

Every conformance test must prove release on success, rejection, cancellation, shutdown, and adapter error.

## 6. Reliability and lifecycle flows

### 6.1 Mini-batch spool-object state machine

```mermaid
stateDiagram-v2
    [*] --> WRITING
    WRITING --> READY: close flush checksum atomic rename
    WRITING --> QUARANTINED: crash or invalid partial
    READY --> UPLOADING: scheduler lease
    UPLOADING --> RETRY_WAIT: retryable failure
    RETRY_WAIT --> UPLOADING: backoff elapsed
    UPLOADING --> UPLOADED: remote bytes verified
    UPLOADED --> COMMITTED: endpoint finalization succeeds
    UPLOADED --> RETRY_WAIT: commit response lost or retryable
    UPLOADING --> FAILED_MANUAL: terminal contract failure
    RETRY_WAIT --> FAILED_MANUAL: retry policy exhausted
    COMMITTED --> RECLAIMABLE: retention policy permits
    RECLAIMABLE --> [*]: local delete
    QUARANTINED --> [*]: explicit repair or cleanup
```

This state machine applies only to `mode: mini_batch`. Only `.ready` immutable five-minute files may enter `UPLOADING`; only remotely verified and finalized objects may enter `COMMITTED`.

### 6.2 Multipart upload control and data planes

```mermaid
sequenceDiagram
    participant Scheduler
    participant Manifest as SQLite manifest
    participant API as Upload control API
    participant Store as Object storage

    Scheduler->>Manifest: lease READY object
    Scheduler->>Manifest: load checkpoint and file identity
    alt no reusable upload session
        Scheduler->>API: multipart create with idempotency request
        API-->>Scheduler: upload_id key part size and count
        Scheduler->>Manifest: persist session checkpoint
    end

    Scheduler->>API: multipart status
    API-->>Scheduler: authoritative uploaded parts or completed state
    Scheduler->>Scheduler: validate part sizes and checksums

    loop bounded batches of missing parts
        Scheduler->>API: sign missing part numbers
        API-->>Scheduler: short-lived signed URLs
        par bounded parallel PUTs
            Scheduler->>Store: PUT file range
            Store-->>Scheduler: ETag or checksum
        end
        Scheduler->>Manifest: persist acknowledged parts
    end

    Scheduler->>API: status and complete ordered parts
    API-->>Scheduler: completed object and checksum
    Scheduler->>Manifest: mark UPLOADED
    Scheduler->>API: upload done with media metadata
    API-->>Scheduler: lifecycle destination confirmation
    Scheduler->>Manifest: mark COMMITTED
```

Media bytes bypass the API process. A lost response is reconciled from remote status rather than guessed from local state.

### 6.3 Continuous stream session

```mermaid
stateDiagram-v2
    [*] --> CONNECTING
    CONNECTING --> STREAMING: upstream accepts session
    CONNECTING --> BACKOFF: connect fails
    STREAMING --> STREAMING: send encoded packets continuously
    STREAMING --> BACKOFF: connection or endpoint failure
    BACKOFF --> CONNECTING: reconnect delay elapsed
    STREAMING --> CLOSING: graceful stop or reconfiguration
    CLOSING --> [*]: session closed
```

This state machine applies only to `mode: stream`. The sender uses a bounded queue while connecting or recovering. If the queue fills, it reports the exact loss interval or stops the source according to policy; it does not create an implicit local mini-batch file.

### 6.4 Crash and restart recovery

```mermaid
flowchart TD
    BOOT[Process start] --> OPEN[Open and migrate SQLite manifest]
    OPEN --> SCAN[Scan partial and ready files]
    SCAN --> PARTIAL{Stale partial file?}
    PARTIAL -->|repairable container| REPAIR[repair validate checksum]
    PARTIAL -->|not safely repairable| QUAR[quarantine and report]
    PARTIAL -->|none| ROWS[Reconcile manifest rows]
    REPAIR --> ROWS
    QUAR --> ROWS

    ROWS --> ORPHAN{Ready file without row?}
    ORPHAN -->|yes and valid| ADOPT[insert READY row]
    ORPHAN -->|invalid| QUAR2[quarantine]
    ORPHAN -->|no| ACTIVE[Inspect nonterminal uploads]
    ADOPT --> ACTIVE
    QUAR2 --> ACTIVE

    ACTIVE --> REMOTE[Ask transport for authoritative status]
    REMOTE -->|parts present| RESUME[resume missing ranges]
    REMOTE -->|object completed| COMMIT[retry final commit or done]
    REMOTE -->|session expired or absent| RECREATE[idempotently recreate or restart]
    REMOTE -->|contract mismatch| MANUAL[FAILED_MANUAL]
```

Recovery must never infer remote success solely from a local `UPLOADING` or `UPLOADED` row.

### 6.5 Backpressure and capacity exhaustion

```mermaid
flowchart TD
    SAMPLE[Periodic resource sample] --> MODE{Ingestion mode}
    MODE -->|mini_batch| HEALTHY{Disk spool and upload within budget?}
    MODE -->|stream| SHEALTHY{Uplink and stream queue within budget?}
    HEALTHY -->|yes| RUN[Continue capture and asynchronous upload]
    HEALTHY -->|no| DISK{Upload reads harming capture writes?}
    DISK -->|yes| REDUCE[Reduce upload concurrency]
    DISK -->|no| DRAIN{Network headroom available?}
    DRAIN -->|yes| INCREASE[Increase bounded upload concurrency]
    DRAIN -->|no| ADAPT{Adaptive quality authorized?}
    ADAPT -->|yes| LOWER[Close segment and activate lower profile]
    ADAPT -->|no| HIGH{Spool high watermark?}
    HIGH -->|yes| SHED[Reject or stop optional sources]
    HIGH -->|no| RUN
    SHED --> CRIT{Spool critical watermark?}
    CRIT -->|no| DEGRADED[Report degraded and predicted time to full]
    CRIT -->|yes| POLICY{Explicit terminal policy}
    POLICY -->|stop_capture| STOP[Stop affected source and finalize]
    POLICY -->|drop_oldest_uncommitted| DROP[Delete and count declared loss]
    POLICY -->|adaptive_quality| LOWER

    SHEALTHY -->|yes| SRUN[Continue streaming]
    SHEALTHY -->|no| SOVER{Adaptive quality authorized?}
    SOVER -->|yes| SLOWER[Start lower stream profile at safe boundary]
    SOVER -->|no| SPOLICY{Stream overflow policy}
    SPOLICY -->|reconnect_and_report_loss| SLOSS[Reconnect and count lost interval]
    SPOLICY -->|stop_source| SSTOP[Stop affected stream]
```

There is no implicit frame, file, packet, or oldest-file deletion. Every loss follows an explicit mode-specific policy and is counted by source, mode, and reason.

### 6.6 Disconnect and dynamic-format change

```mermaid
stateDiagram-v2
    [*] --> ACTIVE
    ACTIVE --> FINALIZING: source offline caps changed or timestamp regressed
    FINALIZING --> READY: mini_batch closes valid file
    FINALIZING --> STREAM_CLOSED: stream closes session and records gap
    FINALIZING --> QUARANTINED: mini_batch file cannot be recovered
    READY --> REPROBE
    STREAM_CLOSED --> REPROBE
    QUARANTINED --> REPROBE
    REPROBE --> REPLAN: new descriptor or source restored
    REPROBE --> BACKOFF: still unavailable
    BACKOFF --> REPROBE: reconnect deadline
    REPLAN --> READMIT: immutable new MediaPlan
    READMIT --> PREROLL: capacity reserved
    READMIT --> STOPPED: capacity or endpoint rejected
    PREROLL --> ACTIVE: keyframe timing and caps valid
    PREROLL --> BACKOFF: source path failed
```

Resolution, codec, profile, memory kind, clock domain, or ownership changes create a new descriptor revision and, when continuity is broken, a new timeline generation.

### 6.7 Graceful shutdown

```mermaid
sequenceDiagram
    actor Operator
    participant SDK
    participant Sources
    participant Pipelines
    participant Spool
    participant Upload

    Operator->>SDK: stop graceful with optional timeout
    SDK->>Sources: stop accepting new buffers
    SDK->>Pipelines: send EOS
    alt mode is mini_batch
        Pipelines->>Spool: finalize current five-minute file or raw bundle
        Spool->>Spool: flush rename ready and transact manifest
        SDK->>Upload: optionally flush committed backlog
        Upload-->>SDK: committed or durable resumable backlog
    else mode is stream
        Pipelines->>Upload: close continuous upstream session
        Upload-->>SDK: final stream status and reported gaps
    end
    SDK->>Upload: stop new leases and persist checkpoints
    SDK-->>Operator: stopped with backlog status
```

Shutdown may leave durable mini-batch `READY` or retryable objects, but it must not leave an object falsely marked committed. Stream shutdown closes the upstream session and does not invent a local recovery file.

## 7. Maintenance and verification flows

### 7.1 Where a change belongs

```mermaid
flowchart TD
    CHANGE[Requested change] --> TYPE{What changes?}
    TYPE -->|public lifecycle or status| SDK[vmodal-sdk]
    TYPE -->|canonical descriptor or persisted contract| CONTRACTS[vmodal-contracts]
    TYPE -->|ROS type QoS clock or calibration mapping| ROS[vmodal-ros]
    TYPE -->|source media path or GStreamer behavior| CAPTURE[vmodal-capture]
    TYPE -->|manifest migration recovery or retention| SPOOL[vmodal-spool]
    TYPE -->|file upload or stream protocol| UPLOAD[vmodal-upload]
    TYPE -->|raw bundle or rosbag2 lifecycle| MCAP[vmodal-mcap]
    TYPE -->|C caller or C++ vendor compatibility| FFI[vmodal-ffi and cpp_compat]

    CONTRACTS --> IMPACT[Run cross-crate compatibility impact]
    SPOOL --> MIGRATE[Add migration and crash fixtures]
    UPLOAD --> SYNC[Cross-check sdk_python and endpoint contract]
    FFI --> ABI[Preserve ABI or increment version]
    ROS --> DISTRO[Run every supported ROS distribution]
    CAPTURE --> CORPUS[Run format corpus and capacity tests]
```

Utility logic belongs in the lowest crate that owns its invariant. Do not duplicate contract parsing or state transitions in the CLI, ROS adapter, or C++ shim.

### 7.2 Adding a new source adapter

```mermaid
flowchart LR
    NEED[New source requirement] --> EXIST{Existing typed adapter?}
    EXIST -->|yes| CONFIG[Add configuration and fixture]
    EXIST -->|no| GST{Supported by GStreamer?}
    GST -->|yes| TEMPLATE[Add validated Rust pipeline template]
    GST -->|no| ROS{Generated ROS message available?}
    ROS -->|yes| RUST[Add typed Rust SourceAdapter]
    ROS -->|no| CAPI{Vendor C API available?}
    CAPI -->|yes| RUSTFFI[Add narrow Rust FFI binding]
    CAPI -->|no| CPP{C++ only and safe in process?}
    CPP -->|yes| CPPSHIM[Add minimal C ABI shim]
    CPP -->|no| SIDECAR[Add isolated sidecar]

    CONFIG --> HARNESS[Shared adapter conformance harness]
    TEMPLATE --> HARNESS
    RUST --> HARNESS
    RUSTFFI --> HARNESS
    CPPSHIM --> HARNESS
    SIDECAR --> HARNESS
    HARNESS --> RATE[Capacity and one-hour rate test]
    RATE --> MATRIX[Update generated capability matrix]
```

Uploader, spool, and canonical contracts should remain unchanged unless the new source exposes a semantic that the versioned descriptor genuinely cannot represent.

### 7.3 Contract-change impact

```mermaid
flowchart TD
    CONTRACT[Change in vmodal-contracts] --> VERSION{Backward compatible?}
    VERSION -->|yes| REV[Increment descriptor or schema revision]
    VERSION -->|no| MAJOR[Add new contract version and migration]

    REV --> ADAPTERS[All source adapters]
    MAJOR --> ADAPTERS
    REV --> MANIFEST[SQLite schema and migration]
    MAJOR --> MANIFEST
    REV --> UPLOAD[Endpoint metadata serialization]
    MAJOR --> UPLOAD
    REV --> FFI[C ABI size-versioned structures]
    MAJOR --> FFI
    REV --> DOCS[Proposal flow and endpoint docs]
    MAJOR --> DOCS

    ADAPTERS --> FIXTURES[Golden descriptor fixtures]
    MANIFEST --> FIXTURES
    UPLOAD --> FIXTURES
    FFI --> FIXTURES
    DOCS --> REVIEW[Cross-component consistency review]
    FIXTURES --> REVIEW
```

Unknown compatible fields must be preserved where the contract allows extensions; they must not be silently discarded by one adapter or FFI path.

### 7.4 Verification and release gates

```mermaid
flowchart LR
    BUILD[Build pinned Rust and optional C++ targets] --> UNIT[Crate unit tests]
    UNIT --> CONTRACT[Canonical and endpoint contract tests]
    CONTRACT --> ABI[C and C++ ABI tests]
    ABI --> CORPUS[ROS and media format corpus]
    CORPUS --> RECOVERY[Crash restart and network recovery]
    RECOVERY --> CAPACITY[One-hour mini-batch catch-up and stream reconnect capacity]
    CAPACITY --> SOAK[24-hour bounded-memory soak]
    SOAK --> MATRIX[Generate hardware capability matrix]
    MATRIX --> SECRET[Secret-detection release gate]
    SECRET --> RELEASE[Release artifact]

    DISTROS[Each supported ROS distribution] --> BUILD
    HARDWARE[Each supported hardware profile] --> CAPACITY
```

A release fails if any source silently drops archival data, any persisted state cannot recover, any C/C++ buffer leaks or double-releases, or the measured deployment lacks the required production headroom.

### 7.5 Documentation synchronization

```mermaid
flowchart TD
    CODE[Code or contract change] --> SUBJECT{Affected subject}
    SUBJECT -->|input format or ROS mapping| COMPAT[Compatibility tables and input diagrams]
    SUBJECT -->|crate boundary| DEPS[Package tree and dependency diagrams]
    SUBJECT -->|state or recovery| STATES[Spool recovery and shutdown diagrams]
    SUBJECT -->|endpoint protocol| UPLOAD[File-upload or stream flow and sdk_python cross-check where applicable]
    SUBJECT -->|C ABI| CPP[C++ part FFI diagrams and ABI tests]
    SUBJECT -->|capacity policy| PRESSURE[Admission backpressure and acceptance diagrams]

    COMPAT --> CHECK[Check proposal and flow document agree]
    DEPS --> CHECK
    STATES --> CHECK
    UPLOAD --> CHECK
    CPP --> CHECK
    PRESSURE --> CHECK
```

The proposal defines the contracts and decisions; this document visualizes them. Update both in the same change whenever behavior or ownership moves across a component boundary.
