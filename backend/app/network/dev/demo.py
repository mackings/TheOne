"""Demo data: wipe the network tables and load a simulated customer base with planted mule rings.
Only reachable when NETWORK_SIMULATION_ENABLED is on."""
from __future__ import annotations

import random
from datetime import timedelta

from app.core.config import Settings
from app.core.errors import Forbidden
from app.network.application.analysis import cache
from app.network.application.ingest import add_report, ingest, set_label
from app.network.application.ports import NibssConnector
from app.network.dev.simulate import generate
from app.network.domain.engine import Analysis


def require_simulation(s: Settings) -> None:
    if not s.network_simulation_enabled:
        raise Forbidden("simulation is disabled (NETWORK_SIMULATION_ENABLED=false)")


def reset_network(uow) -> None:
    from app.network.dev.mock_obn import reset_state

    reset_state()
    uow.wipe_network()
    uow.commit()
    cache.reset()


def seed(uow, s: Settings, nibss: NibssConnector, seed: int, customers: int, rings: int) -> tuple[dict, Analysis]:
    """Generate and load the demo bank, then analyse it. Returns what was generated and the analysis."""
    g = generate(seed, customers, rings, s.network_home_bank_code)
    unique = {(x["bank_code"], x["account_no"]): x for x in g.accounts.values()}
    ingest(uow, list(unique.values()), g.transfers, s, nibss)
    label_simulated(uow, g)
    for r in g.reports:
        add_report(uow, r["kind"], r["bank_code"], r["account_no"], r["transfer_reference"], r["note"], r["reporter"])
    return {"accounts": len(unique), "transfers": len(g.transfers), "reports": len(g.reports)}, cache.run(uow)


def label_simulated(uow, gen) -> int:
    """Demo ground truth as a bank would hold it: mules confirmed 12-72 hours after they first received
    money, when complaints arrive; victims and investigated look-alikes confirmed legitimate."""
    rng = random.Random(gen.seed)
    first_in = uow.transfers.first_received_since(gen.start)
    n = 0
    for acc in uow.accounts.with_synthetic_label():
        if acc.synthetic_label == "mule":
            t = first_in.get(acc.id)
            set_label(uow, acc.id, "mule", t + timedelta(hours=rng.uniform(12, 72)) if t else None, "simulation")
        elif acc.synthetic_label in {"victim", "lookalike"}:
            set_label(uow, acc.id, "legit", None, "simulation")
        else:
            continue
        n += 1
    uow.commit()
    return n
