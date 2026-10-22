"""Application settings, read from the environment and backend/.env."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    database_url: str = f"sqlite:///{BACKEND_DIR / 'voiceid.db'}"
    template_encryption_key: str | None = None

    # Voice: speaker model (sherpa-onnx, speechbrain or fake) and recording limits.
    embedder_backend: str = "sherpa-onnx"
    speaker_model_path: str = "models/3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx"
    embedder_threads: int = 2
    target_sample_rate: int = 16000
    min_sample_seconds: float = 1.5
    max_sample_seconds: float = 20.0
    enrolment_samples_required: int = 3

    # Voice decision: match and spoof thresholds. High-risk actions need the accept score plus the margin.
    match_accept_threshold: float = 0.55
    match_stepup_threshold: float = 0.40
    spoof_stepup_threshold: float = 0.60
    spoof_reject_threshold: float = 0.90
    high_risk_accept_margin: float = 0.05
    continuous_ema_alpha: float = 0.4

    # Iris: each customer's accept limit is their enrolment agreement plus a margin, kept within floor and cap.
    iris_accept_hd: float = 0.36
    iris_enrol_max_hd: float = 0.31
    iris_accept_margin: float = 0.07
    iris_accept_floor: float = 0.28
    iris_accept_cap: float = 0.34
    iris_min_focus: float = 25.0
    iris_min_radius_px: int = 36
    iris_min_frames: int = 3

    # Mule detection: accounts score 0 to 1; flagged from 0.60, payments held from 0.85.
    network_home_bank_code: str = "999"
    network_home_bank_name: str = "TheOne Demo Bank"
    network_window_days: int = 30
    network_fast_window_min: int = 120
    network_flag_threshold: float = 0.60
    network_hold_threshold: float = 0.85
    network_ring_min_score: float = 0.50
    network_id_pepper: str = "dev-only-pepper-change-me"
    network_simulation_enabled: bool = True
    network_recompute_min_interval_s: float = 3.0
    network_full_rebuild_s: int = 600

    # Payment checks on the sender's side. KYC tier limits are placeholders until confirmed against CBN rules.
    network_sender_stepup: float = 0.50
    network_new_payee_naira: int = 200_000
    network_thin_file_naira: int = 1_000_000
    network_review_cap_naira: int = 100_000_000
    network_kyc_daily_limits: str = "1:50000,2:200000"
    network_utc_offset_hours: int = 1
    network_safe_limit_cooling_hours: int = 24
    network_require_attested_device: bool = True
    stepup_challenge_ttl_s: int = 120

    # The bank: "enforce" sends holds, "shadow" only records them. Connector "none" or "obn" (Open Banking Nigeria).
    network_mode: str = "enforce"
    network_bank_connector: str = "none"
    network_obn_base_url: str = "http://localhost:8000/mock-obn"
    network_obn_client_id: str = "theone-demo"
    network_obn_client_secret: str = "theone-demo-secret"
    network_obn_token_path: str = "/access/token"
    network_obn_timeout_s: float = 8.0

    # NIBSS traces and the BVN watch-list. Connector "none" or "http"; the default URL is the built-in mock.
    network_nibss_connector: str = "none"
    network_nibss_base_url: str = "http://localhost:8000/mock-nibss"
    network_nibss_api_key: str = ""

    # Bank file imports: timezone of times without one (WAT is +1), and the largest background upload.
    network_import_utc_offset_hours: int = 1
    network_import_max_mb: int = 4096

    # Learning rule weights from confirmed outcomes.
    network_learning_enabled: bool = True
    network_learning_min_samples: int = 5
    network_learning_prior_strength: float = 10.0

    # Assistant (Gemini). The key stays in backend/.env or the host's secrets, never in the repo.
    gemini_api_key: str = ""
    gemini_text_model: str = "gemini-2.5-flash"
    gemini_text_fallbacks: str = "gemini-flash-latest,gemini-3-flash-preview"
    gemini_live_model: str = "gemini-3.1-flash-live-preview"
    gemini_voice: str = "Kore"
    # What the analyst's speech is transcribed as. Left to auto-detect, noise and echo come out as other languages.
    gemini_live_language_codes: str = "en-NG,en-US"

    # Access: API_KEYS is "key:role,..."; API_KEY alone acts as admin. With no keys the API is open (development only).
    api_keys: str = ""
    api_key: str | None = None
    cors_origins: str = "http://localhost:3000"

    @property
    def sqlalchemy_url(self) -> str:
        """Render and Heroku hand out postgres:// URLs; SQLAlchemy 2 + psycopg 3 needs postgresql+psycopg://."""
        url = self.database_url
        if url.startswith("postgres://"):
            url = "postgresql+psycopg://" + url[len("postgres://"):]
        elif url.startswith("postgresql://"):
            url = "postgresql+psycopg://" + url[len("postgresql://"):]
        return url

    @property
    def speaker_model_abspath(self) -> Path:
        p = Path(self.speaker_model_path)
        return p if p.is_absolute() else BACKEND_DIR / p

    @property
    def role_keys(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for part in self.api_keys.split(","):
            if ":" in part:
                key, role = part.rsplit(":", 1)
                if key.strip():
                    out[key.strip()] = role.strip()
        if self.api_key:
            out[self.api_key] = "admin"
        return out

    @property
    def kyc_daily_limits(self) -> dict[int, int]:
        out: dict[int, int] = {}
        for part in self.network_kyc_daily_limits.split(","):
            if ":" in part:
                tier, limit = part.split(":", 1)
                out[int(tier.strip())] = int(limit.strip())
        return out

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
