from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from .model_client import invoke


def _quote_from_answer(answer: str, requested_quote: Any = "") -> str:
    """Keep the model's short quote when it is real; otherwise derive one safely."""
    answer = str(answer or "").strip()
    requested = str(requested_quote or "").strip()
    if requested and requested in answer:
        return requested[:160]
    normalized_requested = " ".join(requested.split())
    normalized_answer = " ".join(answer.split())
    if normalized_requested and normalized_requested in normalized_answer:
        return normalized_requested[:160]
    return answer[:160]


def _validated_evidence(
    raw_evidence: Any,
    valid_answers: dict[int, str],
    used_turns: set[int],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for item in raw_evidence if isinstance(raw_evidence, list) else []:
        if not isinstance(item, dict):
            continue
        try:
            turn = int(item.get("turn", -1))
        except (TypeError, ValueError):
            continue
        if turn not in valid_answers:
            continue
        candidates.append(
            {"turn": turn, "quote": _quote_from_answer(valid_answers[turn], item.get("quote"))}
        )

    # The report UI shows the first item for each dimension. Prefer different
    # answer turns so three dimensions do not collapse to one repeated example.
    selected: list[dict[str, Any]] = []
    first = next((item for item in candidates if item["turn"] not in used_turns), None)
    if first is None:
        fallback = next((turn for turn in valid_answers if turn not in used_turns), None)
        if fallback is not None:
            first = {"turn": fallback, "quote": _quote_from_answer(valid_answers[fallback])}
    if first is not None:
        selected.append(first)
        used_turns.add(first["turn"])

    seen = {(item["turn"], item["quote"]) for item in selected}
    for item in candidates:
        marker = (item["turn"], item["quote"])
        if marker in seen:
            continue
        selected.append(item)
        seen.add(marker)
    return selected


def _model_report(
    messages: list[dict[str, Any]], session: dict[str, Any]
) -> dict[str, Any] | None:
    dialogue = [
        {"turn_no": item["turn_no"], "role": item["role"], "content": item["content"]}
        for item in messages
    ]
    content = invoke(
        [
            SystemMessage(
                content=(
                    "你是严格的技术面试评估专家。只根据给出的完整问答评分，不得编造。"
                    "返回纯 JSON：overall_score(0-100), dimensions，其中必须有 professional、logic、communication；"
                    "每个维度含 score 和 evidence，evidence 每项含 turn 和 quote；另外返回 highlights、problems、suggestions。"
                    "每个证据 turn 必须来自真实用户回答轮次，quote 必须是原回答中的短句。"
                )
            ),
            HumanMessage(
                content=json.dumps(
                    {
                        "target_role": session["target_role"],
                        "difficulty": session["difficulty"],
                        "dialogue": dialogue,
                    },
                    ensure_ascii=False,
                )
            ),
        ],
        caller="report.generate",
    )
    if not content:
        return None
    try:
        cleaned = content.strip().replace(chr(96) * 3 + "json", "").replace(chr(96) * 3, "").strip()
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        return None
    dimensions = parsed.get("dimensions", {})
    if not all(key in dimensions for key in ("professional", "logic", "communication")):
        return None
    valid_answers = {
        int(item["turn_no"]): item["content"] for item in messages if item["role"] == "user"
    }
    used_turns: set[int] = set()
    for key in ("professional", "logic", "communication"):
        value = dimensions[key]
        score = value.get("score")
        if not isinstance(score, (int, float)) or not 0 <= score <= 100:
            return None
        value["evidence"] = _validated_evidence(value.get("evidence", []), valid_answers, used_turns)
    parsed["overall_score"] = int(
        round(sum(float(item["score"]) for item in dimensions.values()) / len(dimensions))
    )
    parsed["target_role"] = session["target_role"]
    parsed["meta"] = {
        "answer_count": len(valid_answers),
        "version_note": "百炼结构化评估，后端已校验证据轮次",
        "mode": "bailian",
    }
    return parsed


def generate_report(messages: list[dict[str, Any]], session: dict[str, Any]) -> dict[str, Any]:
    model_report = _model_report(messages, session)
    if model_report is not None:
        return model_report
    answers = [item for item in messages if item["role"] == "user"]
    if not answers:
        answers = [{"turn_no": 0, "content": "暂无回答"}]
    average_length = sum(len(item["content"]) for item in answers) / len(answers)
    detail_bonus = min(18, int(average_length / 20))
    dimensions = {
        "professional": {
            "score": min(95, 62 + detail_bonus),
            "evidence": [
                {"turn": item["turn_no"], "quote": item["content"][:120]} for item in answers[:2]
            ],
        },
        "logic": {
            "score": min(95, 60 + detail_bonus),
            "evidence": [
                {"turn": item["turn_no"], "quote": item["content"][:120]} for item in answers[1:3]
            ],
        },
        "communication": {
            "score": min(95, 64 + detail_bonus),
            "evidence": [
                {"turn": item["turn_no"], "quote": item["content"][:120]} for item in answers[-2:]
            ],
        },
    }
    valid_answers = {int(item["turn_no"]): item["content"] for item in answers}
    used_turns: set[int] = set()
    for key in ("professional", "logic", "communication"):
        dimensions[key]["evidence"] = _validated_evidence(
            dimensions[key]["evidence"], valid_answers, used_turns
        )
    overall = round(sum(item["score"] for item in dimensions.values()) / len(dimensions))
    return {
        "overall_score": overall,
        "target_role": session["target_role"],
        "dimensions": dimensions,
        "highlights": ["能够围绕项目经历进行回答"],
        "problems": ["部分回答仍可补充具体数据、边界条件和个人负责范围"],
        "suggestions": ["使用“问题—行动—结果”结构回答，并补充可验证指标"],
        "meta": {
            "answer_count": len(answers),
            "version_note": "首版规则报告，后续接入结构化模型评分",
            "mode": "fallback",
        },
    }
