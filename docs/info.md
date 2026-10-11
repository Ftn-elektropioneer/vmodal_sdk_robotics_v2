


```markdown
When designing or evaluating a reference architecture for routing video from an edge robot running ROS/ROS 2 to a cloud environment, production-grade solutions generally fall into three established archetypes.
------------------------------
## Archetype 1: Managed Enterprise Cloud Ingestion (e.g., AWS Kinesis Reference Architecture)
Originally open-sourced via the [[aws-robotics/kinesisvideo-ros2](https://github.com/aws-robotics/kinesisvideo-ros2)](https://github.com/aws-robotics/kinesisvideo-ros2) stack and implemented widely on commercial fleets via edge container managers like [[AWS IoT Greengrass](https://aws.amazon.com/blogs/iot/ingesting-media-to-kinesis-video-streams/)](https://aws.amazon.com/blogs/iot/ingesting-media-to-kinesis-video-streams/). [1, 2, 3] 

┌───────────────────────── ROBOT EDGE ─────────────────────────┐     ┌────────── AWS CLOUD ──────────┐
│                                                              │     │                               │
│  [Camera Driver] ──► (sensor_msgs/Image)                     │     │  ┌─────────────────────────┐  │
│                               │                              │     │  │  Amazon Kinesis Video   │  │
│                               ▼                              │     │  │         Streams         │  │
│                   [h264_video_encoder Node]                  │     │  └────────────┬────────────┘  │
│                               │                              │     │               │               │
│                               ▼ (h264 NAL Units)             │     │               ▼               │
│                    [Kinesis Streamer Node]                   │     │  ┌─────────────────────────┐  │
│                               │                              │     │  │    Amazon Rekognition   │  │
│                               ▼ (MKV Fragmented Streams)     │     │  │     (AI / ML Inference) │  │
│                   [AWS Kinesis Video SDK C++] ───────────────┼────►┼─►└─────────────────────────┘  │
│                                                              │     │                               │
└──────────────────────────────────────────────────────────────┘     └───────────────────────────────┘


* 
* How it works: Raw ROS topics are intercepted by a localized H.264/H.265 compression node. The Kinesis Video Producer SDK wraps these compressed payloads inside an MKV container format and streams them using an optimized payload scheme over HTTPS/WebSockets to the cloud ingestion gate. [1, 4] 
* Core Strengths: Extremely resilient payload chunking. Out-of-the-box native plumbing into cloud AI/ML computer vision utilities (like Amazon Rekognition or custom SageMaker nodes). [1] 
* Best Used For: Machine learning data pipelines, cloud-side tele-analysis, security archiving, and persistent telemetry harvesting. [1] 
* 

------------------------------
## Archetype 2: Ultra-Low Latency Teleoperation Pipeline (e.g., WebRTC / GStreamer Architecture)
Modern fleet operations require sub-second latency for live piloting. Community reference packages like ros_camera_server explicitly replace traditional heavy TCP setups with dynamic [[WebRTC or SRT/RTP](https://discourse.openrobotics.org/t/camera-streaming-made-easy-new-release/54562)](https://discourse.openrobotics.org/t/camera-streaming-made-easy-new-release/54562) infrastructure. [5, 6, 7] 

┌───────────────────────── ROBOT EDGE ─────────────────────────┐     ┌────────── CLOUD / WebRTC ─────────┐
│                                                              │     │                                   │
│  [Camera Driver]                                             │     │       ┌───────────────────┐       │
│         │                                                    │     │       │ WebRTC Signaling  │       │
│         ▼ (sensor_msgs/CompressedImage)                      │     │       │      Gateway      │       │
│  [GStreamer / ffmpeg_pipeline]                               │     │       └─────────┬─────────┘       │
│         │ (Hardware Accelerated Encode)                      │     │                 ▲ (ICE Candidate) │
│         ▼                                                    │     │                 │                 │
│  [WebRTC Native Client (Signaling / STUN / TURN)] ───────────┼─────┼─────────────────┘                 │
│         │                                                    │     │                                   │
│         └───────────────────(Direct Peer-to-Peer SRT / RTP Video Track via UDP)─────────────────────┐ │
│                                                              │     │                                 │ │
└──────────────────────────────────────────────────────────────┘     └─────────────────────────────────┼─┘
                                                                                                       ▼
                                                                                             ┌───────────────────┐
                                                                                             │ Operator Web UI   │
                                                                                             │ (Foxglove / Custom)│
                                                                                             └───────────────────┘


* 
* How it works: Hardware-accelerated pipelines (e.g., [[ffmpeg_pipeline](https://github.com/yoshito-n-students/ffmpeg_pipeline)](https://github.com/yoshito-n-students/ffmpeg_pipeline) or customized GStreamer bridges) immediately downscale and compress camera frames. An integrated WebRTC client handles network signaling handshake configurations via a cloud gateway, establishing a direct peer-to-peer secure UDP pipeline. [5, 6, 7, 8] 
* Core Strengths: Extreme latency reduction (often sub-200ms end-to-end delay), ideal for dynamic Wi-Fi/Cellular handoffs due to aggressive UDP networking. It actively maps ROS metadata into custom RTP header structures to guarantee timeline alignment. [6, 7, 9] 
* Best Used For: Real-time remote operation (teleop), continuous situational mapping, and low-lag visual browser monitoring. [6, 10] 
* 

------------------------------
## Archetype 3: Distributed Cloud Robotics Framework (e.g., [FogROS 2](https://arxiv.org/pdf/2205.09778) Reference Architecture)
Developed as an open-source platform by UC Berkeley, [FogROS 2](https://arxiv.org/pdf/2205.09778) treats cloud compute assets as an extended local cluster by optimizing the underlying middleware. [10] 

┌───────────────────────── ROBOT EDGE ─────────────────────────┐     ┌─────────── CLOUD COMPUTE ─────────┐
│                                                              │     │                                   │
│  [Local Sensor Subscriptions]                                │     │  [FogROS2 Extracted Cloud Node]   │
│               │                                              │     │                 │                 │
│               ▼                                              │     │                 ▼                 │
│  [FogROS2 Local Video Compression Engine]                    │     │  [H.264 Stream Video Decompressor]│
│               │                                              │     │                 │                 │
│               ▼ (Stream Compression)                         │     │                 ▼                 │
│  [Secure VPN Tunnel / DDS Transceiver] ──────────────────────┼────►┼─►[Heavy Compute: Cloud SLAM / VLA]│
│                                                              │     │                                   │
└──────────────────────────────────────────────────────────────┘     └───────────────────────────────────┘


* 
* How it works: Extends the standard ros2 launch mechanisms. The framework automatically separates user-defined nodes (like deep perception or heavy visual SLAM models) and pushes them onto cloud VM nodes. It introduces an internal video compression transport module specifically to route video topics across standard DDS boundaries over the internet efficiently.
* Core Strengths: Seamless developer integration—no specialized custom web gateways are required since the cloud instances operate seamlessly within the native ROS 2 node architecture tree.
* Best Used For: Offloading intensive compute components (such as 3D neural scene reconstruction or complex grasping algorithms) to the cloud without sacrificing edge memory. [10, 11] 
* 

------------------------------
## Core Hardware-Software Matrix
This reference overview breaks down how these architectural layers align against typical system stacks:

| Component | Standard ROS Approach | Advanced Cloud Ingestion Standard | Industry Reference Tooling |
|---|---|---|---|
| Edge Ingestion | Uncompressed sensor_msgs/Image | Zero-Copy Shared Memory Borrowing | ROS 2 components, skinny_vision |
| Edge Encoding | CPU Bound Image Processing | Hardware ASICs via Jetson NVENC or Intel VAAPI | FFmpeg / GStreamer, ffmpeg_pipeline |
| Network Transport | DDS over TCP/UDP (Prone to drops) | Secure Fragmented Chunks or Adaptive Bitrate UDP | AWS Kinesis Video SDK C++, WebRTC |

Would you like to explore a concrete implementation example (such as a sample ROS 2 GStreamer element configuration) or dive deeper into how timestamp synchronization is managed across these network links? [6, 12] 

[1] [[https://github.com](https://github.com/aws-robotics/kinesisvideo-ros2)](https://github.com/aws-robotics/kinesisvideo-ros2)
[2] [[https://d1.awsstatic.com](https://d1.awsstatic.com/events/Summits/awstorontosummit/Patterns_for_cloud-enabled_robots_ROB201.pdf)](https://d1.awsstatic.com/events/Summits/awstorontosummit/Patterns_for_cloud-enabled_robots_ROB201.pdf)
[3] [[https://aws.amazon.com](https://aws.amazon.com/blogs/iot/ingesting-media-to-kinesis-video-streams/)](https://aws.amazon.com/blogs/iot/ingesting-media-to-kinesis-video-streams/)
[4] [[https://github.com](https://github.com/aws-robotics/kinesisvideo-ros2)](https://github.com/aws-robotics/kinesisvideo-ros2)
[5] [[https://transitiverobotics.com](https://transitiverobotics.com/blog/streaming-video-from-robots/)](https://transitiverobotics.com/blog/streaming-video-from-robots/)
[6] [[https://discourse.openrobotics.org](https://discourse.openrobotics.org/t/camera-streaming-made-easy-new-release/54562)](https://discourse.openrobotics.org/t/camera-streaming-made-easy-new-release/54562)
[7] [[https://robotics.stackexchange.com](https://robotics.stackexchange.com/questions/113144/how-to-visualize-images-and-pointcloud-remotely)](https://robotics.stackexchange.com/questions/113144/how-to-visualize-images-and-pointcloud-remotely)
[8] [[https://github.com](https://github.com/yoshito-n-students/ffmpeg_pipeline)](https://github.com/yoshito-n-students/ffmpeg_pipeline)
[9] [[https://clearpathrobotics.com](https://clearpathrobotics.com/blog/2025/04/optimizing-video-streaming-in-ros-2/)](https://clearpathrobotics.com/blog/2025/04/optimizing-video-streaming-in-ros-2/)
[10] [[https://arxiv.org](https://arxiv.org/pdf/2205.09778)](https://arxiv.org/pdf/2205.09778)
[11] [[https://aws.amazon.com](https://aws.amazon.com/blogs/industries/building-an-end-to-end-physical-ai-data-pipeline-for-autonomous-vehicle-3-0-on-aws-with-nvidia/)](https://aws.amazon.com/blogs/industries/building-an-end-to-end-physical-ai-data-pipeline-for-autonomous-vehicle-3-0-on-aws-with-nvidia/)
[12] [[https://vimeo.com](https://vimeo.com/1136204802)](https://vimeo.com/1136204802)


-------------------------------------------------------------------



To handle a large variety of streaming protocols (e.g., WebRTC, RTMP, SRT, RTSP, HLS/DASH) in a single architecture, industrial robotics fleets and enterprise media companies rely on a Unified Media Proxy Gateway Engine. [1, 2, 3, 4] 
Rather than overloading the edge robot with multiple protocol stacks, the optimal approach decouples the pipeline: the robot uses one stable native edge protocol (like SRT for high packet-loss resilience over cellular networks, or WebRTC for sub-second teleoperation), while an Open-Source Streaming Media Server (SRS, Wowza, or GStreamer Daemon) handles multiprotocol transformation on the cloud. [1, 2, 5] 
------------------------------
## A) Multiprotocol Architecture Blueprint## 1. EdgeProtocolAdapter (Robot-Side)

* 
* Goal/Purpose: Translates ROS sensor_msgs/msg/Image frames into a single, high-efficiency backbone protocol (typically WebRTC for live teleop or SRT for erratic cellular networks). [1, 5] 
* Methods:
* bindRosTopic(std::string topic) : Attaches to the native video node.
   * setUplinkProtocol(ProtocolType type) : Dynamically switches the robot's export interface (e.g., swapping from WebRTC to SRT depending on network health metrics).
* 

## 2. CloudIngestionMultiplexer (Cloud-Side Gateway Instance)

* 
* Goal/Purpose: Acts as the protocol multi-tool receiver. It hosts concurrent listeners for all inbound video paths. [6] 
* Methods:
* createIngestEndpoint(DeviceID id, ProtocolType protocol) -> URI : Provisions a dynamic streaming socket endpoint (e.g., rtmp://..., srt://..., http://.../whip).
   * routeToTranscoder(StreamID stream_id) : Handshakes incoming frames to the processing engine. [1] 
* 

## 3. DynamicTransmuxEngine (Core Transformation Engine)

* 
* Goal/Purpose: Performs packet-level transmuxing (re-wrapping video payload without decoding, which saves massive CPU overhead) or transcoding (re-encoding to different codecs when necessary). [5] 
* Methods:
* transmux(StreamPacket packet, ProtocolType target_format) -> OutPacket : Converts WebRTC/RTP payloads into standardized HLS blocks or RTMP flows on-the-fly.
   * injectMetadata(StreamID id, RosTelemetry telemetry) : Interleaves synchronized robotic data (IMU, coordinates, laser ranges) inside the video data structure (e.g., SEI NAL metadata or RTMP metadata packets). [1, 4] 
* 

------------------------------
## B) Multiprotocol Data Flow Diagram
Industry solutions (such as the [[Simple Realtime Server (SRS)](https://ossrs.net/lts/en-us/product)](https://ossrs.net/lts/en-us/product) framework or custom [[Wowza Ingestion Gateways](https://www.wowza.com/blog/contribution-and-delivery-protocols-in-video-streaming-workflows)](https://www.wowza.com/blog/contribution-and-delivery-protocols-in-video-streaming-workflows)) use a centralized Shared Media Hub Model: [4, 6] 

 ┌────────────────────── ROBOT FLEET EDGE (Varying Interfaces) ──────────────────────┐
 │                                                                                   │
 │  [Robot A: Legacy] ───► RTMP Ingest (TCP-backed, universal support) ───┐  │
 │                                                                                │  │
 │  [Robot B: Teleop] ───► WebRTC/WHIP Ingest (Ultra-low latency UDP) ───┼──┤
 │                                                                                │  │
 │  [Robot C: Outdor] ───► SRT Ingest (Lossy cellular network fallback) ─┼──┘
 └────────────────────────────────────────────────────────────────────────────────┘
                                         │
                                         ▼ (Different Protocols)
 ┌───────────────────────────── CLOUD INGESTION MATRIX ──────────────────────────────┐
 │                                                                                   │
 │  ┌─────────────────────────────────────────────────────────────────────────────┐  │
 │  │             Cloud Media Gateway (e.g., Open-Source SRS / GStreamer)         │  │
 │  └──────────────────────────────────────┬──────────────────────────────────────┘  │
 │                                         │                                         │
 │                                         ▼                                         │
 │  ┌─────────────────────────────────────────────────────────────────────────────┐  │
 │  │              Dynamic Transmux / Core Shared Memory Kernel                   │  │
 │  └──────┬───────────────────────────────┬───────────────────────────────┬──────┘  │
 │         │                               │                               │         │
 └─────────┼───────────────────────────────┼───────────────────────────────┼─────────┘
           ▼ (Format Transmuxing)          ▼ (Multiplexing)                ▼ (Storage Engine)
 ┌───────────────────┐           ┌───────────────────┐           ┌───────────────────┐
 │ Operator Web UI   │           │ Machine Learning  │           │ Video-on-Demand   │
 │ (WebRTC / WebRTC) │           │ (RTSP Core / RTP) │           │ (HLS/DASH Chunks) │
 └───────────────────┘           └───────────────────┘           └───────────────────┘

------------------------------
## C) Failure Cases & Critical Design Elements## 1. Frame Remuxing Time Drift

* 
* The Failure: When translating an asymmetric incoming stream (like an SRT stream experiencing packet burst dropouts) to a downstream protocol (like HLS or standard RTMP), the cloud platform can lose track of time anchors. This skews telemetry metadata synchronization. [1, 4, 5] 
* Mitigation: The cloud server must use a standardized monotonic clock infrastructure across all entryways. Every packet should have an explicit NTP wall-clock timestamp appended to its metadata wrapper immediately upon hitting the gateway interface.
* 

## 2. Codec-Protocol Mismatches (H.264 vs. H.265 / HEVC)

* 
* The Failure: Legacy RTMP pipelines natively struggle to process or map modern H.265 (HEVC) or AV1 video profiles efficiently. If a modern robot sends H.265 data via an RTMP gateway, it can crash the downstream decoder. [5] 
* Mitigation: Implement a fallback handshake system (WHIP/WHEP endpoints for WebRTC or modern Enhanced RTMP which formally adds H.265 compatibility). If an un-routable codec is encountered, it must programmatically trigger a cloud-side compute container to transcode the video stream into standard H.264 baseline profiles.
* 

## 3. Head-of-Line Blocking Cascades

* 
* The Failure: RTMP uses TCP. If a robot streams over a noisy cellular connection via RTMP, a single lost packet freezes the entire transport queue. If the cloud gateway attempts to re-stream that data out to an automated ML loop via WebRTC, the TCP lag cascades, triggering memory buffer exhaustion (OOM) on the gateway.
* Mitigation: Use an isolated non-blocking ring buffer architecture inside the gateway kernel. If an input protocol lag is caught, the gateway will intentionally drop older frames on the floor rather than allowing the network buffer cascade to bottleneck subsequent real-time consumers. [1, 7] 
* 

------------------------------
To tailor the server framework, are you building a custom WebRTC/SRT application stack using GStreamer/FFmpeg on your own cloud nodes, or looking to orchestrate managed cloud platforms like Wowza, AWS Kinesis, or LiveKit? [1, 3, 4] 

[1] [[https://www.mux.com](https://www.mux.com/articles/rtmp-vs-srt-vs-webrtc-live-streaming-ingest-protocols)](https://www.mux.com/articles/rtmp-vs-srt-vs-webrtc-live-streaming-ingest-protocols)
[2] [[https://aws.amazon.com](https://aws.amazon.com/blogs/machine-learning/build-real-time-voice-streaming-applications-with-amazon-nova-sonic-and-webrtc/)](https://aws.amazon.com/blogs/machine-learning/build-real-time-voice-streaming-applications-with-amazon-nova-sonic-and-webrtc/)
[3] [[https://github.com](https://github.com/aws-samples/cloud-gateway-for-amazon-kinesis-video-streams)](https://github.com/aws-samples/cloud-gateway-for-amazon-kinesis-video-streams)
[4] [[https://www.wowza.com](https://www.wowza.com/blog/contribution-and-delivery-protocols-in-video-streaming-workflows)](https://www.wowza.com/blog/contribution-and-delivery-protocols-in-video-streaming-workflows)
[5] [[https://castr.com](https://castr.com/blog/video-streaming-protocols-everything-you-need-to-know/)](https://castr.com/blog/video-streaming-protocols-everything-you-need-to-know/)
[6] [[https://ossrs.net](https://ossrs.net/lts/en-us/product)](https://ossrs.net/lts/en-us/product)
[7] [[https://docs.vulcanexus.org](https://docs.vulcanexus.org/en/jazzy/rst/tutorials/core/wifi/large_data/large_data.html)](https://docs.vulcanexus.org/en/jazzy/rst/tutorials/core/wifi/large_data/large_data.html)



-------------------------------------------------------------------------------------------



Phase | Selected Open-Source Tool | Primary Responsibility
-- | -- | --
Edge Capture | ros_camera_server | Subscribes to ROS 2 topics and compresses frames using hardware ASICs via GStreamer.
Transport | SRT Protocol (Secure Reliable Transport) | Streams frames out from the robot over unpredictable cellular networks via UDP with error-correction.
Cloud Proxy Hub | SRS (Simple Realtime Server) | Acts as the unified gateway. Ingests SRT data and transmuxes it on-the-fly without heavy re-decoding.
Consumer Endpoints | WHIP/WHEP WebRTC & HLS | Emits ultra-low latency tracks for remote pilots, while piping standard HLS blocks into file storage libraries.


Yes. Multiple mature, production-grade open-source tools can handle the dynamic multiprotocol parsing and ingestion needed for this architecture.
In enterprise cloud robotics, the design splits into Robot-Side Adapters (which bundle the ROS imagery into a standard stream) and Cloud Media Proxies (which process, transmux, and multiplex that stream into WebRTC, SRT, RTMP, or HLS/DASH).
------------------------------
These tools sit directly on the robot's onboard system, hook into the ROS 2 node graph, handle hardware acceleration, and output to an upstream proxy server.

* 
* [[ros_camera_server](https://discourse.openrobotics.org/t/camera-streaming-made-easy-new-release/54562)](https://discourse.openrobotics.org/t/camera-streaming-made-easy-new-release/54562)
* What it does: Explicitly built for ROS 2 to provide low-latency video streaming to operator stations. It automatically builds and optimizes GStreamer pipelines beneath the hood.
   * Protocols Supported: Transmutes sensor_msgs/Image directly into WebRTC, SRT, or RTP.
   * Standout Feature: It can dynamically rewrite the outgoing RTP packet header extension with the original ROS image capture/header timestamp to ensure downstream telemetry alignment. [1] 
* [[web_video_server](https://github.com/RobotWebTools/web_video_server)](https://github.com/RobotWebTools/web_video_server)
* What it does: The standard open-source choice from the RobotWebTools ecosystem. It runs as a standard ROS 2 node, subscribing to native image topics and hosting an HTTP-based server.
   * Protocols Supported: Primarily formats streams into MJPEG, H.264 (via HTTP/WebSocket-FLV), and basic Web-friendly formats.
   * Standout Feature: Best used for rapid prototyping and local web-UI debugging setups rather than massive public cellular transport. [2, 3] 
* [[Foxglove / MCAP Ecosystem](https://github.com/foxglove)](https://github.com/foxglove)
* What it does: If the objective is cloud file uploads (bags/logs) rather than live video streaming, Foxglove’s open-source MCAP file format acts as a powerful data connector.
   * Capabilities: Compresses raw high-definition video channels alongside 200 Hz robotic joint states in structured chunks without bottlenecking disk I/O. [4] 
* 

------------------------------
These servers operate in the cloud as the "Unified Media Proxy Gateway" engine. The robot sends a single stream configuration, and these proxies translate the feed for multiple end-consumers simultaneously.

* 
* [[SRS (Simple Realtime Server)](https://ossrs.net/)](https://ossrs.net/)
* What it does: A highly efficient, widely adopted open-source industrial cluster media server written in C++.
   * Protocols Supported: WebRTC (WHIP/WHEP), SRT, RTMP, RTSP, HLS, and HTTP-FLV.
   * Why it fits: You can configure SRS to receive an SRT stream from a robot navigating an outdoor network, read it via an isolated thread buffer, and deliver it via WebRTC to a web browser operator interface while concurrently saving it to HLS chunks for cloud storage storage. [3] 
* [[ZLMediaKit](https://github.com/ZLMediaKit/ZLMediaKit)](https://github.com/ZLMediaKit/ZLMediaKit)
* What it does: A lightweight, high-performance open-source media streaming framework.
   * Protocols Supported: Natively supports RTSP, RTMP, HLS, HTTP-FLV, WebRTC, and SRT.
   * Why it fits: Exceptional at zero-copy protocol translation. It dynamically generates stream endpoints automatically upon receiving an input feed (e.g., pushing an RTMP stream creates a WebRTC and HLS link instantly).
* [[MediaMTX (formerly rtsp-simple-server)](https://github.com/bluenviron/mediamtx)](https://github.com/bluenviron/mediamtx)
* What it does: A zero-dependency, single-binary routing server written in Go, built specifically as a media proxy.
   * Protocols Supported: RTSP, RTMP, LL-HLS, WebRTC (WHIP), and SRT.
   * Why it fits: Because it compiles down to a single binary with zero external DLL requirements, it is ideal for cloud architectures running inside orchestration containers like Kubernetes or Docker. [5, 6] 
* 

------------------------------

| Phase | Selected Open-Source Tool | Primary Responsibility |
|---|---|---|
| Edge Capture | ros_camera_server | Subscribes to ROS 2 topics and compresses frames using hardware ASICs via GStreamer. |
| Transport | SRT Protocol (Secure Reliable Transport) | Streams frames out from the robot over unpredictable cellular networks via UDP with error-correction. |
| Cloud Proxy Hub | SRS (Simple Realtime Server) | Acts as the unified gateway. Ingests SRT data and transmuxes it on-the-fly without heavy re-decoding. |
| Consumer Endpoints | WHIP/WHEP WebRTC & HLS | Emits ultra-low latency tracks for remote pilots, while piping standard HLS blocks into file storage libraries. |

------------------------------
To proceed with building out the deployment, do you want to write a sample GStreamer launch string for the ros_camera_server layer, or look at how a Docker Compose template configurations map for the SRS Cloud Media Gateway? [1] 

[1] [[https://discourse.openrobotics.org](https://discourse.openrobotics.org/t/camera-streaming-made-easy-new-release/54562)](https://discourse.openrobotics.org/t/camera-streaming-made-easy-new-release/54562)
[2] [[https://github.com](https://github.com/RobotWebTools/web_video_server)](https://github.com/RobotWebTools/web_video_server)
[3] [[https://github.com](https://github.com/EasyDarwin/EasyDarwin)](https://github.com/EasyDarwin/EasyDarwin)
[4] [[https://www.trossenrobotics.com](https://www.trossenrobotics.com/post/robotics-data-pipeline-tools-mcap-vs-lerobot-vs-openpi)](https://www.trossenrobotics.com/post/robotics-data-pipeline-tools-mcap-vs-lerobot-vs-openpi)
[5] [[https://github.com](https://github.com/cool-japan/oximedia)](https://github.com/cool-japan/oximedia)
[6] [[https://github.com](https://github.com/datarhei/core)](https://github.com/datarhei/core)



```



----------------------------------------------------------------

1. Your experience with Jetson nvidia or other framework
Jetson — no hands-on deployment. I haven't worked with JetPack, TensorRT or DeepStream. I've trained and served vision models, but not optimised them for Jetson hardware,… Show more
2. Your experience with Robotics software
Robotics software — ROS 2 (nodes, topics, services, TF, launch), Gazebo, PyBullet, Python and C++. Started working through Nav2 for navigation stack familiarity. Some bas… Show more
3. your experience with robotics SDK
Robotics SDK — no commercial SDK integration history. My integration experience is API and pipeline work at production scale; applying it inside a ROS graph is the part I've done, integrating a specific vendor SDK is the part I haven't. Show less

Vision SDK integrations in ROS 2 tend to fail in two places that look like "instability" but aren't.

The first is QoS. Most vision SDKs publish image and detection topics with the sensor-data profile — BEST_EFFORT, small depth. A subscriber declared RELIABLE never connects to it. No error, no warning, the topic simply appears empty while ros2 topic list shows it right there. It's the single most common reason a working SDK looks broken after integration.

The second is timestamp handling. If detections are stamped with the time they were computed rather than the acquisition time of the source frame, every TF lookup resolves against the wrong pose. At 30 fps with a few hundred milliseconds of inference latency, the arm reaches for where the object was, not where it is — and the error scales with how fast the scene moves, which is why it passes bench testing and fails in operation.

Both are cheap to fix and expensive to diagnose from the outside.

Relevant work:

ROS 2 robotic arm with a FastAPI control interface (GitHub) — arm control exposed over an HTTP layer running against the ROS graph. That bridging problem, external service ↔ ROS nodes, is structurally what SDK integration is.
PyBullet arm with vision-driven sorting — full perception-to-grasp loop: camera frame → colour segmentation → object pose → pick and place. Simulated, but the loop is the loop.
On the perception side specifically: a YOLOv8 pipeline in production — 14 classes, ~900 annotated documents, mAP50 ≈ 0.91, served behind a FastAPI endpoint. Trained and deployed, not a tutorial run.

Background is an engineering degree in automation, cybernetics and robotics (Gdańsk University of Technology), including PLC/SCADA lab work.


