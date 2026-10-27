"""Pinned, narrowly scoped resources for the two provider development tasks."""
import hashlib
import json
import stat
from pathlib import Path

REVISION = "5ce88104df2a91e057619eb70fb51f56fc5949eb"
WORLD_ID = "healthverse-pa-v2-provider"
WORLD_SHA256 = "7d77133c451396332bc8df08e957bbf57d0132acd4941c850c89e3a02fd1aa2b"
TASK_FILES = {
    "pa_t013_t013_o002_p01_new_referral_provider": {
        "instruction.md": (1460, "30a214794621e177678c3481aafa15ca87c4ffab6c8c8cf4dec12f87b87f2c05"),
        "tool_reference.md": (3021, "a5b5b78cdf962d21d5b69230ee216aaa56ff18eef4b53f04684e48f583b0e52e"),
        "task.toml": (569, "9c431f757d5048291efb0f10bf4223e1574121ba57846054d2e046c6bc5e4a1c"),
        "fixtures/manifest.json": (375, "b82dba0c7199806d04f68ad4a4d7b755e721668907545d8cce156828d237f804"),
        "fixtures/expectations.json": (8827, "90b6d70b9118ef274a0fbcbf25133ca7e0ef5f24d19cb74c71afb1c57a59bb06"),
    },
    "pa_t019_t019_o001_p01_new_referral_provider": {
        "instruction.md": (1479, "409303f50fed1907dac8909a4b2251d98eb248e91e8bef862786cf1a06181d46"),
        "tool_reference.md": (3021, "a5b5b78cdf962d21d5b69230ee216aaa56ff18eef4b53f04684e48f583b0e52e"),
        "task.toml": (569, "f5ca7f8907d6046d4cc1a95eb7966f1ed1872349e0f31ed4b6ed0f5beb1ded51"),
        "fixtures/manifest.json": (375, "b21bcb4eec27d19081c664a604b106f1b47595c3524f623c8f71cf82a878ac85"),
        "fixtures/expectations.json": (10735, "4632c25526489acb35b6584001852f32b54f1b95d152c547592f44dac1e9e91c"),
    },
}

def identity(task_id):
    files = TASK_FILES[task_id]
    return {"revision": REVISION, "task_id": task_id, "world_id": WORLD_ID, "world_sha256": WORLD_SHA256,
            "files": {name: {"size": size, "sha256": digest} for name, (size, digest) in files.items()}}

def verify(root: Path, task_id: str):
    if task_id not in TASK_FILES:
        raise ValueError("unknown task")
    dataset = root / "data" / "provider-baseline" / REVISION
    task = dataset / "prior_auth_provider" / "tasks" / task_id
    def read(path):
        for parent in (path, *path.parents):
            if parent.is_symlink():
                raise ValueError("symlink")
        if not stat.S_ISREG(path.stat().st_mode):
            raise ValueError("not regular")
        return path.read_bytes()
    manifest = json.loads(read(dataset / "resource-manifest.json"))
    if {p.relative_to(task).as_posix() for p in task.rglob("*") if not p.is_dir()} != set(TASK_FILES[task_id]):
        raise ValueError("unexpected task files")
    if any(p.is_symlink() for p in task.rglob("*")):
        raise ValueError("symlink")
    if (manifest.get("schema") != "chi-provider-baseline-resources-v1"
            or manifest.get("dataset") != "actava/chi-bench" or manifest.get("revision") != REVISION
            or task_id not in manifest.get("tasks", [])):
        raise ValueError("manifest mismatch")
    for name, (size, digest) in TASK_FILES[task_id].items():
        relative = f"prior_auth_provider/tasks/{task_id}/{name}"
        if manifest.get("files", {}).get(relative) != {"size": size, "sha256": digest}:
            raise ValueError("manifest file mismatch")
        raw = read(task / name)
        if len(raw) != size or hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError("resource mismatch")
    metadata = json.loads(read(task / "fixtures/manifest.json"))
    expectations = json.loads(read(task / "fixtures/expectations.json"))
    if (metadata.get("task_id") != task_id or metadata.get("world_id") != WORLD_ID
            or metadata.get("task_actor") != "provider" or metadata.get("payer_mode") != "agent"
            or expectations.get("verifier_contract") != "contract_v5"
            or expectations.get("task_actor", "provider") != "provider"):
        raise ValueError("unsupported metadata")
    return task, identity(task_id)
