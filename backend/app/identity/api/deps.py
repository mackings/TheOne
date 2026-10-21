"""The biometric engines the identity use cases are given."""
from __future__ import annotations

from fastapi import Request

from app.identity.application.ports import AntiSpoofScorer, SpeakerEmbedder
from app.identity.application.verification import Voice
from app.identity.infrastructure.audio import SoundfileAudioDecoder
from app.identity.infrastructure.iris_engine import OpenCvIrisEngine
from app.infrastructure.crypto import cipher

decoder = SoundfileAudioDecoder()
iris_engine = OpenCvIrisEngine()


def get_embedder(request: Request) -> SpeakerEmbedder:
    return request.app.state.embedder


def get_antispoof(request: Request) -> AntiSpoofScorer:
    return request.app.state.antispoof


def get_voice(request: Request) -> Voice:
    return Voice(decoder, get_embedder(request), get_antispoof(request), cipher)
