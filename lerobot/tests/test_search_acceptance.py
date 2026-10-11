from typing import List, Dict, Tuple, Optional, Any, Union
from dataclasses import dataclass
import os,sys
import fire
from src.utils.util_log import log_info, log_error, log_trace, log_warning
from src.utils.util_base import os_makedirs, os_path_cleanup

from examples.search_acceptance import accept_hit
from tests.utils_datafake import pd_fake_search

import json

dirtest="ztmp/ztests"


def test1():
    data = pd_fake_search()
    data["hit"]["score"] = 0.9
    result = accept_hit(**data)
    assert result["status"] == "REJECTED"
    assert result["raw_hit"]["score_ui"] == 1.0
    assert result["calibration_version"] == "synthetic-v1"


def test2():
    data = pd_fake_search()
    data["hit"]["score"] = data["profile"]["max_distance"]
    assert accept_hit(**data)["status"] == "ACCEPTED"
    data["hit"]["score"] += 0.000001
    assert accept_hit(**data)["status"] == "REJECTED"


def test3():
    for value in (float("nan"), float("inf"), -float("inf"), "0.1", True, 10**1000):
        data = pd_fake_search()
        data["hit"]["score"] = value
        assert accept_hit(**data)["status"] == "REJECTED"
    data = pd_fake_search()
    del data["hit"]["score"]
    assert accept_hit(**data)["status"] == "UNKNOWN"


def test4():
    for key in pd_fake_search()["scope"]:
        data = pd_fake_search()
        data["scope"][key] = "different"
        assert accept_hit(**data)["status"] == "REJECTED"
        del data["scope"][key]
        assert accept_hit(**data)["status"] == "UNKNOWN"
    data = pd_fake_search()
    data["scope"]["index_version"] = 0
    data["profile"]["scope"]["index_version"] = 0
    assert accept_hit(**data)["status"] == "ACCEPTED"


def test5():
    data = pd_fake_search()
    data["evidence"].update(capture_wall_time=995.0, clock_uncertainty_seconds=0.0)
    assert accept_hit(**data)["status"] == "ACCEPTED"
    data["evidence"]["clock_uncertainty_seconds"] = 0.1
    assert accept_hit(**data)["status"] == "REJECTED"
    for value in (None, float("nan"), "995"):
        data["evidence"]["capture_wall_time"] = value
        assert accept_hit(**data)["status"] == "UNKNOWN"
    data["evidence"]["capture_wall_time"] = 1001.0
    assert accept_hit(**data)["status"] == "UNKNOWN"


def test6():
    data = pd_fake_search()
    for key in ("wire_record", "clock_mapping_record"):
        missing = dict(data, evidence=dict(data["evidence"]))
        del missing["evidence"][key]
        assert accept_hit(**missing)["status"] == "UNKNOWN"
    data["evidence"]["clock_uncertainty_seconds"] = 0.21
    assert accept_hit(**data)["status"] == "UNKNOWN"
    data = pd_fake_search()
    data["evidence"]["raw_distance_qualified"] = False
    data["hit"]["score"] = 0.0
    assert accept_hit(**data)["status"] == "UNKNOWN"
    data["evidence"]["raw_distance_qualified"] = True
    data["evidence"]["distance_field"] = "score_ui"
    assert accept_hit(**data)["status"] == "UNKNOWN"


def test7():
    data = pd_fake_search()
    data["hit"] = {}
    assert accept_hit(**data)["status"] == "UNKNOWN"
    data = pd_fake_search()
    with open("docs/search_profile.json", encoding="utf-8") as handle:
        data["profile"] = json.load(handle)
    assert accept_hit(**data)["status"] == "UNKNOWN"


def test8():
    for key in ("max_distance", "freshness_seconds", "max_clock_uncertainty_seconds", "false_accept_budget"):
        for value in (None, -1.0, float("nan"), float("inf")):
            data = pd_fake_search()
            data["profile"][key] = value
            assert accept_hit(**data)["status"] == "UNKNOWN"
    for key in ("calibration_version", "calibration_record", "consumer_approved"):
        data = pd_fake_search()
        del data["profile"][key]
        assert accept_hit(**data)["status"] == "UNKNOWN"
    data = pd_fake_search()
    data["profile"]["scope"]["sampling_policy"] = "new-policy"
    assert accept_hit(**data)["status"] == "REJECTED"
    data["profile"]["scope"] = None
    assert accept_hit(**data)["status"] == "UNKNOWN"
    data = pd_fake_search()
    data["profile"]["distance_field"] = ["score"]
    assert accept_hit(**data)["status"] == "UNKNOWN"
    data["profile"]["schema_version"] = True
    assert accept_hit(**data)["status"] == "UNKNOWN"
    for key in ("hit", "scope", "profile", "evidence"):
        for value in (None, [], "invalid"):
            data = pd_fake_search()
            data[key] = value
            assert accept_hit(**data)["status"] == "UNKNOWN"


def test9():
    data = pd_fake_search()
    for raw, expected in ((0.3, "ACCEPTED"), (0.9, "REJECTED")):
        data["hit"]["score"] = raw
        for top_k in (1, 5, 100):
            hits = [data["hit"]] + [{"score": 0.99}] * (top_k - 1)
            data["hit"]["score_ui"] = 1.0 / top_k
            result = accept_hit(**dict(data, hit=hits[0]))
            assert result["status"] == expected
    with open(os.path.join(os_makedirs(dirtest), "synthetic_search_policy.json"), "w", encoding="utf-8") as handle:
        json.dump(result, handle)


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
    log_info("test_search_acceptance: all passed (synthetic policy evidence)")


if __name__ == '__main__':
    import fire
    fire.Fire()
