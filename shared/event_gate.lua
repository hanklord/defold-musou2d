-- Event gate: de-duplicates animation events that can arrive from two sources
-- (the Spine runtime `spine_event` callback and the script-side fallback
-- schedule in constants.ANIM_EVENTS). Each schedule index fires at most once per
-- animation activation (per loop cycle for looping animations), regardless of
-- which source delivers it first.
local M = {}
M.__index = M

function M.new(schedule, loop_duration)
	local self = setmetatable({}, M)
	self:reset(schedule, loop_duration)
	return self
end

-- Start a new activation (call on every animation (re)start / FSM transition).
function M:reset(schedule, loop_duration)
	self.schedule = schedule or {}
	self.loop_duration = (loop_duration and loop_duration > 0) and loop_duration or nil
	self.fired = {}
	self.cycle = 0
end

-- Map absolute state time to local (in-cycle) time; resets fired marks when a
-- looping animation wraps into a new cycle.
function M:_local_time(state_time)
	state_time = state_time or 0.0
	if not self.loop_duration then
		return state_time
	end
	local cycle = math.floor(state_time / self.loop_duration)
	if cycle ~= self.cycle then
		self.cycle = cycle
		self.fired = {}
	end
	return state_time - cycle * self.loop_duration
end

-- Index of the schedule entry for `event_name` whose time is closest to t.
function M:_match(event_name, t)
	local best, best_d = nil, nil
	for i = 1, #self.schedule do
		local item = self.schedule[i]
		if item.event == event_name then
			local d = math.abs(item.time - t)
			if best_d == nil or d < best_d then
				best, best_d = i, d
			end
		end
	end
	return best
end

-- Spine-delivered event. Returns true if it should be processed, false if the
-- matching schedule index already fired (duplicate). Events that have no entry
-- in the schedule are always passed through.
function M:claim(event_name, state_time)
	local t = self:_local_time(state_time)
	local idx = self:_match(event_name, t)
	if not idx then
		return true
	end
	if self.fired[idx] then
		return false
	end
	self.fired[idx] = true
	return true
end

-- Fallback schedule poll. Returns the list of schedule items due at state_time
-- that have not been fired by either source yet, marking them fired.
function M:poll(state_time)
	local t = self:_local_time(state_time)
	local due = {}
	for i = 1, #self.schedule do
		local item = self.schedule[i]
		if not self.fired[i] and t >= item.time then
			self.fired[i] = true
			due[#due + 1] = item
		end
	end
	return due
end

return M
