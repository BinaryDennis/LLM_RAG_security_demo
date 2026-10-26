import os

import pytest

from secure_rag_demo.embeddings import FastEmbedService

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_MODEL_SMOKE") != "1",
    reason="downloads the real model; set RUN_MODEL_SMOKE=1",
)


def test_real_model_returns_384_dims() -> None:
    svc = FastEmbedService()
    assert len(svc.embed_query("Vad är informationssäkerhet?")) == 384
    assert len(svc.embed_passages(["Informationssäkerhet handlar om skydd."])[0]) == 384
