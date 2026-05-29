import numpy as np
import pytest

from palubicki.geom.leaf_blade import (
    _outline_linear,
    _triangulate_fan,
    build_blade,
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
    _outline_cordate,
    _outline_elliptic,
    _outline_lanceolate,
    _outline_ovate,
)


def _segments_intersect(a, b, c, d) -> bool:
    """Return True if open segments [a,b] and [c,d] properly intersect."""
    def cross(o, x, y):
        return (x[0] - o[0]) * (y[1] - o[1]) - (x[1] - o[1]) * (y[0] - o[0])
    d1 = cross(c, d, a)
    d2 = cross(c, d, b)
    d3 = cross(a, b, c)
    d4 = cross(a, b, d)
    return bool((d1 > 0 and d2 < 0 or d1 < 0 and d2 > 0) and (d3 > 0 and d4 < 0 or d3 < 0 and d4 > 0))


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


from palubicki.geom.leaf_blade import _outline_palmate


def test_palmate_outline_invariants():
    boundary, anchor = _outline_palmate(L=1.0, W=1.0)
    assert boundary.shape[1] == 2
    assert _polygon_signed_area(boundary) > 0
    assert _point_in_polygon(anchor, boundary)
    assert _is_star_shape_from(anchor, boundary)


def test_palmate_has_five_radial_peaks():
    """A palmate outline should have 5 local maxima in radial distance from anchor."""
    boundary, anchor = _outline_palmate(L=1.0, W=1.0)
    radii = np.linalg.norm(boundary - anchor, axis=1)
    # Count local maxima (compare to both neighbors with wraparound).
    n = len(radii)
    peaks = 0
    for i in range(n):
        if radii[i] > radii[(i - 1) % n] and radii[i] > radii[(i + 1) % n]:
            peaks += 1
    assert peaks == 5, f"expected 5 lobe peaks, got {peaks}"


def test_palmate_under_64_verts():
    pos, _, _, _ = build_blade(
        length=1.0, width=1.0, shape="palmate", margin="entire",
        margin_depth=0.0, margin_count=0,
    )
    assert pos.shape[0] <= 64


from palubicki.geom.leaf_blade import _apply_margin


def test_apply_margin_entire_is_noop():
    b, _ = _outline_ovate(L=1.0, W=0.5)
    b_out = _apply_margin(b, "entire", 0.1, 5, "ovate", 1.0, 0.5)
    np.testing.assert_array_equal(b, b_out)


def test_apply_margin_zero_count_is_noop():
    b, _ = _outline_ovate(L=1.0, W=0.5)
    b_out = _apply_margin(b, "serrate", 0.1, 0, "ovate", 1.0, 0.5)
    np.testing.assert_array_equal(b, b_out)


def test_apply_margin_serrate_adds_2N_verts():
    b, _ = _outline_ovate(L=1.0, W=0.5)
    b_out = _apply_margin(b, "serrate", 0.08, 8, "ovate", 1.0, 0.5)
    assert b_out.shape[0] == b.shape[0] + 2 * 8


def test_apply_margin_dentate_adds_2N_verts():
    b, _ = _outline_ovate(L=1.0, W=0.5)
    b_out = _apply_margin(b, "dentate", 0.08, 6, "ovate", 1.0, 0.5)
    assert b_out.shape[0] == b.shape[0] + 2 * 6


def test_apply_margin_lobed_increases_boundary_variance():
    b, _ = _outline_ovate(L=1.0, W=0.5)
    b_lobed = _apply_margin(b, "lobed", 0.35, 5, "ovate", 1.0, 0.5)
    radii_smooth = np.linalg.norm(b - b.mean(axis=0), axis=1)
    radii_lobed = np.linalg.norm(b_lobed - b_lobed.mean(axis=0), axis=1)
    assert radii_lobed.var() > radii_smooth.var()


def test_apply_margin_serrate_teeth_point_forward():
    """For serrate, peak verts should have higher mean v than valley verts."""
    b, _ = _outline_ovate(L=1.0, W=0.5)
    b_out = _apply_margin(b, "serrate", 0.08, 8, "ovate", 1.0, 0.5)
    # New verts are inserted in pairs (valley, peak) — find them by diffing.
    # Easier: re-run with depth=0 to get same count but no perturbation, then
    # compare. With depth=0 the inserted verts coincide with the midpoints.
    b_flat = _apply_margin(b, "serrate", 0.0, 8, "ovate", 1.0, 0.5)
    # Verts that moved are the toothed ones; pair them up by index parity.
    # We expect 8 valleys + 8 peaks. By construction (valley before peak in
    # insertion order), even-indexed extras are valleys, odd-indexed are peaks.
    diff = np.linalg.norm(b_out - b_flat, axis=1)
    moved_idx = np.where(diff > 1e-9)[0]
    valleys_v = b_out[moved_idx[0::2], 1]
    peaks_v = b_out[moved_idx[1::2], 1]
    assert peaks_v.mean() > valleys_v.mean()


def test_apply_margin_lobed_lower_count_than_serrate():
    """Lobed defaults bias toward fewer, deeper teeth.
    This test just checks that lobed with depth=0.35, count=5 produces an
    outline whose radial-max-minus-radial-min is larger than serrate's at
    depth=0.05, count=15 (same total insertions)."""
    b, _ = _outline_ovate(L=1.0, W=0.5)
    b_lobed = _apply_margin(b, "lobed", 0.35, 5, "ovate", 1.0, 0.5)
    b_serr = _apply_margin(b, "serrate", 0.05, 15, "ovate", 1.0, 0.5)
    def radial_range(b):
        c = b.mean(axis=0)
        r = np.linalg.norm(b - c, axis=1)
        return r.max() - r.min()
    assert radial_range(b_lobed) > radial_range(b_serr)


def test_build_blade_ovate_serrate_birch_under_64():
    pos, _, _, _ = build_blade(
        length=1.0, width=0.7, shape="ovate", margin="serrate",
        margin_depth=0.08, margin_count=12,
    )
    assert pos.shape[0] <= 64


def test_build_blade_ovate_lobed_oak_under_64():
    pos, _, _, _ = build_blade(
        length=1.0, width=0.7, shape="ovate", margin="lobed",
        margin_depth=0.35, margin_count=7,
    )
    assert pos.shape[0] <= 64
