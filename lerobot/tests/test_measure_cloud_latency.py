from typing import List, Dict, Tuple, Optional, Any, Union
from dataclasses import dataclass
import os,sys
import fire
from src.utils.util_log import log_info, log_error, log_trace, log_warning
from src.utils.util_base import os_makedirs, os_path_cleanup

from examples.measure_cloud_latency import account_run, build_report, known_event, measure_sdk, report, validate_live
from examples.search_acceptance import accept_hit
from tests.utils_datafake import pd_fake_latency, pd_fake_search
from vmodal_robot.utils import os_json_load, os_json_save

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

dirtest="ztmp/ztests"


def test1():
    run = pd_fake_latency()
    row = account_run(run)
    assert row["stages_seconds"]["capture_buffering"] == 2
    assert row["stages_seconds"]["admission"] == 2
    assert row["stages_seconds"]["queue_residence"] == 95
    assert row["stages_seconds"]["retry_residence"] == 2
    assert row["stages_seconds"]["upload"] == 2
    assert row["upload_bytes_per_second"] == 500
    assert row["stages_seconds"]["end_to_end"] == 121
    assert row["freshness"]["upper_seconds"] == 121.1


def test2():
    run = pd_fake_latency()
    del run["events"]["index_ready"]
    row = account_run(run)
    assert "index_processing" in row["missing_stages"]
    assert "search_visibility" in row["missing_stages"]
    assert build_report([run], {}, 200, .2)["suitability"] == "UNKNOWN"
    run = pd_fake_latency()
    run["index_ready_verified"] = False
    assert "index_processing" in account_run(run)["missing_stages"]


def test3():
    success = pd_fake_latency()
    failed = pd_fake_latency()
    failed.update(run_id="index-failed", status="failed", failure="indexing failed")
    failed["events"] = {key: value for key, value in failed["events"].items() if value < 115}
    failed["accepted_verified"] = False
    timeout = dict(failed, run_id="outage-timeout", status="timeout")
    result = build_report([success, failed, timeout], {"fixture": "synthetic"}, 200, .2)
    assert result["n"] == 3 and len(result["runs"]) == 3
    assert result["failures"] == 2 and result["timeouts"] == 1
    assert result["failure_rate"] == 2 / 3
    assert result["stages_seconds"]["end_to_end"]["n"] == 1
    assert result["stages_seconds"]["end_to_end"]["missing"] == 2
    assert result["suitability"] == "UNKNOWN"


def test4():
    run = pd_fake_latency()
    row = account_run(run)
    assert row["stages_seconds"]["index_processing"] == 7
    assert row["stages_seconds"]["search_visibility"] == 5
    run["events"]["index_ready"] = 119.0
    assert account_run(run)["stages_seconds"]["search_visibility"] == 1
    run["search_verified"] = False
    assert "search_visibility" in account_run(run)["missing_stages"]


def test5():
    run = pd_fake_latency()
    assert build_report([run], {}, 122, .2)["suitability"] == "OBSERVED_WITHIN_BUDGET"
    assert build_report([run], {}, 121, .2)["suitability"] == "OBSERVED_UNSUITABLE"
    run["clock_uncertainty_seconds"] = .3
    assert build_report([run], {}, 200, .2)["suitability"] == "OBSERVED_UNSUITABLE"
    run["clock_mapping_qualified"] = False
    assert account_run(run)["freshness"] is None
    data = pd_fake_search()
    data["now_wall"] += 100
    assert accept_hit(**data)["status"] == "REJECTED"


def test6():
    run = pd_fake_latency()
    run["durable_ack_verified"] = False
    row = account_run(run)
    assert "upload" in row["missing_stages"]
    assert "revision_publication" in row["missing_stages"]
    assert row["upload_bytes_per_second"] is None
    cfg = dict(expected_hit={"artifact_id": "front-1", "camera": "front"},
               event_time_field="source_seconds", event_interval=[1, 2])
    assert known_event(dict(artifact_id="front-1", camera="front", source_seconds=1.5), cfg)
    assert not known_event(dict(artifact_id="wrist-1", camera="front", source_seconds=1.5), cfg)
    assert not known_event(dict(artifact_id="front-1", camera="front", source_seconds=3), cfg)
    assert not known_event(dict(artifact_id="front-1", camera="front"), cfg)


def test7():
    first, second = pd_fake_latency(), pd_fake_latency()
    second["events"]["capture"] = -100
    second["run_id"] = "synthetic-002"
    result = build_report([first, second], {})
    assert result["stages_seconds"]["end_to_end"]["p50"] == 171
    assert result["stages_seconds"]["end_to_end"]["p99"] == 220
    assert result["suitability"] == "UNKNOWN"
    path = os.path.join(os_makedirs(dirtest), "latency_trace.json")
    output = os.path.join(dirtest, "latency_report.json")
    os_json_save(path, dict(runs=[first, second], metadata={"fixture": "synthetic"}))
    assert report(path, output)["n"] == 2
    assert os_json_load(output)["metadata"]["fixture"] == "synthetic"


def test8():
    async def exercise(failed=False, missing=False):
        run = dict(run_id="sdk-fake", correlation={}, events={}, requests=[], status="pending")
        data = pd_fake_search()
        data["hit"].update(camera="front", source_seconds=1.5)
        cfg = dict(upload={}, index={}, search={}, index_ready_states=["ready"],
                   index_failed_states=["failed"], poll_seconds=.001,
                   expected_hit={"camera": "front"}, event_time_field="source_seconds", event_interval=[1, 2],
                   source_wall_anchor=996.5, event_time_unit_seconds=1,
                   scope=data["scope"], profile=data["profile"], evidence=data["evidence"])
        calls = []
        pending = asyncio.Event()

        async def model(value):
            return SimpleNamespace(model_dump=lambda **kw: value)

        async def search(**kw):
            calls.append("search")
            return await model(dict(data=[] if len(calls) == 1 else [data["hit"]], execution_time_ms=40))

        async def status(**kw):
            pending.set()
            return await model(dict(job_id="job-1", status="failed" if failed else "pending" if missing else "ready"))

        client = SimpleNamespace(collections=SimpleNamespace(video_upload=lambda **kw: model({"ok": True})),
                                 indexes=SimpleNamespace(create_index=lambda **kw: model({"job_id": "job-1"}), index_status=status),
                                 searches=SimpleNamespace(search_video=search))
        with patch("examples.measure_cloud_latency.time.time", return_value=1000):
            if missing:
                task = asyncio.create_task(measure_sdk(client, cfg, run))
                await pending.wait()
                task.cancel()
                cancelled = await asyncio.gather(task, return_exceptions=True)
                assert isinstance(cancelled[0], asyncio.CancelledError)
            else:
                await measure_sdk(client, cfg, run)
        return run, calls

    run, calls = asyncio.run(exercise())
    assert run["status"] == "success" and len(calls) == 2
    assert "first_verified_retrieval" in run["events"]
    assert "durable_ack" not in run["events"]
    assert run["requests"][-1]["response"]["execution_time_ms"] == 40
    run, calls = asyncio.run(exercise(failed=True))
    assert run["status"] == "failed" and calls == []
    run, calls = asyncio.run(exercise(missing=True))
    assert "index_ready" not in run["events"] and calls == []


def test9():
    cfg = dict(disposable=True, upload={"collection_name": "robot-latency-test", "sub_collection_name": "front"},
               index={"group_name": "robot-latency-test", "stream_name": "front"},
               search={"group_name": "robot-latency-test", "stream_name": "front"},
               timeout_seconds=1, poll_seconds=.1, expected_hit={"artifact_id": "fake"},
               event_time_field="timestamp", event_interval=[1, 2], index_ready_states=["ready"],
               index_failed_states=["failed"], readiness_record="fake-ready-record", wire_mapping_record="fake-wire-record",
               source_wall_anchor=1000, capture_source_time=1, event_time_unit_seconds=1,
               scope={}, profile={}, evidence={}, environment={})
    validate_live(cfg)
    run = pd_fake_latency()
    run["requests"] = [dict(operation="search", elapsed_seconds=.04, status="success"),
                       dict(operation="search", elapsed_seconds=.2, status="timeout")]
    result = build_report([run], {})
    assert result["request_seconds"]["search"]["n"] == 1
    assert result["request_seconds"]["search"]["attempts"] == 2
    assert result["request_seconds"]["search"]["failures"] == 1


def test_all():
    test1()
    test2()
    test3()
    test4()
    test5()
    test6()
    test7()
    test8()
    test9()
    log_info("test_measure_cloud_latency: all passed (synthetic timing only)")


if __name__ == '__main__':
    import fire
    fire.Fire()
