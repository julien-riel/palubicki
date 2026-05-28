import numpy as np
import pytest

from palubicki.geom.leaf_blade import (
    _outline_linear, _triangulate_fan, build_blade,
)


def _polygon_signed_area(pts: np.ndarray) -> float:
    x = pts[:, 0]
    y = pts[:, 1]
    return 0.5 * float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))


def _point_in_polygon(pt: np.ndarray, poly: np.ndarray) -> bool:
    x, y = float(pt[0]), float(pt[1])
    n = len(poly)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-30) + xi):
            inside = not inside
        j = i
    return inside


def test_linear_outline_has_4_corners():
    boundary, anchor = _outline_linear(L=1.0, W=0.2)
    assert boundary.shape == (4, 2)
    assert boundary.dtype == np.float64
    assert anchor.shape == (2,)


def test_linear_outline_bounding_box():
    boundary, _ = _outline_linear(L=1.0, W=0.2)
    assert boundary[:, 0].min() == pytest.approx(-0.1)
    assert boundary[:, 0].max() == pytest.approx(0.1)
    assert boundary[:, 1].min() == pytest.approx(0.0)
    assert boundary[:, 1].max() == pytest.approx(1.0)


def test_linear_outline_ccw():
    boundary, _ = _outline_linear(L=1.0, W=0.2)
    assert _polygon_signed_area(boundary) > 0


def test_linear_anchor_inside_polygon():
    boundary, anchor = _outline_linear(L=1.0, W=0.2)
    assert _point_in_polygon(anchor, boundary)


def test_triangulate_fan_basic_shape():
    boundary = np.array([[-0.1, 0.0], [0.1, 0.0], [0.1, 1.0], [-0.1, 1.0]],
                        dtype=np.float64)
    anchor = np.array([0.0, 0.5], dtype=np.float64)
    positions, indices = _triangulate_fan(boundary, anchor)
    # anchor at index 0, 4 boundary points at indices 1..4
    assert positions.shape == (5, 2)
    np.testing.assert_allclose(positions[0], anchor)
    # 4 triangles (one per boundary segment), 12 indices
    assert indices.shape == (12,)
    assert indices.max() < 5
    # All triangles share vertex 0 (the anchor)
    tris = indices.reshape(-1, 3)
    assert (tris[:, 0] == 0).all()


def test_triangulate_fan_covers_polygon():
    boundary = np.array([[-0.1, 0.0], [0.1, 0.0], [0.1, 1.0], [-0.1, 1.0]],
                        dtype=np.float64)
    anchor = np.array([0.0, 0.5], dtype=np.float64)
    positions, indices = _triangulate_fan(boundary, anchor)
    tri_area_sum = 0.0
    for i in range(0, len(indices), 3):
        a, b, c = positions[indices[i]], positions[indices[i+1]], positions[indices[i+2]]
        tri_area_sum += 0.5 * abs(
            (b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1])
        )
    assert tri_area_sum == pytest.approx(_polygon_signed_area(boundary), rel=1e-9)


def test_build_blade_linear_entire_returns_consistent_arrays():
    pos, norm, uv, idx = build_blade(
        length=1.0, width=0.2, shape="linear", margin="entire",
        margin_depth=0.0, margin_count=0,
    )
    assert pos.shape[0] == norm.shape[0] == uv.shape[0]
    assert pos.shape[1] == 3
    assert norm.shape[1] == 3
    assert uv.shape[1] == 2
    assert idx.shape[0] % 3 == 0
    assert int(idx.max()) < pos.shape[0]


def test_build_blade_linear_uvs_span_unit_square():
    _, _, uv, _ = build_blade(
        length=1.0, width=0.2, shape="linear", margin="entire",
        margin_depth=0.0, margin_count=0,
    )
    assert uv[:, 0].min() == pytest.approx(0.0)
    assert uv[:, 0].max() == pytest.approx(1.0)
    assert uv[:, 1].min() == pytest.approx(0.0)
    assert uv[:, 1].max() == pytest.approx(1.0)


def test_build_blade_unknown_shape_raises():
    with pytest.raises(ValueError, match="unknown leaf shape"):
        build_blade(length=1.0, width=0.2, shape="invalid", margin="entire",
                    margin_depth=0.0, margin_count=0)


def test_build_blade_unknown_margin_raises():
    with pytest.raises(ValueError, match="unknown leaf margin"):
        build_blade(length=1.0, width=0.2, shape="linear", margin="invalid",
                    margin_depth=0.0, margin_count=0)


def test_build_blade_rejects_zero_length():
    with pytest.raises(ValueError, match="length"):
        build_blade(length=0.0, width=0.2, shape="linear", margin="entire",
                    margin_depth=0.0, margin_count=0)


def test_build_blade_rejects_zero_width():
    with pytest.raises(ValueError, match="width"):
        build_blade(length=1.0, width=0.0, shape="linear", margin="entire",
                    margin_depth=0.0, margin_count=0)


def test_build_blade_rejects_margin_depth_out_of_range():
    with pytest.raises(ValueError, match="margin_depth"):
        build_blade(length=1.0, width=0.2, shape="linear", margin="entire",
                    margin_depth=1.5, margin_count=0)
    with pytest.raises(ValueError, match="margin_depth"):
        build_blade(length=1.0, width=0.2, shape="linear", margin="entire",
                    margin_depth=-0.1, margin_count=0)


def test_build_blade_rejects_negative_margin_count():
    with pytest.raises(ValueError, match="margin_count"):
        build_blade(length=1.0, width=0.2, shape="linear", margin="entire",
                    margin_depth=0.0, margin_count=-1)


from palubicki.geom.leaf_blade import (
    _outline_elliptic, _outline_lanceolate, _outline_ovate, _outline_cordate,
)


def _segments_intersect(a, b, c, d) -> bool:
    """Return True if open segments [a,b] and [c,d] properly intersect."""
    def cross(o, x, y):
        return (x[0] - o[0]) * (y[1] - o[1]) - (x[1] - o[1]) * (y[0] - o[0])
    d1 = cross(c, d, a)
    d2 = cross(c, d, b)
    d3 = cross(a, b, c)
    d4 = cross(a, b, d)
    if ((d1 > 0 and d2 < 0) or (d1 < 0 and d2 > 0)) and \
       ((d3 > 0 and d4 < 0) or (d3 < 0 and d4 > 0)):
        return True
    return False


def _is_star_shape_from(anchor: np.ndarray, boundary: np.ndarray) -> bool:
    """Every boundary vertex must have unobstructed line-of-sight to anchor."""
    n = len(boundary)
    for i in range(n):
        p = boundary[i]
        for j in range(n):
            j2 = (j + 1) % n
            if j == i or j2 == i:
                continue  # adjacent edges share p
            if _segments_intersect(anchor, p, boundary[j], boundary[j2]):
                return False
    return True


@pytest.mark.parametrize("name,fn,extra_v_range", [
    ("elliptic", _outline_elliptic, 0.0),
    ("lanceolate", _outline_lanceolate, 0.0),
    ("ovate", _outline_ovate, 0.0),
    ("cordate", _outline_cordate, 0.2),  # allow basal notch slack
])
def test_convex_outline_basic_invariants(name, fn, extra_v_range):
    boundary, anchor = fn(L=1.0, W=0.5)
    assert boundary.shape[1] == 2
    assert boundary.dtype == np.float64
    assert _polygon_signed_area(boundary) > 0, f"{name} not CCW"
    assert _point_in_polygon(anchor, boundary), f"{name} anchor not inside"
    assert _is_star_shape_from(anchor, boundary), f"{name} not star-shaped"
    # Bounding box check
    assert boundary[:, 0].min() >= -0.25 - 1e-6
    assert boundary[:, 0].max() <= 0.25 + 1e-6
    assert boundary[:, 1].min() >= -extra_v_range - 1e-6
    assert boundary[:, 1].max() <= 1.0 + 1e-6


def test_lanceolate_widest_at_lower_third():
    boundary, _ = _outline_lanceolate(L=1.0, W=0.5)
    # The widest u-coordinate should occur at v ~ L/3 (one-third).
    widest_idx = int(np.argmax(boundary[:, 0]))
    widest_v = boundary[widest_idx, 1]
    assert 0.2 < widest_v < 0.5, f"expected widest near v=L/3, got {widest_v}"


def test_ovate_broader_at_base_than_lanceolate():
    """At v = L/4, ovate should be wider than lanceolate."""
    b_ovate, _ = _outline_ovate(L=1.0, W=0.5)
    b_lanc, _ = _outline_lanceolate(L=1.0, W=0.5)
    def half_width_at(boundary, v_target):
        return max(
            abs(boundary[i, 0]) for i in range(len(boundary))
            if abs(boundary[i, 1] - v_target) < 0.1
        )
    assert half_width_at(b_ovate, 0.25) > half_width_at(b_lanc, 0.25)


def test_cordate_has_basal_notch():
    boundary, _ = _outline_cordate(L=1.0, W=0.5)
    # Notch creates a point with v < 0
    assert boundary[:, 1].min() < 0.0


@pytest.mark.parametrize("shape", ["elliptic", "lanceolate", "ovate", "cordate"])
def test_build_blade_convex_shapes_under_64_verts(shape):
    pos, _, _, _ = build_blade(
        length=1.0, width=0.5, shape=shape, margin="entire",
        margin_depth=0.0, margin_count=0,
    )
    assert pos.shape[0] <= 64
