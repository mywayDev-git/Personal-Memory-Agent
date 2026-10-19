"""Pinned evaluation-only model downloads. Never modifies the application's models."""

import argparse
import hashlib
import json
import shutil
from pathlib import Path

import requests

MODELS = {
    "generation-q4": {
        "repo": "unsloth/Qwen3-4B-Instruct-2507-GGUF",
        "revision": "a06e946bb6b655725eafa393f4a9745d460374c9",
        "filename": "Qwen3-4B-Instruct-2507-Q4_K_M.gguf",
        "sha256": "3605803b982cb64aead44f6c1b2ae36e3acdb41d8e46c8a94c6533bc4c67e597",
        "bytes": 2497281120,
        "upstream": "Qwen/Qwen3-4B-Instruct-2507",
        "upstream_reference_revision": "cdbee75f17c01a7cc42f958dc650907174af0554",
        "conversion_tool_revision": None,
    },
    "generation-q8": {
        "repo": "unsloth/Qwen3-4B-Instruct-2507-GGUF",
        "revision": "a06e946bb6b655725eafa393f4a9745d460374c9",
        "filename": "Qwen3-4B-Instruct-2507-Q8_0.gguf",
        "sha256": "391c1e410fd9f4cf2de2b510273b56a84c19ce18f4fa3bfb3774031dac4ef068",
        "bytes": 4280405600,
        "upstream": "Qwen/Qwen3-4B-Instruct-2507",
        "upstream_reference_revision": "cdbee75f17c01a7cc42f958dc650907174af0554",
        "conversion_tool_revision": None,
    },
    "embedding-q8": {
        "repo": "Qwen/Qwen3-Embedding-0.6B-GGUF",
        "revision": "370f27d7550e0def9b39c1f16d3fbaa13aa67728",
        "filename": "Qwen3-Embedding-0.6B-Q8_0.gguf",
        "sha256": "06507c7b42688469c4e7298b0a1e16deff06caf291cf0a5b278c308249c3e439",
        "bytes": 639150592,
        "conversion_tool_revision": None,
    },
}


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def download(name, directory):
    spec = MODELS[name]
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / spec["filename"]
    if target.exists():
        if target.stat().st_size != spec["bytes"] or digest(target) != spec["sha256"]:
            raise ValueError("EXISTING_MODEL_HASH_MISMATCH")
        return target
    partial = target.with_suffix(".partial")
    offset = partial.stat().st_size if partial.exists() else 0
    if offset < spec["bytes"]:
        url = f"https://huggingface.co/{spec['repo']}/resolve/{spec['revision']}/{spec['filename']}"
        with requests.Session() as session:
            session.trust_env = False
            with session.get(url, headers={"Range": f"bytes={offset}-"} if offset else {},
                             stream=True, timeout=(30, 120)) as response:
                response.raise_for_status()
                if offset and response.status_code != 206:
                    raise ValueError("MODEL_RESUME_UNSUPPORTED")
                if offset and not response.headers.get("Content-Range", "").startswith(f"bytes {offset}-"):
                    raise ValueError("MODEL_RESUME_RANGE_MISMATCH")
                last = offset // (256 * 1024 * 1024)
                with partial.open("ab" if offset else "wb") as stream:
                    for chunk in response.iter_content(1024 * 1024):
                        stream.write(chunk)
                        offset += len(chunk)
                        current = offset // (256 * 1024 * 1024)
                        if current > last:
                            print(json.dumps({"model": name, "bytes": offset}), flush=True)
                            last = current
    if partial.stat().st_size != spec["bytes"] or digest(partial) != spec["sha256"]:
        raise ValueError("DOWNLOADED_MODEL_HASH_MISMATCH")
    partial.rename(target)
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path(".local/response-latency/models"))
    parser.add_argument("--models", nargs="+", choices=list(MODELS), default=list(MODELS))
    args = parser.parse_args()
    args.directory.mkdir(parents=True, exist_ok=True)
    remaining = sum(max(0, MODELS[name]["bytes"] -
                        ((args.directory / MODELS[name]["filename"]).stat().st_size
                         if (args.directory / MODELS[name]["filename"]).exists() else
                         (args.directory / MODELS[name]["filename"]).with_suffix(".partial").stat().st_size
                         if (args.directory / MODELS[name]["filename"]).with_suffix(".partial").exists() else 0))
                    for name in args.models)
    if shutil.disk_usage(args.directory).free < remaining + 512 * 1024 * 1024:
        parser.error("insufficient disk space: choose --directory on a drive with room for all selected models plus 512 MiB")
    for name in args.models:
        print(json.dumps({"model": name, "path": str(download(name, args.directory)),
                          **MODELS[name]}), flush=True)


if __name__ == "__main__":
    main()
