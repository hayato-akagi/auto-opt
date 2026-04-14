from typing import Tuple


def apply_position(coll_x: float, coll_y: float) -> Tuple[float, float]:
    """Return effective lens shifts from commanded XY positions.

    Current implementation is a passthrough. Keep this isolated so nonlinear
    mechanics (e.g. backlash or hysteresis) can be introduced later.
    """
    return coll_x, coll_y
