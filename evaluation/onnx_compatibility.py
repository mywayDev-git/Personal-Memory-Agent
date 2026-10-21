"""Configuration-level probe; missing GenAI config prevents CPU/GPU trials."""

import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        print(json.dumps({"status": "PLAN_ONLY", "model": str(args.model)}))
        return
    if args.output.exists():
        parser.error("Previous probe results are immutable; choose another output")
    import onnxruntime_genai as genai
    result = {"version": genai.__version__, "model": str(args.model),
              "genai_config_present": (args.model / "genai_config.json").exists(),
              "inference_measured": False, "cpu_quality_verified": False, "gpu_quality_verified": False}
    try:
        genai.Model(str(args.model))
        result["configuration_loaded"] = True
    except Exception as exc:
        result.update(configuration_loaded=False, error_type=type(exc).__name__,
                      error=str(exc)[:500])
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
