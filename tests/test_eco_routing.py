import ecocost
import pytest

from usage_costs.eco import ecocost_route


@pytest.mark.parametrize(
    "enum,model_id,url,expected",
    [
        # Gooey's own routes for open models
        (
            "fireworks",
            "accounts/fireworks/models/deepseek-v4-pro-0813",
            None,
            "fireworks",
        ),
        ("openai", "mistral-small-2603", None, "mistral"),
        ("openai", "AI71ai/agrillm-Qwen3-30B-A3B", None, "modal"),
        # served from Gooey's own cluster, despite the prefix
        ("aks", "aisingapore/llama3-8b-cpt-sea-lionv2.1-instruct", None, "unknown-us"),
        # ecocost resolves a base_url host itself
        (
            "openai",
            "openai/gpt-oss-20b",
            "https://inference.api.nscale.com/v1",
            "nscale",
        ),
        (
            "openai",
            "qwen3.8-max",
            "https://ws-x.ap-southeast-1.maas.aliyuncs.com/v1",
            "alibaba-sg",
        ),
        # and infers a closed model's vendor
        ("openai", "claude-sonnet-5", None, "anthropic"),
        ("openai_responses", "gpt-6-astra", None, "openai"),
        ("openai", "google/gemini-3.1-pro-preview", None, "google-vertex"),
        # anything else gets its US defaults
        ("groq", "meta-llama/Llama-3.3-70B-Instruct", None, "unknown-us"),
    ],
)
def test_ecocost_estimates_the_upstream_gooey_calls(enum, model_id, url, expected):
    route = ecocost_route(provider_enum=enum, model_id=model_id, base_url=url)
    assert ecocost.estimate(model_id, output_tokens=1, **route)["provider"] == expected
