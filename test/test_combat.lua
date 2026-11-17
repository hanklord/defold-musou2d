local constants = require("shared.constants")
local combat_mod = require("shared.combat")

local M = {}

local function assert_eq(actual, expected, msg)
	if actual ~= expected then
		error(string.format("%s: expected %s, got %s", msg or "assert_eq failed", tostring(expected), tostring(actual)), 2)
	end
end

local function assert_true(val, msg)
	if not val then
		error(msg or "assert_true failed", 2)
	end
end

function M.run()
	local passed = 0

	-- 1. Spine event hitbox_on / hitbox_off and 2.5D sector + Y-depth filtering
	do
		local c = combat_mod.new({ musou_gauge = 50 })
		assert_eq(c.hitbox.active, false, "hitbox initially inactive")

		c:on_spine_event("hitbox_on", 12, 1.0, "N1", nil)
		assert_true(c.hitbox.active, "hitbox activated by spine_event")
		assert_eq(c.hitbox.tag, "N1", "hitbox tag is N1")
		assert_eq(c.hitbox.damage, 12, "hitbox damage is 12")

		local player_pos = { x = 400.0, y = 300.0 }
		local targets = {
			{ id = "dummy_front", x = 490.0, y = 315.0, alive = true },     -- In range_x (90 <= 140) and range_y (15 <= 48)
			{ id = "dummy_behind", x = 300.0, y = 300.0, alive = true },    -- Behind facing=1 (dx = -100)
			{ id = "dummy_far_y", x = 480.0, y = 380.0, alive = true },     -- Out of 2.5D Y depth (dy = 80 > 48)
			{ id = "dummy_far_x", x = 620.0, y = 300.0, alive = true }      -- Out of X reach (dx = 220 > 140)
		}

		local hits = c:evaluate_hits(player_pos, 1, targets)
		assert_eq(#hits, 1, "only front dummy within 2.5D depth should be hit")
		assert_eq(hits[1].id, "dummy_front", "hit target is dummy_front")
		assert_eq(hits[1].damage, 12, "hit damage is 12")
		assert_eq(c.combo_count, 1, "combo count incremented to 1")
		assert_eq(c.musou_gauge, 65, "musou gauge increased by +15 (50 -> 65)")

		-- Evaluating again during the same active hitbox wave does not double-hit the same target
		local repeat_hits = c:evaluate_hits(player_pos, 1, targets)
		assert_eq(#repeat_hits, 0, "same hitbox wave does not double-hit")

		c:on_spine_event("hitbox_off", 0, 0.0, "", nil)
		assert_eq(c.hitbox.active, false, "hitbox deactivated by hitbox_off")
		passed = passed + 1
	end

	-- 2. Charge variant upgrade (CHARGE -> C2/C3/C4) and omnidirectional Musou hit
	do
		local c = combat_mod.new({ musou_gauge = 70 })
		c:on_spine_event("hitbox_on", 32, 2.2, "CHARGE", "C3")
		assert_eq(c.hitbox.tag, "C3", "CHARGE upgraded to C3 when charge_variant is C3")
		assert_eq(c.hitbox.damage, constants.ATTACK_SPECS.C3.damage, "C3 damage applied")

		-- Musou omnidirectional wave hits both front and back targets
		c:on_spine_event("hitbox_on", 28, 2.5, "MUSOU", nil)
		local player_pos = { x = 500.0, y = 300.0 }
		local targets = {
			{ id = "dummy_left", x = 350.0, y = 320.0, alive = true },
			{ id = "dummy_right", x = 650.0, y = 280.0, alive = true }
		}
		local hits = c:evaluate_hits(player_pos, 1, targets)
		assert_eq(#hits, 2, "omnidirectional MUSOU hits both left and right dummies")
		assert_eq(c.musou_gauge, 100, "musou gauge clamped at max 100")
		passed = passed + 1
	end

	-- 3. Combo timeout decay after 3.0s
	do
		local c = combat_mod.new()
		c:register_hit(15, "N2")
		c:register_hit(22, "N3")
		assert_eq(c.combo_count, 2, "combo is 2")
		c:update(2.0)
		assert_eq(c.combo_count, 2, "combo still active at 2.0s < 3.0s")
		c:update(1.1)
		assert_eq(c.combo_count, 0, "combo resets to 0 after 3.0s timeout")
		assert_eq(c.max_combo, 2, "max_combo preserved")
		passed = passed + 1
	end

	print(string.format("  [PASS] test_combat (%d suites)", passed))
	return passed
end

return M
