"""Calibration experiment: neutral vs primed framing across the panel.

Question: does Jev's probability distribution rent its ground under
priming? For each cell, both framings; seal RAW + DECISION/REFUSAL rows;
measure shift = |noul_neutral - noul_primed| per cell, and correctness
vs PANEL_TRUTH.

Claim rule (act/escalate threshold): noul >= CLAIM_Q16 -> CLAIM with
chosen class; else REFUSE with polarity=positive (restraint: the model
had the means and declined). Transport failure -> REFUSE polarity=
negative (abstention: no means) — the polarity law keeps an outage
from masquerading as honesty.

Live network required; skipped in CI (tests use canned raws).
"""
from __future__ import annotations

import sys

from . import jev, panel, receipts

CLAIM_Q16 = 9 * 6554  # ~0.9 act threshold; escalate below

ORDER = ("parse", "route", "echo", "math", "idle")
FRAMINGS = ("neutral", "primed")


def q16(x: float) -> int:
    return round(x * 65536)


def run(exercise_ids=ORDER, framings=FRAMINGS, out_path=None,
        emit=print) -> list[dict]:
    rows: list[dict] = []
    for ex_id in exercise_ids:
        for framing in framings:
            state = panel.state_for(ex_id, framing)
            try:
                raw = jev.decide_raw(state, panel.claim_questions())
            except jev.JevTransportError as exc:
                rows.append(receipts.seal_refusal(
                    jev.MODEL, ex_id, framing, f"transport:{exc}",
                    "negative", 0))
                emit(f"{ex_id}/{framing}: TRANSPORT REFUSAL ({exc})")
                continue
            rows.append(receipts.seal_raw(jev.MODEL, ex_id, framing,
                                          state, raw))
            body = __import__("json").loads(raw)
            body = body.get("body", body)
            ans = body["answers"]
            noul = q16(ans["vuln"].get("noul", 0.0))
            cls = ans["class"].get("choice", "none")
            conf = q16(ans["class"].get("confidence", 0.0))
            act = "CLAIM" if noul >= CLAIM_Q16 else "REFUSE"
            rows.append(receipts.seal_decision(jev.MODEL, ex_id, framing,
                                               noul, cls, conf, act))
            emit(f"{ex_id}/{framing}: noul={noul} class={cls} conf={conf} "
                 f"-> {act}")
            if act == "REFUSE":
                rows.append(receipts.seal_refusal(
                    jev.MODEL, ex_id, framing, "below_act_threshold",
                    "positive", noul))
    sealed = receipts.chain_rows(rows)
    ok, errors = receipts.verify_rows([dict(r) for r in sealed])
    assert ok, errors
    if out_path:
        receipts.rows_to_file(rows, out_path)
        emit(f"sealed {len(rows)} rows -> {out_path} (chain verified)")
    return rows


def calibration_table(rows: list[dict], exercise_ids=ORDER) -> list[dict]:
    """Per exercise: noul shift and truth agreement, re-derived from
    sealed rows only. Numbers are computed, never re-typed."""
    table = []
    for ex_id in exercise_ids:
        entry = {"exercise_id": ex_id, "truth": panel.PANEL_TRUTH[ex_id]}
        for framing in FRAMINGS:
            dec = next(r for r in rows
                       if r.get("kind") == "JEVLAB/DECISION"
                       and r.get("exercise_id") == ex_id
                       and r.get("framing") == framing)
            entry[f"noul_{framing}"] = dec["noul_q16"]
            entry[f"class_{framing}"] = dec["chosen_class"]
        entry["shift_q16"] = abs(entry["noul_neutral"] - entry["noul_primed"])
        entry["correct_neutral"] = (
            panel.PANEL_TRUTH[ex_id] == entry["class_neutral"]
            if panel.PANEL_TRUTH[ex_id] else entry["class_neutral"] == "none")
        table.append(entry)
    return table


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "receipts/probe-panel.jsonl"
    rows_ = run(out_path=out)
    for row in calibration_table(rows_):
        print(row)
