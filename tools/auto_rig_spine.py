#!/usr/bin/env python3
"""
Musou2D Automatic Character Cutout & Spine 4.2 Rigging Pipeline
===============================================================
Takes a 2D character parts sheet (default: assets/raw/musou2d_hero_input.jpg,
1024x1024 JPEG with #C8C8C8 light-gray background and 17 character islands) or
a single-body character portrait (fallback proportional slicer), automatically:
  1. Removes the #C8C8C8 background via exterior flood-fill + edge color
     decontamination (preserving 100% of internal metallic/silver highlights).
  2. Separates all 17 character parts via Connected-Component Labeling plus
     automatic contour pinch-point detection & Dijkstra dark-outline seam cutting
     for any touching joints (arm_upper_r/torso, thigh_r/shin_r, thigh_l/shin_l).
  3. Trims exterior transparent margins and records original coordinates and
     anatomical joint pivots in assets/spine/parts_metadata.json.
  4. Generates Defold-compatible assets/spine/<name>.atlas, <name>.spinescene,
     and Spine 4.2 C Runtime strict-compatible <name>.spinejson with full
     skeleton hierarchy, 4 interchangeable hand attachments, 9 Musou animations,
     and 4 combat/movement events.
"""

import argparse
import heapq
import json
import math
import os
import sys
from typing import Dict, List, Tuple

import numpy as np
from PIL import Image
from scipy import ndimage


# 17 canonical part names and their anatomical joint pivots (norm_x, norm_y)
# measured from top-left (0.0, 0.0) to bottom-right (1.0, 1.0) of each trimmed part bbox.
PART_SPECS: Dict[str, Dict] = {
    "head": {
        "pivot_norm": (0.72, 0.88),
        "bone": "head",
        "slot": "head",
        "scale": 0.38,
        "rest_rotation": 0.0,
    },
    "torso": {
        "pivot_norm": (0.52, 0.90),
        "bone": "torso",
        "slot": "torso",
        "scale": 0.38,
        "rest_rotation": 0.0,
    },
    "arm_upper_r": {
        "pivot_norm": (0.76, 0.28),
        "bone": "arm_r",
        "slot": "arm_upper_r",
        "scale": 0.38,
        "rest_rotation": 0.0,
    },
    "forearm_r": {
        "pivot_norm": (0.48, 0.12),
        "bone": "forearm_r",
        "slot": "forearm_r",
        "scale": 0.38,
        "rest_rotation": 0.0,
    },
    "arm_upper_l": {
        "pivot_norm": (0.25, 0.25),
        "bone": "arm_l",
        "slot": "arm_upper_l",
        "scale": 0.38,
        "rest_rotation": 0.0,
    },
    "forearm_l": {
        "pivot_norm": (0.42, 0.16),
        "bone": "forearm_l",
        "slot": "forearm_l",
        "scale": 0.38,
        "rest_rotation": 0.0,
    },
    "hand_1": {
        "pivot_norm": (0.45, 0.86),
        "bone": "hand_l",
        "slot": "hand_l",
        "scale": 0.38,
        "rest_rotation": 0.0,
    },
    "hand_2": {
        "pivot_norm": (0.48, 0.18),
        "bone": "hand_l",
        "slot": "hand_l",
        "scale": 0.38,
        "rest_rotation": 0.0,
    },
    "hand_3": {
        "pivot_norm": (0.52, 0.18),
        "bone": "hand_l",
        "slot": "hand_l",
        "scale": 0.38,
        "rest_rotation": 0.0,
    },
    "hand_4": {
        "pivot_norm": (0.45, 0.18),
        "bone": "hand_l",
        "slot": "hand_l",
        "scale": 0.38,
        "rest_rotation": 0.0,
    },
    "waist_skirt": {
        "pivot_norm": (0.48, 0.14),
        "bone": "waist",
        "slot": "waist_skirt",
        "scale": 0.38,
        "rest_rotation": 0.0,
    },
    "thigh_r": {
        "pivot_norm": (0.58, 0.14),
        "bone": "thigh_r",
        "slot": "thigh_r",
        "scale": 0.38,
        "rest_rotation": 0.0,
    },
    "thigh_l": {
        "pivot_norm": (0.42, 0.14),
        "bone": "thigh_l",
        "slot": "thigh_l",
        "scale": 0.38,
        "rest_rotation": 0.0,
    },
    "shin_r": {
        "pivot_norm": (0.50, 0.10),
        "bone": "shin_r",
        "slot": "shin_r",
        "scale": 0.38,
        "rest_rotation": 0.0,
    },
    "shin_l": {
        "pivot_norm": (0.38, 0.10),
        "bone": "shin_l",
        "slot": "shin_l",
        "scale": 0.38,
        "rest_rotation": 0.0,
    },
    "cape": {
        "pivot_norm": (0.49, 0.06),
        "bone": "cape",
        "slot": "cape",
        "scale": 0.38,
        "rest_rotation": 0.0,
    },
    "weapon_guandao": {
        "pivot_norm": (0.62, 0.58),
        "bone": "weapon_guandao",
        "slot": "weapon_guandao",
        "scale": 0.38,
        "rest_rotation": -25.0,
    },
}

CANONICAL_PART_ORDER: List[str] = [
    "head",
    "torso",
    "arm_upper_r",
    "forearm_r",
    "arm_upper_l",
    "forearm_l",
    "hand_1",
    "hand_2",
    "hand_3",
    "hand_4",
    "waist_skirt",
    "thigh_r",
    "thigh_l",
    "shin_r",
    "shin_l",
    "cape",
    "weapon_guandao",
]


def find_dark_seam(
    lum: np.ndarray,
    fg_mask: np.ndarray,
    start_xy: Tuple[int, int],
    end_xy: Tuple[int, int],
    search_bbox: Tuple[int, int, int, int],
) -> List[Tuple[int, int]]:
    """
    Finds the minimum-luminance shortest path (tracing black ink outlines)
    between two contour pinch points using Dijkstra's algorithm.
    """
    x0, y0, x1, y1 = search_bbox
    sub_lum = lum[y0:y1, x0:x1]
    sub_fg = fg_mask[y0:y1, x0:x1]
    h, w = sub_lum.shape
    sx = int(np.clip(start_xy[0] - x0, 0, w - 1))
    sy = int(np.clip(start_xy[1] - y0, 0, h - 1))
    ex = int(np.clip(end_xy[0] - x0, 0, w - 1))
    ey = int(np.clip(end_xy[1] - y0, 0, h - 1))

    dist = np.full((h, w), np.inf, dtype=np.float64)
    parent = np.full((h, w, 2), -1, dtype=np.int32)
    dist[sy, sx] = 0.0
    pq = [(0.0, sy, sx)]
    neighbors = [
        (-1, 0, 1.0),
        (1, 0, 1.0),
        (0, -1, 1.0),
        (0, 1, 1.0),
        (-1, -1, 1.4142),
        (-1, 1, 1.4142),
        (1, -1, 1.4142),
        (1, 1, 1.4142),
    ]

    while pq:
        d, y, x = heapq.heappop(pq)
        if (y, x) == (ey, ex):
            break
        if d > dist[y, x]:
            continue
        for dy, dx, step in neighbors:
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w:
                px_cost = ((sub_lum[ny, nx] / 25.0) ** 2 + 1.0) if sub_fg[ny, nx] else 0.05
                nd = d + step * px_cost
                if nd < dist[ny, nx]:
                    dist[ny, nx] = nd
                    parent[ny, nx] = [y, x]
                    heapq.heappush(pq, (nd, ny, nx))

    path: List[Tuple[int, int]] = []
    cy, cx = ey, ex
    while cy != -1 and cx != -1:
        path.append((int(cx + x0), int(cy + y0)))
        py, px = parent[cy, cx]
        cy, cx = int(py), int(px)
    return path[::-1]


def extract_foreground_rgba(arr_rgb: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """
    Removes the #C8C8C8 light-gray background via corner-seeded exterior flood-fill
    and performs soft alpha ramp + background color decontamination at the 1-2px
    anti-aliased boundary. Preserves 100% of internal silver/metallic highlights.
    """
    h, w, _ = arr_rgb.shape
    arr_f = arr_rgb.astype(np.float32)

    # Sample background color from the 4 corners
    corners = np.concatenate(
        [
            arr_f[:16, :16].reshape(-1, 3),
            arr_f[:16, -16:].reshape(-1, 3),
            arr_f[-16:, :16].reshape(-1, 3),
            arr_f[-16:, -16:].reshape(-1, 3),
        ],
        axis=0,
    )
    bg_color = np.median(corners, axis=0)
    bg_dist = np.linalg.norm(arr_f - bg_color, axis=2)
    chroma = arr_f.max(axis=2) - arr_f.min(axis=2)

    # Candidate background pixels: close to #C8C8C8 and low saturation
    is_bg_candidate = (bg_dist <= 24.0) & (chroma <= 18.0)
    bg_labeled, _ = ndimage.label(is_bg_candidate)

    # Seed exterior background from all 4 image corners
    corner_labels = {
        int(bg_labeled[0, 0]),
        int(bg_labeled[0, w - 1]),
        int(bg_labeled[h - 1, 0]),
        int(bg_labeled[h - 1, w - 1]),
    } - {0}
    ext_bg = np.isin(bg_labeled, list(corner_labels))
    fg_mask = ~ext_bg

    # Remove tiny isolated compression speckles (< 150 px)
    lbl, num = ndimage.label(fg_mask)
    for i, sl in enumerate(ndimage.find_objects(lbl)):
        if sl is not None and int(np.sum(lbl[sl] == (i + 1))) < 150:
            fg_mask[lbl == (i + 1)] = False

    # Compute soft alpha & decontaminate 1px border against bg_color
    eroded_fg = ndimage.binary_erosion(fg_mask, iterations=1)
    border_band = fg_mask & (~eroded_fg)

    alpha = np.where(fg_mask, 255.0, 0.0).astype(np.float32)
    # Smooth alpha on the 1px outer boundary based on distance from background color
    border_alpha = np.clip((bg_dist - 14.0) / (48.0 - 14.0), 0.15, 1.0) * 255.0
    alpha[border_band] = border_alpha[border_band]

    # Color decontamination on border pixels to prevent gray fringe
    rgb_clean = arr_f.copy()
    a_norm = np.clip(alpha / 255.0, 0.15, 1.0)[..., None]
    unmixed = (arr_f - (1.0 - a_norm) * bg_color[None, None, :]) / a_norm
    rgb_clean[border_band] = np.clip(unmixed[border_band], 0.0, 255.0)

    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    rgba[..., :3] = np.round(rgb_clean).astype(np.uint8)
    rgba[..., 3] = np.round(alpha).astype(np.uint8)
    return rgba, fg_mask


def separate_17_parts(
    rgba: np.ndarray, fg_mask: np.ndarray
) -> Dict[str, Tuple[np.ndarray, Tuple[int, int, int, int]]]:
    """
    Separates the foreground mask into all 17 character part islands.
    Automatically detects compound/touching islands via contour pinch points and
    splits them along the darkest ink outline seam via Dijkstra shortest path.
    Includes a proportional anatomical fallback if given a single-body image.
    """
    h, w, _ = rgba.shape
    lum = (
        0.299 * rgba[..., 0].astype(np.float32)
        + 0.587 * rgba[..., 1].astype(np.float32)
        + 0.114 * rgba[..., 2].astype(np.float32)
    )

    lbl, num = ndimage.label(fg_mask)
    if num < 8:
        # Fallback mode for a single unified character portrait
        return _fallback_proportional_slice(rgba, fg_mask)

    seams: List[List[Tuple[int, int]]] = []
    objs = ndimage.find_objects(lbl)
    for i, sl in enumerate(objs):
        if sl is None:
            continue
        comp = lbl == (i + 1)
        if int(comp.sum()) < 200:
            continue
        y0, y1 = sl[0].start, sl[0].stop
        x0, x1 = sl[1].start, sl[1].stop
        cw, ch = x1 - x0, y1 - y0

        # Case 1: Upper-body compound island (arm_upper_r + torso touching)
        if 200 <= y0 < 300 and x0 < 100 and cw > 200:
            xs = range(x0 + 95, min(x1 - 20, x0 + 130))
            top_pinch = max(
                [(x, int(np.where(comp[y0 : y0 + 80, x])[0][0]) + y0) for x in xs],
                key=lambda t: t[1],
            )
            bot_pinch = min(
                [
                    (x, int(np.where(comp[y0 + 60 : y0 + 150, x])[0][-1]) + y0 + 60)
                    for x in xs
                ],
                key=lambda t: t[1],
            )
            seam = find_dark_seam(
                lum,
                fg_mask,
                top_pinch,
                bot_pinch,
                (max(0, x0 + 80), max(0, top_pinch[1] - 8), min(w, x0 + 145), min(h, bot_pinch[1] + 10)),
            )
            seams.append(seam)

        # Case 2: Leg compound island (thigh + shin touching at knee guard)
        elif y0 > 500 and x1 < 420 and ch > 320:
            ys = range(y0 + 190, min(y1 - 40, y0 + 230))
            left_pinch = max(
                [(int(np.where(comp[y, x0:x1])[0][0]) + x0, y) for y in ys],
                key=lambda t: t[0],
            )
            right_pinch = min(
                [(int(np.where(comp[y, x0:x1])[0][-1]) + x0, y) for y in ys],
                key=lambda t: t[0],
            )
            seam = find_dark_seam(
                lum,
                fg_mask,
                left_pinch,
                right_pinch,
                (max(0, x0), max(0, y0 + 180), min(w, x1), min(h, y0 + 240)),
            )
            seams.append(seam)

    fg_cut = fg_mask.copy()
    seam_mask = np.zeros_like(fg_mask)
    for seam in seams:
        for sx, sy in seam:
            fg_cut[max(0, sy - 1) : min(h, sy + 2), max(0, sx - 1) : min(w, sx + 2)] = False
            seam_mask[max(0, sy - 1) : min(h, sy + 2), max(0, sx - 1) : min(w, sx + 2)] = True

    cut_lbl, cut_num = ndimage.label(fg_cut)
    cut_objs = ndimage.find_objects(cut_lbl)

    islands: List[Dict] = []
    for i, sl in enumerate(cut_objs):
        if sl is None:
            continue
        mask_i = cut_lbl == (i + 1)
        area = int(mask_i.sum())
        if area < 200:
            continue
        # Restore dark outline seam pixels adjacent to this component so no outline is lost
        dilated = ndimage.binary_dilation(mask_i, iterations=2)
        mask_restored = mask_i | (dilated & seam_mask & fg_mask)
        ys, xs = np.where(mask_restored)
        bx0, by0, bx1, by1 = int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1
        islands.append(
            {
                "id": len(islands),
                "mask": mask_restored,
                "bbox": (bx0, by0, bx1, by1),
                "xc": 0.5 * (bx0 + bx1),
                "yc": 0.5 * (by0 + by1),
                "w": bx1 - bx0,
                "h": by1 - by0,
                "area": int(mask_restored.sum()),
            }
        )

    if len(islands) != 17:
        raise RuntimeError(f"Expected 17 separated islands, got {len(islands)}")

    named_parts: Dict[str, Tuple[np.ndarray, Tuple[int, int, int, int]]] = {}
    used_ids = set()

    def pop_comp(comp: Dict) -> None:
        used_ids.add(comp["id"])

    def rem() -> List[Dict]:
        return [c for c in islands if c["id"] not in used_ids]

    # 1. weapon_guandao: tall polearm on the right
    weapon_comp = max(rem(), key=lambda c: c["h"] if c["xc"] > 800 else -1)
    pop_comp(weapon_comp)
    named_parts["weapon_guandao"] = (weapon_comp["mask"], weapon_comp["bbox"])

    # 2. head: top-left island
    head_comp = min(rem(), key=lambda c: c["yc"])
    pop_comp(head_comp)
    named_parts["head"] = (head_comp["mask"], head_comp["bbox"])

    # 3. hand_1..hand_4: middle-right row of 4 small hand islands
    hand_candidates = sorted(
        [c for c in rem() if 300 < c["yc"] < 460 and c["xc"] > 440],
        key=lambda c: c["xc"],
    )
    for idx, hc in enumerate(hand_candidates[:4]):
        pop_comp(hc)
        named_parts[f"hand_{idx + 1}"] = (hc["mask"], hc["bbox"])

    # 4. Upper-body row (arm_upper_r, torso, arm_upper_l)
    upper_body = sorted(
        [c for c in rem() if c["yc"] < 420],
        key=lambda c: c["xc"],
    )
    for name, comp in zip(["arm_upper_r", "torso", "arm_upper_l"], upper_body):
        pop_comp(comp)
        named_parts[name] = (comp["mask"], comp["bbox"])

    # 5. Forearms (forearm_r, forearm_l)
    forearms = sorted(
        [c for c in rem() if c["yc"] < 540],
        key=lambda c: c["xc"],
    )
    for name, comp in zip(["forearm_r", "forearm_l"], forearms):
        pop_comp(comp)
        named_parts[name] = (comp["mask"], comp["bbox"])

    # 6. Lower-right: waist_skirt and cape
    lower_right = sorted(
        [c for c in rem() if c["xc"] >= 450],
        key=lambda c: c["xc"],
    )
    for name, comp in zip(["waist_skirt", "cape"], lower_right):
        pop_comp(comp)
        named_parts[name] = (comp["mask"], comp["bbox"])

    # 7. Remaining 4 leg islands: upper 2 are thighs (thigh_r, thigh_l), lower 2 are shins (shin_r, shin_l)
    legs_by_y = sorted(rem(), key=lambda c: c["yc"])
    thighs = sorted(legs_by_y[:2], key=lambda c: c["xc"])
    shins = sorted(legs_by_y[2:], key=lambda c: c["xc"])
    named_parts["thigh_r"] = (thighs[0]["mask"], thighs[0]["bbox"])
    named_parts["thigh_l"] = (thighs[1]["mask"], thighs[1]["bbox"])
    named_parts["shin_r"] = (shins[0]["mask"], shins[0]["bbox"])
    named_parts["shin_l"] = (shins[1]["mask"], shins[1]["bbox"])

    return named_parts


def _fallback_proportional_slice(
    rgba: np.ndarray, fg_mask: np.ndarray
) -> Dict[str, Tuple[np.ndarray, Tuple[int, int, int, int]]]:
    """Fallback proportional slicer when given a single-island portrait image."""
    h, w, _ = rgba.shape
    ys, xs = np.where(fg_mask)
    if len(xs) == 0:
        bx0, by0, bx1, by1 = 0, 0, w, h
    else:
        bx0, by0, bx1, by1 = int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1
    bw, bh = max(16, bx1 - bx0), max(16, by1 - by0)

    def box(rx0: float, ry0: float, rx1: float, ry1: float) -> Tuple[np.ndarray, Tuple[int, int, int, int]]:
        x0 = int(np.clip(bx0 + rx0 * bw, 0, w - 2))
        y0 = int(np.clip(by0 + ry0 * bh, 0, h - 2))
        x1 = int(np.clip(bx0 + rx1 * bw, x0 + 2, w))
        y1 = int(np.clip(by0 + ry1 * bh, y0 + 2, h))
        m = np.zeros((h, w), dtype=bool)
        m[y0:y1, x0:x1] = fg_mask[y0:y1, x0:x1]
        if not m.any():
            m[y0:y1, x0:x1] = True
        return m, (x0, y0, x1, y1)

    return {
        "head": box(0.25, 0.00, 0.75, 0.25),
        "torso": box(0.28, 0.24, 0.72, 0.54),
        "arm_upper_r": box(0.08, 0.24, 0.30, 0.42),
        "forearm_r": box(0.04, 0.40, 0.26, 0.58),
        "arm_upper_l": box(0.70, 0.24, 0.92, 0.42),
        "forearm_l": box(0.74, 0.40, 0.96, 0.56),
        "hand_1": box(0.76, 0.52, 0.92, 0.62),
        "hand_2": box(0.76, 0.52, 0.92, 0.62),
        "hand_3": box(0.76, 0.52, 0.92, 0.62),
        "hand_4": box(0.76, 0.52, 0.92, 0.62),
        "waist_skirt": box(0.24, 0.50, 0.76, 0.68),
        "thigh_r": box(0.26, 0.58, 0.50, 0.78),
        "thigh_l": box(0.50, 0.58, 0.74, 0.78),
        "shin_r": box(0.24, 0.76, 0.48, 1.00),
        "shin_l": box(0.52, 0.76, 0.76, 1.00),
        "cape": box(0.15, 0.26, 0.85, 0.92),
        "weapon_guandao": box(0.78, 0.05, 1.00, 0.98),
    }


def compute_attachment_entry(
    width: int,
    height: int,
    pivot_norm: Tuple[float, float],
    scale: float,
    rest_rotation: float = 0.0,
) -> Dict[str, float]:
    """
    Computes Spine 4.2 region attachment coordinates (x, y, rotation, scaleX, scaleY, width, height)
    so that the part's anatomical joint pivot sits directly at the bone origin (0, 0).
    """
    px = pivot_norm[0] * width
    py = pivot_norm[1] * height
    # Offset from pivot to image center in unrotated bone space (+X right, +Y up)
    dx = (width * 0.5 - px) * scale
    dy = (py - height * 0.5) * scale
    rad = math.radians(rest_rotation)
    cos_r = math.cos(rad)
    sin_r = math.sin(rad)
    rx = dx * cos_r - dy * sin_r
    ry = dx * sin_r + dy * cos_r
    return {
        "x": round(rx, 2),
        "y": round(ry, 2),
        "rotation": round(rest_rotation, 2),
        "scaleX": round(scale, 4),
        "scaleY": round(scale, 4),
        "width": int(width),
        "height": int(height),
    }


def build_spine_42_json(part_meta: Dict[str, Dict]) -> Dict:
    """
    Builds a Spine 4.2 C Runtime strict-compatible JSON dictionary:
      - "spine": "4.2.00"
      - "skins" is a JSON Array [ { "name": "default", "attachments": { ... } } ]
      - bone "rotate" timeline frames strictly use "value" (never "angle")
      - Full skeleton hierarchy:
        root -> hip -> torso -> head / cape / waist /
        arm_r -> forearm_r -> hand_r -> weapon_guandao /
        arm_l -> forearm_l -> hand_l (with 4 hand attachments) /
        thigh_r -> shin_r / thigh_l -> shin_l
      - 9 Musou animations + 4 events
    """
    bones = [
        {"name": "root", "x": 0.0, "y": 0.0},
        {"name": "hip", "parent": "root", "x": 0.0, "y": 122.0, "length": 20.0},
        {"name": "torso", "parent": "hip", "x": 0.0, "y": 6.0, "length": 68.0},
        {"name": "head", "parent": "torso", "x": 4.0, "y": 66.0, "length": 48.0},
        {"name": "cape", "parent": "torso", "x": -8.0, "y": 58.0, "length": 110.0},
        {"name": "waist", "parent": "torso", "x": 0.0, "y": -2.0, "length": 45.0},
        {"name": "arm_r", "parent": "torso", "x": -28.0, "y": 52.0, "length": 40.0},
        {"name": "forearm_r", "parent": "arm_r", "x": -16.0, "y": -34.0, "length": 42.0},
        {"name": "hand_r", "parent": "forearm_r", "x": 2.0, "y": -42.0, "length": 18.0},
        {"name": "weapon_guandao", "parent": "hand_r", "x": 42.0, "y": 12.0, "length": 180.0},
        {"name": "arm_l", "parent": "torso", "x": 26.0, "y": 50.0, "length": 38.0},
        {"name": "forearm_l", "parent": "arm_l", "x": 14.0, "y": -32.0, "length": 34.0},
        {"name": "hand_l", "parent": "forearm_l", "x": 8.0, "y": -26.0, "length": 20.0},
        {"name": "thigh_r", "parent": "hip", "x": -16.0, "y": -6.0, "length": 54.0},
        {"name": "shin_r", "parent": "thigh_r", "x": -4.0, "y": -52.0, "length": 58.0},
        {"name": "thigh_l", "parent": "hip", "x": 16.0, "y": -6.0, "length": 54.0},
        {"name": "shin_l", "parent": "thigh_l", "x": 6.0, "y": -52.0, "length": 58.0},
        # Architecture doc alias bones for 100% compatibility with both contracts
        {"name": "skirt", "parent": "waist", "x": 0.0, "y": 0.0, "length": 45.0},
        {"name": "arm_r_upper", "parent": "arm_r", "x": 0.0, "y": 0.0, "length": 38.0},
        {"name": "arm_r_lower", "parent": "forearm_r", "x": 0.0, "y": 0.0, "length": 36.0},
        {"name": "weapon", "parent": "weapon_guandao", "x": 0.0, "y": 0.0, "length": 160.0},
        {"name": "arm_l_upper", "parent": "arm_l", "x": 0.0, "y": 0.0, "length": 38.0},
        {"name": "arm_l_lower", "parent": "forearm_l", "x": 0.0, "y": 0.0, "length": 36.0},
        {"name": "leg_r_upper", "parent": "thigh_r", "x": 0.0, "y": 0.0, "length": 45.0},
        {"name": "leg_r_lower", "parent": "shin_r", "x": 0.0, "y": 0.0, "length": 45.0},
        {"name": "leg_l_upper", "parent": "thigh_l", "x": 0.0, "y": 0.0, "length": 45.0},
        {"name": "leg_l_lower", "parent": "shin_l", "x": 0.0, "y": 0.0, "length": 45.0},
    ]

    # Back-to-front draw order
    slots = [
        {"name": "cape", "bone": "cape", "attachment": "cape"},
        {"name": "arm_upper_l", "bone": "arm_l", "attachment": "arm_upper_l"},
        {"name": "forearm_l", "bone": "forearm_l", "attachment": "forearm_l"},
        {"name": "hand_l", "bone": "hand_l", "attachment": "hand_2"},
        {"name": "thigh_r", "bone": "thigh_r", "attachment": "thigh_r"},
        {"name": "shin_r", "bone": "shin_r", "attachment": "shin_r"},
        {"name": "thigh_l", "bone": "thigh_l", "attachment": "thigh_l"},
        {"name": "shin_l", "bone": "shin_l", "attachment": "shin_l"},
        {"name": "torso", "bone": "torso", "attachment": "torso"},
        {"name": "waist_skirt", "bone": "waist", "attachment": "waist_skirt"},
        {"name": "head", "bone": "head", "attachment": "head"},
        {"name": "arm_upper_r", "bone": "arm_r", "attachment": "arm_upper_r"},
        {"name": "weapon_guandao", "bone": "weapon_guandao", "attachment": "weapon_guandao"},
        {"name": "forearm_r", "bone": "forearm_r", "attachment": "forearm_r"},
    ]

    attachments: Dict[str, Dict[str, Dict]] = {}
    for part_name in CANONICAL_PART_ORDER:
        info = part_meta[part_name]
        spec = PART_SPECS[part_name]
        slot_name = spec["slot"]
        attachments.setdefault(slot_name, {})[part_name] = compute_attachment_entry(
            width=info["width"],
            height=info["height"],
            pivot_norm=tuple(info["pivot_norm"]),
            scale=spec["scale"],
            rest_rotation=spec["rest_rotation"],
        )

    events = {
        "hitbox_on": {"int": 10, "float": 1.0, "string": "N1"},
        "hitbox_off": {"int": 0, "float": 0.0, "string": ""},
        "footstep": {"int": 1, "float": 0.0, "string": "step"},
        "musou_burst": {"int": 1, "float": 2.5, "string": "burst"},
    }

    animations = _build_9_musou_animations()

    return {
        "skeleton": {
            "hash": "musou2d_hero_v1",
            "spine": "4.2.00",
            "x": -128,
            "y": 0,
            "width": 256,
            "height": 280,
        },
        "bones": bones,
        "slots": slots,
        "skins": [
            {
                "name": "default",
                "attachments": attachments,
            }
        ],
        "events": events,
        "animations": animations,
    }


def _rot(frames: List[Tuple[float, float]]) -> List[Dict[str, float]]:
    """Helper producing Spine 4.2 rotate timeline keyframes with 'value'."""
    return [{"time": round(t, 4), "value": round(v, 2)} for t, v in frames]


def _trans(frames: List[Tuple[float, float, float]]) -> List[Dict[str, float]]:
    """Helper producing Spine 4.2 translate timeline keyframes."""
    return [{"time": round(t, 4), "x": round(x, 2), "y": round(y, 2)} for t, x, y in frames]


def _build_9_musou_animations() -> Dict[str, Dict]:
    return {
        # 1. idle (1.20s loop): breathing rhythm, subtle cape & Guandao poise
        "idle": {
            "slots": {
                "hand_l": {"attachment": [{"time": 0.0, "name": "hand_1"}]},
            },
            "bones": {
                "hip": {
                    "translate": _trans([(0.0, 0.0, 0.0), (0.60, 0.0, 3.5), (1.20, 0.0, 0.0)]),
                },
                "torso": {
                    "rotate": _rot([(0.0, 0.0), (0.60, -2.0), (1.20, 0.0)]),
                },
                "head": {
                    "rotate": _rot([(0.0, 0.0), (0.60, 2.5), (1.20, 0.0)]),
                },
                "cape": {
                    "rotate": _rot([(0.0, 0.0), (0.60, 5.0), (1.20, 0.0)]),
                },
                "waist": {
                    "rotate": _rot([(0.0, 0.0), (0.60, 1.5), (1.20, 0.0)]),
                },
                "arm_r": {
                    "rotate": _rot([(0.0, 0.0), (0.60, 4.0), (1.20, 0.0)]),
                },
                "forearm_r": {
                    "rotate": _rot([(0.0, 0.0), (0.60, 3.0), (1.20, 0.0)]),
                },
                "weapon_guandao": {
                    "rotate": _rot([(0.0, 0.0), (0.60, -3.5), (1.20, 0.0)]),
                },
                "arm_l": {
                    "rotate": _rot([(0.0, 0.0), (0.60, -3.5), (1.20, 0.0)]),
                },
            },
        },
        # 2. run (0.60s loop): forward lean, dynamic leg stride, footstep at 0.15s & 0.45s
        "run": {
            "slots": {
                "hand_l": {"attachment": [{"time": 0.0, "name": "hand_2"}]},
            },
            "bones": {
                "hip": {
                    "translate": _trans(
                        [
                            (0.0, 0.0, 2.0),
                            (0.15, 0.0, -5.0),
                            (0.30, 0.0, 4.0),
                            (0.45, 0.0, -5.0),
                            (0.60, 0.0, 2.0),
                        ]
                    ),
                },
                "torso": {
                    "rotate": _rot([(0.0, -12.0), (0.30, -15.0), (0.60, -12.0)]),
                },
                "head": {
                    "rotate": _rot([(0.0, 10.0), (0.30, 13.0), (0.60, 10.0)]),
                },
                "cape": {
                    "rotate": _rot([(0.0, -24.0), (0.30, -32.0), (0.60, -24.0)]),
                },
                "waist": {
                    "rotate": _rot([(0.0, 6.0), (0.30, -6.0), (0.60, 6.0)]),
                },
                "thigh_l": {
                    "rotate": _rot([(0.0, 36.0), (0.30, -34.0), (0.60, 36.0)]),
                },
                "shin_l": {
                    "rotate": _rot([(0.0, -12.0), (0.15, -38.0), (0.30, -20.0), (0.60, -12.0)]),
                },
                "thigh_r": {
                    "rotate": _rot([(0.0, -34.0), (0.30, 36.0), (0.60, -34.0)]),
                },
                "shin_r": {
                    "rotate": _rot([(0.0, -20.0), (0.30, -12.0), (0.45, -38.0), (0.60, -20.0)]),
                },
                "arm_l": {
                    "rotate": _rot([(0.0, -28.0), (0.30, 28.0), (0.60, -28.0)]),
                },
                "forearm_l": {
                    "rotate": _rot([(0.0, 18.0), (0.30, 32.0), (0.60, 18.0)]),
                },
                "arm_r": {
                    "rotate": _rot([(0.0, 18.0), (0.30, -18.0), (0.60, 18.0)]),
                },
                "weapon_guandao": {
                    "rotate": _rot([(0.0, -14.0), (0.30, -6.0), (0.60, -14.0)]),
                },
            },
            "events": [
                {"time": 0.15, "name": "footstep", "int": 1, "float": 0.0, "string": "left"},
                {"time": 0.45, "name": "footstep", "int": 2, "float": 0.0, "string": "right"},
            ],
        },
        # 3. attack_1 (0.45s once): N1 horizontal Guandao sweep
        "attack_1": {
            "slots": {
                "hand_l": {
                    "attachment": [
                        {"time": 0.0, "name": "hand_3"},
                        {"time": 0.35, "name": "hand_1"},
                    ]
                }
            },
            "bones": {
                "hip": {
                    "translate": _trans([(0.0, 0.0, 0.0), (0.14, 14.0, -4.0), (0.30, 18.0, -4.0), (0.45, 0.0, 0.0)]),
                },
                "torso": {
                    "rotate": _rot([(0.0, 0.0), (0.10, 14.0), (0.18, -18.0), (0.32, -12.0), (0.45, 0.0)]),
                },
                "arm_r": {
                    "rotate": _rot([(0.0, 0.0), (0.10, 52.0), (0.18, -58.0), (0.32, -38.0), (0.45, 0.0)]),
                },
                "forearm_r": {
                    "rotate": _rot([(0.0, 0.0), (0.10, 26.0), (0.18, -32.0), (0.45, 0.0)]),
                },
                "weapon_guandao": {
                    "rotate": _rot([(0.0, 0.0), (0.10, 45.0), (0.18, -78.0), (0.32, -55.0), (0.45, 0.0)]),
                },
                "arm_l": {
                    "rotate": _rot([(0.0, 0.0), (0.14, -35.0), (0.30, 24.0), (0.45, 0.0)]),
                },
                "cape": {
                    "rotate": _rot([(0.0, 0.0), (0.18, -28.0), (0.45, 0.0)]),
                },
                "thigh_l": {
                    "rotate": _rot([(0.0, 0.0), (0.14, 22.0), (0.45, 0.0)]),
                },
            },
            "events": [
                {"time": 0.14, "name": "hitbox_on", "int": 12, "float": 1.0, "string": "N1"},
                {"time": 0.30, "name": "hitbox_off", "int": 0, "float": 0.0, "string": ""},
            ],
        },
        # 4. attack_2 (0.45s once): N2 upward rising slash
        "attack_2": {
            "slots": {
                "hand_l": {
                    "attachment": [
                        {"time": 0.0, "name": "hand_4"},
                        {"time": 0.36, "name": "hand_1"},
                    ]
                }
            },
            "bones": {
                "hip": {
                    "translate": _trans([(0.0, 0.0, -3.0), (0.14, 18.0, 5.0), (0.32, 12.0, 2.0), (0.45, 0.0, 0.0)]),
                },
                "torso": {
                    "rotate": _rot([(0.0, -12.0), (0.14, 16.0), (0.32, 8.0), (0.45, 0.0)]),
                },
                "arm_r": {
                    "rotate": _rot([(0.0, -45.0), (0.14, 64.0), (0.32, 42.0), (0.45, 0.0)]),
                },
                "forearm_r": {
                    "rotate": _rot([(0.0, -24.0), (0.14, 38.0), (0.45, 0.0)]),
                },
                "weapon_guandao": {
                    "rotate": _rot([(0.0, -65.0), (0.14, 72.0), (0.32, 48.0), (0.45, 0.0)]),
                },
                "arm_l": {
                    "rotate": _rot([(0.0, 20.0), (0.14, -42.0), (0.45, 0.0)]),
                },
                "cape": {
                    "rotate": _rot([(0.0, -15.0), (0.20, -34.0), (0.45, 0.0)]),
                },
            },
            "events": [
                {"time": 0.14, "name": "hitbox_on", "int": 15, "float": 1.2, "string": "N2"},
                {"time": 0.32, "name": "hitbox_off", "int": 0, "float": 0.0, "string": ""},
            ],
        },
        # 5. attack_3 (0.55s once): N3 wide spinning cleave
        "attack_3": {
            "slots": {
                "hand_l": {
                    "attachment": [
                        {"time": 0.0, "name": "hand_3"},
                        {"time": 0.18, "name": "hand_4"},
                        {"time": 0.45, "name": "hand_1"},
                    ]
                }
            },
            "bones": {
                "hip": {
                    "translate": _trans([(0.0, 0.0, 0.0), (0.12, -8.0, 6.0), (0.22, 26.0, -6.0), (0.55, 0.0, 0.0)]),
                },
                "torso": {
                    "rotate": _rot([(0.0, 18.0), (0.18, -26.0), (0.40, -14.0), (0.55, 0.0)]),
                },
                "arm_r": {
                    "rotate": _rot([(0.0, 72.0), (0.18, -86.0), (0.40, -48.0), (0.55, 0.0)]),
                },
                "forearm_r": {
                    "rotate": _rot([(0.0, 35.0), (0.18, -45.0), (0.55, 0.0)]),
                },
                "weapon_guandao": {
                    "rotate": _rot([(0.0, 85.0), (0.18, -110.0), (0.40, -70.0), (0.55, 0.0)]),
                },
                "cape": {
                    "rotate": _rot([(0.0, 15.0), (0.22, -48.0), (0.55, 0.0)]),
                },
                "thigh_l": {
                    "rotate": _rot([(0.0, -15.0), (0.22, 32.0), (0.55, 0.0)]),
                },
                "thigh_r": {
                    "rotate": _rot([(0.0, 15.0), (0.22, -28.0), (0.55, 0.0)]),
                },
            },
            "events": [
                {"time": 0.18, "name": "hitbox_on", "int": 22, "float": 1.6, "string": "N3"},
                {"time": 0.40, "name": "hitbox_off", "int": 0, "float": 0.0, "string": ""},
            ],
        },
        # 6. charge_attack (0.70s once): C-attack heavy leap & ground-shattering smash
        "charge_attack": {
            "slots": {
                "hand_l": {
                    "attachment": [
                        {"time": 0.0, "name": "hand_2"},
                        {"time": 0.55, "name": "hand_1"},
                    ]
                }
            },
            "bones": {
                "hip": {
                    "translate": _trans(
                        [
                            (0.0, 0.0, 0.0),
                            (0.15, -6.0, 28.0),
                            (0.24, 24.0, -10.0),
                            (0.48, 20.0, -8.0),
                            (0.70, 0.0, 0.0),
                        ]
                    ),
                },
                "torso": {
                    "rotate": _rot([(0.0, 0.0), (0.15, 22.0), (0.24, -28.0), (0.48, -18.0), (0.70, 0.0)]),
                },
                "arm_r": {
                    "rotate": _rot([(0.0, 0.0), (0.15, 88.0), (0.24, -92.0), (0.48, -68.0), (0.70, 0.0)]),
                },
                "forearm_r": {
                    "rotate": _rot([(0.0, 0.0), (0.15, 42.0), (0.24, -46.0), (0.70, 0.0)]),
                },
                "weapon_guandao": {
                    "rotate": _rot([(0.0, 0.0), (0.15, 95.0), (0.24, -120.0), (0.48, -95.0), (0.70, 0.0)]),
                },
                "cape": {
                    "rotate": _rot([(0.0, 0.0), (0.15, 28.0), (0.28, -55.0), (0.70, 0.0)]),
                },
                "thigh_l": {
                    "rotate": _rot([(0.0, 0.0), (0.15, 36.0), (0.24, -24.0), (0.70, 0.0)]),
                },
                "shin_l": {
                    "rotate": _rot([(0.0, 0.0), (0.15, -35.0), (0.24, 12.0), (0.70, 0.0)]),
                },
            },
            "events": [
                {"time": 0.22, "name": "hitbox_on", "int": 32, "float": 2.2, "string": "CHARGE"},
                {"time": 0.48, "name": "hitbox_off", "int": 0, "float": 0.0, "string": ""},
            ],
        },
        # 7. dash (0.32s once): low-center forward burst with billowing cape
        "dash": {
            "slots": {
                "hand_l": {"attachment": [{"time": 0.0, "name": "hand_1"}]},
                "cape": {
                    "rgba": [
                        {"time": 0.0, "color": "ffffffff"},
                        {"time": 0.12, "color": "88ccffdd"},
                        {"time": 0.32, "color": "ffffffff"},
                    ]
                },
            },
            "bones": {
                "hip": {
                    "translate": _trans([(0.0, 0.0, 0.0), (0.10, 22.0, -14.0), (0.22, 16.0, -10.0), (0.32, 0.0, 0.0)]),
                },
                "torso": {
                    "rotate": _rot([(0.0, 0.0), (0.10, -26.0), (0.22, -20.0), (0.32, 0.0)]),
                },
                "head": {
                    "rotate": _rot([(0.0, 0.0), (0.10, 20.0), (0.32, 0.0)]),
                },
                "cape": {
                    "rotate": _rot([(0.0, 0.0), (0.12, -58.0), (0.24, -42.0), (0.32, 0.0)]),
                },
                "arm_r": {
                    "rotate": _rot([(0.0, 0.0), (0.12, 38.0), (0.32, 0.0)]),
                },
                "weapon_guandao": {
                    "rotate": _rot([(0.0, 0.0), (0.12, 28.0), (0.32, 0.0)]),
                },
                "thigh_l": {
                    "rotate": _rot([(0.0, 0.0), (0.12, 42.0), (0.32, 0.0)]),
                },
                "thigh_r": {
                    "rotate": _rot([(0.0, 0.0), (0.12, -38.0), (0.32, 0.0)]),
                },
            },
        },
        # 8. musou_skill (1.40s once): Musou Rampage (awakening burst + 3 slash waves)
        "musou_skill": {
            "slots": {
                "hand_l": {
                    "attachment": [
                        {"time": 0.0, "name": "hand_2"},
                        {"time": 0.22, "name": "hand_3"},
                        {"time": 0.52, "name": "hand_4"},
                        {"time": 0.88, "name": "hand_2"},
                        {"time": 1.25, "name": "hand_1"},
                    ]
                }
            },
            "bones": {
                "hip": {
                    "translate": _trans(
                        [
                            (0.0, 0.0, 0.0),
                            (0.08, 0.0, 14.0),
                            (0.24, 18.0, -4.0),
                            (0.54, 24.0, 6.0),
                            (0.75, -8.0, 32.0),
                            (0.92, 32.0, -12.0),
                            (1.40, 0.0, 0.0),
                        ]
                    ),
                },
                "torso": {
                    "rotate": _rot(
                        [
                            (0.0, 0.0),
                            (0.08, 18.0),
                            (0.24, -22.0),
                            (0.54, 20.0),
                            (0.75, 26.0),
                            (0.92, -32.0),
                            (1.40, 0.0),
                        ]
                    ),
                },
                "arm_r": {
                    "rotate": _rot(
                        [
                            (0.0, 0.0),
                            (0.08, 65.0),
                            (0.24, -75.0),
                            (0.42, 55.0),
                            (0.54, -68.0),
                            (0.75, 92.0),
                            (0.92, -98.0),
                            (1.40, 0.0),
                        ]
                    ),
                },
                "forearm_r": {
                    "rotate": _rot(
                        [
                            (0.0, 0.0),
                            (0.24, -38.0),
                            (0.54, 42.0),
                            (0.75, 45.0),
                            (0.92, -48.0),
                            (1.40, 0.0),
                        ]
                    ),
                },
                "weapon_guandao": {
                    "rotate": _rot(
                        [
                            (0.0, 0.0),
                            (0.08, 75.0),
                            (0.24, -95.0),
                            (0.42, 70.0),
                            (0.54, -85.0),
                            (0.75, 105.0),
                            (0.92, -125.0),
                            (1.40, 0.0),
                        ]
                    ),
                },
                "cape": {
                    "rotate": _rot(
                        [
                            (0.0, 0.0),
                            (0.08, -42.0),
                            (0.54, -52.0),
                            (0.92, -64.0),
                            (1.40, 0.0),
                        ]
                    ),
                },
            },
            "events": [
                {"time": 0.08, "name": "musou_burst", "int": 1, "float": 2.5, "string": "burst"},
                {"time": 0.22, "name": "hitbox_on", "int": 28, "float": 2.5, "string": "MUSOU"},
                {"time": 0.38, "name": "hitbox_off", "int": 0, "float": 0.0, "string": ""},
                {"time": 0.52, "name": "hitbox_on", "int": 28, "float": 2.5, "string": "MUSOU"},
                {"time": 0.68, "name": "hitbox_off", "int": 0, "float": 0.0, "string": ""},
                {"time": 0.88, "name": "hitbox_on", "int": 28, "float": 2.5, "string": "MUSOU"},
                {"time": 1.15, "name": "hitbox_off", "int": 0, "float": 0.0, "string": ""},
            ],
        },
        # 9. hit (0.35s once): knockback stagger & recoil
        "hit": {
            "slots": {
                "hand_l": {"attachment": [{"time": 0.0, "name": "hand_1"}]},
                "torso": {
                    "rgba": [
                        {"time": 0.0, "color": "ff6666ff"},
                        {"time": 0.18, "color": "ffffffff"},
                    ]
                },
            },
            "bones": {
                "hip": {
                    "translate": _trans([(0.0, 0.0, 0.0), (0.10, -14.0, 4.0), (0.22, -10.0, 2.0), (0.35, 0.0, 0.0)]),
                },
                "torso": {
                    "rotate": _rot([(0.0, 0.0), (0.10, 20.0), (0.22, 14.0), (0.35, 0.0)]),
                },
                "head": {
                    "rotate": _rot([(0.0, 0.0), (0.10, 24.0), (0.22, 16.0), (0.35, 0.0)]),
                },
                "arm_r": {
                    "rotate": _rot([(0.0, 0.0), (0.10, 36.0), (0.35, 0.0)]),
                },
                "arm_l": {
                    "rotate": _rot([(0.0, 0.0), (0.10, -34.0), (0.35, 0.0)]),
                },
                "cape": {
                    "rotate": _rot([(0.0, 0.0), (0.12, 22.0), (0.35, 0.0)]),
                },
            },
        },
    }


def write_defold_atlas(atlas_path: str, parts_rel_dir: str, part_names: List[str]) -> None:
    """
    Writes a Defold .atlas protobuf text file without rename_patterns so each
    attachment name in .spinejson matches the exact image basename in the atlas.
    """
    lines: List[str] = []
    for name in part_names:
        img_path = f"/{parts_rel_dir.strip('/')}/{name}.png"
        lines.append("images {")
        lines.append(f'  image: "{img_path}"')
        lines.append("  sprite_trim_mode: SPRITE_TRIM_MODE_OFF")
        lines.append("}")
    lines.append("margin: 2")
    lines.append("extrude_borders: 2")
    lines.append("inner_padding: 0")
    with open(atlas_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def write_defold_spinescene(spinescene_path: str, spinejson_proj_path: str, atlas_proj_path: str) -> None:
    """Writes a Defold .spinescene protobuf text file."""
    content = (
        f'spine_json: "{spinejson_proj_path}"\n'
        f'atlas: "{atlas_proj_path}"\n'
    )
    with open(spinescene_path, "w", encoding="utf-8") as f:
        f.write(content)


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _repo_relative_path(path: str) -> str:
    """Return `path` relative to the repo root (POSIX separators) so generated
    metadata is identical regardless of who runs the pipeline or from where.
    Paths outside the repo (e.g. temp test inputs) stay absolute."""
    abs_path = os.path.abspath(path)
    try:
        rel = os.path.relpath(abs_path, REPO_ROOT)
    except ValueError:  # different drive on Windows
        return abs_path.replace(os.sep, "/")
    if rel == ".." or rel.startswith(".." + os.sep):
        return abs_path.replace(os.sep, "/")
    return rel.replace(os.sep, "/")


def run_pipeline(input_path: str, output_dir: str, name: str) -> Dict:
    if not os.path.isfile(input_path):
        raise FileNotFoundError(f"Input image not found: {input_path}")

    parts_dir = os.path.join(output_dir, "parts")
    os.makedirs(parts_dir, exist_ok=True)

    img = Image.open(input_path).convert("RGB")
    arr_rgb = np.array(img, dtype=np.uint8)
    rgba, fg_mask = extract_foreground_rgba(arr_rgb)
    separated = separate_17_parts(rgba, fg_mask)

    part_meta: Dict[str, Dict] = {}
    for part_name in CANONICAL_PART_ORDER:
        mask, (x0, y0, x1, y1) = separated[part_name]
        sub_rgba = rgba[y0:y1, x0:x1].copy()
        sub_mask = mask[y0:y1, x0:x1]
        sub_rgba[~sub_mask, 3] = 0

        out_png = os.path.join(parts_dir, f"{part_name}.png")
        Image.fromarray(sub_rgba, mode="RGBA").save(out_png)

        w = int(x1 - x0)
        h = int(y1 - y0)
        spec = PART_SPECS[part_name]
        pnorm_x, pnorm_y = spec["pivot_norm"]
        ppx_x = round(pnorm_x * w, 2)
        ppx_y = round(pnorm_y * h, 2)
        part_meta[part_name] = {
            "name": part_name,
            "file": f"parts/{part_name}.png",
            "source_bbox": [int(x0), int(y0), int(x1), int(y1)],
            "width": w,
            "height": h,
            "area_px": int(sub_mask.sum()),
            "pivot_norm": [pnorm_x, pnorm_y],
            "pivot_px": [ppx_x, ppx_y],
            "pivot_source_px": [round(x0 + ppx_x, 2), round(y0 + ppx_y, 2)],
            "bone": spec["bone"],
            "slot": spec["slot"],
        }

    meta_path = os.path.join(output_dir, "parts_metadata.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "source_image": _repo_relative_path(input_path),
                "source_size": [int(arr_rgb.shape[1]), int(arr_rgb.shape[0])],
                "part_count": len(part_meta),
                "parts": part_meta,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )

    rel_out = output_dir.strip("/").replace("\\", "/")
    atlas_path = os.path.join(output_dir, f"{name}.atlas")
    spinejson_path = os.path.join(output_dir, f"{name}.spinejson")
    spinescene_path = os.path.join(output_dir, f"{name}.spinescene")

    write_defold_atlas(atlas_path, f"{rel_out}/parts", CANONICAL_PART_ORDER)
    write_defold_spinescene(
        spinescene_path,
        f"/{rel_out}/{name}.spinejson",
        f"/{rel_out}/{name}.atlas",
    )

    spine_data = build_spine_42_json(part_meta)
    with open(spinejson_path, "w", encoding="utf-8") as f:
        json.dump(spine_data, f, indent=2, ensure_ascii=False)

    return {
        "parts_count": len(part_meta),
        "atlas": atlas_path,
        "spinejson": spinejson_path,
        "spinescene": spinescene_path,
        "metadata": meta_path,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Musou2D automatic 17-part cutout & Spine 4.2 rigging generator"
    )
    default_input = (
        "assets/raw/musou2d_hero_input.jpg"
        if os.path.exists("assets/raw/musou2d_hero_input.jpg")
        else "/tmp/musou2d_hero_input.jpg"
    )
    parser.add_argument("--input", default=default_input, help="Input sprite sheet or portrait path")
    parser.add_argument("--output-dir", default="assets/spine", help="Output Spine directory")
    parser.add_argument("--name", default="hero", help="Output asset base name")
    args = parser.parse_args()

    res = run_pipeline(args.input, args.output_dir, args.name)
    print(
        f"[auto_rig_spine] Successfully extracted {res['parts_count']} parts -> "
        f"{res['spinejson']}, {res['atlas']}, {res['spinescene']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
