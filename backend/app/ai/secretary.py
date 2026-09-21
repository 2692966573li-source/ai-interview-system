from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from .model_client import invoke


TECHNICAL_WORDS = {
    "Python",
    "FastAPI",
    "LangChain",
    "Redis",
    "MySQL",
    "PostgreSQL",
    "SQLite",
    "Docker",
    "ChromaDB",
    "向量检索",
    "数据库",
    "缓存",
    "接口",
    "并发",
    "性能",
    "事务",
    "索引",
    "大模型",
}

SUMMARY_LIST_FIELDS = (
    "project_details",
    "skills_covered",
    "keywords",
    "asked_question_ids",
    "unresolved_points",
    "score_evidence",
)


def _keywords(text: str) -> list[str]:
    found = [word for word in TECHNICAL_WORDS if word.lower() in text.lower()]
    found.extend(re.findall(r"\b\d+(?:\.\d+)?%?\b", text))
    return list(dict.fromkeys(found))[:12]


def deterministic_summary(messages: list[dict[str, Any]]) -> dict[str, Any]:
    user_messages = [item for item in messages if item["role"] == "user"]
    joined = " ".join(item["content"] for item in user_messages)
    facts = [
        {
            "fact": item["content"][:160],
            "source_turns": [item["turn_no"]],
            "confidence": 0.65,
        }
        for item in user_messages[-5:]
    ]
    return {
        "confirmed_facts": facts,
        "project_details": [item["content"][:160] for item in user_messages[-3:]],
        "skills_covered": _keywords(joined),
        "keywords": _keywords(joined),
        "asked_question_ids": [],
        "unresolved_points": [],
        "score_evidence": [],
        "next_focus": "从最近一个具体技术点继续追问",
    }


def _source_turns(value: Any) -> list[int]:
    if isinstance(value, list):
        return [int(item) for item in value if str(item).isdigit()]
    return [
        int(item)
        for item in re.findall(r"(?:turn_no|turn|第)\s*[:：]?\s*(\d+)", str(value), re.I)
    ]


def normalize_summary(
    parsed: dict[str, Any],
    recent: list[dict[str, Any]],
    previous: dict[str, Any],
) -> dict[str, Any]:
    """把模型的近似 JSON 收紧成后端可稳定读取的固定结构。"""
    user_answers = {
        int(item["turn_no"]): item["content"]
        for item in recent
        if item.get("role") == "user"
    }
    normalized_facts: list[dict[str, Any]] = []
    raw_facts = [*previous.get("confirmed_facts", []), *parsed.get("confirmed_facts", [])]
    for item in raw_facts:
        if isinstance(item, dict):
            fact = str(item.get("fact", "")).strip()
            turns = _source_turns(item.get("source_turns", []))
            confidence = item.get("confidence", 0.8)
        else:
            fact = str(item).strip()
            turns = _source_turns(item)
            confidence = 0.8
        if fact:
            normalized_facts.append(
                {"fact": fact[:240], "source_turns": turns, "confidence": confidence}
            )

    covered = {turn for fact in normalized_facts for turn in fact["source_turns"]}
    for turn, answer in user_answers.items():
        if turn not in covered:
            normalized_facts.append(
                {"fact": answer[:180], "source_turns": [turn], "confidence": 0.7}
            )

    output: dict[str, Any] = {"confirmed_facts": normalized_facts[-20:]}
    for field in SUMMARY_LIST_FIELDS:
        value = parsed.get(field, previous.get(field, []))
        output[field] = value if isinstance(value, list) else ([value] if value else [])
    next_focus = parsed.get("next_focus", previous.get("next_focus", ""))
    if isinstance(next_focus, list):
        next_focus = "；".join(str(item) for item in next_focus)
    output["next_focus"] = str(next_focus or "从最近一个具体技术点继续追问")
    return output


def summarize(messages: list[dict[str, Any]], previous: dict[str, Any]) -> dict[str, Any]:
    # 摘要按“轮”触发，一轮同时包含用户回答和面试官追问。
    # 不能简单截取最后 5 条消息，否则实际只会覆盖约 2 轮对话。
    covered_turn = int(previous.get("covered_turn", 0))
    recent = [item for item in messages if int(item.get("turn_no", 0)) > covered_turn]
    prompt = {
        "previous_summary": previous,
        "recent_messages": [
            {"turn_no": item["turn_no"], "role": item["role"], "content": item["content"]}
            for item in recent
        ],
    }
    content = invoke(
        [
            SystemMessage(
                content=(
                    "你是面试记忆管家。只根据对话事实更新摘要，不得编造。"
                    "必须返回 JSON，字段为 confirmed_facts, project_details, skills_covered, "
                    "keywords, asked_question_ids, unresolved_points, score_evidence, next_focus。"
                    "confirmed_facts 的每项必须是 fact、source_turns、confidence 三字段对象，"
                    "且 recent_messages 中每个用户回答轮次至少保留一项事实；不得只把轮次写进字符串。"
                )
            ),
            HumanMessage(content=json.dumps(prompt, ensure_ascii=False)),
        ],
        caller="secretary.summarize",
    )
    if content:
        try:
            cleaned = content.strip().replace(chr(96) * 3 + "json", "").replace(chr(96) * 3, "").strip()
            parsed = json.loads(cleaned)
            if isinstance(parsed, dict):
                return normalize_summary(parsed, recent, previous)
        except json.JSONDecodeError:
            pass
    return deterministic_summary(messages)
