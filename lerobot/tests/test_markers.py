"""Plain-assert durable source-event and rotation checks.

# Usage:
  - python tests/test_markers.py test_all
"""
from typing import List, Dict, Tuple, Optional, Any, Union
from dataclasses import dataclass
import os,sys
import fire
from src.utils.util_log import log_info, log_error, log_trace, log_warning
from src.utils.util_base import os_makedirs, os_path_cleanup

from unittest.mock import patch
from vmodal_robot.markers import Marker, mark, marker_load, marker_rotate, marker_attach
from vmodal_robot.reconciliation.temporal import ClockMap, SourceRecord, TemporalProfile
from vmodal_robot.cli import RobotCli
from vmodal_robot.utils import os_read_bytes, os_marker_append

dirtest = "ztmp/ztests"


def pd_fake_markers(name="markers"):
    root = os.path.join(dirtest, name)
    os_path_cleanup(root)
    os_makedirs(root)
    return os.path.join(root, "active.jsonl")


def test1():
    path = pd_fake_markers()
    first = mark("grasp slipped", ("failure",), path, 100, "camera", "reset-1",
                 episode_index=0, marker_id="event-1")
    mark("grasp slipped", ("failure",), path, 100, "camera", "reset-1",
         episode_index=0, marker_id="event-1")
    assert marker_load(path) == (first,)
    before = os_read_bytes(path)
    target = os.path.join(os.path.dirname(path), "closed.jsonl")
    marker_rotate(path, target)
    assert os_read_bytes(target) == before
    assert not os.path.exists(path)
    mark("new event", path=path, marker_id="event-2")
    assert os_read_bytes(target) == before
    assert marker_load(path)[0].marker_id == "event-2"
    assert marker_load(path)[0].clock == "monotonic"


def test2():
    path = pd_fake_markers("marker_conflict")
    mark("first", path=path, source_ns=1, clock="ros", epoch="e1", marker_id="id")
    mark("changed", path=path, source_ns=1, clock="ros", epoch="e1", marker_id="id")
    try:
        marker_load(path)
    except ValueError as exc:
        assert "conflicting marker identity" in str(exc)
    else:
        assert False, "conflicting replay must fail"
    try:
        mark("missing epoch", path=path, source_ns=1)
    except ValueError as exc:
        assert "clock epoch" in str(exc)
    else:
        assert False, "explicit source time needs an epoch"


def test3():
    path = pd_fake_markers("marker_durability")
    mark("first", path=path)
    before = os_read_bytes(path)
    # A failed durable append propagates and restores the last complete record.
    with patch("vmodal_robot.utils.os.fsync", side_effect=[OSError("disk failure"), None]):
        try:
            mark("second", path=path)
        except OSError as exc:
            assert "disk failure" in str(exc)
        else:
            assert False, "disk failure must reach recorder"
    assert os_read_bytes(path) == before
    try:
        mark("x" * 5000, path=path)
    except ValueError as exc:
        assert "exceeds 4096" in str(exc)
    else:
        assert False, "bounded marker writes are required"
    assert os_read_bytes(path) == before


def test4():
    path = pd_fake_markers("marker_cli")
    value = RobotCli().mark("e-stop", tags="failure,operator", path=path,
                            source_ns=10, clock="ros", epoch="sim-reset-2", episode_index=1)
    assert '"origin": "operator"' in value
    assert marker_load(path)[0].tags == ("failure", "operator")
    target = path + ".closed"
    RobotCli().markers_close(path, target)
    mark("active", path=path)
    try:
        marker_rotate(path, target)
    except ValueError as exc:
        assert "exists" in str(exc)
    else:
        assert False, "closed artifacts cannot be replaced"
    assert marker_load(target)[0].label == "e-stop"


def test5():
    marker = Marker("id", "contact", (), 100, "camera", "e1", episode_index=0)
    clock = ClockMap("map1", "camera", "e1", "ref", "e1", 0, 0, 0, 1000,
                     evidence="synthetic-hardware-anchor")
    frame = SourceRecord("frame1", "r1", "0", "front", "video", "camera", "e1", 98,
                         artifact_id="video1", track="video:0", pts=3, time_base_num=1, time_base_den=30)
    profile = TemporalProfile("synthetic", "1", ("front",), {"front": 5},
                              {"front": "nearest"}, max_age_ns={"front": 5})
    result = marker_attach(marker, "r1", [frame], [clock], profile, "ref", "e1")
    assert result["status"] == "attached"
    assert result["selection"].sources == (frame,)
    assert result["selection"].skew_ns == -2
    assert marker_attach(marker, "r1", [frame], [clock], profile, "ref", "reset-2")["reason"] == "unknown_clock_relation"
    other = Marker("other", "unscoped", (), 100, "camera", "e1")
    assert marker_attach(other, "r1", [frame], [clock], profile, "ref", "e1")["reason"] == "missing_episode"


def test_all():
    test1()
    test2()
    test3()
    test4()
    test5()


if __name__ == "__main__":
    fire.Fire()
