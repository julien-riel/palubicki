"""Bit-identical fast paths for 3-vector cross product and norm.

``numpy.cross`` and ``numpy.linalg.norm`` carry large per-call Python dispatch
overhead (``normalize_axis_tuple`` / ``moveaxis`` / ``isComplexType`` …) that
dominates the simulator's hot loops, where they are called on plain length-3
``float64`` vectors millions of times per run. These helpers compute the SAME
floating-point result with none of that overhead.

Bit-exactness (verified on 50k random vectors, see the perf pass):

* ``cross3(a, b)`` == ``numpy.cross(a, b)`` for length-3 inputs — the cross
  product is three ``x*y - z*w`` terms with no summation reassociation, so the
  IEEE result is identical.
* ``norm3(v)`` == ``float(numpy.linalg.norm(v))`` for length-3 inputs —
  ``numpy.linalg.norm`` of a real 1-D vector reduces to ``sqrt(v·v)`` with the
  dot accumulated low-to-high index, which ``math.sqrt`` of the same in-order
  sum reproduces exactly.

These are drop-in replacements ONLY for the length-3 case; do not use them for
batched/ND inputs (use the dedicated batched code paths there).
"""
from __future__ import annotations

import math

import numpy as np


def cross3(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Cross product of two length-3 vectors. Bit-identical to ``np.cross``."""
    a0, a1, a2 = float(a[0]), float(a[1]), float(a[2])
    b0, b1, b2 = float(b[0]), float(b[1]), float(b[2])
    return np.array([
        a1 * b2 - a2 * b1,
        a2 * b0 - a0 * b2,
        a0 * b1 - a1 * b0,
    ], dtype=np.float64)


def norm3(v: np.ndarray) -> float:
    """Euclidean norm of a length-3 vector. Bit-identical to ``float(np.linalg.norm(v))``."""
    v0, v1, v2 = float(v[0]), float(v[1]), float(v[2])
    return math.sqrt(v0 * v0 + v1 * v1 + v2 * v2)


def cross3_batch(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Row-wise cross product of two ``(N, 3)`` arrays. Bit-identical to
    ``np.cross(a, b)`` (each component is one ``x*y - z*w`` term, no reassociation)
    but without np.cross's per-call ``normalize_axis_tuple`` / ``moveaxis`` dispatch
    overhead — which dominates when called once per rendered leaf blade."""
    a0, a1, a2 = a[:, 0], a[:, 1], a[:, 2]
    b0, b1, b2 = b[:, 0], b[:, 1], b[:, 2]
    out = np.empty_like(a)
    out[:, 0] = a1 * b2 - a2 * b1
    out[:, 1] = a2 * b0 - a0 * b2
    out[:, 2] = a0 * b1 - a1 * b0
    return out
