local constants = require("shared.constants")
local fsm_mod = require("shared.fsm")

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

	-- 1. Initial state & Idle <-> Run transitions
	do
		local f = fsm_mod.new()
		assert_eq(f.state, constants.STATES.IDLE, "initial state should be idle")
		f:set_move_intent(true)
		assert_eq(f.state, constants.STATES.RUN, "move intent should transition idle -> run")
		f:set_move_intent(false)
		assert_eq(f.state, constants.STATES.IDLE, "stop move intent should transition run -> idle")
		passed = passed + 1
	end

	-- 2. Light attack 3-hit combo chain (N1 -> N2 -> N3 -> idle)
	do
		local f = fsm_mod.new()
		assert_true(f:press_light(), "N1 start from idle")
		assert_eq(f.state, constants.STATES.ATTACK_1, "state is attack_1")
		assert_eq(f.combo_step, 1, "combo_step is 1")
		assert_eq(f.attack_tag, "N1", "attack_tag is N1")

		-- Buffer N2 early (at t=0.10s < 0.26s chain window)
		f:update(0.10, false)
		assert_true(f:press_light(), "buffer N2 during attack_1")
		assert_eq(f.buffered_action, "light", "buffered_action is light")
		assert_eq(f.state, constants.STATES.ATTACK_1, "still in attack_1 before chain window")

		-- Advance across chain window (0.10 + 0.18 = 0.28s >= 0.26s)
		f:update(0.18, false)
		assert_eq(f.state, constants.STATES.ATTACK_2, "chained into attack_2 at window")
		assert_eq(f.combo_step, 2, "combo_step is 2")
		assert_eq(f.attack_tag, "N2", "attack_tag is N2")

		-- Buffer N3 and advance past window
		f:update(0.10, false)
		assert_true(f:press_light(), "buffer N3 during attack_2")
		f:update(0.20, false)
		assert_eq(f.state, constants.STATES.ATTACK_3, "chained into attack_3")
		assert_eq(f.combo_step, 3, "combo_step is 3")
		assert_eq(f.attack_tag, "N3", "attack_tag is N3")

		-- Finish N3 animation -> returns to idle
		f:update(0.60, false)
		assert_eq(f.state, constants.STATES.IDLE, "returned to idle after N3 finishes")
		assert_eq(f.combo_step, 0, "combo_step reset to 0")
		passed = passed + 1
	end

	-- 3. Charge variants C1, N1->C2, N2->C3, N3->C4
	do
		-- C1: Direct heavy from idle
		local f1 = fsm_mod.new()
		assert_true(f1:press_heavy(), "press heavy from idle")
		assert_eq(f1.state, constants.STATES.CHARGE_ATTACK, "state is charge_attack")
		assert_eq(f1.charge_variant, "C1", "direct heavy is C1")
		assert_eq(f1.attack_tag, "C1", "attack_tag is C1")

		-- C2: N1 -> Heavy
		local f2 = fsm_mod.new()
		f2:press_light()
		f2:update(0.10, false)
		f2:press_heavy()
		assert_eq(f2.charge_variant, "C2", "pre-assigned C2 variant")
		f2:update(0.20, false)
		assert_eq(f2.state, constants.STATES.CHARGE_ATTACK, "transitioned to charge_attack for C2")
		assert_eq(f2.charge_variant, "C2", "variant is C2")
		assert_eq(f2.attack_tag, "C2", "attack_tag is C2")

		-- C3: N1 -> N2 -> Heavy
		local f3 = fsm_mod.new()
		f3:press_light()
		f3:update(0.28, false)
		f3:press_light() -- immediately chains to N2 since t>=0.26
		assert_eq(f3.state, constants.STATES.ATTACK_2, "in attack_2")
		f3:update(0.10, false)
		f3:press_heavy()
		f3:update(0.20, false)
		assert_eq(f3.state, constants.STATES.CHARGE_ATTACK, "transitioned to charge_attack for C3")
		assert_eq(f3.charge_variant, "C3", "variant is C3")
		assert_eq(f3.attack_tag, "C3", "attack_tag is C3")

		-- C4: N1 -> N2 -> N3 -> Heavy
		local f4 = fsm_mod.new()
		f4:press_light()
		f4:update(0.28, false)
		f4:press_light()
		f4:update(0.28, false)
		f4:press_light()
		assert_eq(f4.state, constants.STATES.ATTACK_3, "in attack_3")
		f4:update(0.10, false)
		f4:press_heavy()
		f4:update(0.20, false)
		assert_eq(f4.state, constants.STATES.CHARGE_ATTACK, "transitioned to charge_attack for C4")
		assert_eq(f4.charge_variant, "C4", "variant is C4")
		assert_eq(f4.attack_tag, "C4", "attack_tag is C4")
		passed = passed + 1
	end

	-- 4. Dash Cancel & Invulnerability Frames
	do
		local f = fsm_mod.new()
		f:press_light()
		f:update(0.12, false)
		assert_eq(f.state, constants.STATES.ATTACK_1, "in attack_1 before dash cancel")
		assert_true(f:press_dash(), "dash cancel mid-attack_1")
		assert_eq(f.state, constants.STATES.DASH, "cancelled into dash")
		assert_true(f:is_invulnerable(), "dash grants invulnerability")
		assert_eq(f:apply_hit(), false, "hit ignored during dash i-frames")
		assert_eq(f.state, constants.STATES.DASH, "still in dash after ignored hit")

		-- Cooldown prevents immediate second dash
		f:update(0.35, false)
		assert_eq(f.state, constants.STATES.IDLE, "dash finished -> idle")
		assert_eq(f:press_dash(), false, "dash blocked while cooldown > 0")
		f:update(0.12, false)
		assert_true(f:press_dash(), "dash available again after cooldown expires")
		passed = passed + 1
	end

	-- 5. Musou Skill (Super Armor & Gauge Consumption)
	do
		local f = fsm_mod.new({ musou_gauge = 100 })
		f:press_light()
		assert_true(f:press_musou(100), "musou skill cancels attack when gauge == 100")
		assert_eq(f.state, constants.STATES.MUSOU_SKILL, "entered musou_skill")
		assert_eq(f.musou_gauge, 0, "musou gauge consumed")
		assert_true(f:is_invulnerable(), "musou skill has full super armor / invulnerability")
		assert_eq(f:apply_hit(), false, "cannot be hit-stunned during musou_skill")
		f:update(1.45, false)
		assert_eq(f.state, constants.STATES.IDLE, "returned to idle after 1.40s musou_skill")
		assert_eq(f:press_musou(f.musou_gauge), false, "cannot use musou with 0 gauge")
		passed = passed + 1
	end

	-- 6. Hit stun & recovery
	do
		local f = fsm_mod.new()
		f:press_light()
		assert_true(f:apply_hit(), "hit interrupts normal attack")
		assert_eq(f.state, constants.STATES.HIT, "entered hit state")
		assert_eq(f:press_dash(), false, "cannot dash cancel out of hit stun")
		f:update(0.40, true)
		assert_eq(f.state, constants.STATES.RUN, "recovers from hit into run when move intent is true")
		passed = passed + 1
	end

	print(string.format("  [PASS] test_fsm (%d suites)", passed))
	return passed
end

return M
