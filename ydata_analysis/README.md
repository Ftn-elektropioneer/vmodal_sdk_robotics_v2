# V-Modal Robot Analysis

## Install with one prompt

Paste this into your coding assistant from your analysis workspace:

```text
Install and configure V-Modal robot analysis tooling in this workspace:

- Python SDK: https://pypi.org/project/vmodal/ (import: vmodal)
- MCP server: https://github.com/v-modal/vmodal_mcp

1. Inspect the existing Python environment, dependencies, secret configuration,
   and AI assistant setup. Reuse project conventions; do not create a new
   virtualenv or Conda environment, or introduce Poetry or Pipenv.
2. Install the SDK in the existing analysis environment:
     pip install "vmodal>=1,<2"
   Record the installed version in the project's dependency file.
3. Install the MCP server using an existing isolated tool environment. Keep it
   separate from the SDK: both provide a `vmodal` command, and the MCP package's
   `src` module can conflict with project code. If no suitable tool environment
   exists, explain what is needed before installing it.
4. Configure VMODAL_API_KEY for the SDK and api_key (or VMODAL_API_KEY) for MCP
   through the existing secret mechanism. Use PUT_API_KEY_HERE in examples;
   never commit credentials. If the key is missing, finish setup and report
   the manual step needed.
5. Register `vmodal-mcp run --transport stdio` with the AI assistant in use.
   Check its current configuration instructions and the installed --help.
   Use the absolute executable path if needed. Set MCP_IMAGE_DIR to an
   absolute, git-ignored output directory for downloaded frames.
6. Verify imports, CLI help, connection, account, and collection listing.
   With a supplied collection, run a text search limited to five results and
   download the matching frames. Do not upload, index, or delete data.
7. Reuse or add a minimal search example that saves raw hits to CSV or Parquet:
   group_name, stream_name, filename, ts_unix_13digits, score, and query text.
   Robot episode/frame resolution and aligned telemetry are planned features;
   do not present raw search hits as resolved robot frames.
8. Keep analysis on workstations, notebooks, or CI, outside robot control,
   safety, and recording paths. Report changed files, installed versions,
   executable paths, verification results, and remaining manual steps.

Verify commands against installed help and package documentation. Report
failures directly; do not hide errors or guess unsupported flags.
```

## What this is for

Search uploaded robot video, download matching frames, and use the results in
scripts, notebooks, or an AI assistant. Use the MCP server for chat and the
Python SDK for repeatable analysis.

Typical flow:

```text
Robot capture → durable upload → V-Modal index → search → download frames
```

Suggested collection names: a project such as `lab_pick_place`, with a robot or
session such as `arm-cell-07` as the sub-collection.

## Try a search

```text
Find a robot gripper dropping an object in collection lab_pick_place.
Show filename, timestamp, and score for the top five hits.
Save the matching frames so I can inspect them.
```

## Status and next steps

The SDK and MCP server support collection listing, search, and frame downloads.
The stock robot upload backend is not yet qualified. Robot-aware hit resolution,
aligned telemetry, and LeRobot dataset export are planned in the
[analysis backlog](todo/00_new_analysis.md).

Short events may be missed by sampling. An empty search result does not prove
that an event never happened; see [search qualification](../lerobot/docs/search_qualification.md).

- [Robot capture and upload](../lerobot/README.md)
- [Analysis backlog](todo/00_new_analysis.md)
- [Robot-flow backlog](../todo/inside_ros/00_new_researcher.md)
- [MCP server](https://github.com/v-modal/vmodal_mcp)
- [Python SDK](https://pypi.org/project/vmodal/)
