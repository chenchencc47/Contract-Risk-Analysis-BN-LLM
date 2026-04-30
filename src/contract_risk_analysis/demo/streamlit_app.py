import copy
import json
import sys
from dataclasses import asdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

import streamlit as st

from contract_risk_analysis.bn.inference import assess_risk
from contract_risk_analysis.bn.network_schema import load_network_config
from contract_risk_analysis.domain.review_schema import ReviewFinding, ReviewResult, RiskEvidence
from contract_risk_analysis.pipeline.build_evidence import build_evidence
from contract_risk_analysis.review.ai_review import review_contract_text
from contract_risk_analysis.review.report_writer import polish_report


DEFAULT_SAMPLE_PATH = PROJECT_ROOT / "sample_data" / "review_result_examples" / "nda_example.json"

from contract_risk_analysis.constants import DIMENSION_LABELS, RISK_LABELS


def apply_overrides(view_model: dict, node_overrides: dict[str, str], cpt_overrides: dict[str, float]) -> dict:
    updated = copy.deepcopy(view_model)

    for node_name, state in node_overrides.items():
        if state:
            updated["evidence"][node_name] = state

    for override_key, value in cpt_overrides.items():
        cpt_name, state_name = override_key.split(".", 1)
        updated["network_config"]["cpts"][cpt_name][state_name] = value

    return updated


def build_demo_view_model(
    review_result: ReviewResult, allowed_priorities: set[str] | None = None
) -> dict:
    evidence = build_evidence(review_result, allowed_priorities=allowed_priorities)
    network_config = load_network_config()
    report = assess_risk(evidence)
    return {
        "contract_id": review_result.contract_id,
        "findings": [asdict(finding) for finding in review_result.findings],
        "evidence": evidence.node_states,
        "node_observations": [
            asdict(observation) for observation in evidence.node_observations
        ],
        "triggered_findings": evidence.triggered_findings,
        "supporting_findings_by_node": evidence.supporting_findings_by_node,
        "supporting_evidence_by_node": evidence.supporting_evidence_by_node,
        "network_config": copy.deepcopy(network_config),
        "report": asdict(report),
        "report_obj": report,
        "report_json": json.dumps(asdict(report), ensure_ascii=False, indent=2),
    }


def _review_result_from_json_text(payload_text: str) -> ReviewResult:
    payload = json.loads(payload_text)
    findings_payload = payload.get("findings")
    if not isinstance(findings_payload, list):
        raise ValueError("上传的 JSON 必须包含 findings 数组；请上传结构化审查结果 JSON，而不是风险报告 JSON。")
    findings = [ReviewFinding(**item) for item in findings_payload]
    return ReviewResult(
        contract_id=payload["contract_id"],
        findings=findings,
        review_type=payload.get("review_type"),
        source_document=payload.get("source_document"),
    )


def _recalculate_report(view_model: dict) -> dict:
    evidence = RiskEvidence(
        contract_id=view_model["contract_id"],
        node_states=view_model["evidence"],
        triggered_findings=view_model["triggered_findings"],
        node_observations=[],
        supporting_findings_by_node=view_model.get("supporting_findings_by_node", {}),
        supporting_evidence_by_node=view_model.get("supporting_evidence_by_node", {}),
    )
    report = assess_risk(evidence, network_config=view_model["network_config"])
    view_model["report"] = asdict(report)
    view_model["report_obj"] = report
    view_model["report_json"] = json.dumps(asdict(report), ensure_ascii=False, indent=2)
    return view_model


def _load_review_result_from_sidebar() -> ReviewResult:
    input_mode = st.sidebar.radio("输入模式", ["结构化审查结果 JSON", "合同文本 AI 审查"])
    if input_mode == "结构化审查结果 JSON":
        uploaded_file = st.sidebar.file_uploader("上传审查结果 JSON", type=["json"])
        if uploaded_file is not None:
            payload_text = uploaded_file.getvalue().decode("utf-8")
            st.sidebar.success("已加载你上传的 JSON 文件")
        else:
            payload_text = DEFAULT_SAMPLE_PATH.read_text(encoding="utf-8")
            st.sidebar.info(f"当前使用默认样例：{DEFAULT_SAMPLE_PATH.name}")
        return _review_result_from_json_text(payload_text)

    contract_id = st.sidebar.text_input("合同编号", value="nda-text-001")
    uploaded_text_file = st.sidebar.file_uploader("上传合同文本 TXT / MD", type=["txt", "md"])
    contract_text = st.sidebar.text_area("合同文本", height=220)
    if uploaded_text_file is not None:
        contract_text = uploaded_text_file.getvalue().decode("utf-8")
        st.sidebar.success("已加载你上传的合同文本")
    if not st.sidebar.button("生成 AI 审查结果"):
        st.stop()
    return review_contract_text(
        contract_text,
        contract_id=contract_id,
        source_document=getattr(uploaded_text_file, "name", None),
    )


def _render_polished_report(report: dict, report_obj: object) -> None:
    """尝试调用 LLM 润色并渲染中文风险报告。"""
    polished = None
    with st.spinner("正在调用 LLM 生成中文风险报告，请稍候…"):
        try:
            polished = polish_report(report_obj)
        except Exception as exc:
            st.warning(f"LLM 润色调用失败（{exc}），将展示结构化风险数据。")

    if not polished:
        _render_fallback_report(report)
        return

    # 概览
    overview_cols = st.columns(4)
    with overview_cols[0]:
        st.metric("总体风险", RISK_LABELS.get(report["overall_risk"], report["overall_risk"]))
    with overview_cols[1]:
        st.metric("签署建议", report.get("signing_recommendation", "有条件签署"))
    with overview_cols[2]:
        st.metric("人工复核", "建议复核" if report["requires_manual_review"] else "暂不需要")
    with overview_cols[3]:
        st.metric("重点问题数", str(len(report.get("top_risks", []))))

    # 摘要
    st.markdown("## 风险摘要")
    st.markdown(polished.executive_summary or "暂无摘要。")

    # 签署建议
    if polished.signing_advice:
        st.markdown("## 签署建议")
        st.markdown(polished.signing_advice)

    # 维度洞察
    st.markdown("## 维度风险")
    for dim_key, insight in polished.dimension_insights.items():
        dim_label = DIMENSION_LABELS.get(dim_key, dim_key)
        st.markdown(f"### {dim_label}")
        st.markdown(insight)

    # 法务问题报告
    if polished.issue_reports:
        st.markdown("## 法务问题报告")
        for idx, issue in enumerate(polished.issue_reports, start=1):
            st.markdown(f"### 问题 {idx}：{issue.title}")
            st.markdown(f"**风险等级**：{RISK_LABELS.get(issue.risk_level, issue.risk_level)}")
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

    # 风险归因链（P5.1 - 展示证据驱动路径）
    top_risks = report.get("top_risks", [])
    if top_risks:
        st.markdown("## 风险归因链（证据→节点→维度→总体风险）")
        for risk in top_risks:
            dim_label = DIMENSION_LABELS.get(risk.get("dimension", ""), risk.get("dimension", ""))
            level = RISK_LABELS.get(risk.get("risk_level", ""), risk.get("risk_level", ""))
            with st.expander(f"[{level}] {risk['title']} → {dim_label}"):
                st.markdown(f"**原因**：{risk.get('reason', '无')}")
                st.markdown(f"**建议**：{risk.get('recommendation', '无')}")
                evidence_list = risk.get("evidence", [])
                if evidence_list:
                    st.markdown("**支持证据**：")
                    for ev in evidence_list:
                        st.markdown(f"> {ev}")

    # 多角色视图（P5.2）
    st.markdown("## 多角色视图")
    role_tabs = st.tabs(["管理层视图", "业务视图", "法务视图"])
    with role_tabs[0]:
        st.markdown(polished.executive_view or polished.executive_summary or "暂无管理层摘要。")
    with role_tabs[1]:
        st.markdown(polished.business_view or "暂无业务视图（LLM 未生成）。")
    with role_tabs[2]:
        st.markdown(polished.legal_view or "暂无法务视图（LLM 未生成）。")

    # 维度关联
    if polished.cross_dimension_notes:
        st.markdown("## 维度关联风险")
        for note in polished.cross_dimension_notes:
            st.markdown(f"- {note}")

    # 整改计划
    st.markdown("## 整改计划")
    if polished.action_plan:
        for idx, action in enumerate(polished.action_plan, start=1):
            st.markdown(f"{idx}. {action}")
    else:
        top_risks_list = report.get("top_risks", [])
        for idx, risk in enumerate(top_risks_list[:5], start=1):
            st.markdown(f"{idx}. {risk.get('recommendation', '')}")

    # 人工复核
    manual_items = report.get("manual_review_items", [])
    st.markdown("## 人工复核项")
    if manual_items:
        for idx, item in enumerate(manual_items, start=1):
            st.markdown(f"{idx}. {item}")
    else:
        st.markdown("当前没有必须升级人工复核的事项。")


def _render_fallback_report(report: dict) -> None:
    """LLM 润色失败时的降级展示。"""
    st.markdown("## 风险摘要")
    summary_reasons = report.get("summary_reasons") or ["当前未识别到高优先级风险原因。"]
    signing_recommendation = report.get("signing_recommendation", "有条件签署")
    st.markdown(
        f"该合同整体为**{RISK_LABELS.get(report['overall_risk'], report['overall_risk'])}**，"
        f"当前签署建议为**{signing_recommendation}**，"
        f"最需要关注的是：{summary_reasons[0]}。"
    )

    st.markdown("## 维度风险")
    for dim_key, score in report.get("dimension_scores", {}).items():
        dim_label = DIMENSION_LABELS.get(dim_key, dim_key)
        level = "high" if score >= 0.7 else ("medium" if score >= 0.35 else "low")
        st.markdown(f"- **{dim_label}**：{RISK_LABELS.get(level, level)}（分数 {score:.2f}）")

    top_risks = report.get("top_risks", [])
    if top_risks:
        st.markdown("## 关键风险项")
        for idx, risk in enumerate(top_risks, start=1):
            st.markdown(f"{idx}. **{risk['title']}** — {risk['reason']}")


def main() -> None:
    st.set_page_config(page_title="合同风险演示系统", layout="wide")
    st.title("合同风险研究演示系统")
    st.caption("上传结构化审查结果 JSON，或直接输入合同文本交给 AI 审查，再查看贝叶斯风险评估结果。")

    with st.expander("使用指引", expanded=True):
        st.markdown(
            """
1. 左侧可选择两种输入模式：上传结构化审查结果 JSON，或直接输入合同文本并交给 AI 审查。
2. 选择 JSON 模式时，页面会展示原始审查结果、映射后的贝叶斯证据和最终风险报告。
3. 选择 AI 模式时，先输入合同编号与合同文本，再点击"生成 AI 审查结果"。
4. 「中文报告」标签页展示 LLM 润色后的业务可读风险报告（需要 Ollama 运行）。
5. 「原始数据」标签页展示结构化审查结果、证据映射和风险评估的原始 JSON。
6. 「BN 调参」标签页允许临时修改节点状态和关键 CPT 概率值，观察风险变化。
            """.strip()
        )

    st.sidebar.header("输入数据")
    try:
        review_result = _load_review_result_from_sidebar()
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        st.sidebar.error(str(error))
        st.stop()
    view_model = build_demo_view_model(review_result)

    report = view_model["report"]
    report_obj = view_model["report_obj"]

    tab_polished, tab_raw, tab_bn = st.tabs(["中文报告", "原始数据", "BN 调参"])

    # ── 标签 1：中文风险报告 ──
    with tab_polished:
        _render_polished_report(report, report_obj)

    # ── 标签 2：原始结构化数据 ──
    with tab_raw:
        left, right = st.columns(2)
        with left:
            st.subheader("原始审查结果")
            st.json(view_model["findings"])
            st.subheader("映射后的贝叶斯证据")
            st.json(view_model["evidence"])
            st.subheader("触发的审查项")
            st.json(view_model["triggered_findings"])
        with right:
            st.subheader("风险评估结果")
            st.json(report)
            st.subheader("风险报告 JSON")
            st.code(view_model["report_json"], language="json")

    # ── 标签 3：BN 调参 ──
    with tab_bn:
        st.sidebar.header("节点覆盖")
        node_overrides: dict[str, str] = {}
        for node_name, current_state in view_model["evidence"].items():
            states = view_model["network_config"]["nodes"][node_name]["states"]
            node_overrides[node_name] = st.sidebar.selectbox(
                f"{node_name}",
                states,
                index=states.index(current_state),
            )

        st.sidebar.header("关键 CPT 调参")
        cpt_overrides = {
            "termination_risk.present": st.sidebar.slider("termination_risk.present", 0.0, 1.0, float(view_model["network_config"]["cpts"]["termination_risk"]["present"]), 0.01),
            "liability_risk.acceptable": st.sidebar.slider("liability_risk.acceptable", 0.0, 1.0, float(view_model["network_config"]["cpts"]["liability_risk"]["acceptable"]), 0.01),
            "confidentiality_risk.entailment": st.sidebar.slider("confidentiality_risk.entailment", 0.0, 1.0, float(view_model["network_config"]["cpts"]["confidentiality_risk"]["entailment"]), 0.01),
        }

        tuned_vm = apply_overrides(view_model, node_overrides=node_overrides, cpt_overrides=cpt_overrides)
        tuned_vm = _recalculate_report(tuned_vm)
        tuned_report = tuned_vm["report"]
        tuned_report_obj = tuned_vm["report_obj"]

        st.markdown("### 调参后风险概览")
        tuned_cols = st.columns(4)
        with tuned_cols[0]:
            st.metric("总体风险", RISK_LABELS.get(tuned_report["overall_risk"], tuned_report["overall_risk"]))
        with tuned_cols[1]:
            st.metric("签署建议", tuned_report.get("signing_recommendation", "有条件签署"))
        with tuned_cols[2]:
            st.metric("人工复核", "建议复核" if tuned_report["requires_manual_review"] else "暂不需要")
        with tuned_cols[3]:
            st.metric("重点问题数", str(len(tuned_report.get("top_risks", []))))

        st.markdown("### 调参后维度风险")
        for dim_key, score in tuned_report.get("dimension_scores", {}).items():
            dim_label = DIMENSION_LABELS.get(dim_key, dim_key)
            level = "high" if score >= 0.7 else ("medium" if score >= 0.35 else "low")
            st.markdown(f"- **{dim_label}**：{RISK_LABELS.get(level, level)}（分数 {score:.2f}）")

        with st.expander("调参后完整报告 JSON"):
            st.json(tuned_report)


if __name__ == "__main__":
    main()
