-- Regression tests for B1 (double hit when Spine event and fallback schedule
-- both deliver the same hitbox_on) and N5 (footstep "left"/"right" strings).
local constants = require("shared.constants")
local event_gate_mod = require("shared.event_gate")

local M = {}

local function assert_eq(actual, expected, msg)
	if actual ~= expected then
		error(string.format("%s: expected %s, got %s", msg or "assert_eq failed", tostring(expected), tostring(actual)), 2)
	end
end

-- Minimal mock of the Defold runtime, enough to load and drive player.script.
local function load_player()
	local h = {
		posts = {},
		cb = nil,
		anim = nil
	}
	-- Defold hashes are userdata, not strings: intern opaque tables so that
	-- resolve_event_string() must go through HASH_TO_TAG like on device.
	local interned = {}
	local function hash(s)
		s = tostring(s)
		if not interned[s] then
			interned[s] = setmetatable({}, { __tostring = function() return "hash: [" .. s .. "]" end })
		end
		return interned[s]
	end
	local env = setmetatable({}, { __index = _G })
	env.hash = hash
	env.vmath = {
		vector3 = function(x, y, z) return { x = x, y = y, z = z } end,
		vector4 = function(...) return { ... } end,
		quat_rotation_y = function() return {} end
	}
	env.go = {
		PLAYBACK_ONCE_FORWARD = 1,
		PLAYBACK_LOOP_FORWARD = 2,
		get_position = function(p)
			if p == "/dummy_1" then return { x = 700, y = 300, z = 0 } end
			if p then error("no such object") end
			return { x = 640, y = 300, z = 0 }
		end,
		set_position = function() end,
		set_rotation = function() end,
		set = function() end
	}
	env.msg = {
		post = function(to, id, m) h.posts[#h.posts + 1] = { to = to, id = id, m = m } end
	}
	env.spine = {
		play_anim = function(_, anim, _, _, cb)
			h.anim = anim
			h.anim_t = 0.0
			h.cb = cb
		end
	}
	local chunk
	if setfenv then
		chunk = assert(loadfile("player/player.script"))
		setfenv(chunk, env)
	else
		chunk = assert(loadfile("player/player.script", "t", env))
	end
	chunk()
	h.env = env
	h.hash = hash
	h.self = {}
	env.init(h.self)
	h.self.pos.x = 640
	h.self.pos.y = 300
	return h
end

local function count_posts(h, id, to)
	local n = 0
	for _, p in ipairs(h.posts) do
		if p.id == id and (to == nil or p.to == to) then
			n = n + 1
		end
	end
	return n
end

local function count_shakes(h, intensity)
	local n = 0
	for _, p in ipairs(h.posts) do
		if p.id == "camera_shake" and p.m.intensity == intensity then
			n = n + 1
		end
	end
	return n
end

-- Simulate frames. order = "fallback_first": script update runs before the Spine
-- component advances (Defold default). "spine_first": Spine events delivered
-- before the script update of the frame. spine_lead offsets Spine clock.
local function simulate(h, frames, order, spine_lead)
	local dt = 1 / 60
	spine_lead = spine_lead or 0.0
	local fired = {}
	local cur_anim = h.anim
	local function push_spine()
		if h.anim ~= cur_anim then
			cur_anim = h.anim
			fired = {}
		end
		local sched = constants.ANIM_EVENTS[h.anim] or {}
		for k, e in ipairs(sched) do
			if not fired[k] and h.anim_t + spine_lead >= e.time then
				fired[k] = true
				h.cb(h.self, h.hash("spine_event"), {
					event_id = h.hash(e.event),
					integer = e.int,
					float = e.float,
					string = h.hash(e.string)
				})
			end
		end
	end
	for _ = 1, frames do
		if order == "spine_first" then
			h.anim_t = h.anim_t + dt
			push_spine()
			h.env.update(h.self, dt)
		else
			h.env.update(h.self, dt)
			h.anim_t = h.anim_t + dt
			push_spine()
		end
	end
end

function M.run()
	local passed = 0

	-- 1. Gate unit: fallback first, then Spine for same index -> dropped.
	do
		local g = event_gate_mod.new(constants.ANIM_EVENTS.attack_1)
		local due = g:poll(0.15)
		assert_eq(#due, 1, "fallback delivers hitbox_on once")
		assert_eq(due[1].event, "hitbox_on", "due event is hitbox_on")
		assert_eq(g:claim("hitbox_on", 0.16), false, "late Spine hitbox_on is a duplicate")
		assert_eq(#g:poll(0.2), 0, "no re-fire from fallback")
		passed = passed + 1
	end

	-- 2. Gate unit: Spine first, then fallback -> fallback skips.
	do
		local g = event_gate_mod.new(constants.ANIM_EVENTS.attack_1)
		assert_eq(g:claim("hitbox_on", 0.13), true, "Spine hitbox_on accepted")
		assert_eq(#g:poll(0.15), 0, "fallback skips already-fired index")
		assert_eq(g:claim("hitbox_on", 0.14), false, "repeated Spine hitbox_on dropped")
		assert_eq(g:claim("hitbox_off", 0.30), true, "hitbox_off accepted")
		assert_eq(#g:poll(0.31), 0, "fallback hitbox_off skipped")
		passed = passed + 1
	end

	-- 3. Gate unit: MUSOU multi-wave matches each Spine event to nearest index.
	do
		local g = event_gate_mod.new(constants.ANIM_EVENTS.musou_skill)
		local due = g:poll(0.25) -- burst + wave1 by fallback
		assert_eq(#due, 2, "fallback fires burst + wave 1")
		assert_eq(g:claim("musou_burst", 0.26), false, "late Spine musou_burst dropped")
		assert_eq(g:claim("hitbox_on", 0.26), false, "late Spine wave-1 dropped")
		assert_eq(g:claim("hitbox_on", 0.52), true, "wave-2 still accepted")
		assert_eq(g:claim("hitbox_on", 0.88), true, "wave-3 still accepted")
		passed = passed + 1
	end

	-- 4. Gate unit: looping run re-arms footsteps every cycle; events off-schedule pass.
	do
		local g = event_gate_mod.new(constants.ANIM_EVENTS.run, constants.ANIM_DURATION.run)
		assert_eq(#g:poll(0.50), 2, "cycle 0 footsteps")
		assert_eq(g:claim("footstep", 0.46), false, "dup footstep dropped")
		assert_eq(#g:poll(0.70), 0, "cycle 1 before first step")
		assert_eq(g:claim("footstep", 0.75), true, "cycle 1 Spine left step accepted")
		assert_eq(#g:poll(1.10), 1, "cycle 1 fallback right step only")
		assert_eq(event_gate_mod.new({}):claim("hitbox_on", 0.1), true, "unscheduled event passes")
		passed = passed + 1
	end

	-- 5/6. Integration (player.script with mocked Defold): one J press, both orders.
	for _, order in ipairs({ "fallback_first", "spine_first" }) do
		for _, lead in ipairs({ 0.0, 0.03, -0.03 }) do
			local h = load_player()
			h.env.on_input(h.self, h.hash("attack_light"), { pressed = true })
			assert_eq(h.anim, "attack_1", "N1 animation started")
			simulate(h, 24, order, lead)
			local tag = order .. " lead=" .. lead
			assert_eq(count_posts(h, "apply_hit", "/dummy_1#script"), 1, "single N1 hit on dummy_1 [" .. tag .. "]")
			assert_eq(h.self.combat.combo_count, 1, "combo == 1 [" .. tag .. "]")
		end
		passed = passed + 1
	end

	-- 7/8. Integration: musou burst once, three waves hit once each, both orders.
	for _, order in ipairs({ "fallback_first", "spine_first" }) do
		local h = load_player()
		h.env.on_input(h.self, h.hash("musou"), { pressed = true })
		assert_eq(h.anim, "musou_skill", "musou animation started")
		simulate(h, 75, order, 0.0)
		assert_eq(h.self.combat.burst_count, 1, "musou_burst once [" .. order .. "]")
		assert_eq(count_shakes(h, 9.0), 1, "burst camera shake once [" .. order .. "]")
		assert_eq(count_posts(h, "apply_hit", "/dummy_1#script"), 3, "three MUSOU waves, one hit each [" .. order .. "]")
		passed = passed + 1
	end

	-- 9. N5: footstep "left"/"right" hashes resolve and are counted once per step.
	do
		local h = load_player()
		local seen = {}
		local orig = h.self.combat.on_spine_event
		h.self.combat.on_spine_event = function(c, name, i, f, s, cv)
			if name == "footstep" then seen[#seen + 1] = s end
			return orig(c, name, i, f, s, cv)
		end
		h.env.on_input(h.self, h.hash("move_right"), {})
		h.env.update(h.self, 1 / 60)
		assert_eq(h.anim, "run", "run animation started")
		local dt = 1 / 60
		for _ = 1, 30 do
			h.env.on_input(h.self, h.hash("move_right"), {})
			h.anim_t = h.anim_t + dt
			for _, e in ipairs(constants.ANIM_EVENTS.run) do
				if h.anim_t >= e.time and h.anim_t - dt < e.time then
					h.cb(h.self, h.hash("spine_event"), {
						event_id = h.hash("footstep"), integer = e.int, float = 0.0, string = h.hash(e.string)
					})
				end
			end
			h.env.update(h.self, dt)
		end
		assert_eq(#seen, 2, "two footsteps in one run cycle")
		assert_eq(seen[1], "left", "first footstep resolves to left")
		assert_eq(seen[2], "right", "second footstep resolves to right")
		passed = passed + 1
	end

	print(string.format("  [PASS] test_event_gate (%d suites)", passed))
	return passed
end

return M
