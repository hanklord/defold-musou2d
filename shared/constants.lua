local M = {}

M.STATES = {
	IDLE = "idle",
	RUN = "run",
	ATTACK_1 = "attack_1",
	ATTACK_2 = "attack_2",
	ATTACK_3 = "attack_3",
	CHARGE_ATTACK = "charge_attack",
	DASH = "dash",
	MUSOU_SKILL = "musou_skill",
	HIT = "hit"
}

M.ANIM_DURATION = {
	idle = 1.20,
	run = 0.60,
	attack_1 = 0.45,
	attack_2 = 0.45,
	attack_3 = 0.55,
	charge_attack = 0.70,
	dash = 0.32,
	musou_skill = 1.40,
	hit = 0.35
}

M.ANIM_PLAYBACK = {
	idle = "LOOP_FORWARD",
	run = "LOOP_FORWARD",
	attack_1 = "ONCE_FORWARD",
	attack_2 = "ONCE_FORWARD",
	attack_3 = "ONCE_FORWARD",
	charge_attack = "ONCE_FORWARD",
	dash = "ONCE_FORWARD",
	musou_skill = "ONCE_FORWARD",
	hit = "ONCE_FORWARD"
}

M.MOVE_SPEED_X = 260.0
M.MOVE_SPEED_Y = 180.0
M.DASH_SPEED = 520.0
M.DASH_DURATION = 0.32
M.DASH_INVULNERABLE_TIME = 0.25
M.DASH_COOLDOWN = 0.45

M.COMBO_CHAIN_WINDOW = 0.26
M.COMBO_TIMEOUT = 3.0

M.MUSOU_DURATION = 1.40
M.MUSOU_INVULNERABLE_TIME = 1.40
M.MUSOU_COST = 100
M.INITIAL_MUSOU = 100
M.MAX_MUSOU = 100
M.MUSOU_GAIN_ON_HIT = 15

M.INITIAL_HP = 100
M.MAX_HP = 100

M.DEFAULT_RANGE_X = 145.0
M.DEFAULT_RANGE_Y = 55.0
M.BACK_OVERLAP_TOLERANCE = 16.0

M.ARENA_BOUNDS = {
	min_x = 80.0,
	max_x = 1200.0,
	min_y = 100.0,
	max_y = 520.0
}

M.Z_BASE = 0.5
M.Z_SCALE = 1000.0

M.ATTACK_STEP = {
	attack_1 = { start_t = 0.0, end_t = 0.22, speed = 110.0 },
	attack_2 = { start_t = 0.0, end_t = 0.24, speed = 130.0 },
	attack_3 = { start_t = 0.0, end_t = 0.28, speed = 160.0 },
	charge_attack = { start_t = 0.0, end_t = 0.30, speed = 180.0 },
	musou_skill = { start_t = 0.10, end_t = 1.05, speed = 140.0 }
}

M.ATTACK_SPECS = {
	N1 = {
		tag = "N1",
		damage = 12,
		knockback = 1.0,
		range_x = 140.0,
		range_y = 48.0,
		omnidirectional = false,
		label = "N1 Light Slash 1"
	},
	N2 = {
		tag = "N2",
		damage = 15,
		knockback = 1.2,
		range_x = 150.0,
		range_y = 48.0,
		omnidirectional = false,
		label = "N2 Rising Cut"
	},
	N3 = {
		tag = "N3",
		damage = 22,
		knockback = 1.6,
		range_x = 170.0,
		range_y = 54.0,
		omnidirectional = false,
		label = "N3 Wide Sweep"
	},
	CHARGE = {
		tag = "CHARGE",
		damage = 32,
		knockback = 2.2,
		range_x = 175.0,
		range_y = 56.0,
		omnidirectional = false,
		label = "Charge Cleave"
	},
	C1 = {
		tag = "C1",
		damage = 28,
		knockback = 1.8,
		range_x = 160.0,
		range_y = 52.0,
		omnidirectional = false,
		label = "C1 Guard Breaker"
	},
	C2 = {
		tag = "C2",
		damage = 32,
		knockback = 2.0,
		range_x = 168.0,
		range_y = 54.0,
		omnidirectional = false,
		label = "C2 Launcher Slash"
	},
	C3 = {
		tag = "C3",
		damage = 36,
		knockback = 2.2,
		range_x = 180.0,
		range_y = 58.0,
		omnidirectional = false,
		label = "C3 Cyclone Finisher"
	},
	C4 = {
		tag = "C4",
		damage = 45,
		knockback = 2.8,
		range_x = 200.0,
		range_y = 64.0,
		omnidirectional = true,
		label = "C4 Earthquake Slam"
	},
	MUSOU = {
		tag = "MUSOU",
		damage = 28,
		knockback = 2.5,
		range_x = 220.0,
		range_y = 80.0,
		omnidirectional = true,
		label = "Musou Rampage"
	}
}

M.ANIM_EVENTS = {
	idle = {},
	run = {
		{ time = 0.15, event = "footstep", int = 1, float = 0.0, string = "step" },
		{ time = 0.45, event = "footstep", int = 1, float = 0.0, string = "step" }
	},
	attack_1 = {
		{ time = 0.14, event = "hitbox_on", int = 12, float = 1.0, string = "N1" },
		{ time = 0.30, event = "hitbox_off", int = 0, float = 0.0, string = "" }
	},
	attack_2 = {
		{ time = 0.14, event = "hitbox_on", int = 15, float = 1.2, string = "N2" },
		{ time = 0.32, event = "hitbox_off", int = 0, float = 0.0, string = "" }
	},
	attack_3 = {
		{ time = 0.18, event = "hitbox_on", int = 22, float = 1.6, string = "N3" },
		{ time = 0.40, event = "hitbox_off", int = 0, float = 0.0, string = "" }
	},
	charge_attack = {
		{ time = 0.22, event = "hitbox_on", int = 32, float = 2.2, string = "CHARGE" },
		{ time = 0.48, event = "hitbox_off", int = 0, float = 0.0, string = "" }
	},
	dash = {},
	musou_skill = {
		{ time = 0.08, event = "musou_burst", int = 1, float = 2.5, string = "burst" },
		{ time = 0.22, event = "hitbox_on", int = 28, float = 2.5, string = "MUSOU" },
		{ time = 0.38, event = "hitbox_off", int = 0, float = 0.0, string = "" },
		{ time = 0.52, event = "hitbox_on", int = 28, float = 2.5, string = "MUSOU" },
		{ time = 0.68, event = "hitbox_off", int = 0, float = 0.0, string = "" },
		{ time = 0.88, event = "hitbox_on", int = 28, float = 2.5, string = "MUSOU" },
		{ time = 1.15, event = "hitbox_off", int = 0, float = 0.0, string = "" }
	},
	hit = {}
}

return M
