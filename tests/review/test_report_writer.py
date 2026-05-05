from contract_risk_analysis.review.report_writer import _parse_narrative_to_polished, _strip_think_tags


SAMPLE_MARKDOWN = """## 一、执行摘要

经贝叶斯网络模型对本合同进行系统性风险评估，综合判定整体风险等级为**中风险**。

主要风险驱动因素为终止条款缺失和法律可执行性维度的不确定性。建议在补齐关键条款后签署。

## 二、风险总览

| 维度 | 分数 | 等级 | 概述 |
|------|------|------|------|
| 法律可执行性风险 | 0.78 | 高风险 | 终止条款与适用法律缺失导致执行路径不稳定 |

该合同的终止条款缺失与履约交付风险存在跨维度关联——缺少有效的退出机制可能导致交付争议无法及时解决。

## 三、逐条款风险分析

### 终止条款完整性

**风险识别**：合同未明确约定终止条件、通知期限和解除后义务。

**因果链**：终止条款缺失（证据层节点）→ 驱动法律可执行性风险升高 → 推高整体合同风险。

**建议修改**：补充完整终止条款，包括终止条件、通知周期和解除后责任安排。

## 四、反事实分析

| 条款 | 当前状态 | 改善后 | 高风险概率降幅 |
|------|---------|--------|--------------|
| 终止条款完整性 | missing | present | 25% |

## 五、筹码防御与谈判策略

本合同的核心筹码为付款结构（发货前到账90%）和管辖地（乙方所在地法院）。对方律师最可能以"显失公平"为由攻击付款条款。防守话术：预付款+发货款是建材行业标准做法，乙方需提前备料排产。若必须让步，可退至分期付款但要求对方在责任上限条款上接受100%上限。

## 六、签署建议

建议在补齐终止条款和适用法律条款后签署。优先谈判事项：终止机制、法律适用、责任上限。

## 七、整改行动计划

- 补充终止条款（签署前，甲方起草）
- 明确适用法律（签署前，双方协商）
- 约定责任上限（签署后30日内，双方）

## 八、附录

本报告基于 LLM → BN → LLM 三层架构生成。
"""


def test_parse_narrative_extracts_sections() -> None:
    polished = _parse_narrative_to_polished(SAMPLE_MARKDOWN)

    assert polished.narrative_report == SAMPLE_MARKDOWN
    assert "中风险" in polished.executive_summary
    assert "补齐" in polished.signing_advice
    assert len(polished.action_plan) == 3
    assert "补充终止条款" in polished.action_plan[0]
    assert len(polished.cross_dimension_notes) >= 1
    assert "跨维度" in polished.cross_dimension_notes[0]
    assert len(polished.legal_view) > 50


def test_strip_think_tags_removes_deepseek_reasoning() -> None:
    raw = "前缀内容\n<think>\n这是推理过程，应该被移除。\n</think>\n报告正文\n## 一、执行摘要\n内容"
    cleaned = _strip_think_tags(raw)
    assert "<think>" not in cleaned
    assert "推理过程" not in cleaned
    assert "报告正文" in cleaned
    assert "前缀内容" in cleaned


def test_parse_narrative_handles_empty_report() -> None:
    polished = _parse_narrative_to_polished("")
    assert polished.narrative_report == ""
    assert polished.action_plan == []
    assert polished.signing_advice == ""
