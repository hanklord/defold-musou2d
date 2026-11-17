local constants = require("shared.constants")

local M = {}
M.__index = M

function M.new(opts)
	opts = opts or {}
	local self = setmetatable({}, M)
	self.hp = opts.hp or constants.INITIAL_HP
	self.max_hp = opts.max_hp or constants.MAX_HP
	self.musou_gauge = opts.musou_gauge ~= nil and opts.musou_gauge or constants.INITIAL_MUSOU
	self.max_musou = opts.max_musou or constants.MAX_MUSOU
	self.combo_count = 0
	self.max_combo = 0
	self.combo_timer = 0.0
	self.last_damage = 0
	self.last_hit_tag = "NONE"
	self.burst_count = 0
	self.footstep_count = 0

	self.hitbox = {
		active = false,
		tag = "NONE",
		damage = 0,
		knockback = 0.0,
		range_x = constants.DEFAULT_RANGE_X,
		range_y = constants.DEFAULT_RANGE_Y,
		omnidirectional = false,
		hit_targets = {}
	}
	return self
end

function M:activate_hitbox(tag, damage, knockback, opts)
	opts = opts or {}
	tag = (tag and tag ~= "") and tag or "N1"
	local spec = constants.ATTACK_SPECS[tag] or constants.ATTACK_SPECS.N1

	self.hitbox.active = true
	self.hitbox.tag = tag
	self.hitbox.damage = (damage and damage > 0) and damage or spec.damage
	self.hitbox.knockback = (knockback and knockback > 0) and knockback or spec.knockback
	self.hitbox.range_x = opts.range_x or spec.range_x or constants.DEFAULT_RANGE_X
	self.hitbox.range_y = opts.range_y or spec.range_y or constants.DEFAULT_RANGE_Y
	self.hitbox.omnidirectional = (opts.omnidirectional ~= nil) and opts.omnidirectional or (spec.omnidirectional or false)
	self.hitbox.hit_targets = {}
	return self.hitbox
end

function M:deactivate_hitbox()
	self.hitbox.active = false
	self.hitbox.hit_targets = {}
	return self.hitbox
end

function M:on_spine_event(event_name, int_val, float_val, string_val, charge_variant)
	if event_name == "hitbox_on" then
		local tag = (string_val and string_val ~= "") and string_val or "N1"
		if tag == "CHARGE" and charge_variant and constants.ATTACK_SPECS[charge_variant] then
			local cspec = constants.ATTACK_SPECS[charge_variant]
			return self:activate_hitbox(charge_variant, cspec.damage, cspec.knockback)
		end
		return self:activate_hitbox(tag, int_val, float_val)
	elseif event_name == "hitbox_off" then
		return self:deactivate_hitbox()
	elseif event_name == "musou_burst" then
		self.burst_count = self.burst_count + 1
		return self.burst_count
	elseif event_name == "footstep" then
		self.footstep_count = self.footstep_count + 1
		return self.footstep_count
	end
	return nil
end

function M.is_in_hitbox(attacker_pos, facing, target_pos, hitbox)
	if not attacker_pos or not target_pos or not hitbox then
		return false
	end
	if hitbox.active == false then
		return false
	end

	facing = (facing == -1) and -1 or 1
	local dx = (target_pos.x or 0.0) - (attacker_pos.x or 0.0)
	local dy = (target_pos.y or 0.0) - (attacker_pos.y or 0.0)
	local range_x = hitbox.range_x or constants.DEFAULT_RANGE_X
	local range_y = hitbox.range_y or constants.DEFAULT_RANGE_Y

	if math.abs(dy) > range_y then
		return false
	end

	if math.abs(dx) > range_x then
		return false
	end

	if not hitbox.omnidirectional then
		if (dx * facing) < -constants.BACK_OVERLAP_TOLERANCE then
			return false
		end
	end

	return true
end

function M:check_hit_25d(attacker_pos, facing, target_pos, range_x, range_y, omnidirectional)
	local query_box = {
		active = true,
		range_x = range_x or self.hitbox.range_x or constants.DEFAULT_RANGE_X,
		range_y = range_y or self.hitbox.range_y or constants.DEFAULT_RANGE_Y,
		omnidirectional = (omnidirectional ~= nil) and omnidirectional or self.hitbox.omnidirectional
	}
	return M.is_in_hitbox(attacker_pos, facing, target_pos, query_box)
end

function M:register_hit(damage, tag)
	damage = damage or 10
	tag = tag or self.hitbox.tag or "N1"
	self.combo_count = self.combo_count + 1
	if self.combo_count > self.max_combo then
		self.max_combo = self.combo_count
	end
	self.combo_timer = constants.COMBO_TIMEOUT
	self.musou_gauge = math.min(self.max_musou, self.musou_gauge + constants.MUSOU_GAIN_ON_HIT)
	self.last_damage = damage
	self.last_hit_tag = tag
	return self.combo_count, self.musou_gauge
end

function M:evaluate_hits(attacker_pos, facing, targets)
	local hits = {}
	if not self.hitbox.active or not targets then
		return hits
	end

	facing = (facing == -1) and -1 or 1
	for i = 1, #targets do
		local t = targets[i]
		local tid = t.id or i
		if t.alive ~= false and not self.hitbox.hit_targets[tid] then
			if M.is_in_hitbox(attacker_pos, facing, t, self.hitbox) then
				self.hitbox.hit_targets[tid] = true
				self:register_hit(self.hitbox.damage, self.hitbox.tag)
				local dir = facing
				if self.hitbox.omnidirectional then
					local dx = (t.x or 0.0) - (attacker_pos.x or 0.0)
					dir = (dx < 0.0) and -1 or 1
				end
				hits[#hits + 1] = {
					id = tid,
					damage = self.hitbox.damage,
					knockback = self.hitbox.knockback,
					knockback_x = dir * self.hitbox.knockback * 42.0,
					attack_tag = self.hitbox.tag
				}
			end
		end
	end

	return hits
end

function M:consume_musou(amount)
	amount = amount or constants.MUSOU_COST
	if self.musou_gauge < amount then
		return false
	end
	self.musou_gauge = math.max(0, self.musou_gauge - amount)
	return true
end

function M:take_damage(amount)
	amount = amount or 10
	self.hp = math.max(0, self.hp - amount)
	if self.hp <= 0 then
		self.hp = self.max_hp
	end
	return self.hp
end

function M:update(dt)
	if dt == nil or dt <= 0 then
		return
	end
	if self.combo_count > 0 then
		self.combo_timer = self.combo_timer - dt
		if self.combo_timer <= 0.0 then
			self.combo_count = 0
			self.combo_timer = 0.0
		end
	end
end

return M
