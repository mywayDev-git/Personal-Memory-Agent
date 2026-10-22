"""Read saved synthetic trials only; never starts a model or touches a database."""
import argparse
import html
import json
import statistics
from pathlib import Path


def summarize(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    groups = {}
    for row in data.get("runs", []):
        if row.get("warmup"):
            continue
        groups.setdefault((row["case"], row["variant"]), []).append(row)
    result = []
    for (case, variant), rows in groups.items():
        calls = [[c for c in (r.get("performance") or {}).get("model_http_calls", [])
                  if c.get("operation") == "/v1/chat/completions"] for r in rows]
        phases = sorted({c.get("phase", "unknown") for cs in calls for c in cs})
        def peak(key):
            values = [r[key] for r in rows if r.get(key) is not None]
            return max(values) if values else None
        free = [r["system_available_ram_min_mb"] for r in rows
                if r.get("system_available_ram_min_mb") is not None]
        completed = [r for r in rows if not r.get("error_code") and r.get("status")]
        result.append(dict(case=case, variant=variant, samples=len(rows),
            median_seconds=statistics.median(r["seconds"] for r in rows),
            maximum_seconds=max(r["seconds"] for r in rows),
            quality_passes=sum((r.get("quality") or {}).get("passed") is True for r in rows),
            errors=sum(bool(r.get("error_code")) for r in rows),
            completed_samples=len(completed),
            completed_median_seconds=statistics.median(r["seconds"] for r in completed) if completed else None,
            completed_maximum_seconds=max(r["seconds"] for r in completed) if completed else None,
            qwen_calls_median=statistics.median(len(cs) for cs in calls),
            phase_seconds_median={p: statistics.median(sum(c.get("seconds", 0)
                for c in cs if c.get("phase", "unknown") == p) for cs in calls) for p in phases},
            ram_peak_mib=peak("ram_peak_mb"), private_commit_peak_mib=peak("private_commit_peak_mb"),
            device_vram_peak_mib=peak("gpu_total_peak_mb"),
            available_ram_min_mib=min(free) if free else None))
    return dict(path=str(path.resolve()), status=data.get("status"),
                execution_completed=data.get("execution_completed"), groups=result,
                configuration=data.get("configuration"), hashes=data.get("hashes"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(".local/latency-goal"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("runs", nargs="+")
    args = parser.parse_args()
    summaries = []
    for name in args.runs:
        for placement in ("cpu", "gpu"):
            path = args.root / name / placement / "results.json"
            if path.is_file():
                summaries.append(dict(run=name, placement=placement, **summarize(path)))
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "summary.json").write_text(json.dumps(dict(
        read_only=True, personal_database_used=False, cpu_forced_on_gpu_host=True,
        gpu_absent_environment_verified=False, summaries=summaries),
        ensure_ascii=False, indent=2), encoding="utf-8")
    esc = html.escape
    body = []
    for s in summaries:
        cells = []
        for r in s["groups"]:
            values = [r["case"], r["variant"], r["samples"],
                f'{r["median_seconds"]:.2f}' + (' (실패 포함)' if r['errors'] else ''),
                f'{r["maximum_seconds"]:.2f}' + (' (실패 포함)' if r['errors'] else ''),
                f'{r["quality_passes"]}/{r["samples"]}', r['errors'], r["qwen_calls_median"],
                *(f'{r[k]:.0f}' if r[k] is not None else "—" for k in (
                    "ram_peak_mib", "private_commit_peak_mib", "device_vram_peak_mib", "available_ram_min_mib"))]
            cells.append("<tr>" + "".join(f"<td>{esc(str(v))}</td>" for v in values) + "</tr>")
        artifact = Path(s["path"]).parent / "answers.html"
        link = f'<p><a href="{esc(artifact.as_uri())}">답변·원문·인용 검토표</a></p>' if artifact.is_file() else ""
        for filename, label in (("results.json", "실측 원자료"),
                ("review-quality.json", "정상·변조 답변 검증 자료"),
                ("manual-source-adjudications.json", "답변·인용 직접 대조 판정"),
                ("manual-adjudications.json", "자동 검사와 별도의 품질 판정")):
            attachment = Path(s["path"]).parent / filename
            if attachment.is_file():
                link += f'<p><a href="{esc(attachment.as_uri())}">{label}</a></p>'
        body.append(f'<h2>{esc(s["run"])} / {s["placement"]}</h2><p>실행 완료: {esc(str(s["execution_completed"]))}</p>{link}'
            '<div class="scroll"><table><thead><tr>' + ''.join(f'<th>{x}</th>' for x in (
            '사례','경로','횟수','측정 중앙값 초','측정 최댓값 초','품질','실패','Qwen 호출','RAM MiB','commit MiB','장치 VRAM MiB','여유 RAM MiB')) +
            '</tr></thead><tbody>' + ''.join(cells) + '</tbody></table></div>')
    page = '''<!doctype html><html lang="ko"><meta charset="utf-8"><title>검색·답변 최적화 실측</title>
<style>body{font:16px/1.6 system-ui;max-width:1280px;margin:36px auto;padding:0 24px;color:#182430}h1,h2{line-height:1.3}h2{margin-top:40px}.scroll{overflow:auto}table{border-collapse:collapse;width:100%;white-space:nowrap}td,th{border:1px solid #ccd4dc;padding:8px;text-align:right}td:first-child,th:first-child{text-align:left}th{background:#edf3f7}a{color:#075ca6}</style>
<h1>검색·답변 최적화 실측</h1><p>저장된 합성 자료만 읽는 검토표입니다. 이 페이지를 열거나 새로고침해도 모델이나 평가를 실행하지 않습니다.</p>
<p>준비 실행은 통계에서 제외합니다. CPU는 GPU 탑재 PC에서 강제 실행했으며 실제 GPU 없는 환경은 검증하지 않았습니다. VRAM은 장치 전체 사용량입니다. 시간 초과를 정상 완료 시간이나 개선율로 해석하지 않습니다. 적은 표본의 최댓값은 전체 요청의 P95 보장이 아닙니다.</p>'''
    (args.output / "index.html").write_text(page + ''.join(body) + '</html>', encoding="utf-8")
    print(args.output.resolve() / "index.html")


if __name__ == "__main__":
    main()
