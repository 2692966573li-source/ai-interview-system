from __future__ import annotations

import re
from typing import Any


CONFIDENT_MARKERS = (
    "我负责", "我实现", "我设计", "我主导", "我优化", "我排查", "我解决",
    "我独立", "实测", "验证过", "具体来说", "举个例子", "例如", "压测",
)
HESITATION_MARKERS = (
    "可能", "大概", "应该吧", "好像", "似乎", "不太确定", "不确定",
    "记不清", "忘了", "差不多", "也许", "没研究过", "不了解", "猜",
)
NEGATIVE_MARKERS = (
    "失败", "出错", "故障", "事故", "延期", "搞砸", "不知道",
    "没做好", "崩溃", "卡住", "被问倒",
)
POSITIVE_MARKERS = (
    "顺利", "成功", "提升", "效果明显", "解决", "收益", "达标", "落地",
)


def analyze_answer(text: str) -> dict[str, Any]:
    """基于中文文本信号的轻量情绪分析，本地规则运行，不消耗模型额度。"""
    content = str(text or "")
    confident = sum(1 for word in CONFIDENT_MARKERS if word in content)
    hesitant = sum(1 for word in HESITATION_MARKERS if word in content)
    negative = sum(1 for word in NEGATIVE_MARKERS if word in content)
    positive = sum(1 for word in POSITIVE_MARKERS if word in content)
    has_metrics = bool(re.search(r"\d", content)) and bool(
        re.search(r"%|ms|毫秒|秒|倍|QPS|qps|万", content)
    )
    length = len(content.strip())

    score = 60
    score += min(24, confident * 6)
    if has_metrics:
        score += 8
    if length >= 200:
        score += 10
    elif length >= 80:
        score += 6
    elif length < 30:
        score -= 10
    score -= min(28, hesitant * 7)
    score -= min(20, negative * 5)
    score += min(12, positive * 4)
    score = max(0, min(100, score))

    if score >= 72:
        label = "自信"
        hint = "表达笃定，继续保持用数据和案例支撑观点的习惯。"
    elif score >= 55:
        label = "平稳"
        hint = "整体平稳，可以再多给出量化结果增强说服力。"
    elif score >= 40:
        label = "偏紧张"
        hint = "出现较多不确定表述，回答前先在心里组织要点再作答。"
    else:
        label = "明显紧张"
        hint = "紧张明显，先从最熟悉的项目讲起建立节奏，再展开细节。"

    return {
        "label": label,
        "score": score,
        "signals": {
            "confident": confident,
            "hesitant": hesitant,
            "negative": negative,
            "positive": positive,
            "has_metrics": has_metrics,
            "length": length,
        },
        "hint": hint,
    }


def aggregate_emotion(timeline: list[dict[str, Any]]) -> dict[str, Any]:
    """把每轮情绪汇总为画像、平均分和趋势（执行手册 6.3 进阶：情绪辅助分析）。"""
    if not timeline:
        return {
            "timeline": [],
            "average_score": 0,
            "dominant_label": "平稳",
            "trend": "暂无数据",
        }
    scores = [int(item.get("score", 0)) for item in timeline]
    labels = [str(item.get("label", "")) for item in timeline]
    average = round(sum(scores) / len(scores))
    dominant = max(set(labels), key=labels.count)
    half = len(scores) // 2
    if half:
        first = sum(scores[:half]) / half
        second = sum(scores[half:]) / (len(scores) - half)
        diff = second - first
        if diff >= 8:
            trend = "渐入佳境"
        elif diff <= -8:
            trend = "逐渐紧张"
        else:
            trend = "整体平稳"
    else:
        trend = "整体平稳"
    return {
        "timeline": timeline,
        "average_score": average,
        "dominant_label": dominant,
        "trend": trend,
    }


def emotion_section(messages: list[dict[str, Any]]) -> dict[str, Any]:
    """从消息里汇总情绪轨迹；旧消息没有情绪元数据时现场补算。"""
    timeline = []
    for item in messages:
        if item.get("role") != "user" or int(item.get("turn_no", 0)) == 0:
            continue
        emotion = (item.get("metadata") or {}).get("emotion")
        if not isinstance(emotion, dict) or "score" not in emotion:
            emotion = analyze_answer(str(item.get("content", "")))
        timeline.append(
            {
                "turn": int(item.get("turn_no", 0)),
                "label": emotion.get("label", ""),
                "score": int(emotion.get("score", 0)),
                "hint": emotion.get("hint", ""),
            }
        )
    return aggregate_emotion(timeline)


AUDIO_EMOTION_PROMPT = (
    "你是面试情绪分析专家。分析这段面试回答音频的语音情绪（语速、音量、停顿、语气），"
    "不要只根据说话内容判断。只返回 JSON，字段为："
    '{"score": 0到100的整数，越高代表越自信平稳, '
    '"label": "自信|平稳|偏紧张|明显紧张" 之一, '
    '"pace": "语速偏快|语速适中|语速偏慢" 之一, '
    '"tone": "一句话描述语音语气"}'
)


def analyze_audio_emotion(audio_bytes: bytes, audio_format: str = "wav") -> dict[str, Any] | None:
    """进阶：音频情绪推理（赛题三进阶 2）。

    把音频传给多模态模型，从韵律层面推理情绪得分；失败返回 None，
    由调用方降级为纯文本情绪分析，不阻塞面试流程。
    """
    import base64
    import json as _json
    import logging

    from openai import OpenAI

    from ..config import settings

    logger = logging.getLogger("ai_interview.emotion")
    if not settings.dashscope_api_key or not audio_bytes:
        return None
    if len(audio_bytes) > 15 * 1024 * 1024:
        return None
    audio_format = (audio_format or "wav").lower().lstrip(".")
    data_uri = f"data:audio/{audio_format};base64,{base64.b64encode(audio_bytes).decode()}"
    try:
        client = OpenAI(
            api_key=settings.dashscope_api_key,
            base_url=settings.bailian_base_url,
            timeout=60,
            max_retries=0,
        )
        completion = client.chat.completions.create(
            model=settings.voice_model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": AUDIO_EMOTION_PROMPT},
                        {
                            "type": "input_audio",
                            "input_audio": {"data": data_uri, "format": audio_format},
                        },
                    ],
                }
            ],
            stream=False,
            extra_body={"modalities": ["text"]},
        )
    except Exception as exc:
        logger.warning("emotion.audio error=%s", type(exc).__name__)
        return None
    content = completion.choices[0].message.content
    if not isinstance(content, str):
        content = str(content or "")
    cleaned = content.strip().replace(chr(96) * 3 + "json", "").replace(chr(96) * 3, "").strip()
    try:
        parsed = _json.loads(cleaned)
    except _json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict) or "score" not in parsed:
        return None
    try:
        parsed["score"] = max(0, min(100, int(parsed["score"])))
    except (TypeError, ValueError):
        return None
    parsed.setdefault("label", "平稳")
    parsed["source"] = "audio"
    return parsed
