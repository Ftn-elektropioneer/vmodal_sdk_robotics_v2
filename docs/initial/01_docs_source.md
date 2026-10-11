



## 19. OSS and protocol references

- [ROS 2 `image_transport` overview](https://github.com/ros-perception/image_common/blob/rolling/image_transport/doc/overview.rst) — plugin-based raw/compressed image subscription.
- [ROS 2 `common_interfaces`](https://github.com/ros2/common_interfaces) and [`sensor_msgs/Image`](https://github.com/ros2/common_interfaces/blob/rolling/sensor_msgs/msg/Image.msg) — standard robotics message families and the exact raw-image field contract.
- [ROS 2 image encodings](https://github.com/ros2/common_interfaces/blob/rolling/sensor_msgs/include/sensor_msgs/image_encodings.hpp) and [`sensor_msgs/CameraInfo`](https://github.com/ros2/common_interfaces/blob/rolling/sensor_msgs/msg/CameraInfo.msg) — standard pixel-encoding names, acquisition timestamps, optical frames, and calibration fields.
- [`sensor_msgs/CompressedImage`](https://github.com/ros2/common_interfaces/blob/rolling/sensor_msgs/msg/CompressedImage.msg) — transport-defined compressed payload format and acquisition/optical-frame header semantics.
- [rosbag2 recording and storage/serialization plugins](https://github.com/ros2/rosbag2/blob/rolling/README.md) — generic topic recording, QoS overrides, simulation time, transient-local repetition, splitting, MCAP storage, and serialization constraints.
- [`ros1_bridge`](https://github.com/ros2/ros1_bridge) — ROS 1/ROS 2 bridge behavior, build-time interface mappings, and supported-host constraints.
- [Gazebo ROS 2 integration](https://gazebosim.org/docs/harmonic/ros2_integration/) — exposing supported Gazebo Transport messages as ROS 2 topics through `ros_gz_bridge`.
- [ROS 2 QoS settings](https://docs.ros.org/en/humble/Concepts/Intermediate/About-Quality-of-Service-Settings.html) — sensor-data profile and compatibility rules.
- [GStreamer `appsrc`](https://gstreamer.freedesktop.org/documentation/app/appsrc.html) — injecting application/ROS buffers with bounded queue controls.
- [`rclrs` / ROS 2 for Rust](https://github.com/ros2-rust/ros2_rust) — Rust ROS 2 messages, subscriptions, QoS, clocks, graph queries, loaned messages, dynamic messages, and the upstream warning that the API does not yet provide stability guarantees.
- [GStreamer Rust bindings](https://gstreamer.freedesktop.org/documentation/rust/stable/latest/docs/gstreamer/index.html) and Rust [`AppSrc`](https://gstreamer.freedesktop.org/documentation/rust/stable/latest/docs/gstreamer_app/struct.AppSrc.html) — safe Rust APIs for GStreamer and application-fed media buffers.
- [GStreamer raw-video media types](https://gstreamer.freedesktop.org/documentation/additional/design/mediatype-video-raw.html) and [`GstVideoInfo`](https://gstreamer.freedesktop.org/documentation/video/video-info.html) — plane layout, strides, colorimetry, interlace, frame rate, and other raw-video semantics reflected in `MediaDescriptor`.
- [GStreamer media types and typefinding](https://gstreamer.freedesktop.org/documentation/plugin-development/advanced/media-types.html) — runtime identification and caps-based format negotiation.
- [GStreamer playback components](https://gstreamer.freedesktop.org/documentation/playback/index.html) — `parsebin`, `decodebin3`, and URI source building blocks used selectively by the planner.
- [GStreamer libav plugin](https://gstreamer.freedesktop.org/documentation/libav/index.html) — broad optional software decoder coverage.
- [GStreamer `splitmuxsink`](https://gstreamer.freedesktop.org/documentation/multifile/splitmuxsink.html) — time/size splitting at keyframe boundaries and asynchronous finalization.
- [GStreamer `rtspsrc`](https://gstreamer.freedesktop.org/documentation/rtsp/rtspsrc.html) and [`srtsrc`](https://gstreamer.freedesktop.org/documentation/srt/srtsrc.html) — reusable network source elements.
- [`ros_camera_server`](https://github.com/StefanFabian/ros_camera_server) — ROS/GStreamer live-source and output reference.
- [`rosbag2_storage_mcap`](https://github.com/ros2/rosbag2/blob/rolling/rosbag2_storage_mcap/README.md) — ROS 2 MCAP writer profiles, including `fastwrite` and chunked compression.
- [MCAP project](https://github.com/foxglove/mcap) — serialization-agnostic robotics log format and libraries.
- [Rust FFI and `repr(C)`](https://doc.rust-lang.org/nomicon/ffi.html) — explicit C calling convention, data layout, opaque handles, ownership, callbacks, and unwind constraints for the compatibility boundary.
- [Rust ABI reference](https://doc.rust-lang.org/reference/items/external-blocks.html) — the native Rust ABI has no stability guarantee, which is why dynamic compatibility uses a C ABI rather than Rust trait objects.
- [`reqwest::Client`](https://docs.rs/reqwest/latest/reqwest/struct.Client.html), [Tokio](https://tokio.rs/tokio/topics), and [`rusqlite`](https://docs.rs/rusqlite/latest/rusqlite/) — Rust connection pooling, bounded async orchestration, and SQLite access for the upload/spool implementation.
- [TUS resumable upload protocol 1.0](https://tus.io/protocols/resumable-upload/1-0-x) — authoritative offset reconciliation and resumable `PATCH` uploads.
- [`tusd`](https://github.com/tus/tusd) — OSS reference server with local, S3, and S3-compatible storage support.
- [Cloudflare Stream resumable uploads](https://developers.cloudflare.com/stream/uploading-videos/resumable-uploads/) — current TUS chunk constraints used by `infra/api_stream`.
- [Cloudflare R2 upload methods](https://developers.cloudflare.com/r2/objects/upload-objects/) — single versus multipart behavior, resumability, parallelism, and part limits.


