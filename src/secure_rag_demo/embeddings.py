from typing import Protocol

from fastembed import TextEmbedding
from fastembed.common.model_description import ModelSource, PoolingType

MODEL_NAME = "intfloat/multilingual-e5-small"


class EmbeddingService(Protocol):
    def embed_passages(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class FastEmbedService:
    """Local multilingual embeddings; text never leaves the machine."""

    _registered = False

    def __init__(self) -> None:
        if not FastEmbedService._registered:
            TextEmbedding.add_custom_model(
                model=MODEL_NAME,
                pooling=PoolingType.MEAN,
                normalization=True,
                sources=ModelSource(hf=MODEL_NAME),
                dim=384,
                model_file="onnx/model.onnx",
            )
            FastEmbedService._registered = True
        self._model = TextEmbedding(model_name=MODEL_NAME)

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        return [[float(x) for x in v] for v in self._model.embed([f"passage: {t}" for t in texts])]

    def embed_query(self, text: str) -> list[float]:
        return [float(x) for x in next(iter(self._model.embed([f"query: {text}"])))]
