local constants = require("shared.constants")

local M = {}
M.__index = M

local STATES = constants.STATES
local ANIM_DURATION = constants.ANIM_DURATION

local function enter_state(self, new_state, combo_step, charge_variant, attack_tag)
	self.prev_state = self.state
	self.state = new_state
	self.state_time = 0.0
	self.combo_step = combo_step or 0
	self.buffered_action = nil
	self.charge_variant = charge_variant
	self.attack_tag = attack_tag or "NONE"
	self.transition_count = (self.transition_count or 0) + 1
	return true
end

function M.new(opts)
	opts = opts or {}
	local self = setmetatable({}, M)
	self.state = opts.initial_state or STATES.IDLE
	self.prev_state = self.state
	self.state_time = 0.0
	self.combo_step = 0
	self.buffered_action = nil
	self.charge_variant = nil
	self.attack_tag = "NONE"
	self.invulnerable_timer = 0.0
	self.dash_cooldown = 0.0
	self.musou_gauge = opts.musou_gauge or constants.INITIAL_MUSOU
	self.is_moving = false
	self.transition_count = 0
	return self
end

function M:is_attacking()
	return self.state == STATES.ATTACK_1
		or self.state == STATES.ATTACK_2
		or self.state == STATES.ATTACK_3
		or self.state == STATES.CHARGE_ATTACK
		or self.state == STATES.MUSOU_SKILL
end

function M:is_invulnerable()
	return self.invulnerable_timer > 0.0 or self.state == STATES.MUSOU_SKILL
end

function M:can_dash()
	if self.dash_cooldown > 1e-6 then
		return false
	end
	if self.state == STATES.HIT or self.state == STATES.MUSOU_SKILL or self.state == STATES.DASH then
		return false
	end
	return true
end

function M:can_use_musou(external_gauge)
	local gauge = external_gauge ~= nil and external_gauge or self.musou_gauge
	if gauge < constants.MUSOU_COST then
		return false
	end
	if self.state == STATES.HIT or self.state == STATES.MUSOU_SKILL then
		return false
	end
	return true
end

local function try_consume_buffer(self)
	if not self.buffered_action then
		return false
	end
	if self.buffered_action == "light" then
		if self.state == STATES.ATTACK_1 then
			return enter_state(self, STATES.ATTACK_2, 2, nil, "N2")
		elseif self.state == STATES.ATTACK_2 then
			return enter_state(self, STATES.ATTACK_3, 3, nil, "N3")
		end
	elseif self.buffered_action == "heavy" then
		if self.state == STATES.ATTACK_1 then
			return enter_state(self, STATES.CHARGE_ATTACK, 0, "C2", "C2")
		elseif self.state == STATES.ATTACK_2 then
			return enter_state(self, STATES.CHARGE_ATTACK, 0, "C3", "C3")
		elseif self.state == STATES.ATTACK_3 then
			return enter_state(self, STATES.CHARGE_ATTACK, 0, "C4", "C4")
		end
	end
	return false
end

function M:set_move_intent(is_moving)
	self.is_moving = is_moving and true or false
	if self.state == STATES.IDLE and self.is_moving then
		return enter_state(self, STATES.RUN, 0, nil, "NONE")
	elseif self.state == STATES.RUN and not self.is_moving then
		return enter_state(self, STATES.IDLE, 0, nil, "NONE")
	end
	return false
end

function M:press_light()
	if self.state == STATES.IDLE or self.state == STATES.RUN then
		return enter_state(self, STATES.ATTACK_1, 1, nil, "N1")
	elseif self.state == STATES.ATTACK_1 or self.state == STATES.ATTACK_2 then
		self.buffered_action = "light"
		if self.state_time >= constants.COMBO_CHAIN_WINDOW then
			return try_consume_buffer(self)
		end
		return true
	end
	return false
end

function M:press_heavy()
	if self.state == STATES.IDLE or self.state == STATES.RUN then
		return enter_state(self, STATES.CHARGE_ATTACK, 0, "C1", "C1")
	elseif self.state == STATES.ATTACK_1 then
		self.buffered_action = "heavy"
		self.charge_variant = "C2"
		if self.state_time >= constants.COMBO_CHAIN_WINDOW then
			return try_consume_buffer(self)
		end
		return true
	elseif self.state == STATES.ATTACK_2 then
		self.buffered_action = "heavy"
		self.charge_variant = "C3"
		if self.state_time >= constants.COMBO_CHAIN_WINDOW then
			return try_consume_buffer(self)
		end
		return true
	elseif self.state == STATES.ATTACK_3 then
		self.buffered_action = "heavy"
		self.charge_variant = "C4"
		if self.state_time >= constants.COMBO_CHAIN_WINDOW then
			return try_consume_buffer(self)
		end
		return true
	end
	return false
end

function M:press_dash()
	if not self:can_dash() then
		return false
	end
	self.invulnerable_timer = constants.DASH_INVULNERABLE_TIME
	self.dash_cooldown = constants.DASH_COOLDOWN
	return enter_state(self, STATES.DASH, 0, nil, "DASH")
end

function M:press_musou(external_gauge)
	if not self:can_use_musou(external_gauge) then
		return false
	end
	local gauge = external_gauge ~= nil and external_gauge or self.musou_gauge
	self.musou_gauge = math.max(0, gauge - constants.MUSOU_COST)
	self.invulnerable_timer = constants.MUSOU_INVULNERABLE_TIME
	return enter_state(self, STATES.MUSOU_SKILL, 0, nil, "MUSOU")
end

function M:apply_hit()
	if self:is_invulnerable() then
		return false
	end
	return enter_state(self, STATES.HIT, 0, nil, "NONE")
end

function M:apply_damage()
	return self:apply_hit()
end

function M:handle_input(action, context)
	context = context or {}
	if action == "attack_light" or action == "light" then
		return self:press_light()
	elseif action == "attack_heavy" or action == "heavy" then
		return self:press_heavy()
	elseif action == "dash" then
		return self:press_dash()
	elseif action == "musou" or action == "musou_skill" then
		return self:press_musou(context.musou_gauge)
	elseif action == "test_hit" or action == "hit" then
		return self:apply_hit()
	elseif action == "move" then
		return self:set_move_intent(context.is_moving)
	end
	return false
end

function M:on_anim_done(anim_id)
	if anim_id and anim_id ~= self.state then
		return false
	end
	if self.state == STATES.IDLE or self.state == STATES.RUN then
		return false
	end
	if try_consume_buffer(self) then
		return true
	end
	local next_state = self.is_moving and STATES.RUN or STATES.IDLE
	return enter_state(self, next_state, 0, nil, "NONE")
end

function M:update(dt, is_moving)
	if dt == nil or dt < 0 then
		dt = 0
	end
	if is_moving ~= nil then
		self.is_moving = is_moving and true or false
	end

	if self.invulnerable_timer > 0.0 then
		self.invulnerable_timer = math.max(0.0, self.invulnerable_timer - dt)
	end
	if self.dash_cooldown > 0.0 then
		self.dash_cooldown = math.max(0.0, self.dash_cooldown - dt)
	end

	if self.state == STATES.IDLE and self.is_moving then
		enter_state(self, STATES.RUN, 0, nil, "NONE")
	elseif self.state == STATES.RUN and not self.is_moving then
		enter_state(self, STATES.IDLE, 0, nil, "NONE")
	end

	self.state_time = self.state_time + dt

	if (self.state == STATES.ATTACK_1 or self.state == STATES.ATTACK_2 or self.state == STATES.ATTACK_3)
		and self.buffered_action ~= nil
		and self.state_time >= constants.COMBO_CHAIN_WINDOW then
		if try_consume_buffer(self) then
			return self.state
		end
	end

	local duration = ANIM_DURATION[self.state]
	if duration and self.state ~= STATES.IDLE and self.state ~= STATES.RUN then
		if self.state_time >= duration then
			self:on_anim_done(self.state)
		end
	end

	return self.state
end

return M
