from __future__ import annotations

import base64
import logging
import time
import uuid
from pathlib import Path

from openai import OpenAI

from ..config import settings


logger = logging.getLogger("ai_interview.voice")

TRANSCRIBE_PROMPT = (
    "把这段音频中的语音逐字转写成中文文本。只输出转写结果，不要解释。"
    "如果没有人声，只输出：无人声。"
)

SUPPORTED_FORMATS = {"wav", "mp3", "m4a", "aac", "flac", "amr", "opus"}


class VoiceError(RuntimeError):
    """语音能力失败时的统一错误；调用方转为 503 并提示降级。"""


def _client() -> OpenAI:
    if not settings.dashscope_api_key:
        raise VoiceError("未配置模型密钥，语音功能不可用")
    return OpenAI(
        api_key=settings.dashscope_api_key,
        base_url=settings.bailian_base_url,
        timeout=90,
        max_retries=0,
    )


def transcribe_audio(audio_bytes: bytes, audio_format: str = "wav") -> str:
    """服务端语音转写（执行手册 4.2：HTTP 语音）。失败抛 VoiceError。"""
    audio_format = (audio_format or "wav").lower().lstrip(".")
    if audio_format not in SUPPORTED_FORMATS:
        audio_format = "wav"
    if not audio_bytes:
        raise VoiceError("音频内容为空")
    if len(audio_bytes) > 15 * 1024 * 1024:
        raise VoiceError("音频不能超过 15 MB")
    started = time.perf_counter()
    data_uri = f"data:audio/{audio_format};base64,{base64.b64encode(audio_bytes).decode()}"
    try:
        completion = _client().chat.completions.create(
            model=settings.voice_model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": TRANSCRIBE_PROMPT},
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
        logger.warning("voice.transcribe error=%s", type(exc).__name__)
        raise VoiceError("语音识别失败，请改用文字输入") from exc
    logger.info(
        "voice.transcribe elapsed_ms=%d bytes=%d",
        int((time.perf_counter() - started) * 1000),
        len(audio_bytes),
    )
    content = completion.choices[0].message.content
    if not isinstance(content, str):
        content = str(content or "")
    return content.strip()


def _wav_header(pcm_size: int, sample_rate: int = 24000, channels: int = 1, bits: int = 16) -> bytes:
    """把模型返回的裸 PCM 包上标准 WAV 头（官方示例用 soundfile，这里直接写字节避免额外依赖）。"""
    byte_rate = sample_rate * channels * bits // 8
    block_align = channels * bits // 8
    return (
        b"RIFF"
        + (36 + pcm_size).to_bytes(4, "little")
        + b"WAVEfmt "
        + (16).to_bytes(4, "little")
        + (1).to_bytes(2, "little")
        + channels.to_bytes(2, "little")
        + sample_rate.to_bytes(4, "little")
        + byte_rate.to_bytes(4, "little")
        + block_align.to_bytes(2, "little")
        + bits.to_bytes(2, "little")
        + b"data"
        + pcm_size.to_bytes(4, "little")
    )


def synthesize_speech(text: str) -> tuple[Path, str]:
    """服务端语音合成，返回 WAV 文件路径与音频 ID（执行手册 4.2）。失败抛 VoiceError。"""
    text = str(text or "").strip()
    if not text:
        raise VoiceError("朗读内容为空")
    if len(text) > 800:
        text = text[:800]
    started = time.perf_counter()
    audio_b64 = ""
    try:
        completion = _client().chat.completions.create(
            model=settings.voice_model,
            messages=[{"role": "user", "content": f"请原样朗读下面这段话：\n{text}"}],
            stream=True,
            extra_body={
                "modalities": ["text", "audio"],
                "audio": {"voice": settings.tts_voice, "format": "wav"},
            },
        )
        for chunk in completion:
            if chunk.choices:
                delta = chunk.choices[0].delta
                audio = getattr(delta, "audio", None)
                if audio and audio.get("data"):
                    audio_b64 += audio["data"]
    except Exception as exc:
        logger.warning("voice.synthesize error=%s", type(exc).__name__)
        raise VoiceError("语音合成失败，可改用浏览器朗读") from exc
    if not audio_b64:
        raise VoiceError("语音合成没有返回音频")
    pcm_bytes = base64.b64decode(audio_b64)
    wav_bytes = _wav_header(len(pcm_bytes)) + pcm_bytes
    out_dir = settings.export_dir / "voice"
    out_dir.mkdir(parents=True, exist_ok=True)
    audio_id = f"tts_{uuid.uuid4().hex[:12]}"
    path = out_dir / f"{audio_id}.wav"
    path.write_bytes(wav_bytes)
    logger.info(
        "voice.synthesize elapsed_ms=%d bytes=%d",
        int((time.perf_counter() - started) * 1000),
        len(wav_bytes),
    )
    return path, audio_id
