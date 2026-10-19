"""Build the optional CPython C++ matcher with an explicitly supplied compiler.

Example: python -m evaluation.build_keyword_native --zig PATH/zig.exe
The default output is a local prototype, not an installed application extension.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import sysconfig
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zig", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path(".local/native-keyword"))
    parser.add_argument("--install", action="store_true", help="Copy the tested optional binary into pma")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    suffix = sysconfig.get_config_var("EXT_SUFFIX")
    target = (args.output_dir / ("_keyword_native" + suffix)).resolve()
    library = Path(sys.base_prefix) / "libs" / f"python{sys.version_info.major}{sys.version_info.minor}.lib"
    command = [str(args.zig.resolve()), "c++", "-std=c++17", "-O3", "-shared",
               "-target", "x86_64-windows-gnu", "-I", sysconfig.get_path("include"),
               str(root / "native/keyword_match.cpp"), str(library), "-o", str(target)]
    cache = (root / ".local/cpp-toolchain/cache").resolve()
    temporary = (root / ".local/cpp-toolchain/tmp").resolve()
    cache.mkdir(parents=True, exist_ok=True)
    temporary.mkdir(parents=True, exist_ok=True)
    run = subprocess.run(command, cwd=root, env={**os.environ,
        "ZIG_GLOBAL_CACHE_DIR": str(cache), "ZIG_LOCAL_CACHE_DIR": str(cache / "local"),
        "TEMP": str(temporary), "TMP": str(temporary)})
    if run.returncode:
        raise SystemExit(run.returncode)
    (args.output_dir / "build.json").write_text(json.dumps(dict(
        command=command, python=sys.version, output=str(target)), indent=2), encoding="utf-8")
    print(target)
    if args.install:
        destination = root / "pma" / target.name
        # A running app may hold the previous extension open on Windows.
        # A distinct filename lets the next app process load the new tokenizer.
        destination = destination.with_name("_keyword_native" + suffix)
        if destination.resolve() != target:
            shutil.copy2(target, destination)
        print("Installed optional matcher:", destination)


if __name__ == "__main__":
    main()
