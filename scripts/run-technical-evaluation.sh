#!/bin/sh
set -eu

container="${JINGAO_AGENT_CONTAINER:-jingao-copilot-agent-1}"
log_path="/data/evaluations/technical-run.log"

evaluation_exit=0
docker exec "$container" sh -lc \
  "python -m app.cli evaluate > '$log_path' 2>&1" || evaluation_exit=$?

docker exec -i "$container" python - "$log_path" <<'PY'
import json
import sys
from pathlib import Path

log_path = sys.argv[1]
report_path = Path("/data/evaluations/latest.json")
report = json.loads(report_path.read_text(encoding="utf-8"))
print(json.dumps({
    "report_path": str(report_path),
    "run_log": log_path,
    "technical_status": report["technical_status"],
    "technical_case_count": report["technical_case_count"],
    "metrics": report["metrics"],
    "case_counts": report["case_counts"],
    "passed_counts": report["passed_counts"],
    "gates": report["gates"],
    "failure_count": len(report["failures"]),
}, ensure_ascii=False, indent=2))
PY

exit "$evaluation_exit"
