#!/bin/sh
set -eu

container="${JINGAO_AGENT_CONTAINER:-jingao-copilot-agent-1}"
mode="${1:-intended}"
max_cases="${2:-150}"
label="${3:-manual}"
limit="${4:-8}"
log_path="/data/evaluations/recall-${label}-run.log"

docker exec "$container" sh -lc \
  "python -m app.cli recall-evaluate --mode '$mode' --max-cases '$max_cases' --limit '$limit' --label '$label' > '$log_path' 2>&1"

docker exec -i "$container" python - "$log_path" <<'PY'
import json
import sys
from pathlib import Path

log_path = sys.argv[1]
report_path = Path("/data/evaluations/recall-latest.json")
report = json.loads(report_path.read_text(encoding="utf-8"))
print(json.dumps({
    "report_path": str(report_path),
    "run_log": log_path,
    "label": report["label"],
    "mode": report["mode"],
    "gold_status": report["gold_status"],
    "metrics": report["metrics"],
    "by_category": report["by_category"],
    "failure_count": len(report["failures"]),
}, ensure_ascii=False, indent=2))
PY
