package.path = "./?.lua;./?/init.lua;" .. package.path

local test_fsm = require("test.test_fsm")
local test_movement = require("test.test_movement")
local test_combat = require("test.test_combat")
local test_event_gate = require("test.test_event_gate")

print("Running Musou2D Pure-Lua Unit & Action Smoke Tests...")
local total = 0
total = total + test_fsm.run()
total = total + test_movement.run()
total = total + test_combat.run()
total = total + test_event_gate.run()
print(string.format("SUCCESS: All %d test suites passed!", total))
