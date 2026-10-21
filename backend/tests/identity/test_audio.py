import numpy as np

from app.identity.infrastructure.audio import assess_quality, decode, resample
from helpers.voice import SR, synth_voice, wav_bytes


def test_decode_and_resample_from_48k():
    x = synth_voice(150, seconds=2.0)
    x48 = resample(x, SR, 48000)
    y, sr = decode(wav_bytes(x48, 48000), SR)
    assert sr == SR
    assert abs(y.size - x.size) <= 2


def test_quality_good_voice():
    q = assess_quality(synth_voice(150), SR, 1.5, 20)
    assert q.ok, q.issues
    assert q.snr_db > 8


def test_quality_rejects_silence_and_short():
    q = assess_quality(np.zeros(SR * 2, dtype=np.float32), SR, 1.5, 20)
    assert not q.ok
    q = assess_quality(synth_voice(150, seconds=0.5), SR, 1.5, 20)
    assert any("too short" in i for i in q.issues)


def test_decode_rejects_empty_and_garbage():
    import pytest

    from app.identity.infrastructure.audio import AudioError

    with pytest.raises(AudioError):
        decode(b"", SR)
    with pytest.raises(AudioError):
        decode(b"not audio at all", SR)
