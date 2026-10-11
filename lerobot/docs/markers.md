# Durable source events

The public `mark` function and `vmodal-robot mark` write the same version-1
JSONL contract. The writer performs one bounded local append under a file lock
and fsyncs each record. Disk errors propagate to the caller. There are no network
calls, uploads, clock estimation or sample searches in the capture path. This
policy guarantees completed calls are durable under the filesystem's fsync
contract; it does not guarantee real-time disk latency.

```bash
vmodal-robot mark "grasp slipped" --tags=failure --path=./markers.jsonl
vmodal-robot markers_close --path=./markers.jsonl --target=./closed/episode-000.markers.jsonl
```

```python
from vmodal_robot import mark

mark("controller fault", ("failure",), path="./markers.jsonl",
     source_ns=100_000_000, clock="ros.header", epoch="reset-1",
     episode_index=0, uncertainty_ns=200_000, marker_id="fault-0001")
```

Supply a sensor/ROS stamp with its clock-reset epoch explicitly. The default
timestamp is process-qualified monotonic time and carries no UTC claim. ROS
callbacks can call the same function using their header stamp, `origin="ros"`
and timestamp meaning. A deployed ROS subscriber/hotkey integration remains
caller-owned; this package does not import ROS or guess topic semantics.

Each record preserves marker identity, label, tags, timestamp meaning, source
nanoseconds, clock, epoch, origin, episode hint and uncertainty. Records are at
most 4096 encoded bytes. The writer raises on larger records and failed writes;
it rolls back a failed partial append to the preceding complete record.

Rotate the active event file before hashing and handoff as an existing
`metadata` artifact. A closed artifact is never overwritten by the rotation
API. Subsequent writes create a new active file. All writers/rotators must use
this API's common lock. Include the closed artifact in the dataset descriptor's
explicit dependency inventory, so remote reconstruction preserves the events.
Late events belong in a new annotation revision.

Offline `marker_load(path)` deduplicates identical marker IDs and rejects
conflicting reuse. `marker_attach(marker, revision, frames, clocks, profile,
reference_clock, reference_epoch)` maps event time through a qualified transform
and uses `temporal_video` to select one same-episode frame. The caller supplies
one camera's records and a bounded profile. Fractional reference nanoseconds
round to nearest-even at the request boundary, with the rounding error included
in conservative uncertainty. Missing episode/clock maps, resets, ambiguity and
exceeded budgets produce `unattached` with a reason and retain the source event.

Markers do not change hashed media, alter source timestamps, invent wall-clock
anchors or qualify deployed event-aware sampling. Revision priority and backend
sampler hints need their own qualified scheduling/SDK contracts.

Verification: `python tests/test_markers.py test_all`.
