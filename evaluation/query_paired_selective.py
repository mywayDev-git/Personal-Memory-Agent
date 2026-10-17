"""Generate answers for changed delivered inputs; retain legacy gold-hit selection explicitly."""

import argparse
import hashlib
import shutil
import sqlite3
import time
from dataclasses import replace
from pathlib import Path

from evaluation.kiwi_compare import model_identity
from evaluation.kiwi_runtime import Meter
from evaluation.query_tree import digest
from evaluation.query_tree_run import answer, read, write
from pma.models import LocalModels
from pma.settings import AppSettings


def selection_reasons(entry, method):
    left, right = (entry["arms"][method + flag] for flag in "01")
    reasons = []
    if LocalModels.compact_evidence(left["selected"]) != LocalModels.compact_evidence(
        right["selected"]
    ):
        reasons.append("delivered_model_input")
    baseline = LocalModels.compact_evidence(entry["arms"]["V0"]["selected"])
    if method != "V" and any(
        LocalModels.compact_evidence(a["selected"]) != baseline for a in (left, right)
    ):
        reasons.append("method_vs_V0")
    elif method == "V" and any(
        LocalModels.compact_evidence(a["selected"]) != baseline
        for label, a in entry["arms"].items()
        if label[0] != "V"
    ):
        reasons.append("baseline_for_method_comparison")
    for stage in ("selected", "delivered"):
        if left["metrics"][stage]["hits"] != right["metrics"][stage]["hits"]:
            reasons.append(stage + "_gold_hits")
    return reasons


def changed_pairs(entry, rule="input"):
    return [
        method
        for method in "VMGH"
        if any(
            r.endswith("_gold_hits") or rule == "input" for r in selection_reasons(entry, method)
        )
    ]


def prepare(source, destination):
    if destination.exists():
        raise ValueError("DESTINATION_EXISTS")
    manifest = read(source / "manifest.json")
    assert manifest["suite"] == "paired-v1"
    for path, expected in manifest["files"].items():
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == expected, path
    destination.mkdir(parents=True)
    manifest["answers"] = False
    write(destination / "manifest.json", manifest)
    for name in ("snapshot", "extractions"):
        shutil.copytree(source / name, destination / name)
    (destination / "results").mkdir()
    imported = []
    for path in sorted((source / "results").glob("*.json")):
        if read(path).get("status") == "complete":
            shutil.copy2(path, destination / "results" / path.name)
            imported.append(
                dict(source=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            )
    with (
        sqlite3.connect(source / "vectors.sqlite") as src,
        sqlite3.connect(destination / "vectors.sqlite") as dst,
    ):
        src.backup(dst)
    for name in ("manual-notes.json", "model-file-hashes.json", "frozen-imports.json"):
        if (source / name).exists():
            shutil.copy2(source / name, destination / name)
    write(
        destination / "resume-imports.json",
        dict(
            source=str(source),
            imported=imported,
            policy="Existing completed answers preserved. Remaining questions run retrieval only. Selection rule is frozen in selective-manifest.json before answer generation.",
            source_code_settings_data_verified=True,
        ),
    )
    print(f"Imported {len(imported)} completed cases.")


def run(out, rule="input"):
    manifest = read(out / "manifest.json")
    for path, expected in manifest["files"].items():
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == expected, path
    identity = dict(
        source_manifest=digest(manifest),
        selective_code=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        selection_rule=rule,
    )
    identity_path = out / "selective-manifest.json"
    if identity_path.exists() and read(identity_path) != identity:
        raise ValueError("SELECTIVE_CODE_CHANGED")
    write(identity_path, identity)
    settings = AppSettings.from_env()
    settings = replace(
        settings,
        answer_validation=False,
        embedding_revision=manifest["settings"]["embedding"].split(":")[1],
        llm=replace(settings.llm, **manifest["settings"]["llm"]),
    )
    assert model_identity(settings) == manifest["models"]
    models = LocalModels(settings)
    index = []
    for path in sorted((out / "results").glob("*.json")):
        entry = read(path)
        if entry.get("status") != "complete" or entry["excluded"]:
            continue
        methods = changed_pairs(entry, rule)
        changed_order = [
            m
            for m in "VMGH"
            if [n["id"] for n in entry["arms"][m + "0"]["selected"]]
            != [n["id"] for n in entry["arms"][m + "1"]["selected"]]
        ]
        index.append(
            dict(
                case=entry["case"],
                selected_pairs=methods,
                changed_order_pairs=changed_order,
                reasons={m: selection_reasons(entry, m) for m in methods},
            )
        )
        if not methods:
            continue
        result_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        dest = out / "selective_answers" / path.name
        if dest.exists():
            prior = read(dest)
            if prior["result_sha256"] != result_hash:
                raise ValueError("RESULT_CHANGED")
            if prior.get("status") == "complete":
                continue
        record = dict(case=entry["case"], result_sha256=result_hash, pairs=methods, arms={})
        meter = Meter(models)
        with meter:
            cache = {}
            for method in methods:
                for enabled in ("0", "1"):
                    label = method + enabled
                    arm = entry["arms"][label]
                    key = digest([entry["question"], models.compact_evidence(arm["selected"])])
                    if "response" in arm:
                        value = dict(
                            response=arm["response"],
                            answer_trace=arm["answer_trace"],
                            reused_existing=True,
                            seconds=0,
                        )
                    elif key in cache:
                        value = dict(cache[key], reused_existing=False, reused_within_case=True)
                    else:
                        meter.stage = f"answer-{label}"
                        start = time.perf_counter()
                        response, trace = answer(models, entry["question"], arm["selected"])
                        value = dict(
                            response=response,
                            answer_trace=trace,
                            reused_existing=False,
                            seconds=time.perf_counter() - start,
                        )
                    if not any(t["stage"] == "error" for t in value["answer_trace"]):
                        cache[key] = value
                    record["arms"][label] = value
        record.update(calls=meter.calls, status="complete")
        write(dest, record)
        print(entry["case"], methods, "answers complete", flush=True)
    write(
        out / "answer-selection.json",
        dict(
            rule=rule,
            limitation="Changed-input subset only, not overall answer accuracy. Gold is never passed to answer models. Reused answers are not independent repetitions.",
            cases=index,
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--import-from", type=Path)
    parser.add_argument("--rule", choices=["input", "gold"], default="input")
    args = parser.parse_args()
    if args.import_from:
        prepare(args.import_from, args.run_dir)
    else:
        run(args.run_dir, args.rule)
