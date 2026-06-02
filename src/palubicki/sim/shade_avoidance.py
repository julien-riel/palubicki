"""Shade-avoidance at bud initiation (#63): withhold lateral investment in shade.

The emergent behaviour lives in ``simulator._emit_node``, which uses
:func:`lateral_break_probability` to decide, per lateral, whether it breaks ACTIVE
or starts RESERVE. This module holds only the (pure, RNG-free) probability law so
it can be reasoned about and unit-tested in isolation — mirroring how
``bud_break_bias.position_weight`` is split out from the simulator.
"""
from __future__ import annotations


def lateral_break_probability(light_factor: float, strength: float) -> float:
    """Probability a lateral bud breaks ACTIVE (vs. starts RESERVE) at emission.

    ``light_factor`` in [0, 1] is the local light of the *emitting* (parent) bud
    (1 = full sun, 0 = full shade) — the new laterals have no light of their own
    until the next perception pass, so the parent's value stands in. ``strength``
    in [0, 1] is the fraction of laterals withheld at full shade.

    The law is linear in light::

        p_break = 1 - strength * (1 - light_factor)

    so:

    * ``strength == 0`` or ``light_factor == 1`` → 1.0 (every lateral breaks; the
      legacy behaviour, and the branch on which the caller draws NO RNG).
    * ``light_factor == 0`` → ``1 - strength`` (at ``strength == 1`` no lateral
      breaks in deep shade).

    The result is always in [0, 1] for inputs in [0, 1]; ``strength == 0`` is
    short-circuited to the exact 1.0 so the disabled path is float-exact.
    """
    if strength <= 0.0:
        return 1.0
    return 1.0 - strength * (1.0 - light_factor)
