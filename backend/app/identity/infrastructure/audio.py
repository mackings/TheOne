"""Audio decoding, resampling and quality checks for voice samples."""
from __future__ import annotations

import io
import math
import shutil
import subprocess
from dataclasses import dataclass, asdict

import numpy as np
import soundfile as sf


class AudioError(ValueError):
    pass


@dataclass
class AudioQuality:
    duration_s: float
    sample_rate: int
    rms_dbfs: float
    peak_dbfs: float
    speech_ratio: float
    snr_db: float
    clipped: bool
    ok: bool
    issues: list[str]

    def as_dict(self) -> dict:
        return asdict(self)


def decode(data: bytes, target_sr: int = 16000) -> tuple[np.ndarray, int]:
    """Decode audio bytes to mono float32 at target_sr.

    WAV/FLAC/OGG are decoded with libsndfile. Anything else (AAC/M4A from iOS,
    3GP/AMR/Opus/WebM from Android and browsers) falls back to ffmpeg when it is
    installed. Mobile clients should prefer 16 kHz mono PCM WAV where they can;
    the fallback exists so the API never rejects a phone recording outright.
    """
    if not data:
        raise AudioError("empty audio upload")
    try:
        audio, sr = sf.read(io.BytesIO(data), dtype="float32", always_2d=True)
    except Exception as sf_exc:  # noqa: BLE001
        try:
            audio, sr = _decode_with_ffmpeg(data, target_sr)
        except AudioError as ff_exc:
            raise AudioError(f"could not decode audio ({sf_exc}); {ff_exc}") from ff_exc
    mono = audio.mean(axis=1)
    if sr != target_sr:
        mono = resample(mono, sr, target_sr)
    return np.ascontiguousarray(mono, dtype=np.float32), target_sr


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def _decode_with_ffmpeg(data: bytes, target_sr: int) -> tuple[np.ndarray, int]:
    """Transcode arbitrary container/codec to 16-bit mono PCM at target_sr via ffmpeg."""
    if not ffmpeg_available():
        raise AudioError(
            "unsupported audio format and ffmpeg is not installed; send 16 kHz mono PCM WAV, FLAC or OGG"
        )
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-i", "pipe:0",
        "-ac", "1", "-ar", str(target_sr), "-f", "s16le", "pipe:1",
    ]
    try:
        proc = subprocess.run(cmd, input=data, capture_output=True, timeout=30, check=False)
    except subprocess.TimeoutExpired as exc:
        raise AudioError("ffmpeg timed out decoding audio") from exc
    if proc.returncode != 0 or not proc.stdout:
        raise AudioError(f"ffmpeg could not decode audio: {proc.stderr.decode(errors='ignore').strip()[:200]}")
    pcm = np.frombuffer(proc.stdout, dtype=np.int16).astype(np.float32) / 32768.0
    return pcm[:, None], target_sr


def resample(x: np.ndarray, sr_in: int, sr_out: int) -> np.ndarray:
    """FFT-based band-limited resampling (no scipy dependency)."""
    if sr_in == sr_out or x.size == 0:
        return x
    n_in = x.size
    n_out = int(round(n_in * sr_out / sr_in))
    spec = np.fft.rfft(x)
    n_keep = min(spec.size, n_out // 2 + 1)
    out_spec = np.zeros(n_out // 2 + 1, dtype=complex)
    out_spec[:n_keep] = spec[:n_keep]
    y = np.fft.irfft(out_spec, n=n_out) * (n_out / n_in)
    return y.astype(np.float32)


def _dbfs(v: float) -> float:
    return 20 * math.log10(max(v, 1e-9))


def assess_quality(
    x: np.ndarray,
    sr: int,
    min_seconds: float,
    max_seconds: float,
) -> AudioQuality:
    issues: list[str] = []
    duration = x.size / sr
    if duration < min_seconds:
        issues.append(f"too short ({duration:.1f}s, need at least {min_seconds:.1f}s)")
    if duration > max_seconds:
        issues.append(f"too long ({duration:.1f}s, max {max_seconds:.0f}s)")

    peak = float(np.max(np.abs(x))) if x.size else 0.0
    rms = float(np.sqrt(np.mean(x**2))) if x.size else 0.0
    clipped = bool(np.mean(np.abs(x) > 0.99) > 0.001) if x.size else False
    if clipped:
        issues.append("audio is clipping; speak a little further from the microphone")

    # 25 ms frames with a 10 ms hop separate speech from background noise.
    frame = int(sr * 0.025)
    hop = int(sr * 0.010)
    n_frames = max(0, 1 + (x.size - frame) // hop) if x.size >= frame else 0
    if n_frames > 0:
        idx = np.arange(frame)[None, :] + hop * np.arange(n_frames)[:, None]
        energies = np.mean(x[idx] ** 2, axis=1) + 1e-12
        e_db = 10 * np.log10(energies)
        thresh = max(e_db.max() - 30, np.percentile(e_db, 20) + 6)
        speech = e_db >= thresh
        speech_ratio = float(speech.mean())
        if speech.any() and (~speech).any():
            snr = float(10 * np.log10(energies[speech].mean() / energies[~speech].mean()))
        else:
            snr = 0.0
    else:
        speech_ratio, snr = 0.0, 0.0

    if rms < 0.003:
        issues.append("audio is too quiet or silent")
    if speech_ratio < 0.25:
        issues.append("not enough speech detected; please read the whole sentence")
    if snr < 8:
        issues.append("background noise is high; move to a quieter place")

    return AudioQuality(
        duration_s=round(duration, 2),
        sample_rate=sr,
        rms_dbfs=round(_dbfs(rms), 1),
        peak_dbfs=round(_dbfs(peak), 1),
        speech_ratio=round(speech_ratio, 2),
        snr_db=round(snr, 1),
        clipped=clipped,
        ok=not issues,
        issues=issues,
    )


class SoundfileAudioDecoder:
    def decode(self, data: bytes, target_sr: int) -> tuple[np.ndarray, int]:
        return decode(data, target_sr)

    def assess_quality(self, wav: np.ndarray, sr: int, min_seconds: float, max_seconds: float) -> AudioQuality:
        return assess_quality(wav, sr, min_seconds, max_seconds)
