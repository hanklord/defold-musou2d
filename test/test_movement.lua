local constants = require("shared.constants")
local movement = require("shared.movement")

local M = {}

local function assert_near(actual, expected, eps, msg)
	eps = eps or 1e-4
	if math.abs(actual - expected) > eps then
		error(string.format("%s: expected ~%f, got %f", msg or "assert_near failed", expected, actual), 2)
	end
end

local function assert_true(val, msg)
	if not val then
		error(msg or "assert_true failed", 2)
	end
end

function M.run()
	local passed = 0

	-- 1. 8-way diagonal normalization and 2.5D speed ratio
	do
		local pos = { x = 500.0, y = 300.0, z = movement.compute_z(300.0) }
		local new_pos, facing, vel = movement.step(pos, { x = 1, y = 1 }, constants.STATES.RUN, 1, 1.0, 0.0)
		local inv_sqrt2 = 1.0 / math.sqrt(2.0)
		assert_near(vel.x, constants.MOVE_SPEED_X * inv_sqrt2, 0.01, "diagonal vx normalized")
		assert_near(vel.y, constants.MOVE_SPEED_Y * inv_sqrt2, 0.01, "diagonal vy normalized")
		assert_true(facing == 1, "facing right")
		assert_true(new_pos.x > pos.x and new_pos.y > pos.y, "moved northeast")
		passed = passed + 1
	end

	-- 2. Facing flip and Y-Sorting Z depth formula: z = 0.5 - y / 1000.0
	do
		local pos_front = { x = 500.0, y = 150.0, z = 0.0 }
		local pos_back = { x = 500.0, y = 450.0, z = 0.0 }
		local p1, f1 = movement.step(pos_front, { x = -1, y = 0 }, constants.STATES.RUN, 1, 0.1, 0.0)
		local p2, _ = movement.step(pos_back, { x = 0, y = 0 }, constants.STATES.IDLE, 1, 0.1, 0.0)
		assert_true(f1 == -1, "moving left flips facing to -1")
		assert_near(p1.z, 0.5 - (150.0 / 1000.0), 1e-5, "foreground z formula")
		assert_near(p2.z, 0.5 - (450.0 / 1000.0), 1e-5, "background z formula")
		assert_true(p1.z > p2.z, "foreground character has higher z than background character")
		passed = passed + 1
	end

	-- 3. Arena boundary clamping
	do
		local near_edge = { x = 85.0, y = 515.0, z = 0.0 }
		local clamped = movement.step(near_edge, { x = -1, y = 1 }, constants.STATES.RUN, -1, 1.0, 0.0)
		assert_near(clamped.x, constants.ARENA_BOUNDS.min_x, 1e-4, "clamped to min_x (80)")
		assert_near(clamped.y, constants.ARENA_BOUNDS.max_y, 1e-4, "clamped to max_y (520)")
		passed = passed + 1
	end

	-- 4. Attack forward step impulse & Dash burst impulse
	do
		local start_pos = { x = 400.0, y = 260.0, z = 0.0 }
		local step_pos = movement.step(start_pos, { x = 0, y = 0 }, constants.STATES.ATTACK_1, 1, 0.1, 0.10)
		assert_true(step_pos.x > start_pos.x, "attack_1 steps forward in facing direction")

		local dash_pos = movement.step(start_pos, { x = 0, y = 0 }, constants.STATES.DASH, -1, 0.2, 0.05)
		assert_near(dash_pos.x, 400.0 - constants.DASH_SPEED * 0.2, 0.01, "neutral dash bursts in facing direction")
		passed = passed + 1
	end

	-- Animation cross-fade: idle <-> run uses the longer blend (45 deg idle lean vs upright run)
	do
		local S = constants.STATES
		assert_near(constants.anim_blend_duration(S.IDLE, S.RUN), constants.ANIM_BLEND_IDLE_RUN, 1e-6, "idle->run blend")
		assert_near(constants.anim_blend_duration(S.RUN, S.IDLE), constants.ANIM_BLEND_IDLE_RUN, 1e-6, "run->idle blend")
		assert_near(constants.anim_blend_duration(S.IDLE, S.ATTACK_1), constants.ANIM_BLEND_DEFAULT, 1e-6, "idle->attack blend")
		assert_near(constants.anim_blend_duration(nil, S.IDLE), constants.ANIM_BLEND_DEFAULT, 1e-6, "first anim blend")
		assert_true(constants.ANIM_BLEND_IDLE_RUN > constants.ANIM_BLEND_DEFAULT, "idle/run blend is longer")
		-- Recovering from a strike back into the 45 deg idle lean gets the longer return blend
		for _, st in ipairs({ S.ATTACK_1, S.ATTACK_2, S.ATTACK_3, S.CHARGE_ATTACK, S.MUSOU_SKILL }) do
			assert_near(constants.anim_blend_duration(st, S.IDLE), constants.ANIM_BLEND_ATTACK_TO_IDLE, 1e-6, st .. "->idle blend")
		end
		assert_near(constants.anim_blend_duration(S.ATTACK_1, S.ATTACK_2), constants.ANIM_BLEND_DEFAULT, 1e-6, "combo chain keeps snappy blend")
		passed = passed + 1
	end

	print(string.format("  [PASS] test_movement (%d suites)", passed))

	return passed
end

return M
