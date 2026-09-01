"""The daily prescription: plan cards composed into a report.

The name is a joke with a point. A rashifal is a daily horoscope, and the
format — read your sign, get today's guidance — is genuinely the right shape for
a daily trading brief. **The format is all that is borrowed.** No astrological
input feeds any number here; every figure comes from
:mod:`nepse_trader.advisor.plan`, which reads price history. The rendered report
says so explicitly, because a report that looks like a horoscope should be
loudly clear about not being one.

Structure of a run:

* **Regime** — advancers vs decliners from the reconciled tape, so the cards are
  read in context rather than in isolation.
* **Sector of the day** — the best-performing sector by mean change, computed
  from real prices.
* **Buy cards** — the ``accumulate`` cards, best conviction first.
* **Sell queue** — held positions whose stop, target or horizon says exit, each
  with the earliest date settlement actually permits.
* **Do-not-touch** — symbols deliberately excluded, with the reason. An omission
  with a stated cause is information; a silent omission is a bug.

In AI mode an :class:`~nepse_trader.ai.Analyst` adds prose to each card and a
weekly thesis. It cannot change a number: notes are written to
:attr:`PlanCard.note` and nowhere else. If the analyst is offline, out of
budget, or returns unusable output, its banner is attached and the deterministic
report is delivered whole.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from nepse_trader.advisor.doses import (
    DOSE_HORIZONS,
    DoseReport,
    build_doses,
    save_doses,
)
from nepse_trader.advisor.journal import log_plan_cards
from nepse_trader.advisor.plan import (
    ACCUMULATE,
    REDUCE,
    PlanCard,
    Skipped,
    build_plan_cards,
)

# Horizons the CLI exposes, expressed in trading days.
HORIZONS = dict(DOSE_HORIZONS)


@dataclass
class SellCandidate:
    """A held position the engine wants out of, and why."""

    symbol: str
    quantity: int
    reference_price: float
    reason: str
    earliest_sell_date: date
    stop: float | None = None
    target: float | None = None

    def as_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "quantity": self.quantity,
            "reference_price": self.reference_price,
            "reason": self.reason,
            "earliest_sell_date": self.earliest_sell_date.isoformat(),
            "stop": self.stop,
            "target": self.target,
        }


@dataclass
class Rashifal:
    """One advisor run: the whole daily prescription."""

    run_date: date
    mode: str
    horizon: str
    online: bool
    equity: float
    regime: str = ""
    sector_of_the_day: str = ""
    cards: list[PlanCard] = field(default_factory=list)
    sell_queue: list[SellCandidate] = field(default_factory=list)
    do_not_touch: list[Skipped] = field(default_factory=list)
    breadth: dict = field(default_factory=dict)
    doses: DoseReport | None = None
    banner: str = ""
    thesis: str = ""
    generated_at: datetime | None = None
    run_id: int | None = None

    @property
    def buys(self) -> list[PlanCard]:
        return [c for c in self.cards if c.action == ACCUMULATE]

    @property
    def degraded(self) -> bool:
        return bool(self.banner)

    def as_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "run_date": self.run_date.isoformat(),
            "mode": self.mode,
            "horizon": self.horizon,
            "online": self.online,
            "equity": self.equity,
            "regime": self.regime,
            "sector_of_the_day": self.sector_of_the_day,
            "cards": [c.as_dict() for c in self.cards],
            "sell_queue": [s.as_dict() for s in self.sell_queue],
            "do_not_touch": [{"symbol": s.symbol, "reason": s.reason} for s in self.do_not_touch],
            "breadth": dict(self.breadth),
            "doses": self.doses.as_dict() if self.doses is not None else None,
            "banner": self.banner,
            "thesis": self.thesis,
            "degraded": self.degraded,
            "generated_at": (self.generated_at or datetime.now(UTC)).isoformat(),
        }


def _regime(breadth: dict) -> str:
    """Describe the tape in one phrase, from advancers vs decliners."""
    adv = breadth.get("advancers") or 0
    dec = breadth.get("decliners") or 0
    total = adv + dec
    if total == 0:
        return "no data"
    ratio = adv / total
    if ratio >= 0.65:
        return "broad advance"
    if ratio >= 0.55:
        return "mildly positive"
    if ratio <= 0.35:
        return "broad decline"
    if ratio <= 0.45:
        return "mildly negative"
    return "mixed"


def _sector_of_the_day(sectors: dict[str, list[float]]) -> str:
    """The sector with the best mean change today.

    Takes an already-grouped mapping so this stays a pure function — sector
    membership lives in config, not here.
    """
    best = ""
    best_mean = None
    for sector, changes in sectors.items():
        usable = [c for c in changes if c is not None]
        if not usable:
            continue
        mean = sum(usable) / len(usable)
        if best_mean is None or mean > best_mean:
            best, best_mean = sector, mean
    if not best:
        return "unclassified"
    return f"{best} ({best_mean:+.2f}%)"


def build_sell_queue(
    positions: dict[str, int],
    cards_by_symbol: dict[str, PlanCard],
    *,
    settlement_date_for: object,
) -> list[SellCandidate]:
    """Which held positions to exit, from the engine's own view of each symbol.

    *positions* maps symbol to quantity held; *settlement_date_for* is a callable
    taking a symbol and returning the earliest date its shares may be sold. A
    position whose card says ``reduce``, or whose price has fallen through the
    stop, is queued.
    """
    queue: list[SellCandidate] = []
    for symbol, quantity in sorted(positions.items()):
        if quantity <= 0:
            continue
        card = cards_by_symbol.get(symbol)
        if card is None:
            continue
        reason = ""
        if card.reference_price <= card.stop:
            reason = f"price {card.reference_price} at or below stop {card.stop}"
        elif card.action == REDUCE:
            reason = f"panel says reduce ({card.rationale})"
        elif card.targets and card.reference_price >= card.targets[0]:
            reason = f"price {card.reference_price} reached target {card.targets[0]}"
        if not reason:
            continue
        queue.append(
            SellCandidate(
                symbol=symbol,
                quantity=quantity,
                reference_price=card.reference_price,
                reason=reason,
                earliest_sell_date=settlement_date_for(symbol),
                stop=card.stop,
                target=card.target_1,
            )
        )
    return queue


def build_rashifal(
    *,
    symbols: list[str],
    bars_for: object,
    signals_for: object,
    equity: float,
    run_date: date,
    mode: str = "normal",
    horizon: str = "week",
    online: bool = True,
    breadth: dict | None = None,
    sectors: dict[str, list[float]] | None = None,
    positions: dict[str, int] | None = None,
    analyst: object | None = None,
    evidence_for: object | None = None,
    cost_engine: object | None = None,
    confidence_for: object | None = None,
    dose_allocations: dict[str, float] | None = None,
    max_symbols: int = 25,
    **plan_kwargs,
) -> Rashifal:
    """Compose a full run. Deterministic unless *analyst* is supplied.

    ``mode="ai"`` without an *analyst* is not an error — it produces the
    deterministic report with a banner saying the narrative was unavailable.
    That is the degradation contract: never an exception, never a fabricated
    number.
    """
    horizon_days = HORIZONS.get(horizon, HORIZONS["week"])
    chosen = symbols[:max_symbols]

    cards, skipped = build_plan_cards(
        chosen,
        bars_for,
        signals_for,
        equity=equity,
        today=run_date,
        cost_engine=cost_engine,
        horizon_days=horizon_days,
        confidence_for=confidence_for,
        **plan_kwargs,
    )
    cards.sort(key=lambda c: (-c.conviction, c.symbol))
    by_symbol = {c.symbol: c for c in cards}

    result = Rashifal(
        run_date=run_date,
        mode=mode,
        horizon=horizon,
        online=online,
        equity=equity,
        regime=_regime(breadth or {}),
        sector_of_the_day=_sector_of_the_day(sectors or {}),
        cards=cards,
        do_not_touch=skipped,
        breadth=dict(breadth or {}),
        generated_at=datetime.now(UTC),
    )

    # The selected horizon remains the primary card deck. The dose report is a
    # four-way partition over the same capital, so build the other three decks
    # with identical deterministic inputs and put every generated card in one
    # (and only one) horizon. The selected cards are reused, not rebuilt.
    dose_cards = list(cards)
    for _dose_horizon, dose_days in HORIZONS.items():
        if dose_days == horizon_days:
            continue
        other_cards, _ = build_plan_cards(
            chosen,
            bars_for,
            signals_for,
            equity=equity,
            today=run_date,
            cost_engine=cost_engine,
            horizon_days=dose_days,
            confidence_for=confidence_for,
            **plan_kwargs,
        )
        dose_cards.extend(other_cards)
    result.doses = build_doses(
        cards=dose_cards,
        equity=equity,
        run_date=run_date,
        allocation=dose_allocations,
        cost_engine=cost_engine,
    )

    if positions:
        result.sell_queue = build_sell_queue(
            positions,
            by_symbol,
            settlement_date_for=lambda s: (
                by_symbol[s].earliest_sell_date if s in by_symbol else run_date
            ),
        )
        result.doses = build_doses(
            cards=dose_cards,
            equity=equity,
            run_date=run_date,
            sell_queue=result.sell_queue,
            allocation=dose_allocations,
            cost_engine=cost_engine,
        )

    if mode != "ai":
        return result

    if analyst is None:
        result.banner = "AI narrative unavailable — no analyst configured; numbers are unaffected"
        return result

    _attach_narrative(result, analyst=analyst, evidence_for=evidence_for)
    return result


def _attach_narrative(result: Rashifal, *, analyst: object, evidence_for: object | None) -> None:
    """Ask the analyst for prose. Never let it affect a number, never let it raise.

    The analyst's own contract is that it returns ``None`` and records a
    degradation rather than raising, but this is the boundary where a broken
    narrative would otherwise cost the user their whole report — so it is belt
    and braces on purpose.
    """
    problems: list[str] = []

    for card in result.cards:
        try:
            evidence = evidence_for(card.symbol) if evidence_for else ""
            note = analyst.symbol_note(
                symbol=card.symbol, plan=_render_plan(card), evidence=evidence
            )
        except Exception as exc:  # noqa: BLE001 - narrative must never break the report
            problems.append(f"{type(exc).__name__} while writing notes")
            break
        if note is not None:
            # Only prose crosses this line — `note` is the single field the AI
            # layer may write, and nothing downstream reads a number out of it.
            card.note = _note_text(note)

    try:
        evidence = evidence_for("") if evidence_for else ""
        thesis = analyst.weekly_thesis(
            symbols=[c.symbol for c in result.cards],
            market=f"regime: {result.regime}; sector of the day: {result.sector_of_the_day}",
            evidence=evidence,
            today=result.run_date,
        )
    except Exception as exc:  # noqa: BLE001 - see above
        thesis = None
        problems.append(f"{type(exc).__name__} while writing the thesis")

    if thesis is not None:
        result.thesis = _render_thesis(thesis)

    # The analyst's own banner already collapses repeated reasons across symbols,
    # so prefer it and only add what it cannot know about: a leg that raised.
    reported = analyst.banner() if callable(getattr(analyst, "banner", None)) else ""
    if problems:
        result.banner = "AI narrative incomplete — " + "; ".join(problems)
        if reported:
            result.banner += f"; {reported}"
    elif reported:
        result.banner = reported


def _render_plan(card: PlanCard) -> str:
    """The card as text for the prompt. Read-only: the analyst sees, never sets."""
    lines = [
        f"symbol: {card.symbol}",
        f"engine action: {card.action} (conviction {card.conviction}/5)",
        f"last close: {card.reference_price}",
        f"entry zone: {card.entry_low}–{card.entry_high}",
        f"stop: {card.stop}",
        f"targets: {', '.join(str(t) for t in card.targets) or 'none'}",
        f"quantity: {card.quantity} shares over {card.horizon_days} trading days",
        f"earliest legal sell date (T+2): {card.earliest_sell_date.isoformat()}",
        f"expected net PnL at first target: {card.net_pnl}",
        f"confidence: {card.confidence.value:.2f} ({card.confidence.label})",
        f"strategy votes: {card.rationale}",
    ]
    return "\n".join(lines)


def _render_thesis(thesis: object) -> str:
    """Flatten a :class:`WeeklyThesis` into prose for the report header."""
    parts: list[str] = []
    summary = getattr(thesis, "summary", "")
    if summary:
        parts.append(str(summary).strip())
    regime = getattr(thesis, "regime", "")
    if regime:
        parts.append(f"AI read of the regime: {regime}")
    for attr, label in (
        ("focus_symbols", "Focus"),
        ("avoid_symbols", "Avoid"),
        ("key_risks", "Key risks"),
    ):
        items = getattr(thesis, attr, None)
        if items:
            parts.append(f"{label}: " + "; ".join(str(i) for i in items))
    return "\n\n".join(p for p in parts if p)


def _note_text(note: object) -> str:
    """The prose of a :class:`SymbolNote`, joined.

    ``stance`` and ``conviction`` are deliberately dropped: the card already
    carries the engine's own action and conviction, and printing a second,
    possibly-conflicting pair next to them is how a user ends up acting on the
    LLM's opinion instead of the arithmetic.
    """
    parts: list[str] = []
    thesis = getattr(note, "thesis", "")
    if thesis:
        parts.append(str(thesis).strip())
    for attr, label in (("catalysts", "Catalysts"), ("risks", "Risks")):
        items = getattr(note, attr, None)
        if items:
            parts.append(f"{label}: " + "; ".join(str(i) for i in items))
    citations = getattr(note, "citations", None)
    if citations:
        parts.append("Sources: " + " ".join(str(c) for c in citations))
    return " ".join(p for p in parts if p)


# --------------------------------------------------------------------- storage


def _link_predictions(conn, cards: list, predictions: list, card_ids: dict) -> None:
    """Point each stored ``advice_cards`` row at the prediction it produced."""
    for card, prediction in zip(cards, predictions, strict=True):
        card_id = card_ids.get((card.symbol, card.horizon_days))
        if card_id is not None:
            conn.execute(
                "UPDATE advice_cards SET prediction_id=? WHERE id=?",
                (prediction.prediction_id, card_id),
            )


def save_rashifal(conn, result: Rashifal) -> int:
    """Persist a run and its cards; returns the run id.

    Stored so a call can be scored against what actually happened. An advisor
    whose past prescriptions vanish is one nobody can audit.
    """
    generated = (result.generated_at or datetime.now(UTC)).isoformat()
    cur = conn.execute(
        """
        INSERT INTO advice_runs
            (run_date, mode, horizon, online, regime, sector_of_the_day,
             banner, equity, generated_at, sell_queue, do_not_touch, breadth,
             thesis)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            result.run_date.isoformat(),
            result.mode,
            result.horizon,
            1 if result.online else 0,
            result.regime,
            result.sector_of_the_day,
            result.banner or None,
            result.equity,
            generated,
            json.dumps([s.as_dict() for s in result.sell_queue]),
            json.dumps([{"symbol": s.symbol, "reason": s.reason} for s in result.do_not_touch]),
            json.dumps(dict(result.breadth)),
            result.thesis,
        ),
    )
    run_id = int(cur.lastrowid)
    advice_card_ids: dict[tuple[str, int], int] = {}
    for card in result.cards:
        cur = conn.execute(
            """
            INSERT INTO advice_cards
                (run_id, symbol, action, reference_price, entry_low, entry_high,
                 stop, target_1, target_2, quantity, horizon_days,
                 earliest_sell_date, gross_pnl, net_pnl, entry_cost, exit_cost,
                 capital_gains_tax, conviction, rationale, note, confidence,
                 confidence_band, confidence_basis)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                card.symbol,
                card.action,
                card.reference_price,
                card.entry_low,
                card.entry_high,
                card.stop,
                card.target_1,
                card.target_2,
                card.quantity,
                card.horizon_days,
                card.earliest_sell_date.isoformat(),
                float(card.gross_pnl),
                float(card.net_pnl),
                float(card.entry_cost),
                float(card.exit_cost),
                float(card.capital_gains_tax),
                card.conviction,
                card.rationale,
                card.note or None,
                card.confidence.value,
                card.confidence.band,
                card.confidence.basis,
            ),
        )
        advice_card_ids[(card.symbol, card.horizon_days)] = int(cur.lastrowid)

    # Journal entries are written while every call is still unknown. The dose
    # deck contains the selected horizon too, so logging the four disjoint dose
    # groups records each forecast exactly once.
    journaled: set[tuple[str, int]] = set()
    if result.doses is not None:
        for dose in result.doses.doses:
            cards = list(dose.cards)
            _link_predictions(
                conn,
                cards,
                log_plan_cards(
                    conn,
                    cards,
                    made_on=result.run_date,
                    horizon=dose.horizon,
                    run_id=run_id,
                    commit=False,
                ),
                advice_card_ids,
            )
            journaled.update((c.symbol, c.horizon_days) for c in cards)
        save_doses(conn, result.doses, run_id=run_id)
    # The deck only deploys buys, so a hold-only run assigns no cards to any
    # dose. Those cards are still forecasts, and one that was never journaled
    # can never be scored — which would leave the audit trail empty exactly
    # when the advisor said "sit tight".
    rest = [c for c in result.cards if (c.symbol, c.horizon_days) not in journaled]
    if rest:
        _link_predictions(
            conn,
            rest,
            log_plan_cards(
                conn,
                rest,
                made_on=result.run_date,
                horizon=result.horizon,
                run_id=run_id,
                commit=False,
            ),
            advice_card_ids,
        )
    conn.commit()
    result.run_id = run_id
    return run_id


def _json_or(raw: object, fallback: list | dict) -> list | dict:
    """Decode a stored JSON blob, falling back for rows written before 0014."""
    if not raw:
        return fallback
    try:
        loaded = json.loads(str(raw))
    except (TypeError, ValueError):
        return fallback
    return loaded if isinstance(loaded, type(fallback)) else fallback


def _run_row_to_dict(row, *, context: bool = False) -> dict:
    """Headline fields for a run; the surrounding context only when asked.

    ``run_history`` lists dozens of runs and would otherwise carry every sell
    queue and thesis it never displays, so the blobs are opt-in.
    """
    out = {
        "run_id": row["id"],
        "run_date": row["run_date"],
        "mode": row["mode"],
        "horizon": row["horizon"],
        "online": bool(row["online"]),
        "regime": row["regime"],
        "sector_of_the_day": row["sector_of_the_day"],
        "banner": row["banner"],
        "equity": row["equity"],
        "generated_at": row["generated_at"],
    }
    if context:
        keys = row.keys()
        out["sell_queue"] = _json_or(row["sell_queue"] if "sell_queue" in keys else None, [])
        out["do_not_touch"] = _json_or(row["do_not_touch"] if "do_not_touch" in keys else None, [])
        out["breadth"] = _json_or(row["breadth"] if "breadth" in keys else None, {})
        out["thesis"] = (row["thesis"] if "thesis" in keys else None) or ""
    return out


def latest_run(conn) -> dict | None:
    """The most recent run with its cards, or None if the advisor never ran."""
    row = conn.execute(
        "SELECT * FROM advice_runs ORDER BY generated_at DESC, id DESC LIMIT 1"
    ).fetchone()
    if row is None:
        return None
    out = _run_row_to_dict(row, context=True)
    out["cards"] = [
        dict(c)
        for c in conn.execute(
            "SELECT * FROM advice_cards WHERE run_id = ? ORDER BY conviction DESC, symbol",
            (row["id"],),
        ).fetchall()
    ]
    dose_row = conn.execute(
        "SELECT * FROM dose_runs WHERE run_id=? ORDER BY id DESC LIMIT 1",
        (row["id"],),
    ).fetchone()
    if dose_row is not None:
        out["doses"] = dict(dose_row)
        out["doses"]["doses"] = [
            dict(dose)
            for dose in conn.execute(
                "SELECT * FROM doses WHERE dose_run_id=? ORDER BY id",
                (dose_row["id"],),
            ).fetchall()
        ]
    else:
        out["doses"] = None
    return out


def run_history(conn, limit: int = 30) -> list[dict]:
    """Recent runs, newest first, without their cards."""
    rows = conn.execute(
        "SELECT * FROM advice_runs ORDER BY generated_at DESC, id DESC LIMIT ?",
        (max(1, limit),),
    ).fetchall()
    return [_run_row_to_dict(r) for r in rows]
