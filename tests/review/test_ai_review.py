import pytest

from contract_risk_analysis.domain.free_review_schema import (
    FreeReviewOutput,
    NegotiationChip,
    RiskSegment,
)
from contract_risk_analysis.domain.review_schema import ReviewResult
from contract_risk_analysis.review.adjudicate import adjudicate
from contract_risk_analysis.review.ai_review import (
    AIReviewSettings,
    _completion_to_payload,
    _detect_asset_type_context,
    _free_review_prompt,
    _parse_free_review_payload,
    _parse_review_result_payload,
    free_review_contract_text,
)


class _DummyMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class _DummyChoice:
    def __init__(self, content: str) -> None:
        self.message = _DummyMessage(content)
        self.finish_reason = None


class _DummyCompletion:
    def __init__(self, content: str) -> None:
        self.choices = [_DummyChoice(content)]


def test_parse_review_result_payload_returns_review_result() -> None:
    payload = {
        "contract_id": "nda-ai-001",
        "review_type": "nda",
        "source_document": "inline-text",
        "findings": [
            {
                "clause_type": "termination",
                "status": "missing",
                "evidence_text": "No termination clause found.",
                "confidence": 0.91,
            }
        ],
    }

    review_result = _parse_review_result_payload(payload)

    assert isinstance(review_result, ReviewResult)
    assert review_result.contract_id == "nda-ai-001"
    assert review_result.findings[0].clause_type == "termination"


def test_parse_review_result_payload_accepts_fine_grained_finding_fields() -> None:
    payload = {
        "contract_id": "nda-ai-002",
        "review_type": "sales_contract",
        "source_document": "contract.md",
        "findings": [
            {
                "clause_type": "termination",
                "status": "missing",
                "evidence_text": "No termination clause found.",
                "confidence": 0.91,
                "finding_key": "termination_clause_missing",
                "finding_label": "终止条款缺失",
                "counterparty_favorability": "buyer_favorable",
            }
        ],
    }

    review_result = _parse_review_result_payload(payload)

    finding = review_result.findings[0]
    assert finding.finding_key == "termination_clause_missing"
    assert finding.finding_label == "终止条款缺失"
    assert finding.counterparty_favorability == "buyer_favorable"


def test_parse_review_result_payload_rejects_missing_findings() -> None:
    with pytest.raises(ValueError, match="findings"):
        _parse_review_result_payload({"contract_id": "nda-ai-001"})


def test_risk_segment_preserves_structured_negotiation_chip() -> None:
    segment = RiskSegment(
        clause_type="payment",
        risk_title="预付款比例过高",
        risk_description="预付款比例高于市场惯例，可能造成资金风险。",
        evidence_text="甲方应在签约后5日内支付80%预付款。",
        confidence=0.9,
        severity="high",
        negotiation_chip=NegotiationChip(chip_type="交换筹码"),
    )

    assert segment.negotiation_chip is not None
    assert segment.negotiation_chip.chip_type == "交换筹码"


def test_parse_free_review_payload_builds_structured_chip() -> None:
    payload = {
        "contract_id": "c1",
        "overall_assessment": "summary",
        "risk_segments": [
            {
                "clause_type": "payment",
                "risk_title": "预付款比例过高",
                "risk_description": "risk",
                "evidence_text": "80%预付款",
                "confidence": 0.95,
                "severity": "critical",
                "negotiation_chip": {
                    "chip_type": "交换筹码",
                    "location": "第九条",
                    "reason": "卖方极想保留",
                    "counterparty_attack": "行业惯例",
                    "strategy": "降到50%",
                },
            }
        ],
        "missing_clauses": [],
        "strengths": [],
    }

    result = _parse_free_review_payload(payload)

    assert result.risk_segments[0].negotiation_chip is not None
    assert result.risk_segments[0].negotiation_chip.location == "第九条"


def test_parse_free_review_payload_downgrades_legacy_chip_string() -> None:
    payload = {
        "contract_id": "c1",
        "overall_assessment": "summary",
        "risk_segments": [
            {
                "clause_type": "payment",
                "risk_title": "预付款比例过高",
                "risk_description": "risk",
                "evidence_text": "80%预付款",
                "confidence": 0.95,
                "severity": "critical",
                "negotiation_chip": "响应筹码",
            }
        ],
        "missing_clauses": [],
        "strengths": [],
    }

    result = _parse_free_review_payload(payload)

    assert result.risk_segments[0].negotiation_chip is not None
    assert result.risk_segments[0].negotiation_chip.chip_type == "响应筹码"
    assert result.risk_segments[0].negotiation_chip.reason == "响应筹码"


def test_parse_free_review_payload_rejects_invalid_chip_shape() -> None:
    payload = {
        "contract_id": "c1",
        "overall_assessment": "summary",
        "risk_segments": [
            {
                "clause_type": "payment",
                "risk_title": "预付款比例过高",
                "risk_description": "risk",
                "evidence_text": "80%预付款",
                "confidence": 0.95,
                "severity": "critical",
                "negotiation_chip": ["not", "valid"],
            }
        ],
        "missing_clauses": [],
        "strengths": [],
    }

    with pytest.raises(ValueError, match="negotiation_chip"):
        _parse_free_review_payload(payload)


@pytest.mark.parametrize(
    "chip_payload",
    [
        {
            "chip_type": "交换筹码",
            "location": "第九条",
            "reason": "卖方极想保留",
            "counterparty_attack": "行业惯例",
            "strategy": "降到50%",
            "unexpected": "x",
        },
        {
            "chip_type": "交换筹码",
            "location": ["bad"],
            "reason": "卖方极想保留",
            "counterparty_attack": "行业惯例",
            "strategy": "降到50%",
        },
    ],
)
def test_parse_free_review_payload_rejects_invalid_chip_dict_contract(chip_payload: object) -> None:
    payload = {
        "contract_id": "c1",
        "overall_assessment": "summary",
        "risk_segments": [
            {
                "clause_type": "payment",
                "risk_title": "预付款比例过高",
                "risk_description": "risk",
                "evidence_text": "80%预付款",
                "confidence": 0.95,
                "severity": "critical",
                "negotiation_chip": chip_payload,
            }
        ],
        "missing_clauses": [],
        "strengths": [],
    }

    with pytest.raises(ValueError, match="negotiation_chip"):
        _parse_free_review_payload(payload)


def test_adjudicate_assigns_structured_chip_from_party_rule() -> None:
    output = FreeReviewOutput(
        contract_id="c1",
        overall_assessment="summary",
        risk_segments=[
            RiskSegment(
                clause_type="liability_cap",
                risk_title="无责任上限",
                risk_description="desc",
                evidence_text="evidence",
                confidence=0.9,
                severity="high",
                canonical_type="liability_cap",
            )
        ],
        missing_clauses=[],
        strengths=[],
    )

    result = adjudicate(output, review_party="buyer")

    chip = result.risk_segments[0].negotiation_chip
    assert chip is not None
    assert isinstance(chip, NegotiationChip)
    assert chip.chip_type == "响应筹码"
    assert chip.reason == (
        "无责任上限对买方是核心优势。乙方违约时（如交付不合格产品），甲方可追索全部损失，无上限封顶。"
        "这是谈判中的超级筹码——对方必然恐惧于此——绝不主动提出修改。如对方要求增加责任上限，"
        "只能作为换取对方同步降低核心付款风险、补强担保措施或后移风险节点的交换条件。"
    )


def test_completion_to_payload_reads_json_from_message_content() -> None:
    completion = _DummyCompletion('{"contract_id": "nda-ai-001", "findings": []}')

    payload = _completion_to_payload(completion)

    assert payload["contract_id"] == "nda-ai-001"


def test_free_review_retries_once_after_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    class _DummyClient:
        def __init__(self, contents: list[str]) -> None:
            self.contents = contents
            self.calls = 0
            self.chat = self
            self.completions = self

        def create(self, **kwargs):
            content = self.contents[self.calls]
            self.calls += 1
            return _DummyCompletion(content)

    client = _DummyClient([
        '{"contract_id":"c1","overall_assessment":"x","risk_segments":[{"clause_type":"payment"',
        '{"contract_id":"c1","overall_assessment":"x","risk_segments":[{"clause_type":"payment","risk_title":"ok","risk_description":"ok","evidence_text":"ok","confidence":0.9,"severity":"high","negotiation_chip":{"chip_type":"交换筹码","location":"第九条","reason":"卖方极想保留","counterparty_attack":"行业惯例","strategy":"换取交付让步"}}],"missing_clauses":[],"strengths":[]}',
    ])

    monkeypatch.setattr(
        "contract_risk_analysis.review.ai_review.load_ai_review_settings",
        lambda: AIReviewSettings(api_key="k", base_url="u", model="m"),
    )
    monkeypatch.setattr(
        "contract_risk_analysis.review.ai_review.OpenAI",
        lambda api_key, base_url: client,
    )

    result = free_review_contract_text("合同文本", "c1")

    assert result.contract_id == "c1"
    assert result.risk_segments[0].negotiation_chip is not None
    assert result.risk_segments[0].negotiation_chip.strategy == "换取交付让步"
    assert client.calls == 2


def test_free_review_raises_after_second_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    class _DummyClient:
        def __init__(self, contents: list[str]) -> None:
            self.contents = contents
            self.calls = 0
            self.chat = self
            self.completions = self

        def create(self, **kwargs):
            content = self.contents[self.calls]
            self.calls += 1
            return _DummyCompletion(content)

    bad = '{"contract_id":"c1","overall_assessment":"x","risk_segments":[{"clause_type":"payment"'
    client = _DummyClient([bad, bad])

    monkeypatch.setattr(
        "contract_risk_analysis.review.ai_review.load_ai_review_settings",
        lambda: AIReviewSettings(api_key="k", base_url="u", model="m"),
    )
    monkeypatch.setattr(
        "contract_risk_analysis.review.ai_review.OpenAI",
        lambda api_key, base_url: client,
    )

    with pytest.raises(ValueError, match="JSON 解析失败"):
        free_review_contract_text("合同文本", "c1")

    assert client.calls == 2


def test_free_review_prompt_includes_numeric_discipline_rules() -> None:
    prompt = _free_review_prompt(
        "甲方于合同签订后10日内支付80%预付款。",
        "sales-001",
        None,
        "buyer",
    )

    assert "7. **数字纪律**：所有百分比、金额、天数都必须能直接追溯到合同原文。" in prompt
    assert "只有当合同原文明确出现合同总价、价税合计或其他可作为总额基准的金额时，才允许把百分比换算成金额" in prompt
    assert "若总价未明确，只能保留百分比/天数，不得自行写出“约X元”“预计损失X元”“每下降10%=X元”等金额化表述。" in prompt
    assert "合同总价未明确，暂不进行金额测算" in prompt
    assert "数字只能来自合同原文；不得为了增强说服力补写无来源金额、比例或天数" in prompt



def test_free_review_prompt_requires_dual_sided_analysis_for_deemed_delivery_clause() -> None:
    prompt = _free_review_prompt(
        "甲方经初验签字后视为乙方已交付，且外观验收不免除内在质量责任。",
        "sales-005",
        None,
        "buyer",
    )

    assert "对‘视为交付/签字即交付/逾期未提异议视为合格’类条款，必须同时判断" in prompt
    assert "是否提前触发交付完成或风险转移解释" in prompt
    assert "合同中是否仍保留质量责任、拒收、退换货或终验保护" in prompt


def test_free_review_prompt_includes_legal_basis_and_payment_hierarchy_rules() -> None:
    prompt = _free_review_prompt(
        "甲方于合同签订后10日内支付80%预付款，乙方在支付尾款前提交质保金。",
        "sales-006",
        None,
        "buyer",
    )

    assert "法律依据纪律" in prompt
    assert "禁止为了显得专业而机械套用法条" in prompt
    assert "禁止机械套用与风险点不直接对应的定金罚则或其他法条" in prompt
    assert "应优先识别为一个主风险（付款担保结构失衡/资金结构倒挂）" in prompt
    assert "再将质保不足写成补充性子风险" in prompt
    assert "己方只能在获得对应保护条件或其他关键让步时，才做有限退让" in prompt


def test_free_review_prompt_includes_generalization_guardrails() -> None:
    prompt = _free_review_prompt(
        "甲方于合同签订后10日内支付80%预付款。",
        "sales-007",
        None,
        "buyer",
    )

    assert "**泛化约束**" in prompt
    assert "禁止照搬其他报告中的固定比例、固定天数、固定金额、固定地名" in prompt
    assert "只能输出适用于当前合同文本的结构性判断" in prompt
    assert "不得把外部评价结论当作标准答案回写进本次审查" in prompt
    assert "攻击预判纪律（强制执行）" in prompt
    assert "不得套用'三板斧''显失公平''行业惯例'等无差别攻击模板" in prompt


def test_detect_asset_type_context_returns_hint_for_equipment_contract() -> None:
    text = "甲方采购量子点光谱水质检测仪设备，合同总价1535万元。"
    result = _detect_asset_type_context(text)
    assert "标准工业设备" in result
    assert "标的物属性提示" in result


def test_detect_asset_type_context_returns_hint_for_custom_contract() -> None:
    text = "乙方按甲方需求定制开发非标自动化系统集成，含软件开发和按需设计。"
    result = _detect_asset_type_context(text)
    assert "定制化" in result


def test_detect_asset_type_context_returns_empty_for_unknown() -> None:
    text = "双方就合作事宜达成如下协议。"
    result = _detect_asset_type_context(text)
    assert result == ""


def test_free_review_prompt_includes_asset_type_context_for_equipment() -> None:
    prompt = _free_review_prompt(
        "甲方采购量子点光谱水质检测仪设备，合同总价1535万元。"
        "第九条第2款：甲方于本合同签订后10日内向乙方支付合同金额的80%作为预付款。",
        "equip-001",
        None,
        "buyer",
    )
    assert "标的物属性提示" in prompt
    assert "标准工业设备" in prompt
