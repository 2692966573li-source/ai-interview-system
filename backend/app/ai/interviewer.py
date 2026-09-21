from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from .model_client import invoke, invoke_with_tools
from .question_bank import search as question_bank_search


SEARCH_QUESTION_BANK_TOOL = {
    "type": "function",
    "function": {
        "name": "search_question_bank",
        "description": (
            "按关键词检索面试题库。当用户回答里出现值得追问的技术点，"
            "而预置候选不够贴合时，可用自选关键词再检索一轮，获取带评分标准的候选题。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "检索关键词，例如：Redis 缓存击穿 / 索引优化",
                }
            },
            "required": ["query"],
        },
    },
}


def mock_opening(target_role: str, difficulty: str) -> str:
    return (
        f"你好，我将围绕“{target_role}”岗位进行{difficulty}难度的模拟面试。"
        "请先用 1 分钟介绍一个你最熟悉的项目，以及你在其中承担的具体工作。"
    )


def mock_followup(answer: str, excluded_question_ids: list[str] | None = None) -> tuple[str, dict[str, Any]]:
    lowered = answer.lower()
    excluded = set(excluded_question_ids or [])
    candidates: list[tuple[str, str, str]] = [
        (
            "measure-performance",
            "你刚才提到了性能或指标变化，这个数字是如何测量的？请说明测试环境、优化前后数据，以及你本人负责的部分。",
            "性能验证",
        ),
        (
            "database-design",
            "你提到了数据库设计，为什么选择这个方案？如果数据量和并发继续增长，你会优先优化哪一处？",
            "数据库设计",
        ),
        (
            "tech-implementation",
            "你刚才提到这个技术点，能具体讲一次你亲自处理的实现或故障吗？当时有哪些取舍？",
            "技术实现",
        ),
        (
            "expand-answer",
            "请把刚才的回答展开成“问题—行动—结果”三部分，并说明你本人完成了哪一部分。",
            "表达结构",
        ),
        (
            "design-tradeoff",
            "从你刚才的经历中，我想继续追问一个具体细节：当时为什么这样设计？如果重新做一次，你会改哪里？",
            "设计取舍",
        ),
    ]
    if any(token in lowered for token in ("%", "提升", "降低", "速度", "性能")):
        preferred = [candidates[0], candidates[4]]
    elif any(token in lowered for token in ("数据库", "mysql", "postgresql", "sqlite", "事务", "索引")):
        preferred = [candidates[1], candidates[4]]
    elif any(token in lowered for token in ("缓存", "redis", "部署", "接口", "fastapi", "向量")):
        preferred = [candidates[2], candidates[4]]
    elif len(answer.strip()) < 30:
        preferred = [candidates[3], candidates[4]]
    else:
        preferred = [candidates[4], candidates[1]]
    chosen = next((item for item in preferred if item[0] not in excluded), candidates[4])
    if chosen[0] in excluded:
        chosen = (f"{chosen[0]}-{len(excluded)}", chosen[1], chosen[2])
    return chosen[1], {
        "action": "ask_question",
        "target_skill": chosen[2],
        "question_id": None,
        "reason": "基于回答关键词的本地规则追问",
    }


def opening_question(config: dict[str, Any]) -> str:
    role = config["target_role"]
    difficulty = config["difficulty"]
    content = invoke(
        [
            SystemMessage(content="你是严格但友善的模拟面试官，只输出一个自然的开场问题，不要解释规则。"),
            HumanMessage(
                content=f"目标岗位：{role}\n难度：{difficulty}\n简历摘要：{config.get('resume_text', '')[:1500]}"
            ),
        ],
        caller="interviewer.opening",
    )
    return content.strip() if content else mock_opening(role, difficulty)


def _cleaned_json(content: str) -> dict[str, Any] | None:
    cleaned = content.strip().replace(chr(96) * 3 + "json", "").replace(chr(96) * 3, "").strip()
    try:
        parsed = json.loads(cleaned)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


def next_question(
    config: dict[str, Any],
    summary: dict[str, Any],
    recent_messages: list[dict[str, Any]],
    answer: str,
    candidates: list[dict[str, Any]] | None = None,
) -> tuple[str, dict[str, Any]]:
    covered_turn = int(summary.get("covered_turn", 0))
    if covered_turn:
        window = [item for item in recent_messages if int(item.get("turn_no", 0)) > covered_turn]
    else:
        # 第一次摘要前最多只有五轮；保留完整的首批对话，避免过早遗忘。
        window = recent_messages
    recent_dialogue = [
        {"turn_no": item["turn_no"], "role": item["role"], "content": item["content"]}
        for item in window
    ]
    asked = [item["content"] for item in window if item["role"] == "assistant"]
    # 已问题目 ID 硬去重（执行手册 5.1/5.3）：历史消息与摘要两处合并。
    asked_ids = {
        item.get("question_id")
        for item in recent_messages
        if item.get("role") == "assistant" and item.get("question_id")
    }
    asked_ids.update(str(item) for item in summary.get("asked_question_ids", []) if item)
    candidate_payload = [
        {
            "id": item["id"],
            "question": item["question"],
            "skill": item.get("skill", ""),
            "difficulty": item.get("difficulty", ""),
            "followups": item.get("followups", [])[:2],
        }
        for item in (candidates or [])
    ]
    prompt = (
        f"岗位：{config['target_role']}\n难度：{config['difficulty']}\n"
        f"重点技能：{config.get('focus_skills', [])}\n"
        f"已知摘要：{json.dumps(summary, ensure_ascii=False)}\n"
        f"摘要后的新对话：{json.dumps(recent_dialogue, ensure_ascii=False)}\n"
        f"用户最新回答：{answer}\n摘要后已问问题：{asked[-8:]}\n"
        f"已问题目 ID（禁止重复）：{sorted(asked_ids)}\n题库候选：{json.dumps(candidate_payload, ensure_ascii=False)}"
    )
    system_prompt = (
        "你是 AI 模拟面试官。必须抓住用户最新回答中的一个具体技术、数字、经历或模糊点深入追问。"
        "结合摘要和最近对话，避免重复。只返回 JSON，字段为："
        "action（固定为 ask_question）、question（下一个问题，只能一个问题）、"
        "target_skill（考察技能）、question_id（若使用了题库候选则填其 id，否则为 null）、"
        "reason（为什么这样追问，一句话）。"
        "不得编造用户简历内容，不得输出评分或多个问题。"
    )
    role = config["target_role"]
    difficulty = config["difficulty"]

    def _execute_tool(name: str, args: dict[str, Any]) -> list[dict[str, Any]]:
        if name != "search_question_bank":
            raise ValueError(f"unknown tool: {name}")
        return question_bank_search(str(args.get("query", answer)), role, difficulty, limit=4)

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=prompt),
    ]
    content, tool_calls = invoke_with_tools(
        messages,
        [SEARCH_QUESTION_BANK_TOOL],
        _execute_tool,
        caller="interviewer.next_question",
    )
    if not content:
        # 工具路径失败（模型不支持 Function Call、超时等）时回退到普通调用。
        content = invoke([*messages], caller="interviewer.next_question")
    if content:
        parsed = _cleaned_json(content)
        question = None
        if parsed:
            question = str(parsed.get("question", "")).strip()
        if question:
            metadata = {
                "action": "ask_question",
                "target_skill": str(parsed.get("target_skill", "")) or "综合能力",
                "question_id": parsed.get("question_id"),
                "reason": str(parsed.get("reason", "")) or "基于最新回答深入追问",
                "mode": "bailian_tools" if tool_calls else "bailian",
                "answer_driven": True,
                "question_candidates": candidate_payload,
                "tool_calls": tool_calls,
            }
            if metadata["question_id"] and metadata["question_id"] in asked_ids:
                # 模型选了已问过的题库题：保留问题文本但清掉引用，避免重复计数。
                metadata["question_id"] = None
                metadata["reason"] += "（模型候选命中已问题目，已去除引用）"
            return question, metadata
        if content.strip():
            # 模型没有返回合法 JSON 但有文本时，退回纯文本问题，保证面试不断流。
            return content.strip(), {
                "action": "ask_question",
                "target_skill": "综合能力",
                "question_id": None,
                "reason": "模型未按结构化格式返回，已直接使用文本",
                "mode": "bailian_plain",
                "answer_driven": True,
                "question_candidates": candidate_payload,
            }
    followup, metadata = mock_followup(answer, sorted(asked_ids))
    metadata.update(
        {
            "mode": "mock",
            "answer_driven": True,
            "question_candidates": candidate_payload,
        }
    )
    return followup, metadata
