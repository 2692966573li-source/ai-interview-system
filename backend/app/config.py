from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent
load_dotenv(BACKEND_DIR / ".env")


def _path_from_env(name: str, default: str) -> Path:
    value = os.getenv(name, default)
    path = Path(value)
    if not path.is_absolute():
        path = (BACKEND_DIR / path).resolve()
    return path


class Settings:
    app_name = "AI 模拟面试系统"
    api_prefix = "/api"
    model_name = os.getenv("MODEL_NAME", "qwen-plus")
    dashscope_api_key = os.getenv("DASHSCOPE_API_KEY", "").strip()
    bailian_base_url = os.getenv(
        "BAILIAN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
    )
    database_path = _path_from_env("DATABASE_PATH", "../data/app.db")
    chroma_dir = _path_from_env("CHROMA_DIR", "../data/chroma_db")
    upload_dir = _path_from_env("UPLOAD_DIR", "../data/uploads")
    export_dir = _path_from_env("EXPORT_DIR", "../data/exports")
    max_turns = int(os.getenv("MAX_TURNS", "15"))
    min_turns = int(os.getenv("MIN_TURNS", "6"))
    summary_every_turns = int(os.getenv("SUMMARY_EVERY_TURNS", "5"))
    jwt_secret_key = os.getenv("JWT_SECRET_KEY", "local-ai-interview-jwt-secret-change-me")
    jwt_expire_minutes = int(os.getenv("JWT_EXPIRE_MINUTES", "480"))
    voice_model = os.getenv("VOICE_MODEL", "qwen3-omni-flash")
    tts_voice = os.getenv("TTS_VOICE", "Cherry")


settings = Settings()
for _directory in (
    settings.database_path.parent,
    settings.chroma_dir,
    settings.upload_dir,
    settings.export_dir,
):
    _directory.mkdir(parents=True, exist_ok=True)
