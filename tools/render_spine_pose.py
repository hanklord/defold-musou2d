#!/usr/bin/env python3
"""Offline Spine 4.2 pose renderer (region attachments, rotate/translate/scale
timelines, attachment timelines, linear interpolation) for visual QA of the
auto-rigged hero without launching the engine.

Usage: python3 tools/render_spine_pose.py <spinejson> <parts_dir> <out.png> [anim[:time] ...]
Draws each requested pose side by side (default: setup pose), with bone
origins marked when --bones is passed.
"""
import json
import math
import os
import sys

from PIL import Image, ImageDraw


def _sample(keys, t, fields):
    if not keys:
        return None
    if t <= keys[0].get("time", 0.0):
        k = keys[0]
        return [k.get(f, 0.0) for f in fields]
    for a, b in zip(keys, keys[1:]):
        ta, tb = a.get("time", 0.0), b.get("time", 0.0)
        if ta <= t <= tb:
            u = 0.0 if tb == ta else (t - ta) / (tb - ta)
            return [a.get(f, 0.0) + (b.get(f, 0.0) - a.get(f, 0.0)) * u for f in fields]
    k = keys[-1]
    return [k.get(f, 0.0) for f in fields]


def _mat(x, y, rot, sx, sy):
    c, s = math.cos(math.radians(rot)), math.sin(math.radians(rot))
    return [c * sx, -s * sy, x, s * sx, c * sy, y]


def _mul(p, c):
    return [
        p[0] * c[0] + p[1] * c[3], p[0] * c[1] + p[1] * c[4], p[0] * c[2] + p[1] * c[5] + p[2],
        p[3] * c[0] + p[4] * c[3], p[3] * c[1] + p[4] * c[4], p[3] * c[2] + p[4] * c[5] + p[5],
    ]


def pose(skel, anim=None, t=0.0):
    a = skel["animations"].get(anim, {}) if anim else {}
    ab = a.get("bones", {})
    world = {}
    for b in skel["bones"]:
        x, y = b.get("x", 0.0), b.get("y", 0.0)
        rot = b.get("rotation", 0.0)
        sx, sy = b.get("scaleX", 1.0), b.get("scaleY", 1.0)
        tl = ab.get(b["name"], {})
        r = _sample(tl.get("rotate"), t, ["value"])
        if r:
            rot += r[0]
        tr = _sample(tl.get("translate"), t, ["x", "y"])
        if tr:
            x += tr[0]
            y += tr[1]
        sc = _sample(tl.get("scale"), t, ["x", "y"])
        if sc:
            sx *= sc[0] if "x" in tl["scale"][0] else 1.0
            sy *= sc[1] if "y" in tl["scale"][0] else 1.0
        local = _mat(x, y, rot, sx, sy)
        world[b["name"]] = _mul(world[b["parent"]], local) if b.get("parent") else local
    attach = {sl["name"]: sl.get("attachment") for sl in skel["slots"]}
    for sname, tl in a.get("slots", {}).items():
        keys = [k for k in tl.get("attachment", []) if k.get("time", 0.0) <= t + 1e-9]
        if keys:
            attach[sname] = keys[-1].get("name")
    return world, attach


def render(skel, parts_dir, anim=None, t=0.0, size=(320, 340), origin=(160, 320), bones=False):
    world, attach = pose(skel, anim, t)
    canvas = Image.new("RGBA", size, (27, 32, 44, 255))
    skin = {s["name"]: s for s in skel["skins"]}["default"]["attachments"]
    slot_bone = {sl["name"]: sl["bone"] for sl in skel["slots"]}
    ox, oy = origin
    for sl in skel["slots"]:
        name = attach.get(sl["name"])
        if not name:
            continue
        att = skin.get(sl["name"], {}).get(name)
        if att is None:
            continue
        path = os.path.join(parts_dir, (att.get("path") or name) + ".png")
        img = Image.open(path).convert("RGBA")
        w, h = att["width"], att["height"]
        local = _mat(att.get("x", 0.0), att.get("y", 0.0), att.get("rotation", 0.0),
                     att.get("scaleX", 1.0), att.get("scaleY", 1.0))
        m = _mul(world[slot_bone[sl["name"]]], local)
        # image px (u, v) with v down -> attachment local (u - w/2, h/2 - v) -> world -> canvas
        # Build inverse affine for PIL: canvas -> image px.
        a, b, c, d, e, f = m
        # canvas X = ox + (a*lx + b*ly + c); canvas Y = oy - (d*lx + e*ly + f)
        # lx = u - w/2 ; ly = h/2 - v
        A = [[a, -b], [-d, e]]
        cx = ox + a * (-w / 2) + b * (h / 2) + c
        cy = oy - (d * (-w / 2) + e * (h / 2) + f)
        det = A[0][0] * A[1][1] - A[0][1] * A[1][0]
        if abs(det) < 1e-9:
            continue
        inv = [[A[1][1] / det, -A[0][1] / det], [-A[1][0] / det, A[0][0] / det]]
        coeffs = (inv[0][0], inv[0][1], -(inv[0][0] * cx + inv[0][1] * cy),
                  inv[1][0], inv[1][1], -(inv[1][0] * cx + inv[1][1] * cy))
        layer = img.transform(size, Image.AFFINE, coeffs, resample=Image.BILINEAR)
        canvas.alpha_composite(layer)
    if bones:
        dr = ImageDraw.Draw(canvas)
        for bname in ("hand_r", "hand_l", "forearm_r", "forearm_l", "weapon_guandao"):
            m = world.get(bname)
            if m:
                x, y = ox + m[2], oy - m[5]
                dr.ellipse([x - 2, y - 2, x + 2, y + 2], outline=(0, 255, 0, 255))
    return canvas


def main(argv):
    flags = [a for a in argv if a.startswith("--")]
    args = [a for a in argv if not a.startswith("--")]
    if len(args) < 3:
        print(__doc__)
        return 2
    skel = json.load(open(args[0], encoding="utf-8"))
    poses = args[3:] or ["setup"]
    frames = []
    for p in poses:
        anim, _, ts = p.partition(":")
        frames.append(render(skel, args[1], None if anim == "setup" else anim,
                             float(ts or 0.0), bones="--bones" in flags))
    out = Image.new("RGBA", (sum(f.width for f in frames), frames[0].height))
    x = 0
    for f in frames:
        out.paste(f, (x, 0))
        x += f.width
    out.save(args[2])
    print("wrote", args[2])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
