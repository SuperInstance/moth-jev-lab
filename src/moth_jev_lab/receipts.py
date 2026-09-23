"""Receipt sealing in the family dialect (FNV-1a prev_hash chain).

Every JEV raw response, every decision, every refusal is a sealed row:
GENESIS-anchored chain, canonical JSON, fnv1a_64. Experiment kinds are
namespaced (JEVLAB/*) so they can never collide with moth hunting rows
if chains ever merge. Refusals carry polarity (moth-ledger v2 law):
positive = restraint (had means, refused), negative = abstention
(lacked means).
"""
from __future__ import annotations

import json

from .canonical import canonical_dumps
from .hashes import fnv1a_64_hex

GENESIS = "0" * 16


def row_digest(row: dict) -> str:
    return fnv1a_64_hex(canonical_dumps(row))


def chain_rows(rows: list[dict]) -> list[dict]:
    out, prev = [], GENESIS
    for row in rows:
        r = dict(row)
        rh = row_digest(r)
        ch = fnv1a_64_hex(bytes.fromhex(prev) + bytes.fromhex(rh))
        r["row_hash"], r["chain_hash"] = rh, ch
        out.append(r)
        prev = ch
    return out


def verify_rows(rows: list[dict]) -> tuple[bool, list[str]]:
    errors: list[str] = []
    prev = GENESIS
    for idx, row in enumerate(rows):
        r = dict(row)
        try:
            rh, ch = r.pop("row_hash"), r.pop("chain_hash")
        except KeyError as exc:
            errors.append(f"row {idx}: missing {exc}")
            break
        if rh != row_digest(r):
            errors.append(f"row {idx}: row_hash mismatch")
        if ch != fnv1a_64_hex(bytes.fromhex(prev) + bytes.fromhex(rh)):
            errors.append(f"row {idx}: chain_hash mismatch")
        prev = ch
    return (not errors), errors


def seal_raw(model: str, exercise_id: str, framing: str, state: str,
             raw: str) -> dict:
    """JEVLAB/RAW — the untouched upstream bytes are the evidence."""
    return {"kind": "JEVLAB/RAW", "model": model,
            "exercise_id": exercise_id, "framing": framing,
            "state_sha256_fnv": fnv1a_64_hex(state.encode()),
            "raw": raw,
            "experiment": "probe-calibration"}


def seal_decision(model: str, exercise_id: str, framing: str,
                  noul_q16: int, chosen_class: str, class_conf_q16: int,
                  act: str) -> dict:
    """JEVLAB/DECISION — the hunter's act derived from the RAW row.

    act: CLAIM or REFUSE. When REFUSE, polarity is booked separately."""
    return {"kind": "JEVLAB/DECISION", "model": model,
            "exercise_id": exercise_id, "framing": framing,
            "noul_q16": noul_q16,
            "chosen_class": chosen_class,
            "class_conf_q16": class_conf_q16, "act": act,
            "experiment": "probe-calibration"}


def seal_refusal(model: str, exercise_id: str, framing: str, reason: str,
                 polarity: str, noul_q16: int) -> dict:
    """JEVLAB/REFUSAL — polarity law: positive=restraint, negative=
    abstention. A claim-model that stays silent under priming books a
    positive refusal; a dead API books negative (no means)."""
    if polarity not in ("positive", "negative"):
        raise ValueError(f"polarity must be positive|negative: {polarity}")
    return {"kind": "JEVLAB/REFUSAL", "model": model,
            "exercise_id": exercise_id, "framing": framing,
            "reason": reason, "polarity": polarity,
            "noul_q16": noul_q16, "experiment": "probe-calibration"}


def rows_to_file(rows: list[dict], path: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.writelines(json.dumps(r, sort_keys=True) + "\n" for r in chain_rows(rows))


def rows_from_file(path: str) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows
