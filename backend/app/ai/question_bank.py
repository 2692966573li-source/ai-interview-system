from __future__ import annotations

import hashlib
import re
from typing import Any

from langchain_openai import OpenAIEmbeddings

from ..config import settings


SEED_QUESTIONS = [
    {
        "id": "python-001",
        "question": "Python 中可变对象和不可变对象有什么区别？在实际项目中踩过什么坑？",
        "role": "Python 后端开发",
        "skill": "Python",
        "difficulty": "基础",
        "tags": ["Python", "可变对象", "基础"],
        "followups": ["函数默认参数为什么不建议使用可变对象？"],
        "rubric": ["解释对象可变性", "给出实际例子"],
    },
    {
        "id": "fastapi-001",
        "question": "FastAPI 的依赖注入解决了什么问题？你在哪些场景使用过？",
        "role": "Python 后端开发",
        "skill": "FastAPI",
        "difficulty": "中等",
        "tags": ["FastAPI", "接口", "依赖注入"],
        "followups": ["如何在依赖中处理数据库会话和鉴权？"],
        "rubric": ["理解依赖复用", "能结合项目说明"],
    },
    {
        "id": "database-001",
        "question": "你如何判断一个数据库索引是否真正提升了查询性能？",
        "role": "Python 后端开发",
        "skill": "数据库",
        "difficulty": "中等",
        "tags": ["数据库", "索引", "性能"],
        "followups": ["索引可能在哪些情况下反而拖慢系统？"],
        "rubric": ["会使用执行计划", "考虑写入成本和选择性"],
    },
    {
        "id": "redis-001",
        "question": "缓存击穿、缓存穿透和缓存雪崩有什么区别？",
        "role": "Python 后端开发",
        "skill": "Redis",
        "difficulty": "中等",
        "tags": ["Redis", "缓存", "高并发"],
        "followups": ["如果热点 Key 突然失效，你会怎样保护数据库？"],
        "rubric": ["区分三类问题", "给出工程解决方案"],
    },
    {
        "id": "rag-001",
        "question": "RAG 系统中如何选择文本切分大小和重叠长度？",
        "role": "AI 应用开发",
        "skill": "RAG",
        "difficulty": "中等",
        "tags": ["RAG", "向量检索", "Chunk"],
        "followups": ["如何评价召回结果是否相关？"],
        "rubric": ["解释上下文完整性", "考虑 Token 成本和召回率"],
    },
    {
        "id": "system-001",
        "question": "如果接口流量突然增长十倍，你会先观察哪些指标并如何定位瓶颈？",
        "role": "后端开发",
        "skill": "系统设计",
        "difficulty": "困难",
        "tags": ["并发", "性能", "系统设计"],
        "followups": ["怎样区分应用、数据库和网络瓶颈？"],
        "rubric": ["有监控思路", "能够分层定位"],
    },
    {
        "id": "python-002",
        "question": "GIL 对 Python 多线程有什么影响？你在项目中如何利用多进程或多线程？",
        "role": "Python 后端开发",
        "skill": "Python",
        "difficulty": "中等",
        "tags": ["Python", "GIL", "并发"],
        "followups": ["IO 密集和 CPU 密集任务分别怎么选并发模型？"],
        "rubric": ["理解 GIL 边界", "能结合场景选择方案"],
    },
    {
        "id": "python-003",
        "question": "装饰器在什么场景下会引入隐藏问题？你如何调试一个行为异常的装饰器？",
        "role": "Python 后端开发",
        "skill": "Python",
        "difficulty": "困难",
        "tags": ["Python", "装饰器", "调试"],
        "followups": ["functools.wraps 解决了什么问题？"],
        "rubric": ["了解元信息丢失", "有实际排查经历"],
    },
    {
        "id": "fastapi-002",
        "question": "FastAPI 的 async 路由中执行了阻塞调用会发生什么？你如何处理？",
        "role": "Python 后端开发",
        "skill": "FastAPI",
        "difficulty": "中等",
        "tags": ["FastAPI", "异步", "阻塞"],
        "followups": ["run_in_executor 和 def 路由的区别是什么？"],
        "rubric": ["理解事件循环阻塞", "给出解决方案"],
    },
    {
        "id": "fastapi-003",
        "question": "Pydantic 校验失败时你如何返回统一的错误结构？为什么这样设计？",
        "role": "Python 后端开发",
        "skill": "FastAPI",
        "difficulty": "基础",
        "tags": ["FastAPI", "Pydantic", "错误处理"],
        "followups": ["全局异常处理器要注意哪些坑？"],
        "rubric": ["理解校验层职责", "有统一错误意识"],
    },
    {
        "id": "database-002",
        "question": "什么是慢查询？你会如何一步步排查一条执行很慢的 SQL？",
        "role": "Python 后端开发",
        "skill": "数据库",
        "difficulty": "基础",
        "tags": ["数据库", "慢查询", "SQL"],
        "followups": ["EXPLAIN 的哪些输出项最值得关注？"],
        "rubric": ["有排查步骤", "知道执行计划"],
    },
    {
        "id": "database-003",
        "question": "数据库事务的隔离级别有哪些？你们项目用的哪一种，为什么？",
        "role": "Python 后端开发",
        "skill": "数据库",
        "difficulty": "困难",
        "tags": ["数据库", "事务", "隔离级别"],
        "followups": ["幻读在什么隔离级别下仍可能出现？"],
        "rubric": ["列举四种隔离级别", "结合业务说明取舍"],
    },
    {
        "id": "redis-002",
        "question": "你如何设计缓存 key 和过期时间来避免大量 key 同时失效？",
        "role": "Python 后端开发",
        "skill": "Redis",
        "difficulty": "中等",
        "tags": ["Redis", "缓存", "过期策略"],
        "followups": ["随机化过期时间能完全解决雪崩吗？"],
        "rubric": ["有 key 命名规范", "理解雪崩与抖动"],
    },
    {
        "id": "redis-003",
        "question": "Redis 的持久化方式有哪些？你会如何根据业务选择？",
        "role": "Python 后端开发",
        "skill": "Redis",
        "difficulty": "困难",
        "tags": ["Redis", "持久化", "RDB", "AOF"],
        "followups": ["AOF 重写期间写入请求会怎样处理？"],
        "rubric": ["区分 RDB/AOF", "说明恢复速度与数据安全取舍"],
    },
    {
        "id": "architecture-001",
        "question": "你的项目里接口幂等性是如何保证的？举一个防重复提交的例子。",
        "role": "后端开发",
        "skill": "系统设计",
        "difficulty": "中等",
        "tags": ["幂等", "接口", "系统设计"],
        "followups": ["幂等键放请求头还是业务参数里更合适？"],
        "rubric": ["理解幂等场景", "给出落地机制"],
    },
    {
        "id": "architecture-002",
        "question": "消息队列在你们系统里解决了什么问题？消费失败怎么处理？",
        "role": "后端开发",
        "skill": "消息队列",
        "difficulty": "中等",
        "tags": ["消息队列", "异步", "可靠性"],
        "followups": ["如何保证消息不丢？重试太多次怎么办？"],
        "rubric": ["说明解耦/削峰", "有死信与重试设计"],
    },
    {
        "id": "rag-002",
        "question": "向量检索结果不理想时，你会从哪些方向优化召回质量？",
        "role": "AI 应用开发",
        "skill": "RAG",
        "difficulty": "困难",
        "tags": ["RAG", "召回", "优化"],
        "followups": ["混合检索（关键词+向量）适合什么场景？"],
        "rubric": ["切分与嵌入模型调优", "了解重排序"],
    },
    {
        "id": "rag-003",
        "question": "大模型回答幻觉是什么？你在应用层如何降低幻觉风险？",
        "role": "AI 应用开发",
        "skill": "大模型应用",
        "difficulty": "中等",
        "tags": ["大模型", "幻觉", "提示词"],
        "followups": ["如何设计让模型只根据资料回答？"],
        "rubric": ["理解幻觉成因", "有提示词或引用约束实践"],
    },
    {
        "id": "llm-001",
        "question": "你如何评估一个提示词（Prompt）改得好不好？有量化的办法吗？",
        "role": "AI 应用开发",
        "skill": "提示词工程",
        "difficulty": "中等",
        "tags": ["提示词", "评估", "大模型"],
        "followups": ["小规模评测集要包含哪些样本类型？"],
        "rubric": ["有评测意识", "能设计对比实验"],
    },
    {
        "id": "llm-002",
        "question": "模型响应慢或超时时，你会从架构上做什么降级和兜底？",
        "role": "AI 应用开发",
        "skill": "大模型应用",
        "difficulty": "困难",
        "tags": ["大模型", "降级", "超时"],
        "followups": ["降级到规则后如何让用户感知差异最小？"],
        "rubric": ["有降级预案", "考虑体验一致性"],
    },
    {
        "id": "frontend-001",
        "question": "Vue 的响应式原理是什么？ref 和 reactive 你如何选择？",
        "role": "前端开发",
        "skill": "Vue",
        "difficulty": "中等",
        "tags": ["Vue", "响应式", "ref", "reactive"],
        "followups": ["为什么解构 reactive 对象会丢失响应性？"],
        "rubric": ["理解 Proxy 依赖收集", "有实际选择经验"],
    },
    {
        "id": "frontend-002",
        "question": "首屏加载很慢，你会从哪些方向定位和优化？",
        "role": "前端开发",
        "skill": "性能优化",
        "difficulty": "中等",
        "tags": ["前端", "性能", "首屏"],
        "followups": ["路由懒加载和代码分割有什么区别？"],
        "rubric": ["会用性能面板", "列出加载链路优化手段"],
    },
    {
        "id": "frontend-003",
        "question": "跨域是怎么产生的？你们项目里 CORS 是在前端还是后端解决的？",
        "role": "前端开发",
        "skill": "浏览器",
        "difficulty": "基础",
        "tags": ["前端", "跨域", "CORS"],
        "followups": ["带 cookie 的跨域请求要注意什么？"],
        "rubric": ["理解同源策略", "知道预检请求"],
    },
    {
        "id": "testing-001",
        "question": "你如何为一个接口写自动化测试？会覆盖哪些用例类型？",
        "role": "测试开发",
        "skill": "测试",
        "difficulty": "基础",
        "tags": ["测试", "接口", "自动化"],
        "followups": ["正常、边界、异常用例你会怎么分配精力？"],
        "rubric": ["有用例分层", "覆盖异常路径"],
    },
    {
        "id": "testing-002",
        "question": "线上出现偶现 bug 但测试环境无法复现，你的排查思路是什么？",
        "role": "测试开发",
        "skill": "测试",
        "difficulty": "困难",
        "tags": ["测试", "线上问题", "排查"],
        "followups": ["日志埋点应该提前设计哪些字段？"],
        "rubric": ["有日志与监控意识", "考虑数据与环境差异"],
    },
    {
        "id": "devops-001",
        "question": "你的项目是如何部署的？发布出问题后如何快速回滚？",
        "role": "运维开发",
        "skill": "部署",
        "difficulty": "基础",
        "tags": ["部署", "发布", "回滚"],
        "followups": ["蓝绿发布和滚动发布你倾向哪种？"],
        "rubric": ["有发布流程", "有回滚预案"],
    },
    {
        "id": "devops-002",
        "question": "服务内存持续上涨最终 OOM，你会如何定位泄漏来源？",
        "role": "运维开发",
        "skill": "稳定性",
        "difficulty": "困难",
        "tags": ["内存", "泄漏", "稳定性"],
        "followups": ["容器内存限制和应用内存的关系怎么理解？"],
        "rubric": ["会看监控曲线", "有 dump/剖析工具经验"],
    },
    {
        "id": "security-001",
        "question": "SQL 注入和 XSS 的原理有什么不同？你在项目里怎么防？",
        "role": "后端开发",
        "skill": "安全",
        "difficulty": "基础",
        "tags": ["安全", "SQL注入", "XSS"],
        "followups": ["参数化查询为什么能防注入？"],
        "rubric": ["区分两类攻击面", "给出具体防护手段"],
    },
    {
        "id": "security-002",
        "question": "用户密码在数据库里应该怎么存？为什么不能明文或简单 MD5？",
        "role": "后端开发",
        "skill": "安全",
        "difficulty": "基础",
        "tags": ["安全", "密码", "哈希"],
        "followups": ["加盐和慢哈希各自解决什么问题？"],
        "rubric": ["知道彩虹表", "能说出 PBKDF2/bcrypt"],
    },
]


def seed(conn: Any) -> None:
    for item in SEED_QUESTIONS:
        conn.execute(
            """
            INSERT OR IGNORE INTO question_bank
            (id, question, role, skill, difficulty, question_type, tags_json,
             followups_json, rubric_json, reference_answer, source, created_at)
            VALUES (?, ?, ?, ?, ?, 'technical', ?, ?, ?, '', 'seed', datetime('now'))
            """,
            (
                item["id"],
                item["question"],
                item["role"],
                item["skill"],
                item["difficulty"],
                __import__("json").dumps(item["tags"], ensure_ascii=False),
                __import__("json").dumps(item["followups"], ensure_ascii=False),
                __import__("json").dumps(item["rubric"], ensure_ascii=False),
            ),
        )


def _tokens(text: str) -> set[str]:
    latin = re.findall(r"[a-zA-Z][a-zA-Z0-9+#.-]*", text.lower())
    chinese = [
        word
        for word in (
            "数据库",
            "缓存",
            "接口",
            "性能",
            "并发",
            "索引",
            "事务",
            "向量检索",
            "系统设计",
            "依赖注入",
            "项目",
            "测试",
        )
        if word in text
    ]
    return set(latin + chinese)


def lexical_search(answer: str, role: str, difficulty: str, limit: int = 4) -> list[dict[str, Any]]:
    from .. import db

    query_tokens = _tokens(answer + " " + role)
    with db.connection() as conn:
        seed(conn)
        rows = conn.execute("SELECT * FROM question_bank").fetchall()
    candidates = []
    for row in rows:
        tags = db.loads(row["tags_json"], [])
        document = f"{row['question']} {row['role']} {row['skill']} {' '.join(tags)}"
        overlap = len(query_tokens & _tokens(document))
        role_bonus = 2 if row["role"] in role or role in row["role"] else 0
        difficulty_bonus = 1 if row["difficulty"] == difficulty else 0
        candidates.append(
            {
                "id": row["id"],
                "question": row["question"],
                "skill": row["skill"],
                "difficulty": row["difficulty"],
                "followups": db.loads(row["followups_json"], []),
                "rubric": db.loads(row["rubric_json"], []),
                "score": overlap + role_bonus + difficulty_bonus,
                "retrieval_mode": "metadata_and_keyword",
            }
        )
    return sorted(candidates, key=lambda item: item["score"], reverse=True)[:limit]


def _embedding_client() -> OpenAIEmbeddings | None:
    if not settings.dashscope_api_key:
        return None
    return OpenAIEmbeddings(
        model="text-embedding-v4",
        api_key=settings.dashscope_api_key,
        base_url=settings.bailian_base_url,
        check_embedding_ctx_length=False,
    )


def ensure_vector_index() -> int:
    try:
        import chromadb
    except ImportError:
        return 0
    embeddings = _embedding_client()
    if embeddings is None:
        return 0
    client = chromadb.PersistentClient(path=str(settings.chroma_dir))
    collection = client.get_or_create_collection("interview_questions")
    existing = collection.count()
    if existing >= len(SEED_QUESTIONS):
        return existing
    texts = [
        f"{item['role']} {item['difficulty']} {item['skill']} {' '.join(item['tags'])} {item['question']}"
        for item in SEED_QUESTIONS
    ]
    vectors = embeddings.embed_documents(texts)
    collection.upsert(
        ids=[item["id"] for item in SEED_QUESTIONS],
        documents=texts,
        embeddings=vectors,
        metadatas=[
            {"role": item["role"], "skill": item["skill"], "difficulty": item["difficulty"]}
            for item in SEED_QUESTIONS
        ],
    )
    return collection.count()


def vector_search(answer: str, limit: int = 4) -> list[dict[str, Any]]:
    try:
        import chromadb
    except ImportError:
        return []
    embeddings = _embedding_client()
    if embeddings is None:
        return []
    try:
        ensure_vector_index()
        client = chromadb.PersistentClient(path=str(settings.chroma_dir))
        collection = client.get_collection("interview_questions")
        result = collection.query(
            query_embeddings=[embeddings.embed_query(answer)],
            n_results=min(limit, collection.count()),
            include=["metadatas", "documents", "distances"],
        )
        output = []
        for question_id, document, metadata, distance in zip(
            result["ids"][0],
            result["documents"][0],
            result["metadatas"][0],
            result["distances"][0],
        ):
            item = next(seed_item for seed_item in SEED_QUESTIONS if seed_item["id"] == question_id)
            output.append(
                {
                    **item,
                    "score": round(1 / (1 + float(distance)), 4),
                    "retrieval_mode": "chroma_vector",
                    "document_hash": hashlib.sha256(document.encode()).hexdigest()[:12],
                    "metadata": metadata,
                }
            )
        return output
    except Exception:
        return []


def search(answer: str, role: str, difficulty: str, limit: int = 4) -> list[dict[str, Any]]:
    return vector_search(answer, limit) or lexical_search(answer, role, difficulty, limit)
