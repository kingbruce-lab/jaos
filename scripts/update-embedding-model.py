from __future__ import annotations

import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path


if len(sys.argv) != 4:
    raise SystemExit("usage: update-embedding-model.py PATH OLD_MODEL NEW_MODEL")

path = Path(sys.argv[1])
old_model = sys.argv[2]
new_model = sys.argv[3]
old_line = f"JINGAO_EMBEDDING_MODEL: {old_model}"
new_line = f"JINGAO_EMBEDDING_MODEL: {new_model}"
content = path.read_text(encoding="utf-8")
replacement_count = content.count(old_line)
if replacement_count == 0 and content.count(new_line) > 0:
    print(f"already_configured={new_model}")
    raise SystemExit(0)
if replacement_count != 2:
    raise SystemExit(f"unexpected_replacement_count={replacement_count}")

stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
backup = path.with_name(f"{path.name}.before-embedding-model-{stamp}")
shutil.copy2(path, backup)
path.write_text(content.replace(old_line, new_line), encoding="utf-8")
print(f"updated={path}")
print(f"backup={backup}")
