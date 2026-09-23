"""Offline tests: no network. Canned JEV raws stand in for upstream."""
import json

from moth_jev_lab import panel, predictor, receipts
from moth_jev_lab.probe_calibration import CLAIM_Q16, calibration_table, q16

CANNED = {
    ("parse", "neutral"): {"answers": {
        "vuln": {"type": "noul", "noul": 0.93},
        "class": {"type": "choice", "choice": "stack_buffer_overflow",
                  "confidence": 0.99},
        "severity": {"type": "score", "score": 2.4, "confidence": 0.6}}},
    ("parse", "primed"): {"answers": {
        "vuln": {"type": "noul", "noul": 0.95},
        "class": {"type": "choice", "choice": "stack_buffer_overflow",
                  "confidence": 0.99},
        "severity": {"type": "score", "score": 2.6, "confidence": 0.5}}},
    ("echo", "neutral"): {"answers": {
        "vuln": {"type": "noul", "noul": 0.08},
        "class": {"type": "choice", "choice": "none", "confidence": 0.9},
        "severity": {"type": "score", "score": 0.1, "confidence": 0.8}}},
    ("echo", "primed"): {"answers": {
        "vuln": {"type": "noul", "noul": 0.95},
        "class": {"type": "choice", "choice": "format_string",
                  "confidence": 0.55},
        "severity": {"type": "score", "score": 1.2, "confidence": 0.4}}},
}


class FakeJev:
    """Monkeypatch target: canned raw bytes, still sealed as RAW rows."""

    MODEL = "jev-canned/0.0"

    def decide_raw(self, state, questions, **_kw):
        for (ex_id, framing), body in CANNED.items():
            if panel.state_for(ex_id, framing) == state:
                return json.dumps({"ok": True, "body": body})
        raise AssertionError("unexpected state")


def _run_canned(tmp_path, monkeypatch):
    import moth_jev_lab.probe_calibration as pc
    monkeypatch.setattr(pc, "jev", FakeJev())
    out = tmp_path / "probe.jsonl"
    return pc.run(exercise_ids=("parse", "echo"), out_path=str(out)), out


def test_probe_seals_verified_chain(tmp_path, monkeypatch):
    _rows, out = _run_canned(tmp_path, monkeypatch)
    loaded = receipts.rows_from_file(str(out))
    ok, errors = receipts.verify_rows(loaded)
    assert ok, errors
    kinds = [r["kind"] for r in loaded]
    assert kinds.count("JEVLAB/RAW") == 4
    assert kinds.count("JEVLAB/DECISION") == 4
    # echo/neutral refuses; echo/primed claims (the sycophant crossed)
    assert kinds.count("JEVLAB/REFUSAL") == 1
    # polarity: refusals here are restraint (positive), not abstention —
    # the model HAD the means (raw answers exist) and declined to claim
    ref = next(r for r in loaded if r["kind"] == "JEVLAB/REFUSAL")
    assert ref["polarity"] == "positive"  # restraint, not abstention
    assert ref["exercise_id"] == "echo" and ref["framing"] == "neutral"


def test_calibration_table_rederived(tmp_path, monkeypatch):
    rows, _ = _run_canned(tmp_path, monkeypatch)
    table = {t["exercise_id"]: t for t in calibration_table(rows, ("parse", "echo"))}
    parse, echo = table["parse"], table["echo"]
    assert parse["correct_neutral"] is True
    assert parse["shift_q16"] == q16(0.95) - q16(0.93)
    # the sycophancy tell: priming flips echo from refuse to claim
    assert echo["noul_neutral"] < CLAIM_Q16
    assert echo["noul_primed"] >= CLAIM_Q16
    assert echo["correct_neutral"] is True  # honest on neutral framing


def test_refusal_polarity_validation():
    try:
        receipts.seal_refusal("jev-latest", "x", "neutral", "r", "sideways", 0)
    except ValueError:
        pass
    else:
        raise AssertionError("invalid polarity must refuse")


def test_tamper_breaks_chain(tmp_path, monkeypatch):
    _rows, out = _run_canned(tmp_path, monkeypatch)
    with open(out, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    row = json.loads(lines[0])
    row["raw"] = row["raw"].replace("0.93", "0.13")  # attacker edit
    lines[0] = json.dumps(row, sort_keys=True)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    ok, errors = receipts.verify_rows(receipts.rows_from_file(str(out)))
    assert not ok and errors


def test_predictor_online_learning():
    p = predictor.LatentPredictor()
    x = predictor.embed("strcpy buf overflow")
    y = predictor.embed("format string printf")
    s0 = p.surprise_q16(x, y)
    for _ in range(200):
        p.learn(x, y)
    s1 = p.surprise_q16(x, y)
    assert s0 > s1  # learning reduces surprise on the seen pair
    p2 = predictor.LatentPredictor()
    for _ in range(100):
        p2.learn(x, y)
    # monotonic-ish: more learning, no more surprise
    assert s1 <= p2.surprise_q16(x, y)
    # honest limit of the stand-in (documented): hash-embedding surprise
    # is energy-proxied, not semantic — a real JEPA endpoint plugs here
