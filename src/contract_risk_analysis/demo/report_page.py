import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

import streamlit as st

from contract_risk_analysis.demo.streamlit_app import build_demo_view_model
from contract_risk_analysis.review.ai_review import review_contract_text
from contract_risk_analysis.review.report_writer import polish_report


RISK_LABELS = {
    "high": "高风险",
    "medium": "中风险",
    "low": "低风险",
}

DIMENSION_LABELS = {
    "legal_enforceability_risk": "法律可执行性风险",
    "financial_exposure_risk": "财务暴露风险",
    "performance_delivery_risk": "履约交付风险",
    "dispute_resolution_risk": "争议处置风险",
    "clause_balance_risk": "条款失衡风险",
}

RISK_ITEM_LEVEL_LABELS = {
    "high": "高",
    "medium": "中",
    "low": "低",
}


def _load_text_for_review() -> tuple[str, str, str | None]:
    contract_id = st.sidebar.text_input("合同编号", value="nda-report-001")
    uploaded_text_file = st.sidebar.file_uploader("上传合同文本 TXT / MD", type=["txt", "md"])
    contract_text = st.sidebar.text_area("合同文本", height=240)
    if uploaded_text_file is not None:
        contract_text = uploaded_text_file.getvalue().decode("utf-8")
        st.sidebar.success("已加载你上传的合同文本")
    if not st.sidebar.button("开始审查"):
        st.stop()
    return contract_id, contract_text, getattr(uploaded_text_file, "name", None)


def _risk_label(risk: str) -> str:
    return RISK_LABELS.get(risk, risk)


def _dimension_label(name: str) -> str:
    return DIMENSION_LABELS.get(name, name)


def _risk_item_level_label(level: str) -> str:
    return RISK_ITEM_LEVEL_LABELS.get(level, level)


def _build_summary(report: dict) -> str:
    summary_reasons = report.get("summary_reasons") or ["当前未识别到高优先级风险原因。"]
    signing_recommendation = report.get("signing_recommendation", "有条件签署")
    return (
        f"该合同整体为**{_risk_label(report['overall_risk'])}**，"
        f"当前签署建议为**{signing_recommendation}**，"
        f"最需要关注的是：{summary_reasons[0]}。"
    )


def _build_dimension_rows(report: dict) -> list[dict[str, str]]:
    scores = report.get("dimension_scores", {})
    summaries = report.get("dimension_summaries", {})
    rows: list[dict[str, str]] = []
    for dimension_name, summary in summaries.items():
        rows.append(
            {
                "维度": _dimension_label(dimension_name),
                "维度英文键": dimension_name,
                "风险等级": _risk_label(report["overall_risk"] if dimension_name not in scores else _score_to_level(scores[dimension_name])),
                "风险说明": summary,
            }
        )
    return rows


def _score_to_level(score: float) -> str:
    if score >= 0.7:
        return "high"
    if score >= 0.35:
        return "medium"
    return "low"


def _build_top_risk_cards(report: dict) -> list[dict[str, object]]:
    cards = []
    for risk in report.get("top_risks", []):
        cards.append(
            {
                "标题": risk["title"],
                "维度": _dimension_label(risk["dimension"]),
                "等级": _risk_item_level_label(risk["risk_level"]),
                "原因": risk["reason"],
                "证据": risk.get("evidence", []),
                "建议": risk["recommendation"],
            }
        )
    return cards


def _build_recommendations(report: dict) -> list[str]:
    recommendations: list[str] = []
    for risk in report.get("top_risks", []):
        recommendation = risk.get("recommendation")
        if recommendation and recommendation not in recommendations:
            recommendations.append(recommendation)
    if recommendations:
        return recommendations
    return ["维持当前条款结构，签署前做一次人工抽样复核即可。"]


def main() -> None:
    st.set_page_config(page_title="合同风险报告页", layout="wide")
    st.title("合同风险中文报告")
    st.caption("面向业务和法务负责人的中文风险摘要页面，支持粘贴文本或上传 txt / md 文件。")

    with st.expander("使用说明", expanded=True):
        st.markdown(
            """
1. 左侧输入合同编号，并粘贴合同文本，或上传 `.txt` / `.md` 文件。
2. 点击“开始审查”后，系统会先调用 AI 生成结构化审查结果。
3. 页面主区域默认展示中文风险摘要、维度风险、关键风险项、整改建议和人工复核项。
4. 如需查看 JSON、证据映射和原始风险分值，可在底部展开“调试信息”。
            """.strip()
        )

    st.sidebar.header("输入区")
    try:
        contract_id, contract_text, source_document = _load_text_for_review()
        review_result = review_contract_text(contract_text, contract_id=contract_id, source_document=source_document)
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        st.sidebar.error(str(error))
        st.stop()

    view_model = build_demo_view_model(review_result)
    report = view_model["report"]
    report_obj = view_model["report_obj"]
    top_risk_cards = _build_top_risk_cards(report)
    recommendations = _build_recommendations(report)
    dimension_rows = _build_dimension_rows(report)
    manual_review_items = report.get("manual_review_items", [])

    # --- 第二层 → 第三层：调用 LLM 润色 ---
    polished = None
    with st.spinner("正在调用 LLM 生成中文风险报告，请稍候…"):
        try:
            polished = polish_report(report_obj)
        except Exception as exc:
            st.warning(f"LLM 润色调用失败（{exc}），页面将展示结构化风险数据。")

    # ── 概览指标 ──
    overview_columns = st.columns(5)
    with overview_columns[0]:
        st.metric("总体风险", _risk_label(report["overall_risk"]))
    with overview_columns[1]:
        st.metric("签署建议", report.get("signing_recommendation", "有条件签署"))
    with overview_columns[2]:
        st.metric("人工复核", "建议复核" if report["requires_manual_review"] else "暂不需要")
    with overview_columns[3]:
        st.metric("重点问题数", str(len(top_risk_cards)))
    with overview_columns[4]:
        st.metric("合同编号", view_model["contract_id"])

    # ── 风险摘要 ──
    st.markdown("## 风险摘要")
    if polished and polished.executive_summary:
        st.markdown(polished.executive_summary)
    else:
        st.markdown(_build_summary(report))

    # ── 签署建议 ──
    if polished and polished.signing_advice:
        st.markdown("## 签署建议")
        st.markdown(polished.signing_advice)

    # ── 维度风险 ──
    st.markdown("## 维度风险")
    for row in dimension_rows:
        st.markdown(f"### {row['维度']}")
        st.markdown(f"- 风险等级：{row['风险等级']}")
        if polished and polished.dimension_insights.get(row["维度英文键"]):
            st.markdown(f"- 分析说明：{polished.dimension_insights[row['维度英文键']]}")
        else:
            st.markdown(f"- 风险说明：{row['风险说明']}")

    # ── 法务问题报告（第三层 LLM 输出） ──
    if polished and polished.issue_reports:
        st.markdown("## 法务问题报告")
        for index, issue in enumerate(polished.issue_reports, start=1):
            st.markdown(f"### 问题 {index}：{issue.title}")
            risk_badge = RISK_LABELS.get(issue.risk_level, issue.risk_level)
            st.markdown(f"**风险等级**：{risk_badge}")
            if issue.problem_analysis:
                st.markdown("#### 问题分析")
                st.markdown(issue.problem_analysis)
            if issue.original_clause:
                st.markdown("#### 原条款")
                st.markdown(f"> {issue.original_clause}")
            if issue.legal_basis:
                st.markdown("#### 法律依据")
                st.markdown(issue.legal_basis)
            if issue.best_practice:
                st.markdown("#### 最佳实践")
                st.markdown(issue.best_practice)
            if issue.suggested_revision:
                st.markdown("#### 建议修改为")
                st.markdown(issue.suggested_revision)
            if issue.revision_reason:
                st.markdown("#### 修改理由")
                st.markdown(issue.revision_reason)
    else:
        st.markdown("## 关键风险项")
        if top_risk_cards:
            for index, card in enumerate(top_risk_cards, start=1):
                st.markdown(f"### 问题 {index}：{card['标题']}")
                st.markdown(f"- 所属维度：{card['维度']}")
                st.markdown(f"- 风险等级：{card['等级']}")
                st.markdown(f"- 原因说明：{card['原因']}")
                for evidence_item in card["证据"]:
                    st.markdown(f"- 证据摘录：{evidence_item}")
                st.markdown(f"- 建议动作：{card['建议']}")
        else:
            st.markdown("当前未识别到需要优先处理的关键风险项。")

    # ── 维度关联风险 ──
    if polished and polished.cross_dimension_notes:
        st.markdown("## 维度关联风险")
        for note in polished.cross_dimension_notes:
            st.markdown(f"- {note}")

    # ── 整改建议 ──
    st.markdown("## 整改建议")
    if polished and polished.action_plan:
        for index, action in enumerate(polished.action_plan, start=1):
            st.markdown(f"{index}. {action}")
    else:
        for index, recommendation in enumerate(recommendations, start=1):
            st.markdown(f"{index}. {recommendation}")

    # ── 人工复核项 ──
    st.markdown("## 人工复核项")
    if manual_review_items:
        for index, item in enumerate(manual_review_items, start=1):
            st.markdown(f"{index}. {item}")
    else:
        st.markdown("当前没有必须升级人工复核的事项。")

    with st.expander("调试信息", expanded=False):
        st.subheader("结构化审查结果")
        st.json(view_model["findings"])
        st.subheader("证据映射")
        st.json(view_model["evidence"])
        st.subheader("触发项")
        st.json(view_model["triggered_findings"])
        st.subheader("风险评估结果")
        st.json(report)
        if polished:
            st.subheader("LLM 润色结果")
            st.json({
                "executive_summary": polished.executive_summary,
                "dimension_insights": polished.dimension_insights,
                "signing_advice": polished.signing_advice,
                "action_plan": polished.action_plan,
                "cross_dimension_notes": polished.cross_dimension_notes,
                "issue_reports": [
                    {
                        "issue_id": ir.issue_id,
                        "title": ir.title,
                        "risk_level": ir.risk_level,
                        "problem_analysis": ir.problem_analysis,
                        "original_clause": ir.original_clause,
                        "legal_basis": ir.legal_basis,
                        "best_practice": ir.best_practice,
                        "suggested_revision": ir.suggested_revision,
                        "revision_reason": ir.revision_reason,
                    }
                    for ir in polished.issue_reports
                ],
            })
        st.subheader("风险报告 JSON")
        st.code(view_model["report_json"], language="json")


if __name__ == "__main__":
    main()
