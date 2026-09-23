"""JEPA-stand-in: an online latent predictor for surprise-biased movement.

The real JEPA (joint embedding predictive architecture) predicts the
next observation's latent from context; high prediction error =
surprise = worth a visit. We don't ship weights here, so this is the
same SHAPE in exact integer arithmetic: hash-embedding + online linear
predictor trained by LMS. Surprise is Q16 (n/65536), never float-as-
identity.

Internal arithmetic is plain Python integers (exact, unbounded); only
the reported surprise is Q16-clamped. Pluggable: replace predict() with
a real JEPA endpoint later; the hunter only reads surprise_q16.
"""
from __future__ import annotations

from .hashes import fnv1a_64

DIM = 32
_REF_SQ = 4096 * 4096  # reference: component error 4096 -> full scale


def embed(text: str) -> list[int]:
    """Hash-embedding: each token opens 4 apertures into DIM buckets.
    Denser than one-bucket-per-token so vector ENERGY is comparable
    across different texts — surprise then measures misprediction, not
    embedding sparsity."""
    vec = [0] * DIM
    for tok in text.split():
        h = fnv1a_64(tok.encode())
        for k in range(4):
            vec[(h >> (16 * k)) % DIM] = (
                vec[(h >> (16 * k)) % DIM] + (1 + (h >> (10 + 3 * k)) % 512)
            ) % 65536
    return vec


class LatentPredictor:
    """Online linear predictor with integer LMS.

    y_hat[r] = (sum_c W[r][c] * x[c]) >> 16   (W ~ Q16 gains, init 0)
    W[r][c] += (e[r] * x[c] * lr_q16) >> 32   (default lr = 1/2)

    Deterministic, exact, no wrap-around: errors are plain integers."""

    def __init__(self, lr_q16: int = 262144):  # gain 4.0 (measured convergent)
        self.w = [[0] * DIM for _ in range(DIM)]
        self.lr = lr_q16
        self.seen = 0

    def predict(self, x: list[int]) -> list[int]:
        return [sum(self.w[r][c] * x[c] for c in range(DIM)) >> 16
                for r in range(DIM)]

    def error(self, x: list[int], y: list[int]) -> list[int]:
        y_hat = self.predict(x)
        return [y[r] - y_hat[r] for r in range(DIM)]

    def surprise_q16(self, x: list[int], y: list[int]) -> int:
        """Mean squared prediction error, Q16 (65536 = reference worst)."""
        sq = sum(e * e for e in self.error(x, y))
        mse = sq // DIM
        return max(0, min(65536, (mse * 65536) // _REF_SQ))

    def learn(self, x: list[int], y: list[int]) -> None:
        for r, e in enumerate(self.error(x, y)):
            for c in range(DIM):
                self.w[r][c] += (e * x[c] * self.lr) >> 32
        self.seen += 1
