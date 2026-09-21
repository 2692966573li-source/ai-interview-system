from __future__ import annotations

from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


PAGE_GREEN = colors.HexColor("#173f35")
MUTED = colors.HexColor("#6f8479")
LINE = colors.HexColor("#dbe6df")
PALE_GREEN = colors.HexColor("#edf5ef")


def _register_cjk_font() -> str:
    """优先嵌入 Windows 宋体，Linux 等环境再退回 ReportLab CID 字体。"""
    windows_font = Path(r"C:\Windows\Fonts\simsun.ttc")
    if windows_font.exists():
        font_name = "SimSunLocal"
        if font_name not in pdfmetrics.getRegisteredFontNames():
            try:
                pdfmetrics.registerFont(TTFont(font_name, str(windows_font), subfontIndex=0))
                return font_name
            except Exception:
                pass
    font_name = "STSong-Light"
    if font_name not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(UnicodeCIDFont(font_name))
    return font_name


def _text(value: Any) -> str:
    return escape(str(value or "")).replace("\n", "<br/>")


def _paragraph(value: Any, style: ParagraphStyle) -> Paragraph:
    return Paragraph(_text(value), style)


def create_report_pdf(
    output_path: Path,
    report: dict[str, Any],
    session: dict[str, Any],
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    font_name = _register_cjk_font()
    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "ReportTitle",
        parent=styles["Title"],
        fontName=font_name,
        fontSize=21,
        leading=28,
        textColor=PAGE_GREEN,
        alignment=TA_LEFT,
        spaceAfter=5 * mm,
    )
    subtitle = ParagraphStyle(
        "ReportSubtitle",
        parent=styles["Normal"],
        fontName=font_name,
        fontSize=9,
        leading=14,
        textColor=MUTED,
        spaceAfter=7 * mm,
    )
    section = ParagraphStyle(
        "Section",
        parent=styles["Heading2"],
        fontName=font_name,
        fontSize=12,
        leading=17,
        textColor=PAGE_GREEN,
        spaceBefore=4 * mm,
        spaceAfter=2 * mm,
    )
    body = ParagraphStyle(
        "Body",
        parent=styles["BodyText"],
        fontName=font_name,
        fontSize=9.5,
        leading=16,
        textColor=colors.HexColor("#365146"),
        spaceAfter=2 * mm,
    )
    small = ParagraphStyle(
        "Small",
        parent=body,
        fontSize=8,
        leading=12,
        textColor=MUTED,
    )
    score_style = ParagraphStyle(
        "Score",
        parent=body,
        fontName=font_name,
        fontSize=27,
        leading=31,
        textColor=PAGE_GREEN,
        alignment=TA_CENTER,
    )
    center_small = ParagraphStyle(
        "CenterSmall",
        parent=small,
        alignment=TA_CENTER,
    )

    def footer(canvas: Any, doc: Any) -> None:
        canvas.saveState()
        canvas.setStrokeColor(LINE)
        canvas.line(18 * mm, 14 * mm, 192 * mm, 14 * mm)
        canvas.setFont(font_name, 7)
        canvas.setFillColor(MUTED)
        canvas.drawString(18 * mm, 9 * mm, "AI 模拟面试系统 · 证据化评估报告")
        canvas.drawRightString(192 * mm, 9 * mm, f"第 {doc.page} 页")
        canvas.restoreState()

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=17 * mm,
        bottomMargin=20 * mm,
        title=f"{session.get('target_role', '模拟面试')}评估报告",
        author="AI 模拟面试系统",
    )
    story: list[Any] = []
    target_role = session.get("target_role", "未填写岗位")
    difficulty = session.get("difficulty", "未填写")
    story.append(_paragraph("AI 模拟面试评估报告", title))
    story.append(
        _paragraph(
            f"目标岗位：{target_role}　｜　难度：{difficulty}　｜　回答数量：{report.get('meta', {}).get('answer_count', 0)}",
            subtitle,
        )
    )

    overall = report.get("overall_score", 0)
    score_table = Table(
        [[_paragraph("综合评分", center_small), _paragraph(str(overall), score_style), _paragraph("/ 100", center_small)]],
        colWidths=[45 * mm, 35 * mm, 25 * mm],
        rowHeights=[25 * mm],
    )
    score_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), PALE_GREEN),
                ("BOX", (0, 0), (-1, -1), 0.6, LINE),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.append(score_table)
    story.append(Spacer(1, 5 * mm))

    dimension_rows = [[_paragraph("评估维度", section), _paragraph("分数", section), _paragraph("主要证据", section)]]
    dimension_labels = {
        "professional": "专业能力",
        "logic": "逻辑结构",
        "communication": "表达沟通",
    }
    for key in ("professional", "logic", "communication"):
        item = report.get("dimensions", {}).get(key, {})
        evidence = item.get("evidence", []) or []
        evidence_text = "；".join(
            f"第 {ev.get('turn')} 轮：{ev.get('quote', '')}" for ev in evidence[:2]
        ) or "暂无可引用证据"
        dimension_rows.append(
            [
                _paragraph(dimension_labels[key], body),
                _paragraph(f"{item.get('score', 0)} / 100", body),
                _paragraph(evidence_text, small),
            ]
        )
    dimension_table = Table(dimension_rows, colWidths=[31 * mm, 27 * mm, 117 * mm], repeatRows=1)
    dimension_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), PALE_GREEN),
                ("GRID", (0, 0), (-1, -1), 0.45, LINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    story.append(dimension_table)

    for title_text, key in (("表现亮点", "highlights"), ("还可以更好", "problems"), ("改进建议", "suggestions")):
        section_story = [_paragraph(title_text, section)]
        values = report.get(key, []) or ["暂无内容"]
        for value in values:
            section_story.append(_paragraph(f"- {value}", body))
        story.append(KeepTogether(section_story))

    emotion = report.get("emotion") or {}
    if emotion.get("timeline"):
        story.append(_paragraph("情绪辅助分析（文本信号，仅供参考）", section))
        summary_text = (
            f"平均情绪分 {emotion.get('average_score', 0)} / 100，"
            f"主导状态“{emotion.get('dominant_label', '')}”，趋势：{emotion.get('trend', '')}。"
        )
        story.append(_paragraph(summary_text, body))
        emotion_rows = [[_paragraph("轮次", small), _paragraph("状态", small), _paragraph("分数", small)]]
        for item in emotion.get("timeline", [])[:10]:
            emotion_rows.append(
                [
                    _paragraph(f"第 {item.get('turn')} 轮", small),
                    _paragraph(str(item.get("label", "")), small),
                    _paragraph(str(item.get("score", 0)), small),
                ]
            )
        emotion_table = Table(emotion_rows, colWidths=[40 * mm, 50 * mm, 30 * mm])
        emotion_table.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.45, LINE),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.append(emotion_table)
        story.append(
            _paragraph(
                "说明：情绪分由回答文本中的确定性信号（自信表述、不确定词、量化数据等）规则计算，"
                "不能替代真实心理评估。",
                small,
            )
        )

    story.append(_paragraph("报告说明", section))
    story.append(
        _paragraph(
            "本报告由 AI 根据本次面试中的真实问答生成。分数用于练习复盘，不等同于招聘决定；证据轮次可回到系统中的完整对话核对。",
            small,
        )
    )
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return output_path
