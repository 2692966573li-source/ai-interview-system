from __future__ import annotations

import json
import logging
import time

from langchain_core.messages import BaseMessage
from langchain_openai import ChatOpenAI

from ..config import settings


logger = logging.getLogger("ai_interview.model")


def get_model() -> ChatOpenAI | None:
    if not settings.dashscope_api_key:
        return None
    return ChatOpenAI(
        model=settings.model_name,
        api_key=settings.dashscope_api_key,
        base_url=settings.bailian_base_url,
        temperature=0.2,
        timeout=45,
        max_retries=1,
    )


def _token_usage(response: BaseMessage) -> dict[str, int] | None:
    """提取响应元数据中的 token 用量；不同 SDK 版本字段位置可能不同。"""
    meta = getattr(response, "response_metadata", None) or {}
    usage = (
        meta.get("token_usage")
        or meta.get("usage")
        or (meta.get("model_extra") or {}).get("usage")
    )
    if not isinstance(usage, dict):
        return None
    result = {}
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        value = usage.get(key)
        if isinstance(value, int):
            result[key] = value
    return result or None


def invoke(messages: list[BaseMessage], caller: str = "unknown") -> str | None:
    """调用模型并记录耗时与 token 用量（不记录任何文本内容，见执行手册 0.4）。"""
    model = get_model()
    if model is None:
        logger.info("model=missing caller=%s mode=mock", caller)
        return None
    started = time.perf_counter()
    try:
        response = model.invoke(messages)
    except Exception as exc:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        logger.warning(
            "caller=%s error=%s elapsed_ms=%d",
            caller,
            type(exc).__name__,
            elapsed_ms,
        )
        return None
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    usage = _token_usage(response)
    if usage:
        logger.info(
            "caller=%s elapsed_ms=%d prompt_tokens=%s completion_tokens=%s total_tokens=%s",
            caller,
            elapsed_ms,
            usage.get("prompt_tokens"),
            usage.get("completion_tokens"),
            usage.get("total_tokens"),
        )
    else:
        logger.info("caller=%s elapsed_ms=%d tokens=unavailable", caller, elapsed_ms)
    content = response.content
    return content if isinstance(content, str) else str(content)


def invoke_with_tools(
    messages: list[BaseMessage],
    tools: list[dict],
    execute_tool,
    caller: str = "unknown",
    max_tool_rounds: int = 2,
) -> tuple[str | None, list[dict]]:
    """Function Call 主循环（执行手册 6.2 进阶）。

    模型可请求调用工具；后端执行工具并把结果回传，最多 max_tool_rounds 轮。
    任何失败都返回 (None, tool_calls)，由调用方回退到普通调用路径。
    """
    model = get_model()
    if model is None:
        logger.info("model=missing caller=%s mode=mock", caller)
        return None, []
    started = time.perf_counter()
    executed_calls: list[dict] = []
    try:
        bound = model.bind_tools(tools)
        response = bound.invoke(messages)
        rounds = 0
        while getattr(response, "tool_calls", None) and rounds < max_tool_rounds:
            rounds += 1
            followup = [*messages, response]
            for call in response.tool_calls:
                name = str(call.get("name", ""))
                args = call.get("args") or {}
                try:
                    result = execute_tool(name, args)
                    result_text = json.dumps(result, ensure_ascii=False, default=str)
                    status = "ok"
                except Exception as exc:
                    result_text = json.dumps({"error": type(exc).__name__}, ensure_ascii=False)
                    status = f"error:{type(exc).__name__}"
                executed_calls.append({"name": name, "args": args, "status": status})
                logger.info("tool_call caller=%s tool=%s status=%s", caller, name, status)
                from langchain_core.messages import ToolMessage

                followup.append(
                    ToolMessage(content=result_text, tool_call_id=str(call.get("id", "")))
                )
            response = bound.invoke(followup)
    except Exception as exc:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        logger.warning(
            "caller=%s error=%s elapsed_ms=%d tools=%d",
            caller,
            type(exc).__name__,
            elapsed_ms,
            len(executed_calls),
        )
        return None, executed_calls
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    usage = _token_usage(response)
    logger.info(
        "caller=%s elapsed_ms=%d tool_calls=%d total_tokens=%s",
        caller,
        elapsed_ms,
        len(executed_calls),
        (usage or {}).get("total_tokens", "unavailable"),
    )
    content = response.content
    if not isinstance(content, str):
        content = str(content) if content else None
    return (content.strip() or None) if content else None, executed_calls
