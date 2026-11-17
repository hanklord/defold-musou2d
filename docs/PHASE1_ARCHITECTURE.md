# Musou2D Phase-1 Architecture & Interface Design Proposal

## 1. 專案目標與架構總覽
本提案定義 2D 無雙遊戲（`musou2d-team`）第一階段 **「基礎人物動作系統 + 角色立繪自動拆圖與 Spine 骨骼動畫管線」** 的完整技術契約、目錄權責、資料格式與自動化驗證標準。

### 1.1 技術棧與工具鏈鐵律
- **引擎版本**：Defold 1.13.2（`~/defold-tools/bob.jar` + `~/defold-tools/jdk-25.0.4.1+1`）
- **Spine 擴充套件**：`extension-spine` `4.9.4`
  - Dependency URL：`https://github.com/defold/extension-spine/archive/refs/tags/4.9.4.zip`
  - **目標 Spine Runtime 版本**：**Spine 4.2**（`"spine": "4.2.00"`）
- **Defold 專案鐵律**：
  1. `game.project` 的 `[input] game_binding` 必須設為編譯後路徑 `/input/game.input_bindingc`。
  2. 嚴禁在執行期（`.lua` / `.script` / `.gui_script`）使用 `dofile()`、`loadfile()`、`io.open()` 或動態變數 `require(var)`；所有共享模組一律以字串常值 `require("shared.xxx")` 載入。
  3. 所有 Static / Kinematic Collision Object 的 `mass` 必須為 `0.0`（防止 `Invalid mass for shape type` 導致引擎黑畫面）。
  4. HTML5 打包平台為 `wasm-web`，必須加上 `--build-server https://build.defold.com`，輸出目錄設為 `dist/`（嚴禁使用 `build/`）。

---

## 2. 目錄結構與權責劃分 (Ownership Matrix)

```text
musou2d/
├── game.project                      # [Lead] 專案設定、extension-spine 4.9.4 依賴
├── input/
│   └── game.input_binding            # [Lead] 鍵盤/滑鼠輸入映射
├── main/
│   ├── main.collection               # [Lead] 沙盒主場景（整合 player, dummies, arena, hud）
│   └── main.script                   # [Lead] 場景初始化、攝影機微震動與沙盒控制
├── assets/
│   ├── raw/
│   │   └── test_hero.png             # [Rigger] 測試用單張角色立繪（512x512 RGBA）
│   └── spine/
│       ├── parts/                    # [Rigger] 自動切分之 13 張部位 PNG 圖層
│       ├── hero.atlas                # [Rigger] 自動生成之 Defold Atlas
│       ├── hero.spinejson            # [Rigger] 自動生成之 Spine 4.2 骨骼與 9 動作 JSON
│       └── hero.spinescene           # [Rigger] 綁定 hero.spinejson 與 hero.atlas
├── shared/                           # [Coder] 純 Lua 引擎無關核心邏輯（可獨立單元測試）
│   ├── constants.lua                 # 狀態常數、移動/戰鬥參數、動作幀長與事件定義
│   ├── fsm.lua                       # 角色狀態機（含連段緩衝、C技派生、Dash取消、無雙技）
│   ├── movement.lua                  # 2.5D 八向平面移動、邊界夾限、Y-Z 深度排序、位移衝量
│   └── combat.lua                    # Hitbox 判定、2.5D 碰撞檢測、連擊計數、無雙值累積
├── player/
│   ├── player.go                     # [Coder] 玩家物件（含 spinemodel、script、kinematic collision）
│   └── player.script                 # [Coder] 連接輸入、shared 邏輯與 spine.play_anim 事件回呼
├── enemy/
│   ├── dummy.go                      # [Coder] 沙盒訓練木樁敵人（含 spinemodel、kinematic collision）
│   └── dummy.script                  # [Coder] 受擊閃白、擊退位移、傷害統計與自動回血
├── hud/
│   ├── hud.gui                       # [Coder] HUD 介面（HP、無雙條、Combo 連擊、當前招式、按鍵說明）
│   └── hud.gui_script                # [Coder] HUD 狀態更新與視覺動態
├── tools/
│   ├── auto_rig_spine.py             # [Rigger] 單張立繪自動拆圖 + Atlas + Spine 4.2 JSON 生成器
│   ├── run-tests.sh                  # [Lead] Headless Lua 單元測試 + 靜態檢查 + Spine 管線測試
│   ├── verify-clean-boot.sh          # [Lead] Linux debug engine 啟動日誌 Clean-Boot 驗證
│   └── smoke-html5.sh                # [Lead] HTML5 wasm-web + build-server 打包冒煙驗證
└── test/
    ├── runner.lua                    # [Coder] 純 Lua 測試執行器
    ├── test_fsm.lua                  # [Coder] FSM 狀態轉移與連段/取消測試
    ├── test_movement.lua             # [Coder] 2.5D 八向移動與 Z-depth 測試
    ├── test_combat.lua               # [Coder] Hitbox/Hurtbox 與無雙計量測試
    └── test_spine_pipeline.py        # [Rigger] 自動拆圖與 Spine 4.2 JSON 結構與契約驗證
```

---

## 3. 角色立繪自動拆圖與 Spine 骨骼動畫管線契約 (`musou2d-spine-rigger-t34679`)

### 3.1 CLI 執行介面
工具腳本 `tools/auto_rig_spine.py` 必須支援一鍵命令列執行：
```bash
# 1. 若尚未提供立繪，可自動生成高品質測試無雙武將立繪並跑通全流程：
python3 tools/auto_rig_spine.py --input assets/raw/test_hero.png --output-dir assets/spine --name hero --generate-default-if-missing

# 2. 使用者提供任意角色單張立繪（PNG/JPG）時，直接指定 --input 即可一鍵覆寫更新：
python3 tools/auto_rig_spine.py --input /path/to/user_character.png --output-dir assets/spine --name hero
```
**前處理要求**：
- 若輸入圖片無 Alpha 通道（RGB）或背景非透明，自動以四角背景取樣 + 顏色距離閾值去背轉為 RGBA。
- 自動偵測角色非透明像素 Bounding Box，等比縮放並置中正規化至 `512x512` 標準畫布後進行解剖比例切分，並在關節交界處自動補齊圓弧重疊邊緣（Joint Feathering / Overlap Padding 6~10px），避免旋轉時產生裂縫。

### 3.2 自動拆圖 13 個標準部位圖層 (Cutout Parts Contract)
輸出至 `assets/spine/parts/<part_name>.png`，繪製順序（Slot Draw Order 由後往前）如下：

| 繪製順序 | 部件名稱 (`slot` / `attachment`) | 綁定骨骼 (`bone`) | 解剖切分區域與用途說明 |
| :--- | :--- | :--- | :--- |
| 1 (底層) | `cape` | `cape` | 披風 / 背部飄帶（隨移動與攻擊大幅飄動） |
| 2 | `arm_r_upper` | `arm_r_upper` | 右上臂（後側手） |
| 3 | `arm_r_lower` | `arm_r_lower` | 右前臂與手掌（持武器之手） |
| 4 | `weapon` | `weapon` | 無雙長柄武器（方天畫戟/長刀，具大範圍揮砍軌跡） |
| 5 | `leg_r_upper` | `leg_r_upper` | 右大腿（後側腿） |
| 6 | `leg_r_lower` | `leg_r_lower` | 右小腿與戰靴 |
| 7 (核心) | `torso` | `torso` | 軀幹胸甲與腰甲（角色重心樞紐） |
| 8 | `leg_l_upper` | `leg_l_upper` | 左大腿（前側腿） |
| 9 | `leg_l_lower` | `leg_l_lower` | 左小腿與戰靴 |
| 10 | `head` | `head` | 頭顱、臉部與頭盔主體 |
| 11 | `hair_front` | `hair_front` | 頭冠翎毛 / 前髮（隨頭部動作擺動） |
| 12 | `arm_l_upper` | `arm_l_upper` | 左上臂（前側手） |
| 13 (頂層) | `arm_l_lower` | `arm_l_lower` | 左前臂與手掌 |

### 3.3 Spine 4.2 骨骼階層與嚴格格式規範 (`hero.spinejson`)
`extension-spine` 4.9.4 內建 Spine 4.2 C Runtime (`SkeletonJson.c`)，生成的 `.spinejson` **必須嚴格遵守 Spine 4.2 JSON 規範**：
1. **`skeleton` 標頭**：
   ```json
   "skeleton": {
     "hash": "musou2d_hero_v1",
     "spine": "4.2.00",
     "x": -128,
     "y": 0,
     "width": 256,
     "height": 280
   }
   ```
2. **`bones` 骨骼樹**：
   - `root` `(0, 0)`
     - `hip` `(0, 95)` — 全身重心（控制跑步上下起伏、受擊後仰、閃避前衝）
       - `torso` `(0, 10, length: 65, rotation: 90)`
         - `head` `(65, 0, length: 45, rotation: 0)`
           - `hair_front` `(35, 8, length: 35, rotation: -120)`
         - `cape` `(55, -10, length: 90, rotation: -165)`
         - `arm_l_upper` `(55, 22, length: 38, rotation: -155)`
           - `arm_l_lower` `(38, 0, length: 36, rotation: 25)`
         - `arm_r_upper` `(55, -22, length: 38, rotation: -145)`
           - `arm_r_lower` `(38, 0, length: 36, rotation: 35)`
             - `weapon` `(32, 0, length: 140, rotation: 45)`
       - `leg_l_upper` `(-8, -12, length: 45, rotation: -85)`
         - `leg_l_lower` `(45, 0, length: 45, rotation: -5)`
       - `leg_r_upper` `(8, -12, length: 45, rotation: -95)`
         - `leg_r_lower` `(45, 0, length: 45, rotation: -5)`
3. **`skins` 格式鐵律（Spine 4.2 必填 Array，不可用 Object）**：
   ```json
   "skins": [
     {
       "name": "default",
       "attachments": {
         "torso": {
           "torso": { "x": 32.5, "y": 0, "rotation": -90, "width": 96, "height": 110 }
         }
       }
     }
   ]
   ```
   - 每個 attachment 的 key 與圖片檔名（不含 `.png`）一致，對應 `hero.atlas` 內的圖片名稱。
4. **`rotate` Timeline 格式鐵律（Spine 4.2 必填 `"value"`，不可用 `"angle"`）**：
   - 旋轉關鍵幀：`{ "time": 0.15, "value": -45.0 }`
   - 位移關鍵幀：`{ "time": 0.15, "x": 12.0, "y": -4.0 }`
   - 縮放關鍵幀：`{ "time": 0.15, "x": 1.0, "y": 1.0 }`
5. **`events` 頂層定義與動畫事件契約**：
   頂層 `"events"` 必須宣告以下 4 個標準事件：
   - `"hitbox_on"`：`{ "int": 10, "float": 1.0, "string": "N1" }`（啟動攻擊判定，`int` 為基礎傷害，`float` 為擊退倍率，`string` 為招式標籤）
   - `"hitbox_off"`：`{ "int": 0, "float": 0.0, "string": "" }`（關閉攻擊判定）
   - `"footstep"`：`{ "int": 1, "float": 0.0, "string": "step" }`（腳步事件）
   - `"musou_burst"`：`{ "int": 1, "float": 2.5, "string": "burst" }`（無雙覺醒爆發特效事件）

### 3.4 九大無雙基礎動作規格 (`animations`)

| 動作名稱 (`anim_id`) | 長度 (秒) | 播放模式 | 關鍵幀與動畫事件 (`events`) 規範 |
| :--- | :---: | :---: | :--- |
| `idle` | `1.20` | `LOOP_FORWARD` | 呼吸律動（胸腔微幅起伏、武器與披風微擺） |
| `run` | `0.60` | `LOOP_FORWARD` | 軀幹前傾、雙腿與雙臂反向大幅交替邁步；`0.15s` 與 `0.45s` 觸發 `footstep` |
| `attack_1` | `0.45` | `ONCE_FORWARD` | 輕擊一段（N1 橫掃）：蓄力轉身後右手揮戟橫斬；`0.14s` `hitbox_on` (`string="N1", int=12, float=1.0`)，`0.30s` `hitbox_off` |
| `attack_2` | `0.45` | `ONCE_FORWARD` | 輕擊二段（N2 上挑）：跨步斜上挑斬；`0.14s` `hitbox_on` (`string="N2", int=15, float=1.2`)，`0.32s` `hitbox_off` |
| `attack_3` | `0.55` | `ONCE_FORWARD` | 輕擊三段（N3 大迴旋斬）：大幅全身轉體橫掃；`0.18s` `hitbox_on` (`string="N3", int=22, float=1.6`)，`0.40s` `hitbox_off` |
| `charge_attack` | `0.70` | `ONCE_FORWARD` | 重擊 / C技派生（蓄力重劈震地）：高舉武器重砸前方；`0.22s` `hitbox_on` (`string="CHARGE", int=32, float=2.2`)，`0.48s` `hitbox_off` |
| `dash` | `0.32` | `ONCE_FORWARD` | 閃避衝刺：壓低重心高速前衝、披風向後水平揚起 |
| `musou_skill` | `1.40` | `ONCE_FORWARD` | 無雙亂舞：起手 `0.08s` 觸發 `musou_burst`，接續三波高速狂斬與終結震波（`0.22s~0.38s`、`0.52s~0.68s`、`0.88s~1.15s` 各一組 `hitbox_on`/`hitbox_off`，`int=28, float=2.5, string="MUSOU"`） |
| `hit` | `0.35` | `ONCE_FORWARD` | 受擊硬直：軀幹與頭部後仰、雙臂張開震動後恢復 |

---

## 4. Defold 基礎人物動作系統契約 (`musou2d-coder-t34680`)

### 4.1 輸入映射契約 (`input/game.input_binding`)
| 輸入類型 | 按鍵綁定 | `action_id` | 功能說明 |
| :--- | :--- | :--- | :--- |
| 方向移動 | `W` / `UP` | `move_up` | 往場景深處（+Y）移動 |
| 方向移動 | `S` / `DOWN` | `move_down` | 往場景前景（-Y）移動 |
| 方向移動 | `A` / `LEFT` | `move_left` | 往左（-X）移動並面向左 |
| 方向移動 | `D` / `RIGHT` | `move_right` | 往右（+X）移動並面向右 |
| 輕攻擊 | `J` | `attack_light` | 輕攻擊連段 N1 → N2 → N3 |
| 重攻擊 (C技) | `K` | `attack_heavy` | 單發重擊 C1，或接於 N1/N2/N3 後派生 C2/C3/C4 |
| 閃避取消 | `L` / `SPACE` | `dash` | 閃避衝刺（可取消普攻與重擊收招，具無敵幀） |
| 無雙亂舞 | `U` | `musou` | 消耗 100 無雙值施放無雙亂舞（全程霸體無敵） |
| 測試受擊 | `H` | `test_hit` | 沙盒自測受擊狀態 (`hit`) 與硬直恢復 |

### 4.2 純 Lua 核心模組契約 (`shared/*.lua`)
1. **`shared/constants.lua`**：
   - 定義所有狀態常數、動畫時間表 (`ANIM_DURATION`)、預設動作事件時間點（作為引擎 callback 的雙重安全保護）、移動速度 (`MOVE_SPEED_X = 260`, `MOVE_SPEED_Y = 180`)、沙盒邊界 (`ARENA_BOUNDS = { min_x = 80, max_x = 1200, min_y = 100, max_y = 520 }`)。
2. **`shared/fsm.lua`**：
   - `M.new()` 建立狀態機實例，包含：`state`, `state_time`, `combo_step` (0~3), `buffered_action` (`"light"` / `"heavy"` / `nil`), `charge_variant` (`"C1"` / `"C2"` / `"C3"` / `"C4"`), `invulnerable_timer`, `dash_cooldown`。
   - **連段與派生規則**：
     - `idle` / `run` 按 `attack_light` → `attack_1` (N1)
     - `attack_1` 期間按 `attack_light` 進入緩衝 → 動作結束或切換窗口 (`>= 0.26s`) 轉入 `attack_2` (N2)
     - `attack_2` 期間按 `attack_light` 進入緩衝 → 轉入 `attack_3` (N3)
     - `idle` / `run` 按 `attack_heavy` → `charge_attack` (`variant = "C1"`)
     - `attack_1` 按 `attack_heavy` → `charge_attack` (`variant = "C2"`)
     - `attack_2` 按 `attack_heavy` → `charge_attack` (`variant = "C3"`)
     - `attack_3` 按 `attack_heavy` → `charge_attack` (`variant = "C4"`)
   - **閃避取消 (Dash Cancel)**：在 `idle`、`run`、`attack_1~3`、`charge_attack` 任意時刻按 `dash`（且 `dash_cooldown <= 0`），立即取消當前動作轉入 `dash`，賦予 `0.25s` 無敵幀與高速位移。
   - **無雙亂舞 (`musou_skill`)**：當 `musou_gauge >= 100` 且非 `hit` 狀態時按 `musou`，立即轉入 `musou_skill`，扣除 100 無雙值並賦予 `1.40s` 全程無敵。
3. **`shared/movement.lua`**：
   - `M.step(pos, input_dir, fsm_state, facing, dt)`：
     - 計算 8 向正規化移動向量，套用 2.5D 縱深比例（X 軸 260 px/s，Y 軸 180 px/s）。
     - 處理攻擊微幅前踏位移（Attack Step Impulse）與 `dash` 爆發衝刺位移（520 px/s）。
     - 夾限於 `ARENA_BOUNDS` 內，並計算 `z = 0.5 - (pos.y / 1000.0)` 實現 2.5D Y-Sorting 前後遮擋。
4. **`shared/combat.lua`**：
   - 管理 Hitbox 啟閉（由 `spine_event` 的 `hitbox_on` / `hitbox_off` 驅動）、2.5D 扇區與 Y 軸深度距離判定 (`|dx| <= range_x` 且方向一致、`|dy| <= 48`)。
   - 管理連擊數 `combo_count`（每次命中 +1，超過 `3.0s` 未命中歸零）與無雙值 `musou_gauge`（初始值 `100` 供開局立即體驗，每次命中回復 `+15`，上限 `100`）。

### 4.3 Spine 動畫控制與組件訊息介面
- **玩家 Spine 控制 (`player/player.script`)**：
  - 使用 `spine.play_anim("#spinemodel", anim_id, playback, { blend_duration = 0.1 }, spine_callback)` 播放動畫。
  - 在 `spine_callback(self, message_id, message, sender)` 中處理：
    - `message_id == hash("spine_event")`：讀取 `message.event_id`（`hash("hitbox_on")`、`hash("hitbox_off")`、`hash("footstep")`、`hash("musou_burst")`）、`message.integer`、`message.float`、`message.string`，觸發 `combat.activate_hitbox(...)` 或視覺震動。
    - `message_id == hash("spine_animation_done")`：通知 `fsm.on_anim_done()` 推進緩衝連段或回到 `idle`。
- **場景內訊息契約**：
  - Player → Dummy：由 `main.script` 或 `player.script` 查詢沙盒內木樁座標（或透過群組訊息 `msg.post("/dummy_1#script", "apply_hit", { damage = ..., knockback_x = ..., attack_tag = ... })`）觸發木樁受擊動畫、傷害跳字與擊退。
  - Player → HUD：`msg.post("/hud#hud", "update_hud", { state = ..., attack_tag = ..., combo = ..., hp = ..., max_hp = ..., musou = ..., max_musou = ..., last_damage = ... })`。

---

## 5. 測試與驗證計畫 (Verification Gates)

1. **Gate 1 — Spine 自動拆圖管線驗證 (`test/test_spine_pipeline.py`)**：
   - 自動執行 `tools/auto_rig_spine.py`，斷言產出 13 張非空 RGBA 部件 PNG、`hero.atlas`、`hero.spinescene` 與 `hero.spinejson`。
   - 嚴格檢驗 `hero.spinejson`：`"spine"` 版本為 `"4.2.00"`、`skins` 為 `list`、所有 `rotate` 關鍵幀皆使用 `"value"` 而非 `"angle"`、9 個指定動作與 4 個事件完整存在。
2. **Gate 2 — Headless 純 Lua 單元與整合冒煙測試 (`tools/run-tests.sh`)**：
   - 靜態掃描所有 `.lua` / `.script` / `.gui_script`，禁止 `dofile` / `loadfile` / `io.open` 與非字串常值 `require`。
   - 以 `~/defold-tools/lua test/runner.lua` 執行 FSM、2.5D 移動、N1~N3 連段、C1~C4 派生、Dash 取消、無雙技、Hitbox 2.5D 判定等完整單元與模擬冒煙測試。
3. **Gate 3 — Linux Engine Log Clean-Boot 驗證 (`tools/verify-clean-boot.sh`)**：
   - 使用 `bob.jar` 建置 `x86_64-linux` debug 執行檔並實際啟動引擎，擷取 stdout/stderr，斷言無 `Invalid mass`、`GAMESYS`、`ERROR`、`Failed to` 等執行期初始化錯誤。
4. **Gate 4 — HTML5 (`wasm-web`) Bundle 建置驗證 (`tools/smoke-html5.sh`)**：
   - 使用 `bob.jar --platform wasm-web --archive --variant release --build-server https://build.defold.com --bundle-output dist resolve distclean build bundle` 完成打包，確認 `dist/` 下產出 `.wasm`、`index.html`、`dmloader.js` 與資源壓縮檔。
