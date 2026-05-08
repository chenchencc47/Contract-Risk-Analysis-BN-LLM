import asyncio

from backend.routers.misc import api_demo


def test_api_demo_returns_precomputed_response() -> None:
    payload = asyncio.run(api_demo())

    assert payload["demo"] is True
    assert payload["generation_mode"] == "v2_combined"
    assert payload["review_party"] == "buyer"
    assert payload["polished"]["narrative_report"]
    assert payload["consistency"]["counterfactuals"]
