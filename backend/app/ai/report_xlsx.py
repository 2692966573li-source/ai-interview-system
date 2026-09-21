from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any


HELPER_PATH = Path(__file__).resolve().parents[2] / "tools" / "export_report_xlsx.mjs"


def _node_candidates() -> list[str]:
    configured = os.getenv("NODE_EXECUTABLE", "").strip()
    candidates = [configured] if configured else []
    found = shutil.which("node")
    if found:
        candidates.append(found)
    candidates.append(
        str(
            Path.home()
            / ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe"
        )
    )
    return list(dict.fromkeys(item for item in candidates if item))


def create_report_xlsx(
    output_path: Path,
    report: dict[str, Any],
    session: dict[str, Any],
) -> Path:
    if not HELPER_PATH.exists():
        raise RuntimeError("Excel 导出组件不存在")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"report": report, "session": session}
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", prefix="interview_report_", delete=False, encoding="utf-8"
    ) as stream:
        json.dump(payload, stream, ensure_ascii=False)
        input_path = Path(stream.name)
    try:
        last_error = ""
        for node in _node_candidates():
            try:
                result = subprocess.run(
                    [node, str(HELPER_PATH), str(input_path), str(output_path)],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    timeout=45,
                    check=False,
                )
            except (OSError, subprocess.SubprocessError) as exc:
                last_error = str(exc)
                continue
            if result.returncode == 0 and output_path.exists() and output_path.stat().st_size > 0:
                return output_path
            last_error = (result.stderr or result.stdout or "Excel 导出进程失败").strip()
        raise RuntimeError(f"Excel 导出失败：{last_error[:500]}")
    finally:
        input_path.unlink(missing_ok=True)
