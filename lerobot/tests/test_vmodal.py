from typing import List, Dict, Tuple, Optional, Any, Union
from dataclasses import dataclass, asdict, replace
import os,sys
import fire
from src.utils.util_log import log_info, log_error, log_trace, log_warning
from src.utils.util_base import os_makedirs, os_path_cleanup

import asyncio
import json
import select
import signal
import subprocess
from unittest.mock import patch

from vmodal_robot.adapters.lerobot import LeRobotAdapter
from vmodal_robot.contracts import Receipt, TransportBlocked, TransportCapabilities, TransportRetry, TransportUnknown
from vmodal_robot.runner import Runner
from vmodal_robot.spool import Spool, SpoolConfig
from vmodal_robot.transports.vmodal import VmodalTransport, str_destination_parts, _receipt, _failure
from tests.utils_datafake import pd_fake_data, os_save_bytes, str_sha


dirtest="ztmp/ztests"


class FakeCollections:
    def __init__(self):
        self.calls = []

    async def video_upload(self, **values):
        self.calls.append(values)
        return {"dest_path": "remote/video.mp4", "status": "ACKNOWLEDGED"}


class FakeClient:
    def __init__(self):
        self.collections = FakeCollections()


class FakeArtifactApi:
    capabilities = TransportCapabilities(
        artifact_kinds=("video", "telemetry", "metadata", "opaque"),
        durable_receipts=True, checksum_verified=True,
        artifact_idempotency=True, artifact_reconciliation=True,
        revision_publication=True, revision_idempotency=True, revision_reconciliation=True,
    )

    def __init__(self):
        self.payloads = {}
        self.descriptors = {}
        self.receipts = {}
        self.revisions = {}
        self.creation_effects = 0
        self.finalization_effects = 0
        self.index_effects = 0
        self.revision_effects = 0
        self.lost_artifacts = set()
        self.lost_revisions = set()

    async def deliver_artifact(self, artifact, destination):
        key = (destination, artifact.artifact_id)
        if key not in self.receipts:
            with open(artifact.local_ref, "rb") as handle:
                payload = handle.read()
            checksum = str_sha(payload)
            assert checksum == artifact.checksum
            self.payloads[key] = payload
            self.descriptors[key] = asdict(artifact)
            self.creation_effects += 1
            self.finalization_effects += 1
            self.index_effects += int(artifact.kind == "video")
            self.receipts[key] = Receipt(artifact.artifact_id, f"artifact://{destination}/{artifact.artifact_id}", "ACKNOWLEDGED", checksum, checksum_verified=True)
        if self.receipts[key].checksum != artifact.checksum:
            raise TransportBlocked("artifact identity checksum conflict")
        if key in self.lost_artifacts:
            self.lost_artifacts.remove(key)
            raise ConnectionError("artifact stored but response lost")
        return self.receipts[key]

    async def reconcile_artifact(self, artifact, destination):
        return self.receipts.get((destination, artifact.artifact_id))

    async def publish_revision(self, revision):
        key = (revision.destination, revision.revision_id)
        for artifact_id in revision.artifact_ids:
            assert (revision.destination, artifact_id) in self.descriptors
        if key not in self.revisions:
            self.revision_effects += 1
            self.revisions[key] = Receipt(revision.revision_id, f"revision://{revision.revision_id}", "ACKNOWLEDGED")
        if key in self.lost_revisions:
            self.lost_revisions.remove(key)
            raise ConnectionError("revision stored but response lost")
        return self.revisions[key]

    async def reconcile_revision(self, revision):
        return self.revisions.get((revision.destination, revision.revision_id))


class DiskArtifactApi(FakeArtifactApi):
    """A process-independent fake receiver for crash and side-effect assertions."""

    def __init__(self, root, pause=False):
        super().__init__()
        self.root, self.pause = root, pause
        os_makedirs(root)

    async def reconcile_artifact(self, artifact, destination):
        path = os.path.join(self.root, artifact.artifact_id + ".json")
        if not os.path.isfile(path):
            return None
        with open(path, encoding="utf-8") as handle:
            value = json.load(handle)
        assert value["destination"] == destination
        return _receipt(value["receipt"], artifact.artifact_id, artifact.checksum)

    async def deliver_artifact(self, artifact, destination):
        receipt = await self.reconcile_artifact(artifact, destination)
        if receipt is None:
            receipt = await super().deliver_artifact(artifact, destination)
            counts_path = os.path.join(self.root, "effects.json")
            counts = {"creation": 0, "finalization": 0, "index": 0}
            if os.path.isfile(counts_path):
                with open(counts_path, encoding="utf-8") as handle:
                    counts = json.load(handle)
            for name in counts:
                counts[name] += 1
            with open(counts_path, "w", encoding="utf-8") as handle:
                json.dump(counts, handle)
                handle.flush()
                os.fsync(handle.fileno())
            os_save_bytes(os.path.join(self.root, artifact.artifact_id + ".mp4"), self.payloads[(destination, artifact.artifact_id)])
            path = os.path.join(self.root, artifact.artifact_id + ".json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump({"destination": destination, "receipt": asdict(receipt),
                           "creation_effects": 1, "finalization_effects": 1, "index_effects": 1}, handle)
                handle.flush()
                os.fsync(handle.fileno())
        if self.pause:
            print("READY:" + artifact.artifact_id, flush=True)
            await asyncio.Event().wait()
        return receipt


def crash_child(spool_root: str, remote_root: str):
    spool = Spool(SpoolConfig(spool_root, max_bytes=100000, aux_reserve_bytes=1000))
    runner = Runner(LeRobotAdapter("."), spool, VmodalTransport(FakeClient(), DiskArtifactApi(remote_root, True)))
    asyncio.run(runner.run_once("video"))


def _sigkill_check():
    if os.name != "posix":
        return
    data = pd_fake_data("vmodal_sigkill")
    cfg = SpoolConfig(os.path.join(data["root"], "spool"), max_bytes=100000, aux_reserve_bytes=1000)
    remote = os.path.join(data["root"], "remote")
    spool = Spool(cfg)
    revision = spool.accept(LeRobotAdapter(data["ready"]).discover()[0])
    spool.close()
    proc = subprocess.Popen([sys.executable, __file__, "crash_child", "--spool_root=" + cfg.root,
                             "--remote_root=" + remote], stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True)
    try:
        assert select.select([proc.stdout], [], [], 5)[0]
        line = proc.stdout.readline().strip()
        assert line.startswith("READY:"), line
        artifact_id = line.split(":", 1)[1]
        proc.send_signal(signal.SIGKILL)
        proc.communicate(timeout=3)
        assert proc.returncode == -signal.SIGKILL
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
    spool = Spool(cfg)
    artifact = spool.get_artifact(artifact_id)
    assert spool.artifact_state(artifact_id) == "SENDING"
    api = DiskArtifactApi(remote)
    runner = Runner(LeRobotAdapter("."), spool, VmodalTransport(FakeClient(), api))
    asyncio.run(runner.recover())
    assert spool.artifact_state(artifact_id) == "ACKNOWLEDGED"
    asyncio.run(api.deliver_artifact(artifact, revision.destination))
    with open(os.path.join(remote, artifact_id + ".json"), encoding="utf-8") as handle:
        effects = json.load(handle)
    assert effects["creation_effects"] == effects["finalization_effects"] == effects["index_effects"] == 1
    assert api.creation_effects == api.finalization_effects == api.index_effects == 0
    with open(os.path.join(remote, "effects.json"), encoding="utf-8") as handle:
        assert json.load(handle) == {"creation": 1, "finalization": 1, "index": 1}
    with open(os.path.join(remote, artifact_id + ".mp4"), "rb") as handle:
        assert str_sha(handle.read()) == artifact.checksum
    spool.close()


def test1():
    """Real SDK serialization and remote readback; the readback endpoint is test-only."""
    repo = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../.."))
    sdk = os.path.join(repo, "uinterface", "sdk_python")
    sys.path.insert(0, os.path.join(sdk, "src"))
    sys.path.append(repo)
    from vmodal import Client
    from vmodal.errors import ValidationFailed
    from vmodal.resources.collections import MAX_VIDEO_UPLOAD_BYTES
    from uinterface.sdk_python.tests.utils_sdk import MockResponse, mock_server

    data = pd_fake_data("vmodal_wire")
    spool = Spool(SpoolConfig(os.path.join(data["root"], "spool"), max_bytes=100000, aux_reserve_bytes=1000))
    revision = spool.accept(LeRobotAdapter(data["ready"]).discover()[0])
    videos = [spool.get_artifact(value) for value in revision.artifact_ids if spool.get_artifact(value).kind == "video"]

    async def wire():
        with mock_server([]) as state:
            client = Client(base_url=state.base_url, user_id="test-robot")

            class WireApi(FakeArtifactApi):
                async def deliver_artifact(self, artifact, destination):
                    collection, stream = str_destination_parts(destination)
                    result = await client.collections.video_upload(
                        filepath_local=artifact.local_ref, collection_name=collection,
                        sub_collection_name=stream, reduce_size=False, max_concurrency=1,
                        video_filename=artifact.artifact_id + ".mp4",
                    )
                    stored = await client.http.request("GET", "/test-storage/" + artifact.artifact_id)
                    checksum = str_sha(bytes.fromhex(stored["payload_hex"]))
                    return Receipt(artifact.artifact_id, result.dest_path, "ACKNOWLEDGED", checksum, checksum_verified=True)

            transport = VmodalTransport(client, artifact_api=WireApi())
            try:
                for artifact in videos:
                    with open(artifact.local_ref, "rb") as handle:
                        payload = handle.read()
                    name = artifact.artifact_id + ".mp4"
                    state.responses.extend([
                        MockResponse(body={"user_id": "test-robot", "expires_in": 12600, "key": "uploads/" + name, "url": state.base_url + "/signed-put", "method": "PUT"}),
                        MockResponse(status=204, body=b""),
                        MockResponse(body={"status": "ok", "key": "uploads/" + name, "dest_path": "/remote/" + name, "file_size": len(payload)}),
                        MockResponse(body={"payload_hex": payload.hex()}),
                    ])
                    assert MAX_VIDEO_UPLOAD_BYTES == 100 * 1024 * 1024
                    with patch("vmodal.resources.collections.MAX_VIDEO_UPLOAD_BYTES", len(payload)):
                        receipt = await transport.deliver(artifact, revision.destination)
                    assert receipt.artifact_id == artifact.artifact_id
                    assert receipt.checksum_verified is True
                    assert receipt.checksum == str_sha(payload)
                    requests = state.requests[-4:]
                    assert "filename=" + name in requests[0].path
                    assert requests[1].body == payload
                    assert "filename=" + name in requests[2].path
                    assert "video_filename=" + name in requests[2].path
                    assert "start_datetime_user" not in requests[2].path
                    assert requests[3].method == "GET"
                assert videos[0].artifact_id != videos[1].artifact_id
                assert len(state.requests) == 8
                for multipart in (False, True):
                    with patch("vmodal.resources.collections.MAX_VIDEO_UPLOAD_BYTES", videos[0].byte_length - 1):
                        try:
                            await client.collections.video_upload(
                                filepath_local=videos[0].local_ref, collection_name="robot-data",
                                sub_collection_name="robot-01", multipart=multipart,
                            )
                        except ValidationFailed as exc:
                            assert "video file too large" in str(exc)
                        else:
                            assert False, "multipart must not bypass the SDK preflight cap"
                assert len(state.requests) == 8
            finally:
                await transport.close()

    asyncio.run(wire())
    spool.close()


def test2():
    client = FakeClient()
    transport = VmodalTransport(client)
    for call in (transport.validate_capabilities, VmodalTransport.from_env):
        try:
            call()
        except TransportBlocked as exc:
            for capability in ("storage:telemetry", "storage:metadata", "storage:opaque", "durable_receipts", "checksum_verified", "artifact_idempotency", "revision_publication", "revision_idempotency"):
                assert capability in str(exc)
        else:
            assert False, "unqualified transport must fail"
    assert client.collections.calls == []


def test3():
    data = pd_fake_data("vmodal_generic")
    spool = Spool(SpoolConfig(os.path.join(data["root"], "spool"), max_bytes=100000, aux_reserve_bytes=1000))
    item = LeRobotAdapter(data["ready"]).discover()[0]
    path = os.path.join(data["dataset"], "blobs", "native.bin")
    os_save_bytes(path, b"opaque-native-bytes")
    opaque = replace(item.artifacts[0], rel_path="blobs/native.bin", kind="opaque", content_type="application/octet-stream", source_path=path, checksum=str_sha(b"opaque-native-bytes"), byte_length=len(b"opaque-native-bytes"))
    revision = spool.accept(replace(item, artifacts=item.artifacts + (opaque,)))
    api = FakeArtifactApi()
    transport = VmodalTransport(FakeClient(), artifact_api=api)
    assert transport.validate_capabilities()["qualified"] is True
    runner = Runner(LeRobotAdapter(os.path.join(data["root"], "none")), spool, transport)

    async def drain():
        while await runner.cycle(admit=False):
            pass

    asyncio.run(drain())
    assert spool.pending_count() == 0
    assert spool.blocked_count() == 0
    assert spool.revision_state(revision.revision_id) == "ACKNOWLEDGED"
    for artifact_id in revision.artifact_ids:
        artifact = spool.get_artifact(artifact_id)
        with open(os.path.join(data["dataset"], artifact.rel_path), "rb") as handle:
            assert api.payloads[(revision.destination, artifact_id)] == handle.read()
    assert api.creation_effects == len(revision.artifact_ids)
    assert api.revision_effects == 1
    assert {value["kind"] for value in api.descriptors.values()} == {"video", "telemetry", "metadata", "opaque"}
    spool.close()


def test4():
    assert str_destination_parts("collection/stream") == ("collection", "stream")
    api = FakeArtifactApi()
    transport = VmodalTransport(FakeClient(), artifact_api=api)
    transport.validate_capabilities(api.capabilities.max_video_bytes)
    for size in (0, -1, True, api.capabilities.max_video_bytes + 1):
        try:
            transport.validate_capabilities(size)
        except TransportBlocked:
            pass
        else:
            assert False, "invalid/incompatible size must fail"


def test5():
    good = {"artifact_id": "aid", "remote_ref": "artifact://aid", "status": "ACKNOWLEDGED", "checksum": "abc", "checksum_verified": True}
    assert _receipt(good, "aid", "abc").checksum_verified is True
    bad = ["artifact://aid", {"key": "staging/aid"}]
    for key, value in (("artifact_id", "wrong"), ("remote_ref", ""), ("status", "ACCEPTED"), ("checksum", "wrong"), ("checksum_verified", False), ("checksum_verified", "true")):
        bad.append({**good, key: value})
    for key in good:
        bad.append({name: value for name, value in good.items() if name != key})
    for value in bad:
        try:
            _receipt(value, "aid", "abc")
        except TransportBlocked:
            pass
        else:
            assert False, "invalid receipt must not acknowledge an artifact"


def test6():
    data = pd_fake_data("vmodal_reconcile")
    spool = Spool(SpoolConfig(os.path.join(data["root"], "spool"), max_bytes=100000, aux_reserve_bytes=1000))
    revision = spool.accept(LeRobotAdapter(data["ready"]).discover()[0])
    artifact = spool.get_artifact(revision.artifact_ids[0])
    transport = VmodalTransport(FakeClient(), artifact_api=FakeArtifactApi())

    async def checks():
        assert await transport.reconcile(artifact, revision.destination) is None
        stock = VmodalTransport(FakeClient())
        for lookup in (stock.reconcile(artifact, revision.destination), stock.reconcile_revision(revision)):
            try:
                await lookup
            except TransportUnknown:
                pass
            else:
                assert False, "unsupported lookup cannot establish absence"

        class OfflineApi(FakeArtifactApi):
            async def reconcile_artifact(self, artifact, destination):
                raise ConnectionError("offline lookup")

        offline = VmodalTransport(FakeClient(), artifact_api=OfflineApi())
        try:
            await offline.reconcile(artifact, revision.destination)
        except TransportUnknown:
            pass
        else:
            assert False, "unavailable lookup must remain uncertain"
        receipt = await transport.deliver(artifact, revision.destination)
        assert await transport.reconcile(artifact, revision.destination) == receipt

    asyncio.run(checks())
    spool.close()


def test7(wire: bool = False):
    for exc in (ValueError("invalid"), PermissionError("denied"), NotImplementedError("unsupported")):
        assert isinstance(_failure(exc), TransportBlocked)
    assert isinstance(_failure(ConnectionError("offline")), TransportRetry)
    assert isinstance(_failure(TimeoutError("timeout")), TransportRetry)
    if wire:
        from vmodal.errors import ApiError, AuthError, FeatureDisabled, ValidationFailed
        for status in (408, 425, 429, 500, 503, 504):
            assert isinstance(_failure(ApiError("unavailable", status_code=status)), TransportRetry)
        for status in (400, 401, 403, 404, 409, 413, 422):
            assert isinstance(_failure(ApiError("invalid", status_code=status)), TransportBlocked)
        for exc in (AuthError("auth"), FeatureDisabled("unsupported"), ValidationFailed("input")):
            assert isinstance(_failure(exc), TransportBlocked)


def test8():
    _sigkill_check()
    data = pd_fake_data("vmodal_lost_ack")
    spool = Spool(SpoolConfig(os.path.join(data["root"], "spool"), max_bytes=100000, aux_reserve_bytes=1000))
    revision = spool.accept(LeRobotAdapter(data["ready"]).discover()[0])
    api = FakeArtifactApi()
    transport = VmodalTransport(FakeClient(), artifact_api=api)

    async def checks():
        for artifact_id in revision.artifact_ids:
            artifact = spool.get_artifact(artifact_id)
            api.lost_artifacts.add((revision.destination, artifact_id))
            try:
                await transport.deliver(artifact, revision.destination)
            except TransportRetry:
                pass
            else:
                assert False, "lost response must be retryable"
            found = await transport.reconcile(artifact, revision.destination)
            assert found == await transport.deliver(artifact, revision.destination)
            assert found == await VmodalTransport(FakeClient(), artifact_api=api).reconcile(artifact, revision.destination)
        count = len(revision.artifact_ids)
        assert api.creation_effects == count
        assert api.finalization_effects == count
        assert api.index_effects == 2
        api.lost_revisions.add((revision.destination, revision.revision_id))
        try:
            await transport.publish_revision(revision)
        except TransportRetry:
            pass
        else:
            assert False, "lost publication must be retryable"
        assert await transport.reconcile_revision(revision) == await transport.publish_revision(revision)
        assert api.revision_effects == 1

    asyncio.run(checks())
    spool.close()


def test9():
    data = pd_fake_data("vmodal_collisions")
    item = LeRobotAdapter(data["ready"]).discover()[0]
    template = next(value for value in item.artifacts if value.kind == "video")
    videos = []
    for camera in ("front", "wrist"):
        for chunk in ("000", "001"):
            rel_path = f"videos/{camera}/chunk-{chunk}/file-000.mp4"
            payload = (camera + chunk).encode()
            path = os.path.join(data["dataset"], rel_path)
            os_save_bytes(path, payload)
            videos.append(replace(template, rel_path=rel_path, source_path=path, checksum=str_sha(payload), byte_length=len(payload), source_refs={"camera_key": camera, "chunk": chunk}))
    item = replace(item, artifacts=tuple(videos + [value for value in item.artifacts if value.kind != "video"]))
    spool = Spool(SpoolConfig(os.path.join(data["root"], "spool"), max_bytes=100000, aux_reserve_bytes=1000))
    revision = spool.accept(item)
    api = FakeArtifactApi()
    transport = VmodalTransport(FakeClient(), artifact_api=api)

    async def checks():
        names = set()
        for artifact_id in revision.artifact_ids:
            artifact = spool.get_artifact(artifact_id)
            await transport.deliver(artifact, revision.destination)
            if artifact.kind == "video":
                names.add(os.path.basename(artifact.local_ref))
                assert os.path.basename(artifact.local_ref) == artifact.artifact_id + ".mp4"
                assert api.descriptors[(revision.destination, artifact_id)]["source_refs"] == artifact.source_refs
        assert len(names) == 4
        old = spool.get_artifact(revision.artifact_ids[0])
        old_bytes = api.payloads[(revision.destination, old.artifact_id)]
        os_save_bytes(videos[0].source_path, b"new-content")
        changed = replace(videos[0], checksum=str_sha(b"new-content"), byte_length=len(b"new-content"))
        new = spool.accept(replace(item, source_revision="revision-002", artifacts=tuple([changed] + list(item.artifacts[1:]))))
        artifact = spool.get_artifact(new.artifact_ids[0])
        assert artifact.artifact_id != old.artifact_id
        await transport.deliver(artifact, new.destination)
        assert api.payloads[(revision.destination, old.artifact_id)] == old_bytes
        assert api.payloads[(new.destination, artifact.artifact_id)] == b"new-content"

    asyncio.run(checks())
    spool.close()


def test_all(wire: bool = False):
    """Run the standalone core; the monorepo test.sh opts into SDK wire coverage."""
    if isinstance(wire, str):
        if wire.lower() not in ("true", "false"):
            raise ValueError("wire must be true or false")
        wire = wire.lower() == "true"
    os_makedirs(dirtest)
    if wire:
        test1()
    test2()
    test3()
    test4()
    test5()
    test6()
    test7(wire=wire)
    test8()
    test9()
    log_info("test_vmodal: all passed")


if __name__ == '__main__':
    import fire
    fire.Fire()
