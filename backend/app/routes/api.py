from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .. import db
from ..auth import create_access_token, get_current_user, hash_password, public_user, verify_password
from ..ai.emotion import analyze_answer, emotion_section
from ..ai.interviewer import next_question, opening_question
from ..ai.knowledge_graph import build_graph
from ..ai.question_bank import ensure_vector_index, search
from ..ai.report import generate_report
from ..ai.report_pdf import create_report_pdf
from ..ai.report_xlsx import create_report_xlsx
from ..ai.resume_parser import ALLOWED_EXTENSIONS, extract_text, structure_resume
from ..ai.secretary import summarize
from ..ai.termination import evaluate, next_stage
from ..ai.voice import VoiceError, synthesize_speech, transcribe_audio
from ..config import settings


router = APIRouter(prefix="/api")


class SessionCreate(BaseModel):
    target_role: str = Field(min_length=1, max_length=100)
    difficulty: str = Field(default="中等", max_length=20)
    question_limit: int = Field(default=10, ge=1, le=30)
    time_limit_seconds: int | None = Field(default=None, ge=60, le=7200)
    focus_skills: list[str] = Field(default_factory=list, max_length=12)
    resume_text: str = Field(default="", max_length=12000)
    resume_id: str | None = Field(default=None, max_length=40)
    config_id: str | None = Field(default=None, max_length=40)
    voice_enabled: bool = False


class AnswerCreate(BaseModel):
    content: str = Field(min_length=1, max_length=10000)


class EndRequest(BaseModel):
    reason: str = Field(default="user_requested_end", max_length=100)


class AuthRequest(BaseModel):
    username: str = Field(min_length=2, max_length=40, pattern=r"^[\w\u4e00-\u9fff-]+$")
    password: str = Field(min_length=6, max_length=128)


class ResumeConfirm(BaseModel):
    resume_text: str = Field(default="", max_length=12000)
    education: list[str] = Field(default_factory=list, max_length=20)
    internships: list[str] = Field(default_factory=list, max_length=20)
    projects: list[str] = Field(default_factory=list, max_length=20)
    skills: list[str] = Field(default_factory=list, max_length=30)
    tech_stack: list[str] = Field(default_factory=list, max_length=30)


def _audit(request: Request, user: dict[str, Any], action: str, target_type: str, target_id: str | None) -> None:
    db.add_audit_log(
        user["id"],
        action,
        target_type,
        target_id,
        getattr(request.state, "request_id", None),
    )


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "backend", "model": settings.model_name}


@router.post("/auth/register")
def register(payload: AuthRequest) -> dict[str, Any]:
    username = payload.username.strip()
    if len(username) < 2:
        raise HTTPException(status_code=422, detail="用户名至少需要 2 个字符")
    user = db.create_user(username, hash_password(payload.password))
    if user is None:
        raise HTTPException(status_code=409, detail="用户名已存在")
    return {"access_token": create_access_token(user), "token_type": "bearer", "user": public_user(user)}
@router.post("/auth/login")
def login(payload: AuthRequest) -> dict[str, Any]:
    user = db.get_user_by_username(payload.username.strip())
    if user is None or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    return {"access_token": create_access_token(user), "token_type": "bearer", "user": public_user(user)}


@router.get("/auth/me")
def me(current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    return public_user(current_user)


@router.post("/resumes/parse")
async def parse_resume(
    request: Request,
    file: UploadFile = File(...), current_user: dict[str, Any] = Depends(get_current_user)
) -> dict[str, Any]:
    from pathlib import Path

    original_filename = file.filename or "resume"
    suffix = Path(original_filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=415, detail="仅支持 PDF、DOCX、TXT 或 MD 简历")
    content = await file.read()
    if len(content) > 8 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="简历文件不能超过 8 MB")
    target = settings.upload_dir / f"{db.new_id('upload')}{suffix}"
    target.write_bytes(content)
    try:
        parsed = structure_resume(extract_text(target))
    except Exception as exc:
        target.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=f"简历解析失败：{exc}") from exc
    resume = db.save_resume(current_user["id"], original_filename, str(target), parsed)
    _audit(request, current_user, "resume.parse", "resume", resume["id"])
    return resume


@router.get("/resumes/{resume_id}")
def resume_detail(resume_id: str, current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    resume = db.get_resume_for_user(resume_id, current_user["id"])
    if resume is None:
        raise HTTPException(status_code=404, detail="简历不存在")
    return resume


@router.put("/resumes/{resume_id}")
def confirm_resume(
    request: Request,
    resume_id: str,
    payload: ResumeConfirm,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """用户确认或修改解析草稿；确认后的版本才是面试真正使用的简历（执行手册 3.1）。"""
    resume = db.get_resume_for_user(resume_id, current_user["id"])
    if resume is None:
        raise HTTPException(status_code=404, detail="简历不存在")
    confirmed = payload.model_dump()
    if not confirmed.get("resume_text", "").strip():
        raise HTTPException(status_code=422, detail="确认的简历内容不能为空")
    updated = db.confirm_resume(resume_id, current_user["id"], confirmed)
    if updated is None:
        raise HTTPException(status_code=404, detail="简历不存在")
    _audit(request, current_user, "resume.confirm", "resume", resume_id)
    return updated


@router.post("/interview-configs")
def create_interview_config(
    request: Request,
    payload: SessionCreate, current_user: dict[str, Any] = Depends(get_current_user)
) -> dict[str, Any]:
    """保存面试配置（执行手册 3.1/4.1），返回配置 ID。"""
    data = payload.model_dump()
    data["user_id"] = current_user["id"]
    data["question_limit"] = min(int(data["question_limit"]), settings.max_turns)
    config = db.create_interview_config(data)
    _audit(request, current_user, "interview_config.create", "interview_config", config["id"])
    return config


@router.post("/sessions")
def create_session(
    request: Request,
    payload: SessionCreate, current_user: dict[str, Any] = Depends(get_current_user)
) -> dict[str, Any]:
    data = payload.model_dump()
    data["user_id"] = current_user["id"]
    # 使界面显示的轮次与后端的全局安全上限保持一致。
    data["question_limit"] = min(int(data["question_limit"]), settings.max_turns)
    # 优先使用用户确认后的简历内容（执行手册 3.1：confirmed_json 才是面试用的版本）。
    if data.get("resume_id"):
        resume = db.get_resume_for_user(data["resume_id"], current_user["id"])
        if resume is None:
            raise HTTPException(status_code=404, detail="简历不存在")
        confirmed_text = str(resume.get("confirmed", {}).get("resume_text", "")).strip()
        if confirmed_text:
            data["resume_text"] = confirmed_text[:12000]
    # 没有单独创建配置时，同步落一份 interview_configs，保证手册 3.1 数据模型完整。
    if not data.get("config_id"):
        data["config_id"] = db.create_interview_config(data)["id"]
    else:
        data["config_id"] = None if data["config_id"] in ("", "null") else data["config_id"]
    opening = opening_question(data)
    session = db.create_session(data, opening)
    _audit(request, current_user, "session.create", "session", session.get("id"))
    return session


@router.get("/sessions")
def sessions(current_user: dict[str, Any] = Depends(get_current_user)) -> list[dict[str, Any]]:
    return db.list_sessions(current_user["id"])


@router.get("/sessions/{session_id}")
def session_detail(session_id: str, current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    session = db.get_session_for_user(session_id, current_user["id"])
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    session["focus_skills"] = db.loads(session.pop("focus_skills_json"), [])
    session["messages"] = db.list_messages(session_id)
    session["memory"] = db.latest_summary(session_id)
    session["report"] = db.latest_report(session_id)
    return session


@router.get("/sessions/{session_id}/messages")
def messages(session_id: str, current_user: dict[str, Any] = Depends(get_current_user)) -> list[dict[str, Any]]:
    if db.get_session_for_user(session_id, current_user["id"]) is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return db.list_messages(session_id)


@router.post("/sessions/{session_id}/messages")
def answer(
    session_id: str,
    payload: AnswerCreate,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    session = db.get_session_for_user(session_id, current_user["id"])
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    # END_RECOMMENDED 只是建议结束，用户仍可以继续回答（执行手册 5.5 软规则）。
    if session["status"] not in ("ACTIVE", "END_RECOMMENDED"):
        raise HTTPException(status_code=409, detail="本次面试已经结束")

    question_limit = min(int(session["question_limit"]), settings.max_turns)
    if int(session["turn_count"]) >= question_limit:
        # 兼容修复前已经达到上限、但仍被标记为 ACTIVE 的会话。
        db.update_session(
            session_id,
            status="COMPLETED",
            ended_at=db.now_iso(),
            current_stage="closing",
        )
        raise HTTPException(status_code=409, detail="已达到预设面试轮次，本次面试已自动结束")

    turn_no = int(session["turn_count"]) + 1
    # 文本情绪辅助分析（执行手册 6.3 进阶）：规则版本地运行，写入消息元数据。
    emotion = analyze_answer(payload.content)
    answer_message = db.add_message(
        session_id, turn_no, "user", payload.content, {"emotion": emotion}
    )
    db.update_session(session_id, turn_count=turn_no, current_stage="interview")

    summary = db.latest_summary(session_id)
    compressed = False
    if turn_no % settings.summary_every_turns == 0:
        summary = summarize(db.list_messages(session_id), summary)
        summary = db.save_summary(session_id, turn_no, summary)
        compressed = True

    fresh_session = db.get_session(session_id) or session
    termination = evaluate(fresh_session)
    if termination["can_end_now"]:
        db.update_session(
            session_id,
            status="COMPLETED",
            ended_at=db.now_iso(),
            current_stage="closing",
        )
        return {
            "message": answer_message,
            "citations": [],
            "memory": {"summary_version": summary.get("version", 0), "compressed": compressed},
            "termination": termination,
        }

    # 执行手册 5.5：主 AI 只能建议结束；接近上限时会话进入 END_RECOMMENDED，仍可继续回答。
    new_status = next_stage(str(fresh_session.get("status", "ACTIVE")), termination)
    if new_status != fresh_session.get("status"):
        db.update_session(session_id, status=new_status)

    config = {
        "target_role": session["target_role"],
        "difficulty": session["difficulty"],
        "resume_text": session["resume_text"],
        "focus_skills": db.loads(session.get("focus_skills_json", "[]"), []),
    }
    all_messages = db.list_messages(session_id)
    candidates = search(payload.content, session["target_role"], session["difficulty"])
    # 执行手册 5.3：检索结果必须保存（题目 ID、来源、相似度、使用时间）。
    db.record_retrievals(session_id, turn_no, candidates)
    question, metadata = next_question(config, summary, all_messages, payload.content, candidates)
    citations = [
        {
            "question_id": item["id"],
            "question": item["question"],
            "skill": item.get("skill", ""),
            "similarity": item.get("score", 0),
            "source": item.get("retrieval_mode", "unknown"),
        }
        for item in candidates[:3]
    ]
    next_message = db.add_message(
        session_id,
        turn_no,
        "assistant",
        question,
        metadata,
        question_id=metadata.get("question_id"),
        citations=citations,
    )
    return {
        "message": next_message,
        "citations": citations,
        "emotion": emotion,
        "memory": {"summary_version": summary.get("version", 0), "compressed": compressed},
        "termination": termination,
    }


@router.get("/question-bank/search")
def question_bank_search(
    query: str,
    role: str = "Python 后端开发",
    difficulty: str = "中等",
) -> dict[str, Any]:
    return {"items": search(query, role, difficulty), "query": query}


@router.post("/question-bank/vectorize")
def vectorize_question_bank() -> dict[str, Any]:
    count = ensure_vector_index()
    return {"indexed": count, "mode": "chroma_vector" if count else "fallback_only"}


@router.post("/sessions/{session_id}/voice/transcribe")
async def voice_transcribe(
    session_id: str,
    file: UploadFile = File(...),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """服务端语音转写（执行手册 4.2）。失败返回 503，前端回退浏览器识别或文字输入。"""
    if db.get_session_for_user(session_id, current_user["id"]) is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    audio_bytes = await file.read()
    audio_format = (file.filename or "audio.wav").rsplit(".", 1)[-1]
    try:
        text = transcribe_audio(audio_bytes, audio_format)
    except VoiceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"text": text, "format": audio_format}


@router.post("/sessions/{session_id}/voice/synthesize")
def voice_synthesize(
    session_id: str,
    payload: AnswerCreate,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """服务端语音合成（执行手册 4.2）。返回可直接播放的音频文件。"""
    if db.get_session_for_user(session_id, current_user["id"]) is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    try:
        path, audio_id = synthesize_speech(payload.content)
    except VoiceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"audio_id": audio_id, "audio_url": f"/api/sessions/{session_id}/voice/audio/{audio_id}"}


@router.get("/sessions/{session_id}/voice/audio/{audio_id}")
def voice_audio(
    session_id: str,
    audio_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> FileResponse:
    if db.get_session_for_user(session_id, current_user["id"]) is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    if not audio_id.replace("_", "").isalnum() or "/" in audio_id or "\\" in audio_id:
        raise HTTPException(status_code=422, detail="非法音频 ID")
    path = settings.export_dir / "voice" / f"{audio_id}.wav"
    if not path.exists():
        raise HTTPException(status_code=404, detail="音频不存在或已过期")
    return FileResponse(path, media_type="audio/wav", filename=f"{audio_id}.wav")


@router.websocket("/ws/sessions/{session_id}")
async def session_voice_socket(websocket: WebSocket, session_id: str) -> None:
    """进阶实时语音通道（执行手册 4.2 WS）。

    客户端连接后先发送 {token, mode}；mode="transcribe" 时发送二进制音频分片，
    最后一帧 {type:"stop"} 触发转写并返回 {type:"transcript", text}；
    mode="speak" 时发送 {type:"speak", text}，返回 {type:"audio_url"}。
    鉴权失败或会话不存在时关闭连接；转写/合成失败返回 {type:"error"}，不断开。
    """
    await websocket.accept()
    try:
        handshake = json.loads(await websocket.receive_text())
        token = str(handshake.get("token", ""))
        user = _user_from_token(token)
        if user is None or db.get_session_for_user(session_id, user["id"]) is None:
            await websocket.close(code=4401, reason="未授权")
            return
        mode = str(handshake.get("mode", "transcribe"))
        await websocket.send_text(json.dumps({"type": "ready", "mode": mode}))

        if mode == "speak":
            while True:
                payload = json.loads(await websocket.receive_text())
                if payload.get("type") == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
                    continue
                if payload.get("type") == "close":
                    break
                if payload.get("type") == "speak":
                    try:
                        _path, audio_id = synthesize_speech(str(payload.get("text", "")))
                        await websocket.send_text(
                            json.dumps(
                                {
                                    "type": "audio_url",
                                    "audio_url": f"/api/sessions/{session_id}/voice/audio/{audio_id}",
                                }
                            )
                        )
                    except VoiceError as exc:
                        await websocket.send_text(json.dumps({"type": "error", "message": str(exc)}))
        else:
            chunks: list[bytes] = []
            while True:
                message = await websocket.receive()
                if "bytes" in message and message["bytes"]:
                    chunks.append(message["bytes"])
                    await websocket.send_text(
                        json.dumps({"type": "progress", "received": sum(len(c) for c in chunks)})
                    )
                    continue
                text_payload = message.get("text")
                if not text_payload:
                    continue
                payload = json.loads(text_payload)
                if payload.get("type") == "close":
                    break
                if payload.get("type") == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
                    continue
                if payload.get("type") == "stop":
                    audio_format = str(payload.get("format", "wav"))
                    try:
                        text = transcribe_audio(b"".join(chunks), audio_format)
                        await websocket.send_text(json.dumps({"type": "transcript", "text": text}))
                    except VoiceError as exc:
                        await websocket.send_text(json.dumps({"type": "error", "message": str(exc)}))
                    chunks = []
        await websocket.close()
    except (WebSocketDisconnect, json.JSONDecodeError):
        pass


def _user_from_token(token: str) -> dict[str, Any] | None:
    from jwt import decode, InvalidTokenError

    try:
        payload = decode(token, settings.jwt_secret_key, algorithms=["HS256"])
        user_id = payload.get("sub")
        return db.get_user_by_id(str(user_id)) if user_id else None
    except InvalidTokenError:
        return None


@router.post("/sessions/{session_id}/end")
def end_session(
    request: Request,
    session_id: str,
    payload: EndRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    session = db.get_session_for_user(session_id, current_user["id"])
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    if session["status"] == "ACTIVE" or session["status"] == "END_RECOMMENDED":
        db.update_session(session_id, status="COMPLETED", ended_at=db.now_iso(), current_stage="closing")
    _audit(request, current_user, "session.end", "session", session_id)
    return {"session_id": session_id, "status": "COMPLETED", "reason": payload.reason}


@router.post("/sessions/{session_id}/report")
def report(
    request: Request,
    session_id: str, current_user: dict[str, Any] = Depends(get_current_user)
) -> dict[str, Any]:
    session = db.get_session_for_user(session_id, current_user["id"])
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    if session["status"] == "ACTIVE" or session["status"] == "END_RECOMMENDED":
        raise HTTPException(status_code=409, detail="请先结束面试再生成报告")
    messages = db.list_messages(session_id)
    report_data = generate_report(messages, session)
    # 执行手册 6.3 进阶：情绪辅助分析与知识图谱随报告一起持久化。
    report_data["emotion"] = emotion_section(messages)
    report_data["knowledge_graph"] = build_graph(
        messages, db.loads(session.get("focus_skills_json", "[]"), [])
    )
    saved = db.save_report(session_id, report_data)
    _audit(request, current_user, "report.generate", "session", session_id)
    return saved


@router.get("/sessions/{session_id}/knowledge-graph")
def knowledge_graph_endpoint(
    session_id: str, current_user: dict[str, Any] = Depends(get_current_user)
) -> dict[str, Any]:
    session = db.get_session_for_user(session_id, current_user["id"])
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return build_graph(
        db.list_messages(session_id), db.loads(session.get("focus_skills_json", "[]"), [])
    )


@router.get("/sessions/{session_id}/report.pdf")
def report_pdf(session_id: str, current_user: dict[str, Any] = Depends(get_current_user)) -> FileResponse:
    session = db.get_session_for_user(session_id, current_user["id"])
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    if session["status"] == "ACTIVE":
        raise HTTPException(status_code=409, detail="请先结束面试再导出报告")
    saved_report = db.latest_report(session_id)
    if saved_report is None:
        raise HTTPException(status_code=404, detail="请先生成评估报告")
    output_path = settings.export_dir / f"{session_id}_report_v{saved_report['version']}.pdf"
    create_report_pdf(output_path, saved_report, session)
    return FileResponse(
        output_path,
        media_type="application/pdf",
        filename=f"ai_interview_report_{session_id}.pdf",
    )


@router.get("/sessions/{session_id}/report.xlsx")
def report_xlsx(session_id: str, current_user: dict[str, Any] = Depends(get_current_user)) -> FileResponse:
    session = db.get_session_for_user(session_id, current_user["id"])
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    if session["status"] == "ACTIVE":
        raise HTTPException(status_code=409, detail="请先结束面试再导出报告")
    saved_report = db.latest_report(session_id)
    if saved_report is None:
        raise HTTPException(status_code=404, detail="请先生成评估报告")
    output_path = settings.export_dir / f"{session_id}_report_v{saved_report['version']}.xlsx"
    try:
        create_report_xlsx(output_path, saved_report, session)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return FileResponse(
        output_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=f"ai_interview_report_{session_id}.xlsx",
    )


@router.get("/reports/{report_id}")
def get_report(report_id: str, current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    with db.connection() as conn:
        row = conn.execute(
            """SELECT reports.* FROM reports JOIN sessions ON sessions.id = reports.session_id
            WHERE reports.id = ? AND sessions.user_id = ?""",
            (report_id, current_user["id"]),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="报告不存在")
    data = db.loads(row["report_json"], {})
    data.update({"id": row["id"], "session_id": row["session_id"], "version": row["version"]})
    return data


@router.get("/history")
def history(current_user: dict[str, Any] = Depends(get_current_user)) -> list[dict[str, Any]]:
    result = []
    for session in db.list_sessions(current_user["id"]):
        item = dict(session)
        item["report"] = db.latest_report(session["id"])
        result.append(item)
    return result


@router.delete("/sessions/{session_id}")
def delete(
    request: Request,
    session_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    if not db.delete_session_for_user(session_id, current_user["id"]):
        raise HTTPException(status_code=404, detail="会话不存在")
    _audit(request, current_user, "session.delete", "session", session_id)
    return {"deleted": True, "session_id": session_id}
