import asyncio

from backend.routers.misc import api_demo


def test_api_demo_returns_precomputed_response() -> None:
    payload = asyncio.run(api_demo())

    assert payload["demo"] is True
    assert payload["generation_mode"] == "v2_combined"
    assert payload["review_party"] == "buyer"
    assert payload["polished"]["narrative_report"]
    assert payload["consistency"]["counterfactuals"]


def test_api_demo_returns_full_product_demo_documents() -> None:
    payload = asyncio.run(api_demo())

    narrative_report = payload["polished"]["narrative_report"]

    for heading in (
        "## 二、合同基本信息",
        "## 三、核心风险总览",
        "## 四、重点风险逐项分析",
        "## 五、BN 反事实分析",
        "## 六、修订建议",
        "## 七、签署建议",
        "## 八、Demo 说明与局限",
    ):
        assert heading in narrative_report

    assert "revision_checklist" in payload
    assert "bn_appendix" in payload
    assert "付款结构" in payload["revision_checklist"]
    assert "pgmpy" in payload["bn_appendix"]
    assert len(narrative_report) > 2500
