from __future__ import annotations

import re
from pathlib import Path

from docx import Document
from pypdf import PdfReader


ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}


def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md"}:
        return path.read_text(encoding="utf-8", errors="ignore")
    if suffix == ".pdf":
        reader = PdfReader(str(path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    if suffix == ".docx":
        document = Document(str(path))
        return "\n".join(paragraph.text for paragraph in document.paragraphs)
    raise ValueError("暂不支持该文件类型")


def _section(text: str, labels: tuple[str, ...]) -> list[str]:
    lines = [line.strip(" •\t") for line in text.splitlines() if line.strip()]
    result = []
    for line in lines:
        if any(label in line for label in labels):
            result.append(line)
    return result[:8]


def structure_resume(text: str) -> dict[str, object]:
    normalized = re.sub(r"\n{3,}", "\n\n", text).strip()
    return {
        "raw_text": normalized[:12000],
        "education": _section(normalized, ("教育", "大学", "本科", "硕士", "学历")),
        "internships": _section(normalized, ("实习", "工作经历", "任职")),
        "projects": _section(normalized, ("项目", "系统", "平台")),
        "skills": _section(normalized, ("技能", "熟悉", "掌握")),
        "tech_stack": sorted(
            {
                word
                for word in (
                    "Python",
                    "Java",
                    "JavaScript",
                    "Vue",
                    "FastAPI",
                    "LangChain",
                    "MySQL",
                    "Redis",
                    "Docker",
                    "ChromaDB",
                )
                if word.lower() in normalized.lower()
            }
        ),
    }
