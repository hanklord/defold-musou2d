#!/usr/bin/env python3
"""
Automated verification suite for Musou2D Spine 4.2 Auto-Rigging Pipeline (Gate 1/2).
Validates:
  1. CLI execution of tools/auto_rig_spine.py on assets/raw/musou2d_hero_input.jpg
  2. Extraction of all 17 RGBA transparent part PNGs & parts_metadata.json pivots
  3. Defold assets/spine/hero.atlas (no rename_patterns, all 17 parts matched)
  4. Defold assets/spine/hero.spinescene references
  5. Strict Spine 4.2 C Runtime JSON schema (spine=="4.2.00", skins is list,
     bone rotate keyframes use "value" not "angle", full skeleton hierarchy,
     4 interchangeable hand attachments, 9 Musou animations, and 4 combat events)
  6. Single-image proportional fallback slicer test
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image


ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
EXPECTED_17_PARTS = [
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
EXPECTED_BONES = {
    "root": None,
    "hip": "root",
    "torso": "hip",
    "head": "torso",
    "cape": "torso",
    "waist": "torso",
    "arm_r": "torso",
    "forearm_r": "arm_r",
    "hand_r": "forearm_r",
    "weapon_guandao": "hand_r",
    "arm_l": "torso",
    "forearm_l": "arm_l",
    "hand_l": "forearm_l",
    "thigh_r": "hip",
    "shin_r": "thigh_r",
    "thigh_l": "hip",
    "shin_l": "thigh_l",
}
EXPECTED_9_ANIMS = [
    "idle",
    "run",
    "attack_1",
    "attack_2",
    "attack_3",
    "charge_attack",
    "dash",
    "musou_skill",
    "hit",
]
EXPECTED_4_EVENTS = ["hitbox_on", "hitbox_off", "footstep", "musou_burst"]


class TestSpinePipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cmd = [
            sys.executable,
            os.path.join(ROOT_DIR, "tools", "auto_rig_spine.py"),
            "--input",
            os.path.join(ROOT_DIR, "assets", "raw", "musou2d_hero_input.jpg"),
            "--output-dir",
            "assets/spine",
            "--name",
            "hero",
        ]
        subprocess.run(cmd, cwd=ROOT_DIR, check=True)

    def test_01_17_transparent_part_pngs_and_metadata(self) -> None:
        parts_dir = os.path.join(ROOT_DIR, "assets", "spine", "parts")
        meta_path = os.path.join(ROOT_DIR, "assets", "spine", "parts_metadata.json")
        self.assertTrue(os.path.isfile(meta_path), "parts_metadata.json missing")

        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)

        self.assertEqual(meta["part_count"], 17)
        for part_name in EXPECTED_17_PARTS:
            png_path = os.path.join(parts_dir, f"{part_name}.png")
            self.assertTrue(os.path.isfile(png_path), f"Missing part PNG: {png_path}")
            with Image.open(png_path) as im:
                self.assertEqual(im.mode, "RGBA")
                w, h = im.size
                self.assertGreater(w, 20)
                self.assertGreater(h, 20)
                arr = np.array(im)
                alpha = arr[..., 3]
                self.assertGreater(int((alpha > 200).sum()), 200, f"{part_name} lacks opaque pixels")
                self.assertGreater(int((alpha == 0).sum()), 10, f"{part_name} background not transparent")

            pinfo = meta["parts"][part_name]
            self.assertEqual(pinfo["width"], w)
            self.assertEqual(pinfo["height"], h)
            self.assertEqual(len(pinfo["source_bbox"]), 4)
            self.assertEqual(len(pinfo["pivot_norm"]), 2)
            self.assertEqual(len(pinfo["pivot_px"]), 2)

    def test_02_defold_atlas_and_spinescene(self) -> None:
        atlas_path = os.path.join(ROOT_DIR, "assets", "spine", "hero.atlas")
        scene_path = os.path.join(ROOT_DIR, "assets", "spine", "hero.spinescene")
        self.assertTrue(os.path.isfile(atlas_path))
        self.assertTrue(os.path.isfile(scene_path))

        with open(atlas_path, "r", encoding="utf-8") as f:
            atlas_txt = f.read()
        self.assertNotIn("rename_patterns", atlas_txt)
        for part_name in EXPECTED_17_PARTS:
            self.assertIn(f'/assets/spine/parts/{part_name}.png', atlas_txt)

        with open(scene_path, "r", encoding="utf-8") as f:
            scene_txt = f.read()
        self.assertIn('spine_json: "/assets/spine/hero.spinejson"', scene_txt)
        self.assertIn('atlas: "/assets/spine/hero.atlas"', scene_txt)

    def test_03_spine_42_strict_json_contract(self) -> None:
        json_path = os.path.join(ROOT_DIR, "assets", "spine", "hero.spinejson")
        self.assertTrue(os.path.isfile(json_path))
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # 1. Skeleton header
        self.assertEqual(data["skeleton"]["spine"], "4.2.00")

        # 2. Bone hierarchy
        bone_map = {b["name"]: b.get("parent") for b in data["bones"]}
        for bname, expected_parent in EXPECTED_BONES.items():
            self.assertIn(bname, bone_map, f"Missing bone {bname}")
            self.assertEqual(bone_map[bname], expected_parent, f"Bone {bname} parent mismatch")

        # 3. Skins MUST be a JSON Array (list)
        self.assertIsInstance(data["skins"], list, "Spine 4.2 skins MUST be a list, not dict")
        self.assertGreaterEqual(len(data["skins"]), 1)
        default_skin = data["skins"][0]
        self.assertEqual(default_skin["name"], "default")
        skin_attachments = default_skin["attachments"]

        # Verify all 17 parts are bound in attachments and hand_l has hand_1..hand_4
        found_parts = set()
        for slot_name, att_dict in skin_attachments.items():
            for att_name, att_val in att_dict.items():
                found_parts.add(att_name)
                self.assertIn("width", att_val)
                self.assertIn("height", att_val)
        for part_name in EXPECTED_17_PARTS:
            self.assertIn(part_name, found_parts, f"Part {part_name} missing from skin attachments")
        for hand_idx in range(1, 5):
            self.assertIn(f"hand_{hand_idx}", skin_attachments["hand_l"])

        # 4. Events
        for ev in EXPECTED_4_EVENTS:
            self.assertIn(ev, data["events"], f"Missing top-level event {ev}")

        # 5. 9 Musou animations + strict rotate 'value' check
        anims = data["animations"]
        for anim_name in EXPECTED_9_ANIMS:
            self.assertIn(anim_name, anims, f"Missing animation {anim_name}")
            anim_obj = anims[anim_name]
            for bone_name, timelines in anim_obj.get("bones", {}).items():
                for rframe in timelines.get("rotate", []):
                    self.assertNotIn(
                        "angle",
                        rframe,
                        f"Spine 3.8 'angle' forbidden in {anim_name}.{bone_name}.rotate",
                    )
                    self.assertIn(
                        "value",
                        rframe,
                        f"Spine 4.2 'value' required in {anim_name}.{bone_name}.rotate",
                    )

        # Verify specific animation event contracts
        run_events = [e["name"] for e in anims["run"].get("events", [])]
        self.assertEqual(run_events.count("footstep"), 2)

        for atk_name, tag in [
            ("attack_1", "N1"),
            ("attack_2", "N2"),
            ("attack_3", "N3"),
            ("charge_attack", "CHARGE"),
        ]:
            ev_list = anims[atk_name].get("events", [])
            names = [e["name"] for e in ev_list]
            self.assertIn("hitbox_on", names)
            self.assertIn("hitbox_off", names)
            on_ev = next(e for e in ev_list if e["name"] == "hitbox_on")
            self.assertEqual(on_ev["string"], tag)

        musou_evs = anims["musou_skill"].get("events", [])
        musou_names = [e["name"] for e in musou_evs]
        self.assertIn("musou_burst", musou_names)
        self.assertEqual(musou_names.count("hitbox_on"), 3)
        self.assertEqual(musou_names.count("hitbox_off"), 3)

    def test_04_fallback_single_portrait_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            synth_img = os.path.join(tmpdir, "single_portrait.png")
            arr = np.full((256, 256, 3), 200, dtype=np.uint8)
            arr[32:224, 80:176] = [180, 40, 40]
            Image.fromarray(arr, mode="RGB").save(synth_img)

            out_dir = os.path.join(tmpdir, "out_spine")
            cmd = [
                sys.executable,
                os.path.join(ROOT_DIR, "tools", "auto_rig_spine.py"),
                "--input",
                synth_img,
                "--output-dir",
                out_dir,
                "--name",
                "test_hero",
            ]
            subprocess.run(cmd, cwd=ROOT_DIR, check=True)
            self.assertTrue(os.path.isfile(os.path.join(out_dir, "test_hero.spinejson")))
            self.assertEqual(len(os.listdir(os.path.join(out_dir, "parts"))), 17)


if __name__ == "__main__":
    unittest.main(verbosity=2)
