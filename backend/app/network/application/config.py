"""Domain parameters built from the application settings."""
from __future__ import annotations

from datetime import timedelta

from app.core.config import Settings
from app.network.domain.engine import Config
from app.network.domain.sender import SenderRules


def engine_config(s: Settings, weights: dict[str, float] | None = None) -> Config:
    return Config(window_days=s.network_window_days, fast_window=timedelta(minutes=s.network_fast_window_min),
                  flag=s.network_flag_threshold, hold=s.network_hold_threshold, ring_min=s.network_ring_min_score,
                  home_bank=s.network_home_bank_code, weights=dict(weights or {}))


def sender_rules(s: Settings) -> SenderRules:
    return SenderRules(utc_offset_hours=s.network_utc_offset_hours, review_cap_naira=s.network_review_cap_naira,
                       thin_file_naira=s.network_thin_file_naira, new_payee_naira=s.network_new_payee_naira,
                       kyc_daily_limits=s.kyc_daily_limits)
