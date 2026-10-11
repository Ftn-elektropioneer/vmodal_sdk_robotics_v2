"""Small deterministic temporal inventories independent of media libraries.

# Usage:
  from tests.utils_temporal_fake import pd_fake_temporal
  request, sources, clocks, profile = pd_fake_temporal()
"""
from typing import List, Dict, Tuple, Optional, Any, Union
from dataclasses import dataclass
import os,sys
import fire
from src.utils.util_log import log_info, log_error, log_trace, log_warning

from vmodal_robot.reconciliation.temporal import ClockMap, SourceRecord, TemporalRequest, TemporalProfile

dirtest = "ztmp/ztests"


def pd_fake_temporal():
    """Worked 100 ms sample: 98 ms video, bracket, 48 kHz audio, active action."""
    ms = 1_000_000
    # Audio's exact canonical cutoff has zero target uncertainty. The camera
    # example's separate 0.2 ms target bound is tested with a distinct request.
    req = TemporalRequest("sample-3", "revision-a", "0", "session", "epoch-0", 100*ms)
    clocks = [ClockMap("map-0", "device", "epoch-0", "session", "epoch-0", 0, 0, 0, 1_000*ms,evidence="hardware-trigger-fixture")]
    common = dict(revision="revision-a",episode="0",clock="device",epoch="epoch-0",path="data/original.bin",checksum="a"*64)
    sources = [
        SourceRecord("frame-0", modality="camera", kind="video", source_ns=98*ms, uncertainty_ns=800_000, pts=2940,time_base_den=30_000,track="video:0", **common),
        SourceRecord("row-0", modality="state", kind="telemetry",source_ns=98*ms,ordinal=10, **common),
        SourceRecord("row-1", modality="state", kind="telemetry",source_ns=103*ms,ordinal=11, **common),
        SourceRecord("sound-0",modality="sound",kind="audio",source_ns=0,sample_rate=48_000,sample_count=9_600,channels=2,origin_known=True,trim_known=True,decoder="pcm-fixture-v1",track="audio:0", **common),
        SourceRecord("command-0",modality="action",kind="action",source_ns=90*ms,apply_start_ns=91*ms,apply_end_ns=91*ms,effective_end_ns=101*ms,representation="physical-joint-target", **common),
        SourceRecord("command-1",modality="action",kind="action",source_ns=97*ms,apply_start_ns=101*ms,apply_end_ns=101*ms,effective_end_ns=120*ms,representation="physical-joint-target", **common),
    ]
    profile = TemporalProfile("fixture-offline", "1", ("camera","state","sound","action"),
        {"camera":5*ms,"state":ms,"sound":ms,"action":ms},
        {"camera":"nearest","state":"interpolate","sound":"causal","action":"active"},
        max_age_ns={"camera":5*ms,"state":ms},max_gap_ns={"state":10*ms},
        audio_window_ns={"sound":20*ms},interpolation_error_ns={"state":0})
    return req,sources,clocks,profile


class ContractRaises:
    """Assert a specific malformed contract raises; unexpected exceptions escape."""
    def __init__(self, error, text):
        self.error, self.text = error, text

    def __enter__(self):
        return self

    def __exit__(self, cls, error, tb):
        assert cls is not None, "expected contract validation to fail"
        if not issubclass(cls,self.error):
            return False
        assert self.text in str(error)
        return True
