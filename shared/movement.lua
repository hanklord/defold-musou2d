local constants = require("shared.constants")

local M = {}

local STATES = constants.STATES
local BOUNDS = constants.ARENA_BOUNDS

function M.clamp(val, min_v, max_v)
	if val < min_v then
		return min_v
	elseif val > max_v then
		return max_v
	end
	return val
end

function M.compute_z(y)
	return constants.Z_BASE - (y / constants.Z_SCALE)
end

function M.clamp_to_arena(x, y)
	local cx = M.clamp(x, BOUNDS.min_x, BOUNDS.max_x)
	local cy = M.clamp(y, BOUNDS.min_y, BOUNDS.max_y)
	return cx, cy, M.compute_z(cy)
end

function M.normalize_dir(dx, dy)
	dx = dx or 0.0
	dy = dy or 0.0
	local len = math.sqrt(dx * dx + dy * dy)
	if len > 1e-6 then
		return dx / len, dy / len, true
	end
	return 0.0, 0.0, false
end

function M.step(pos, input_dir, fsm_state, facing, dt, state_time)
	pos = pos or { x = 400.0, y = 300.0, z = 0.2 }
	input_dir = input_dir or { x = 0.0, y = 0.0 }
	fsm_state = fsm_state or STATES.IDLE
	facing = (facing == -1) and -1 or 1
	dt = dt or 0.0
	state_time = state_time or 0.0

	local nx, ny, has_input = M.normalize_dir(input_dir.x, input_dir.y)
	local new_facing = facing

	if fsm_state == STATES.IDLE or fsm_state == STATES.RUN or fsm_state == STATES.DASH then
		if (input_dir.x or 0.0) < -0.01 then
			new_facing = -1
		elseif (input_dir.x or 0.0) > 0.01 then
			new_facing = 1
		end
	end

	local vx = 0.0
	local vy = 0.0

	if fsm_state == STATES.IDLE or fsm_state == STATES.RUN then
		if has_input then
			vx = nx * constants.MOVE_SPEED_X
			vy = ny * constants.MOVE_SPEED_Y
		end
	elseif fsm_state == STATES.DASH then
		if has_input then
			local dash_y_speed = constants.DASH_SPEED * (constants.MOVE_SPEED_Y / constants.MOVE_SPEED_X)
			vx = nx * constants.DASH_SPEED
			vy = ny * dash_y_speed
		else
			vx = new_facing * constants.DASH_SPEED
			vy = 0.0
		end
	elseif constants.ATTACK_STEP[fsm_state] then
		local step_cfg = constants.ATTACK_STEP[fsm_state]
		if state_time >= step_cfg.start_t and state_time <= step_cfg.end_t then
			vx = new_facing * step_cfg.speed
			vy = ny * (constants.MOVE_SPEED_Y * 0.25)
		end
	elseif fsm_state == STATES.HIT then
		vx = 0.0
		vy = 0.0
	end

	local next_x = (pos.x or 0.0) + vx * dt
	local next_y = (pos.y or 0.0) + vy * dt
	local clamped_x, clamped_y, next_z = M.clamp_to_arena(next_x, next_y)

	local new_pos = {
		x = clamped_x,
		y = clamped_y,
		z = next_z
	}
	local velocity = {
		x = vx,
		y = vy
	}

	return new_pos, new_facing, velocity
end

return M
