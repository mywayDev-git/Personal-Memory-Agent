#!/usr/bin/env bash

set -Eeuo pipefail

# 프로젝트 루트로 이동
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

# Python 실행 함수
run_python() {
    if command -v py >/dev/null 2>&1; then
        py -3 "$@"
    elif command -v python >/dev/null 2>&1; then
        python "$@"
    else
        echo "ERROR: Python을 찾을 수 없습니다."
        echo "Windows 터미널에서 'py --version'을 확인하세요."
        return 1
    fi
}

# Python 설치 확인
echo "========================================"
echo " Personal Memory Agent"
echo " Evaluation Pipeline"
echo "========================================"

run_python --version

# 결과 디렉터리 생성
mkdir -p results

# 1. 평가 실행
echo ""
echo "[1/2] Running evaluation..."

run_python evaluation/run_eval.py --prompt prompts/extraction_v5.txt "$@"

# 2. 보고서 생성
echo ""
echo "[2/2] Generating report..."

run_python evaluation/report.py

echo ""
echo "========================================"
echo " Evaluation completed successfully"
echo "========================================"
echo "Results : results/evaluation_v4.jsonl"
echo "Metrics : results/evaluation_v4_metrics.json"
echo "Report  : results/evaluation_report.md"