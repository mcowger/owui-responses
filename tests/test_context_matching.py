import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from owui_manifolds.filters.context_matching import ModelMatcher


MODEL_TOKEN_TABLE = "\n".join(
    (
        "gpt-5*,1000000,92,80",
        "*,200000,92,80",
    )
)


def test_matcher_matches_dot_prefixed_manifold_model_id():
    match = ModelMatcher().match_model(
        "openai_responses_manifold.gpt-5.6-terra", MODEL_TOKEN_TABLE
    )

    assert match["matched_pattern"] == "gpt-5*"
    assert match["limit"] == 1_000_000


def test_matcher_preserves_bare_dotted_model_id():
    match = ModelMatcher().match_model("gpt-5.6-terra", MODEL_TOKEN_TABLE)

    assert match["matched_pattern"] == "gpt-5*"
    assert match["limit"] == 1_000_000
