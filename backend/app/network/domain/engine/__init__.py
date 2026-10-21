"""Mule-network analysis over a time window of transfers.

  typologies  explainable rules that score each account
  scoring     signals combined by noisy-OR with learned weights, then propagated to accounts that
              receive fast-moving money from flagged accounts
  rings       suspicious accounts connected by transfers or shared identifiers, grouped and summarised

Every signal carries a plain reason and evidence, so an analyst can defend each alert. Senders into
a ring are treated as possible victims and are never penalised for paying a mule.
"""
from app.network.domain.engine.rings import find_rings, match_ring, ring_summary
from app.network.domain.engine.scoring import (LEARNING_EXEMPT, MULT_MAX, MULT_MIN, apply_status, base_signals, noisy_or,
                                               propagate, score_all)
from app.network.domain.engine.types import (CASH_CHANNELS, NAIRA, AccountView, Analysis, Config, Edge, RingResult, Signal,
                                             Snapshot, naira, signal_dicts)

__all__ = ["CASH_CHANNELS", "LEARNING_EXEMPT", "MULT_MAX", "MULT_MIN", "NAIRA", "AccountView", "Analysis", "Config", "Edge",
           "RingResult", "Signal", "Snapshot", "apply_status", "base_signals", "find_rings", "match_ring", "naira", "noisy_or",
           "propagate", "ring_summary", "score_all", "signal_dicts"]
