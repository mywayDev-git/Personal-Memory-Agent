"""Pinned, selective runtime artifact inspection/download; never starts models.

Plan-only unless --inspect or --download is explicit. A missing GenAI config is
an artifact compatibility gap, not a claim that ONNX Runtime lacks Qwen3.
"""

import argparse
import hashlib
import json
import shutil
from pathlib import Path

import requests

CANDIDATES = {
    "openvino": {"repo": "OpenVINO/Qwen3-8B-int4-ov", "revision": "5c47abf4b8e12ebe8e99745bb0c1ec17e0c0abcc"},
    "onnx": {"repo": "onnx-community/Qwen3-4B-Instruct-2507-ONNX",
             "revision": "41a4dd4d147229f83043afb98a4d4c803b8bfcbb"},
}
GiB = 1024 ** 3


def inspect(name, session):
    spec = CANDIDATES[name]
    response = session.get(f"https://huggingface.co/api/models/{spec['repo']}/revision/{spec['revision']}",
                           params={"blobs": "true"}, timeout=60)
    response.raise_for_status()
    info = response.json()
    files = []
    for row in info["siblings"]:
        path = row["rfilename"]
        if name == "openvino":
            selected = path.startswith("openvino_") or path in {
                "config.json", "generation_config.json", "tokenizer_config.json", "tokenizer.json",
                "special_tokens_map.json", "chat_template.jinja"}
        else:
            selected = path in {"genai_config.json", "config.json", "generation_config.json",
                               "tokenizer.json", "tokenizer_config.json", "chat_template.jinja",
                               "onnx/model_q4.onnx", "onnx/model_q4.onnx_data", "onnx/model_q4.onnx_data_1"}
        if selected:
            lfs = row.get("lfs", {})
            files.append({"path": path, "bytes": row.get("size", lfs.get("size")),
                          "sha256": lfs.get("sha256")})
    paths = {row["rfilename"] for row in info["siblings"]}
    return {"name": name, "repo": spec["repo"], "revision": info["sha"], "files": files,
            "artifact_bytes": sum(f["bytes"] or 0 for f in files),
            "genai_config_present": "genai_config.json" in paths if name == "onnx" else None,
            "quality_verified": False, "performance_verified": False}


def tree_size(root):
    return sum(p.stat().st_size for p in root.rglob("*") if p.is_file()) if root.exists() else 0


def download(plan, root, session, budget_root):
    # GGUFs and isolated wheels must be under budget_root as well.
    total = tree_size(budget_root)
    target = root / plan["name"]
    needed = sum(f["bytes"] or 0 for f in plan["files"]
                 if not (target / f["path"]).exists())
    if total + needed > 20 * GiB or shutil.disk_usage(root).free - needed < 8 * GiB:
        raise ValueError("RUNTIME_DISK_BUDGET_EXCEEDED")
    for item in plan["files"]:
        path = target / item["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            partial = path.with_name(path.name + ".partial")
            with session.get(f"https://huggingface.co/{plan['repo']}/resolve/{plan['revision']}/{item['path']}",
                             stream=True, timeout=(30, 120)) as response:
                response.raise_for_status()
                with partial.open("wb") as stream:
                    for chunk in response.iter_content(1024 * 1024):
                        if shutil.disk_usage(root).free < 8 * GiB:
                            raise ValueError("RUNTIME_FREE_DISK_FLOOR")
                        stream.write(chunk)
            partial.rename(path)
        with path.open("rb") as stream:
            actual = hashlib.file_digest(stream, "sha256").hexdigest()
        if item["bytes"] is not None and path.stat().st_size != item["bytes"]:
            raise ValueError("RUNTIME_SIZE_MISMATCH")
        if item["sha256"] and item["sha256"] != actual:
            raise ValueError("RUNTIME_HASH_MISMATCH")
        item["sha256"] = actual
        print(json.dumps({"downloaded": item["path"], "bytes": path.stat().st_size}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inspect", action="store_true")
    parser.add_argument("--download", choices=list(CANDIDATES))
    parser.add_argument("--metadata-only", action="store_true")
    parser.add_argument("--root", type=Path, default=Path(".local/first-response"))
    parser.add_argument("--budget-root", type=Path, default=Path(".local/first-response"))
    args = parser.parse_args()
    if not args.inspect and not args.download:
        print(json.dumps({"status": "PLAN_ONLY", "candidates": CANDIDATES,
                          "max_added_gib": 20, "min_free_gib": 8}, indent=2))
        return
    args.root.mkdir(parents=True, exist_ok=True)
    with requests.Session() as session:
        session.trust_env = False
        plans = [inspect(name, session) for name in CANDIDATES]
        if args.download:
            chosen = next(p for p in plans if p["name"] == args.download)
            if args.metadata_only:
                chosen = {**chosen, "files": [f for f in chosen["files"] if (f["bytes"] or 0) < 32 * 1024 * 1024]}
            download(chosen, args.root, session, args.budget_root)
    (args.root / "runtime-artifacts.json").write_text(json.dumps(plans, indent=2), encoding="utf-8")
    print(json.dumps(plans, indent=2))


if __name__ == "__main__":
    main()
