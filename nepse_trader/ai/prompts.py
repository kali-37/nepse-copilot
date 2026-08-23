"""Prompt templates as plain strings.

Kept out of the modules that use them for one reason: a prompt is the part most
likely to need tuning, and having it as an importable constant means a test can
assert on the exact text rather than on a model's mood.

Every template shares :data:`GROUND_RULES`, which states the constraint the whole
design rests on — the model is commentating on numbers that have already been
computed and may not restate, adjust or invent any of them. That rule is in the
prompt *and* enforced by the schemas, because a prompt is a request and a schema
is a guarantee.
"""

from __future__ import annotations

SYSTEM = (
    "You are a disciplined equity analyst covering the Nepal Stock Exchange "
    "(NEPSE). You read supplied evidence and write concise, hedged, decision-useful "
    "commentary. You never invent numbers and you never give financial advice as "
    "certainty."
)

GROUND_RULES = """\
Ground rules — these are absolute:
1. Every price, stop, target, position size and date has already been computed by a
   deterministic engine. Do not restate, adjust, recompute or invent any of them.
2. Use ONLY the evidence given below. If the evidence does not support a claim, say
   the evidence is thin instead of filling the gap.
3. Cite the evidence markers ([E1], [E2], ...) that support each claim.
4. NEPSE settles T+2: shares bought today cannot be sold tomorrow. Never suggest
   otherwise.
5. Reply with a single JSON object and nothing else. No prose before or after it, no
   code fence."""

SYMBOL_NOTE = """\
{ground_rules}

Symbol: {symbol}
Deterministic plan already computed for it:
{plan}

Evidence:
{evidence}

Write the narrative layer for this symbol as JSON with exactly these keys:
  "stance": one of "accumulate", "hold", "reduce", "avoid"
  "conviction": integer 1-5, where 1 is a guess and 5 is well-evidenced
  "thesis": 2-4 sentences on why, referencing the evidence markers
  "catalysts": array of up to 4 short strings — what could make this work
  "risks": array of up to 4 short strings — what could make it fail
  "citations": array of the evidence markers you used

Your stance is commentary on the plan above, not a replacement for it. If the
evidence contradicts the plan, say so in "thesis" and lower "conviction"."""

WEEKLY_THESIS = """\
{ground_rules}

This is the weekly pass for ISO week {week}. It is expensive and runs rarely, so be
substantive. Daily runs will reuse it.

Market state:
{market}

Symbols under coverage: {symbols}

Evidence:
{evidence}

Write the week's posture as JSON with exactly these keys:
  "regime": one short phrase for the market regime (e.g. "range-bound, thin volume")
  "summary": 4-6 sentences on what matters this week and why
  "focus_symbols": array of symbols worth attention, best first
  "avoid_symbols": array of symbols to leave alone this week
  "key_risks": array of up to 5 short strings — what would invalidate this posture
  "citations": array of the evidence markers you used

Only name symbols that appear in the coverage list above."""

CRITIQUE = """\
{ground_rules}

Below is a complete trading plan produced by the deterministic engine. Argue
against it. Your job is to find what it is blind to, not to agree with it.

Plan:
{plan}

Evidence:
{evidence}

Reply as JSON with exactly these keys:
  "verdict": one of "agree", "disagree", "mixed"
  "concerns": array of up to 5 specific objections, each tied to evidence
  "missing_evidence": array of up to 5 things you would need to know to be confident
  "citations": array of the evidence markers you used

Do not propose different prices, stops, targets or sizes — you may only say why the
existing ones might be wrong."""

PING = 'Reply with exactly this JSON and nothing else: {"ok": true}'


def symbol_note_prompt(*, symbol: str, plan: str, evidence: str) -> str:
    return SYMBOL_NOTE.format(
        ground_rules=GROUND_RULES,
        symbol=symbol,
        plan=plan.strip() or "(no plan supplied)",
        evidence=evidence.strip() or "(no evidence available)",
    )


def weekly_thesis_prompt(*, week: str, market: str, symbols: list[str], evidence: str) -> str:
    return WEEKLY_THESIS.format(
        ground_rules=GROUND_RULES,
        week=week,
        market=market.strip() or "(no market summary supplied)",
        symbols=", ".join(symbols) or "(none)",
        evidence=evidence.strip() or "(no evidence available)",
    )


def critique_prompt(*, plan: str, evidence: str) -> str:
    return CRITIQUE.format(
        ground_rules=GROUND_RULES,
        plan=plan.strip() or "(no plan supplied)",
        evidence=evidence.strip() or "(no evidence available)",
    )
