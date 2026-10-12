# VModal Robotics SDK v0.2.0 – Testing, Integration Experience, and Real-World Improvement Suggestions

*Tested on: Ubuntu 22.04 | Python 3.10 | LeRobot v3*

---

Recently I set up and tested the VModal Robotics SDK v0.2.0 on Ubuntu 22.04 (Python 3.10) — a lightweight Python tool designed to move finalized LeRobot v3 datasets from a robot to cloud storage in a crash-resilient way, without putting any network logic inside the robot control loop.

Here's what I found after a full installation, configuration, and code review.

---

## Installation

The recommended pip installation command from the README fails — the package installs as `UNKNOWN 0.0.0` instead of `vmodal-robotics 0.2.0`, and the `vmodal-robot` CLI command is not registered.

**Root cause:** `dynamic = ["version"]` in `pyproject.toml` cannot be resolved at build time by setuptools.

**Workaround:** Clone the repository and install from source using `bash test.sh`.

> ⚠️ Additionally, `test.sh`, `install.sh`, and `cli.sh` all use `python` instead of `python3`, which fails on Ubuntu/Debian out of the box.

---

## What I Found During Testing

After installing from source, all 12 test suites passed using synthetic data — no real robot or cloud account needed:

| Test Suite | Status |
|---|---|
| test_runner | ✅ passed |
| test_cli | ✅ passed |
| test_vmodal | ✅ passed |
| test_search_acceptance | ✅ passed (synthetic policy evidence) |
| test_measure_cloud_latency | ✅ passed (synthetic timing only) |
| temporal contract checks | ✅ passed |
| dataset acceptance | ✅ passed |
| test_artifacts | ✅ passed |

However, a status check against a fresh spool revealed that the stock transport is **not qualified for cloud delivery**:

```json
{
  "transport_qualification": {
    "qualified": false,
    "reason": "missing capabilities: ..."
  }
}
```

This means `run` and `flush` commands fail before any data is admitted — the SDK cannot deliver data to cloud out of the box.

---

## Known Issues and Future Goals

*From `docs/todo/fixes_v1.md` — development plan dated 2026-10-10. None of these fixes are implemented in v0.2.0 (confirmed by git history showing no changes to core source files in the latest release).*

### Known Issues

- Discovery stops after 100 manifests
- Rejected handoffs are never retried
- Spool never reclaims disk space automatically
- SIGTERM exceeds drain budget
- 100 MiB video size limit too small for real recordings
- Upload lanes are not truly independent
- No connectors for Foxglove, Trossen, ReductStore, AWS IoT
- Direct ROS2 integration not yet available

### Future Goals

- **Direct ROS2 integration** — A ROS2 node that automatically creates `ready.json` manifests would remove the manual integration step between ROS2 recording and the SDK.
- **Connectors for major platforms** — Foxglove, Trossen, ReductStore, and AWS IoT connectors are planned but not yet implemented.
- **Search qualification** — Short video clips (under 1 minute) index as a single frame; temporal sampling policy needs qualification.

---

## Real-World Integration Use Cases

Once transport qualification is resolved and the planned connectors are implemented, VModal SDK could serve as the data pipeline layer in several practical robotics workflows:

### 1. Manufacturing QA with Vision Robots
Robotic arms recording visual inspection data (e.g. defect detection) could use the SDK to automatically upload LeRobot datasets to cloud storage after each shift — without interrupting the control loop. The crash-resilient spool means a network outage during upload won't corrupt or lose inspection records.

### 2. Research Lab Dataset Collection
Academic labs running LeRobot experiments could use the SDK to centralize datasets from multiple robots to a shared cloud storage bucket, enabling collaborative training across lab members without manual file transfers.

### 3. Mobile Robot Fleet Management
A fleet of delivery or warehouse robots could each run the SDK locally, uploading trajectory and sensor datasets independently to cloud. The planned independent upload lanes would allow parallel uploads without one robot blocking another.

### 4. ROS2-Based Industrial Robots
Once the planned ROS2 node integration is available, robots using ROS2 for control could feed datasets directly into the SDK pipeline via auto-generated `ready.json` manifests — removing the current manual integration step entirely.

### 5. Long-Duration Autonomy Logging
Robots on extended autonomous missions (search-and-rescue, agricultural, outdoor inspection) generate large video recordings. Once the 100 MiB video size limit is lifted and the spool reclaims disk space automatically, the SDK would be suitable for continuous logging over multi-hour missions.

### 6. Multi-Platform Data Archiving
With the planned connectors for Foxglove, Trossen, ReductStore, and AWS IoT, teams could route the same LeRobot dataset to multiple platforms simultaneously — enabling visualization (Foxglove), hardware-specific logging (Trossen), time-series storage (ReductStore), and cloud ML pipelines (AWS IoT) from one upload step.

---

## Summary

VModal SDK v0.2.0 is functional for development and testing purposes. All 12 test suites pass on synthetic data. The two installation bugs (pip metadata, `python3` invocation) are minor and have simple workarounds. The `transport_qualification: false` status means cloud delivery is not yet operational out of the box, but the development roadmap in `fixes_v1.md` outlines a clear path to v1.0.

**Repo:** https://github.com/v-modal/vmodal_sdk_robotics/tree/main/lerobot
