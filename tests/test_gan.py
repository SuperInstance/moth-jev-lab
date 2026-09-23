"""Offline tests for the GAN template-evolution loop."""
from moth_jev_lab import gan, receipts


def test_truth_by_construction():
    cands = gan.generate(0, 8)
    assert len(cands) == 8
    buggy = [c for c in cands if c["truth"] != "none"]
    clean = [c for c in cands if c["truth"] == "none"]
    assert buggy and clean  # both polarities present
    for c in cands:
        assert c["truth"] == "none" or c["truth"] == c["class"]


def test_separation_margin_sign():
    buggy = {"truth": "stack_buffer_overflow"}
    clean = {"truth": "none"}
    assert gan.separation_score(buggy) > 0  # honest hits, syc flips
    assert gan.separation_score(clean) < 0  # honest quiet, syc claims


def test_evolve_seals_verified_chain():
    rows = gan.evolve(generations=3, per_gen=6, threshold_q16=10000)
    ok, errors = receipts.verify_rows([dict(r) for r in rows])
    assert ok, errors
    kinds = [r["kind"] for r in rows]
    assert kinds.count("JEVLAB/TEMPLATE") == 18
    assert kinds.count("JEVLAB/SCORE") == 18
    # keep/refuse partition exactly
    assert kinds.count("JEVLAB/KEEP") + \
        sum(1 for r in rows if r["kind"] == "JEVLAB/REFUSAL") == 18
    # every refusal carries polarity (restraint — weak template declined)
    for r in rows:
        if r["kind"] == "JEVLAB/REFUSAL":
            assert r["polarity"] == "positive"


def test_determinism():
    a = gan.generate(2, 6)
    b = gan.generate(2, 6)
    assert a == b  # seeded generator; receipts demand determinism
