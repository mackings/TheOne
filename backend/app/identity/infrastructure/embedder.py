"""Speaker embedding backends.

The default backend is sherpa-onnx with a pretrained WeSpeaker CAM++ model
(trained on VoxCeleb). It runs on ONNX Runtime and needs no PyTorch, which
matters on macOS x86_64 where torch wheels are no longer published.

A SpeechBrain ECAPA-TDNN backend is available for Linux/Docker deployments.
"""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path

import numpy as np

from app.identity.application.ports import SpeakerEmbedder
from app.identity.domain.matcher import l2_normalize

log = logging.getLogger(__name__)


class SherpaOnnxEmbedder:
    def __init__(self, model_path: Path, num_threads: int = 2):
        # Imported here so the tests run without it.
        import sherpa_onnx

        if not model_path.exists():
            raise FileNotFoundError(
                f"speaker model not found at {model_path}. See README for download instructions."
            )
        cfg = sherpa_onnx.SpeakerEmbeddingExtractorConfig(
            model=str(model_path), num_threads=num_threads, provider="cpu"
        )
        if not cfg.validate():
            raise RuntimeError(f"invalid speaker model config: {cfg}")
        self._extractor = sherpa_onnx.SpeakerEmbeddingExtractor(cfg)
        self.dim = int(self._extractor.dim)
        self.name = f"sherpa-onnx:{model_path.name}"
        log.info("loaded speaker model %s (dim=%d)", self.name, self.dim)

    def embed(self, audio: np.ndarray, sample_rate: int) -> np.ndarray:
        stream = self._extractor.create_stream()
        stream.accept_waveform(sample_rate=sample_rate, waveform=np.asarray(audio, dtype=np.float32))
        stream.input_finished()
        if not self._extractor.is_ready(stream):
            raise ValueError("audio too short to compute a speaker embedding")
        return l2_normalize(np.array(self._extractor.compute(stream), dtype=np.float32))


class SpeechBrainEmbedder:
    """ECAPA-TDNN via SpeechBrain. Requires torch; use in Docker/Linux."""

    def __init__(self, source: str = "speechbrain/spkrec-ecapa-voxceleb"):
        import torch
        from speechbrain.inference.speaker import EncoderClassifier

        self._torch = torch
        self._model = EncoderClassifier.from_hparams(source=source, run_opts={"device": "cpu"})
        self.dim = 192
        self.name = f"speechbrain:{source}"

    def embed(self, audio: np.ndarray, sample_rate: int) -> np.ndarray:
        wav = self._torch.from_numpy(np.asarray(audio, dtype=np.float32)).unsqueeze(0)
        emb = self._model.encode_batch(wav).squeeze().detach().cpu().numpy()
        return l2_normalize(emb)


class FakeEmbedder:
    """Deterministic stand-in for tests. Embedding depends on coarse audio statistics
    so that identical/similar clips match and dissimilar clips do not."""

    name = "fake"
    dim = 32

    def embed(self, audio: np.ndarray, sample_rate: int) -> np.ndarray:
        x = np.asarray(audio, dtype=np.float32)
        spec = np.abs(np.fft.rfft(x, n=4096))[: self.dim * 8]
        feats = spec.reshape(self.dim, -1).mean(axis=1)
        feats = np.log1p(feats)
        # Keep the spectral shape, drop the overall level.
        feats = feats - feats.mean()
        seed = int(hashlib.sha256(b"fake-embedder").hexdigest(), 16) % (2**32)
        proj = np.random.default_rng(seed).standard_normal((self.dim, self.dim)).astype(np.float32)
        return l2_normalize(proj @ feats)


def build_embedder(backend: str, model_path: Path, threads: int) -> SpeakerEmbedder:
    if backend == "sherpa-onnx":
        return SherpaOnnxEmbedder(model_path, threads)
    if backend == "speechbrain":
        return SpeechBrainEmbedder()
    if backend == "fake":
        return FakeEmbedder()
    raise ValueError(f"unknown EMBEDDER_BACKEND {backend!r}")
