



https://github.com/TrossenRobotics/trossen_sdk



In the robotics industry, several powerful open-source frameworks allow you to capture video streams from robot sensors (such as RGB cameras, depth sensors, and LiDAR) and save them directly to a local disk.
The standard and most reliable tools for this task vary depending on the chosen data format and stack.
------------------------------
## 1. ROS 2 & rosbag2 (The Industry Standard)
If the robot is built on ROS 2, the built-in [rosbag2](https://github.com/topics/rosbag2) framework is the standard choice. It natively subscribes to your robot's camera topics (e.g., sensor_msgs/msg/Image or sensor_msgs/msg/CompressedImage) and writes them directly to local disk. [1] 

* 
* Default Container Format: ROS 2 defaults to the MCAP (.mcap) container file format, developed by Foxglove.
* Why it's great: MCAP is highly optimized for append-only, high-volume files. It embeds the video timestamps, camera sensor schemas, and frame data together natively into a single file.
* How to use it: You simply execute a terminal command on the robot:

ros2 bag record /camera/image_raw /camera/camera_info

[2, 3, 4] 
* 

## 2. Foxglove MCAP SDK (Best for Non-ROS Stacks)
If you are building an autonomous system without using ROS (e.g., a pure Python, C++, or Rust application), you can use the open-source [Foxglove MCAP SDK](https://mcap.dev/). [4, 5, 6] 

* 
* Why it's great: It allows you to pipe arbitrary raw video streams or hardware-accelerated H.264 / H.265 encoded video (NAL units) directly into a localized .mcap file. This prevents you from wasting massive amounts of local disk space on uncompressed raw images. [7, 8] 
* Ecosystem Support: The resulting files can be opened instantly in open-source visualization tools like [Foxglove Studio](https://foxglove.dev/) or PlotJuggler to playback the video frames synced precisely with the robot's other sensor logs. [3, 9, 10, 11] 
* 

## 3. Hugging Face LeRobot (Best for AI & Embodied Robotics)
If your primary goal is collecting video data to train Embodied AI models or imitation learning policies, the open-source [LeRobot](https://github.com/huggingface/lerobot) framework by Hugging Face is the modern standard. [12] 

* 
* Why it's great: LeRobot is explicitly designed to handle multimodal robot data collection. It records low-dimensional telemetry data (like joint states or motor commands) alongside video streams. [12, 13, 14] 
* Storage Layout: It streams video inputs natively into locally saved .mp4 video files combined with efficient metadata structuring, making it instantly ready to feed into PyTorch datasets. [12, 14] 
* 

## 4. OpenCV + GStreamer (Best for Raw, Lightweight Scripts)
If you don't need a massive robotics ecosystem and just want to pull frames directly from a USB/MIPI camera sensor and save them to a file:

* 
* Why it's great: Combining the [OpenCV](https://opencv.org/) library with a GStreamer backend provides full, low-level control over the local disk write process.
* Implementation: You can initialize a cv2.VideoWriter utilizing hardware acceleration (like NVIDIA nvv4l2h264enc on an NVIDIA Jetson, or x264 on normal Linux) to encode video directly to a local .mp4 file with minimal CPU overhead.
* 

------------------------------
## Which should you choose?

| If your primary focus is... | Recommended Framework |
|---|---|
| Core ROS 2 infrastructure & simulation testing | rosbag2 (using MCAP format) |
| Custom C++/Python stack requiring optimized serialization | Foxglove MCAP SDK |
| Machine learning dataset curation & AI training pipelines | LeRobot |
| Quick, minimal hardware-specific video recording scripts | OpenCV + GStreamer |

------------------------------
What type of camera sensor are you sourcing data from (e.g., a standard USB webcam, a RealSense depth camera, or a MIPI CSI sensor), and how do you intend to use the saved video files afterwards?

[1] [https://github.com](https://github.com/topics/rosbag2)
[2] [https://foxglove.dev](https://foxglove.dev/blog/introducing-the-mcap-file-format)
[3] [https://medium.com](https://medium.com/foxglove/mcap-as-the-ros-2-default-bag-format-4cb0a5fe400f)
[4] [https://foxglove.dev](https://foxglove.dev/product/mcap)
[5] [https://segments.ai](https://segments.ai/blog/software-tools-for-robotics-landscape/)
[6] [https://foxglove.dev](https://foxglove.dev/blog/mcap-and-the-foxglove-sdk-record-once-read-forever)
[7] [https://foxglove.dev](https://foxglove.dev/blog/best-practices-for-recording-and-uploading-robotics-data)
[8] [https://robotics.stackexchange.com](https://robotics.stackexchange.com/questions/24188/render-h-264-video-of-robot)
[9] [https://www.trossenrobotics.com](https://www.trossenrobotics.com/post/robotics-dataset-formats-comparison)
[10] [https://dev.to](https://dev.to/reductstore/comparing-data-management-tools-for-robotics-5a61)
[11] [https://foxglove.dev](https://foxglove.dev/blog/announcing-the-mcap-storage-plugin-for-ros2)
[12] [https://github.com](https://github.com/huggingface/lerobot)
[13] [https://www.trossenrobotics.com](https://www.trossenrobotics.com/post/trossen-sdk-open-source-robotics-data-collection)
[14] [https://note.com](https://note.com/npaka/n/n76801a83a5ca?hl=en)





--------------------------------------------------------------------------------


Yes, you can absolutely normalize all of those feeds into the LeRobot output format.
In fact, normalizing multi-modal data (video + telemetry) into a standard, ML-ready disk structure is one of LeRobot's core design philosophies. The framework uses the Hugging Face LerobotDataset format, which stores video feeds as standard MP4 files (encoded via H.264/FFmpeg) alongside coordinated timeseries data stored in Apache Parquet files (with associated JSON metadata).
Here is how you can normalize your diverse feeds into the LeRobot format depending on where the data is originating.
------------------------------
## Method 1: Using LeRobot’s Native Recording Pipeline (Easiest)
If you are streaming camera frames and robot states live, LeRobot provides a built-in telemetry and camera polling loop (lerobot.common.datasets.record).
You define your cameras and robot telemetry in a configuration file, and LeRobot handles the synchronization, compression, and file-writing behind the scenes.

* Video Handling: It grabs raw frames from your camera inputs (via OpenCV/PyAV) and feeds them into an episodic encoder loop.
* Disk Output: It automatically writes the standard episodic .mp4 chunks and .parquet tables to your disk under ~/.cache/huggingface/lerobot/.

## Method 2: Normalizing Existing ROS 2 Bags (rosbag2 ➔ LeRobot)
If you already have bags (like .mcap or .db3 files) from your robot, you can write a short offline Python script to parse the topics and build a LerobotDataset.

import torchimport numpy as npfrom lerobot.common.datasets.lerobot_dataset import LerobotDataset
# 1. Initialize a blank LeRobot dataset layout on local diskfeatures = {
    "observation.image": {
        "dtype": "video",
        "shape": (3, 480, 640),  # Channels, Height, Width
        "names": ["color"],
    },
    "observation.state": {
        "dtype": "float32",
        "shape": (6,),  # e.g., 6-DoF joint positions
    },
    "action": {
        "dtype": "float32",
        "shape": (6,),  # e.g., joint commands
    },
}
dataset = LerobotDataset.create(
    repo_id="your_local_path_or_hf_id",
    fps=30,
    features=features,
    use_videos=True,  # This forces LeRobot to encode images into MP4 on disk
    local_dir="./my_normalized_dataset"
)
# 2. Loop through your ROS2 Bag / Custom data stream# (Pseudocode: replace with your actual ROS bag reader loop)for frame_idx, ros_msg in enumerate(bag_reader.read_messages()):
    
    # Convert ROS image to a standard PyTorch Tensor or NumPy array (C, H, W)
    img_tensor = convert_ros_msg_to_tensor(ros_msg.image) 
    state_array = np.array(ros_msg.joint_states)
    action_array = np.array(ros_msg.actions)

    # Append to the current frame sequence
    dataset.add_frame({
        "observation.image": img_tensor,
        "observation.state": torch.from_numpy(state_array),
        "action": torch.from_numpy(action_array),
    })
# 3. Finalize the episode, writing MP4 and metadata directly to local disk
dataset.save_episode()

## Method 3: Converting Custom OpenCV / GStreamer Captures
If you are bypassing ROS and capturing using raw OpenCV/GStreamer, you can feed those frames frame-by-frame directly into the dataset.add_frame() function illustrated above. Because use_videos=True is enabled, LeRobot's underlying engine captures those raw matrices and handles the FFmpeg pipe internally to output a highly compressed .mp4.
------------------------------
## What the Normalized Disk Structure Looks Like
Once you pass any data stream through the LerobotDataset class, your local directory will look exactly like this:

my_normalized_dataset/
├── meta/
│   ├── info.json                 # Dataset details (FPS, licensing, total frames)
│   └── episodes.json             # Map of start/end frames per episode
├── data/
│   ├── chunk_000/
│   │   ├── observation.image.mp4  # Your robot's video feed, encoded in H.264
│   │   └── episode_000000.parquet # Telemetry (joint angles, timestamp maps)

## Why doing this is highly recommended

   1. Massive Storage Savings: ROS bags store images as uncompressed strings, ballooning file sizes. LeRobot encodes them into H.264 MP4s, saving up to 90%+ disk space.
   2. Instant Training Readiness: The moment data lands on disk in this format, you can immediately pass it to a LeRobot training script (e.g., ACT, Diffusion Policy) without modifying a single line of data-loading code.

------------------------------
Do you already have a set of data logs (like .mcap files) that you need to convert right now, or are you setting up a brand-new data collection loop from scratch?



