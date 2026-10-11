
### F-08 (P1) ROS 2 rosbag2 / MCAP adapter

- Problem: the package is named `sdk_ros_robot` but only reads LeRobot v3. Most
  ROS labs record rosbag2 (MCAP).
- Feature: `RosbagArtifactAdapter` per `docs/03_interface_rev3.md` §4.1: detect
  finalized bag splits, keep the MCAP native, extract camera topics to MP4
  (optional converter behind the adapter boundary), extract selected scalar
  topics (`/joint_states`, `/tf`, `/wrench`, `/diagnostics`) to Parquet for
  F-04. `format_id = rosbag2/mcap`, `group_id = bag id`.
- Constraint: no ROS import in the core package; adapter is an optional extra
  (`vmodal-robotics[ros2]`). Core spool/transport untouched (ADP-06).

### F-09 (P2) Trossen / generic MCAP / proprietary adapters

- Same boundary as F-08 for TrossenMCAP and vendor bundles (rev3 §4.3–4.4).
  Priority set by user demand.
