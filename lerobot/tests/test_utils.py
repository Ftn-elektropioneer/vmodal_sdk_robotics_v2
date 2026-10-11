from typing import List, Dict, Tuple, Optional, Any, Union
from dataclasses import dataclass
import os,sys
import fire
from src.utils.util_log import log_info, log_error, log_trace, log_warning
from src.utils.util_base import os_makedirs, os_path_cleanup

import hashlib

from vmodal_robot.utils import os_atomic_copy, os_safe_relative, str_sha256_file, str_stable_id
from tests.utils_datafake import pd_fake_data


dirtest="ztmp/ztests"


def test1():
    data = pd_fake_data("utils_hash")
    path = os.path.join(data["dataset"], "meta", "info.json")
    assert str_sha256_file(path) == hashlib.sha256(open(path, "rb").read()).hexdigest()
    assert str_stable_id("a", "bc") != str_stable_id("ab", "c")
    assert str_stable_id("a", "bc") == str_stable_id("a", "bc")


def test2():
    data = pd_fake_data("utils_copy")
    source = os.path.join(data["dataset"], "meta", "info.json")
    target = os.path.join(data["root"], "copied", "payload")
    size, checksum = os_atomic_copy(source, target, chunk_bytes=3)
    assert size == os.path.getsize(source)
    assert checksum == str_sha256_file(source)
    assert open(source, "rb").read() == open(target, "rb").read()


def test3():
    assert os_safe_relative("videos/chunk-000/a.mp4") == "videos/chunk-000/a.mp4"


def test_all():
    os_makedirs(dirtest)
    test1()
    test2()
    test3()
    log_info("test_utils: all passed")


if __name__ == '__main__':
    import fire
    fire.Fire()
