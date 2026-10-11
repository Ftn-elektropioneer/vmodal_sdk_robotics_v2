
## 3. Fleet and operations (engineer side)

### F-32 (P1) Fleet status

- `vmodal-robot fleet-status --hosts robots.txt` (or each robot pushes its
  `status` JSON as a small metadata artifact) → one table: backlog bytes,
  oldest item age, blocked count, disk headroom, last searchable revision.

### F-33 (P2) Upload windows and bandwidth cap

- `--upload_window 22:00-06:00`, `--only_when_docked` (file/command probe),
  `--max_upload_bps` (rev3 scheduler contract). Markers with priority ≥ N may
  bypass the window.

### F-34 (P2) Live preview path (separate from durable path)

- Optional low-rate live JPEG/WebRTC preview of one camera for remote
  monitoring (rev3 StreamTransport). Never replays backlog; never shares the
  spool. Lower priority than the durable/search loop.

### F-35 (P2) Episode-level delete and retention

- `vmodal-robot forget --episode 41 --revision X`: removes remote video and
  metadata rows for that episode (collection API) and records a tombstone in the
  spool so it is never re-uploaded. Needed for bad takes and consent requests.
- Dependency: **needs backend** for per-file / per-row delete granularity;
  `collection_delete` is collection-level today.

### F-36 (P3) Privacy filter before upload

- Optional face / screen blur on video before admission (adapter-side
  converter, keeps the original local). Off by default.

## 4. Suggested delivery order

- Qualify stock transport (F-01) and capture timing (F-03), coordinating with
  analysis indexing and metadata (F-02, F-04) before end-to-end search acceptance.
- Add event markers (F-06), ROS ingestion (F-08), and priority upload (F-21).
- Add fleet operations (F-32–F-36) and demand-driven adapters (F-09–F-11).
- The full researcher-loop milestones are in the
  [analysis backlog](../ranalysis/todo/00_new_analysis.md#8-suggested-delivery-order).