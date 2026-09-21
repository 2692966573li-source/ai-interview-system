from __future__ import annotations

import logging
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import db
from .config import settings
from .routes.api import router


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
db.init_db()
app = FastAPI(title=settings.app_name, version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)


def _error_body(code: str, message: str, request_id: str) -> dict[str, dict[str, str]]:
    return {"error": {"code": code, "message": message, "request_id": request_id}}


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """统一错误格式（执行手册 4.3）：{error: {code, message, request_id}}。"""
    request_id = getattr(request.state, "request_id", None) or f"req_{uuid4().hex[:12]}"
    code_names = {
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        409: "CONFLICT",
        413: "PAYLOAD_TOO_LARGE",
        415: "UNSUPPORTED_MEDIA_TYPE",
        422: "VALIDATION_ERROR",
        503: "SERVICE_UNAVAILABLE",
    }
    detail = exc.detail if isinstance(exc.detail, str) else "请求失败"
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_body(
            code_names.get(exc.status_code, f"HTTP_{exc.status_code}"),
            detail,
            request_id,
        ),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None) or f"req_{uuid4().hex[:12]}"
    return JSONResponse(
        status_code=422,
        content=_error_body("VALIDATION_ERROR", "请求参数不合法，请检查后重试", request_id),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None) or f"req_{uuid4().hex[:12]}"
    logging.getLogger("ai_interview").exception("unhandled error request_id=%s", request_id)
    return JSONResponse(
        status_code=500,
        content=_error_body("INTERNAL_ERROR", "服务器内部错误，请稍后重试", request_id),
    )


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request.state.request_id = f"req_{uuid4().hex[:12]}"
    return await call_next(request)


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "AI 模拟面试系统后端已启动", "docs": "/docs"}
