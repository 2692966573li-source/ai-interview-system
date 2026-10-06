from __future__ import annotations

import re
from typing import Any


TECH_VOCABULARY = (
    "Python", "Java", "JavaScript", "TypeScript", "Vue", "React", "Node",
    "FastAPI", "Flask", "Django", "Spring", "LangChain", "MySQL", "PostgreSQL",
    "SQLite", "Redis", "MongoDB", "Docker", "Kubernetes", "Nginx", "Linux",
    "Kafka", "RabbitMQ", "ChromaDB", "Elasticsearch", "Git", "Prometheus",
    "缓存", "数据库", "索引", "事务", "并发", "性能", "接口", "消息队列",
    "向量检索", "大模型", "微服务", "分布式", "负载均衡", "鉴权", "压测",
    "慢查询", "主从", "分库分表", "线程池", "连接池", "限流", "熔断",
)

CATEGORY_BY_TERM = {
    "Python": "语言", "Java": "语言", "JavaScript": "语言", "TypeScript": "语言",
    "缓存": "存储", "Redis": "存储", "MySQL": "存储", "PostgreSQL": "存储",
    "SQLite": "存储", "MongoDB": "存储", "ChromaDB": "存储", "索引": "存储",
    "事务": "存储", "慢查询": "存储", "分库分表": "存储", "主从": "存储",
    "FastAPI": "框架", "Flask": "框架", "Django": "框架", "Spring": "框架",
    "Vue": "框架", "React": "框架", "Node": "框架", "LangChain": "框架",
    "Docker": "运维", "Kubernetes": "运维", "Nginx": "运维", "Linux": "运维",
    "负载均衡": "运维", "Kafka": "中间件", "RabbitMQ": "中间件",
    "消息队列": "中间件", "Elasticsearch": "中间件",
    "向量检索": "AI", "大模型": "AI",
    "并发": "架构", "性能": "架构", "微服务": "架构", "分布式": "架构",
    "限流": "架构", "熔断": "架构", "线程池": "架构", "连接池": "架构",
    "接口": "工程", "鉴权": "工程", "压测": "工程",
}


def _extract_terms(text: str) -> list[str]:
    found: list[str] = []
    for term in TECH_VOCABULARY:
        if term.lower() in text.lower():
            found.append(term)
    found.extend(re.findall(r"\b[A-Za-z][A-Za-z0-9+#.-]{1,24}\b", text))
    normalized = []
    seen: set[str] = set()
    for term in found:
        key = term.lower()
        if key not in seen and len(term) >= 2:
            seen.add(key)
            normalized.append(term)
    return normalized[:10]


def build_graph(messages: list[dict[str, Any]], focus_skills: list[str] | None = None) -> dict[str, Any]:
    """从问答消息构建技能知识图谱：节点=被提及的技能，边=同一回答内的共现。"""
    focus = {str(item).strip() for item in (focus_skills or []) if str(item).strip()}
    mentions: dict[str, dict[str, Any]] = {}
    answer_terms: dict[int, list[str]] = {}

    for item in messages:
        if item.get("role") != "user" or int(item.get("turn_no", 0)) == 0:
            continue
        turn = int(item.get("turn_no", 0))
        terms = _extract_terms(str(item.get("content", "")))
        answer_terms[turn] = terms
        for term in terms:
            node = mentions.setdefault(
                term, {"id": term, "label": term, "mentions": 0, "turns": [], "category": ""}
            )
            node["mentions"] += 1
            if turn not in node["turns"]:
                node["turns"].append(turn)

    for term, node in mentions.items():
        node["category"] = CATEGORY_BY_TERM.get(term, "其他")
        if term in focus:
            node["category"] = "重点"

    edges: dict[tuple[str, str], int] = {}
    for terms in answer_terms.values():
        for i, source in enumerate(terms):
            for target in terms[i + 1 :]:
                key = tuple(sorted((source, target)))
                edges[key] = edges.get(key, 0) + 1

    nodes = sorted(mentions.values(), key=lambda node: -node["mentions"])[:14]
    keep = {node["id"] for node in nodes}
    edge_list = [
        {"source": source, "target": target, "weight": weight}
        for (source, target), weight in edges.items()
        if source in keep and target in keep
    ]
    edge_list.sort(key=lambda edge: -edge["weight"])
    covered_focus = sorted(focus & keep)
    missing_focus = sorted(focus - keep)
    return {
        "nodes": nodes,
        "edges": edge_list[:24],
        "covered_focus": covered_focus,
        "missing_focus": missing_focus,
        "answer_count": len(answer_terms),
    }


def build_graph_v2(
    messages: list[dict[str, Any]],
    focus_skills: list[str] | None = None,
    target_role: str = "",
    retrievals: list[dict[str, Any]] | None = None,
    question_lookup: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """进阶知识图谱（赛题三进阶 4）：岗位—技能—面试题三层多关系网络。

    在技能共现图基础上新增：
    - 岗位中心节点，向技能连"要求"边；
    - 面试题节点（来自题库检索记录），向技能连"考察"边。
    仍以 JSON 结构返回（赛题基础要求），后续可平滑迁移 Neo4j。
    """
    base = build_graph(messages, focus_skills)
    skill_ids = {node["id"] for node in base["nodes"]}
    # 技能节点统一补 type 字段，与岗位/面试题节点结构一致（前端按 type 着色）。
    for node in base["nodes"]:
        node["type"] = "技能"
    lookup = question_lookup or {}

    role_label = str(target_role or "").strip() or "目标岗位"
    role_node = {
        "id": "role::center",
        "label": role_label,
        "mentions": 1,
        "turns": [],
        "category": "岗位",
        "type": "岗位",
    }
    role_edges = [
        {"source": "role::center", "target": node["id"], "relation": "要求", "weight": 2}
        for node in base["nodes"]
    ]

    question_nodes: dict[str, dict[str, Any]] = {}
    question_edges: list[dict[str, Any]] = []
    for record in retrievals or []:
        question_id = str(record.get("question_id", "")).strip()
        if not question_id:
            continue
        node = question_nodes.setdefault(
            question_id,
            {
                "id": f"q::{question_id}",
                "label": str(lookup.get(question_id, {}).get("question", question_id))[:24],
                "mentions": 0,
                "turns": [],
                "category": "面试题",
                "type": "面试题",
                "similarity": float(record.get("similarity", 0) or 0),
            },
        )
        node["mentions"] += 1
        turn = int(record.get("turn_no", 0))
        if turn and turn not in node["turns"]:
            node["turns"].append(turn)
        skill = str(lookup.get(question_id, {}).get("skill", "")).strip()
        if skill and skill in skill_ids:
            edge = {
                "source": f"q::{question_id}",
                "target": skill,
                "relation": "考察",
                "weight": 1,
            }
            if edge not in question_edges:
                question_edges.append(edge)

    return {
        **base,
        "nodes": [role_node, *base["nodes"], *sorted(question_nodes.values(), key=lambda n: -n["similarity"])[:8]],
        "edges": [*role_edges, *base["edges"], *question_edges][:40],
        "graph_version": 2,
    }
