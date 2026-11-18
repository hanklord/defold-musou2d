# Musou2D Phase-1 Architecture & Interface Design Proposal

## 1. 專案目標與架構總覽
本提案定義 2D 無雙遊戲（`musou2d-team`）第一階段 **「基礎人物動作系統 + 角色立繪自動拆圖與 Spine 骨骼動畫管線」** 的完整技術契約、目錄權責、資料格式與自動化驗證標準。

### 1.1 技術棧與工具鏈鐵律
- **引擎版本**：Defold 1.13.2（`~/defold-tools/bob.jar` + `~/defold-tools/jdk-25.0.4.1+1`）
- **Spine 擴充套件**：`extension-spine` `4.8.0`
  - Dependency URL：`https://github.com/defold/extension-spine/archive/refs/tags/4.8.0.zip`
  - 版本選擇理由：4.8.0 是對應 Defold 1.13.2 的最後一版；4.9.x 起要求 Defold 1.14.0+，與鎖定的 1.13.2 工具鏈不相容。升級 Defold 時再一併升級 extension-spine。
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
├── game.project                      # [Lead] 專案設定、extension-spine 4.8.0 依賴
├── input/
│   └── game.input_binding            # [Lead] 鍵盤/滑鼠輸入映射
├── main/
│   ├── main.collection               # [Lead] 沙盒主場景（整合 player, dummies, arena, hud）
│   └── main.script                   # [Lead] 場景初始化、攝影機微震動與沙盒控制
├── assets/
│   ├── raw/
│   │   └── musou2d_hero_input.jpg    # [Rigger] 用戶提供之三國關刀武將 17 部件拆解圖（1024x1024）
│   └── spine/
│       ├── parts/                    # [Rigger] 自動去背 + 連通區塊切分之 17 張部位 PNG 圖層
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
工具腳本 `tools/auto_rig_spine.py` 必須支援一鍵命令列執行（預設處理用戶提供之 `assets/raw/musou2d_hero_input.jpg` 1024×1024 三國關刀武將部件圖，亦支援任意新角色圖）：
```bash
python3 tools/auto_rig_spine.py \
  --input assets/raw/musou2d_hero_input.jpg \
  --output-dir assets/spine \
  --name hero
```
**前處理與連通區塊自動切分要求**：
- 自動以背景色取樣（純淺灰底 `#C8C8C8` 顏色距離閾值 + 邊緣羽化去背）轉為透明 RGBA。
- 透過 Connected-Component Labeling (連通區塊標記) 自動偵測並切分畫面中 **17 個獨立分離部件 Island**（或對單體立繪進行解剖區域切分），自動計算各部件 Pivot 與關節座標。

### 3.2 自動拆圖 17 個標準部位圖層 (17-Island Cutout Parts Contract)
從 `assets/raw/musou2d_hero_input.jpg` 自動切分輸出至 `assets/spine/parts/<part_name>.png`（共 17 個部件 Island，包含 13 個主體骨骼部件 + 4 個可替換手型 Attachments）：

1. **`head`**（左上：頭盔+紅纓+頭部，綁定於 `head` 骨骼）
2. **`torso`**（胸甲軀幹，綁定於 `torso` 骨骼）
3. **`skirt` / `waist`**（中下：腰帶+腰甲戰裙，綁定於 `hip` 或 `skirt` 骨骼）
4. **`cape`**（中右下：紅色披風，最底層 Z-order，綁定於 `cape` 骨骼）
5. **`arm_r_upper`**（左側：右上臂+肩甲，綁定於 `arm_r_upper` 骨骼）
6. **`arm_r_lower`**（最左：右前臂+張開手，綁定於 `arm_r_lower` 骨骼）
7. **`arm_l_upper`**（胸甲右側：左上臂+肩甲，綁定於 `arm_l_upper` 骨骼）
8. **`arm_l_lower`**（左上臂下方：左前臂護腕，綁定於 `arm_l_lower` 骨骼）
9–12. **`hand_1` ~ `hand_4`**（中間排 4 個獨立替換手型：張開手、握拳、左斜握拳、右斜握拳，掛載於 `hand_l` / `weapon_hand` slot 供持刀與攻擊切換 Attachment）
13. **`leg_r_upper`**（右大腿，綁定於 `leg_r_upper` 骨骼）
14. **`leg_r_lower`**（左下：右小腿+戰靴，綁定於 `leg_r_lower` 骨骼）
15. **`leg_l_upper`**（左大腿，綁定於 `leg_l_upper` 骨骼）
16. **`leg_l_lower`**（左中下：左小腿+戰靴，綁定於 `leg_l_lower` 骨骼）
17. **`weapon` / `guandao`**（最右側垂直長柄關刀完整武器，綁定於 `weapon` 骨骼）

### 3.3 Spine 4.2 骨骼階層與嚴格格式規範 (`hero.spinejson`)
`extension-spine` 4.8.0 內建 Spine 4.2 C Runtime (`SkeletonJson.c`)，生成的 `.spinejson` **必須嚴格遵守 Spine 4.2 JSON 規範**：
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
2. **`bones` 骨骼樹**（以 `tools/auto_rig_spine.py` 實際輸出為準；座標為父骨局部座標 `(x, y)`，所有骨骼 `rotation = 0`，`length` 僅供編輯器顯示）：
   - **雙命名（dual-naming）**：骨架分兩層。
     - **動畫骨（Animation bones）**：實際承載 slot 與所有 `rotate` / `translate` / `scale` timeline，命名沿用拆圖部件語意（`arm_r`、`forearm_r`、`thigh_*`、`shin_*`、`weapon_guandao`…）。
     - **契約 alias 骨（Contract alias bones）**：S-1 契約名 `arm_*_upper` / `arm_*_lower` / `leg_*_upper` / `leg_*_lower` / `weapon` / `skirt`，皆為對應動畫骨的 **0 偏移子骨**（`x = y = rotation = 0`），不掛 slot、不打關鍵幀，僅隨父骨移動。供遊戲端 `spine.get_go()` / 掛點 / hitbox 以契約名查找世界座標。
   - 樹狀結構：
     - `root` `(0, 0)`
       - `hip` `(0, 122)` — 全身重心（控制跑步上下起伏、受擊後仰、閃避前衝）；腳底落在 `root` y=0
         - `torso` `(0, 6)`
           - `head` `(4, 66)`
           - `cape` `(-8, 58)`
           - `waist` `(0, -2)` → slot `waist_skirt`
             - `skirt` *(alias, 0 偏移)*
           - `arm_r` `(-28, 52)` → slot `arm_upper_r`
             - `arm_r_upper` *(alias)*
             - `forearm_r` `(-16, -34)` → slot `forearm_r`
               - `arm_r_lower` *(alias)*
               - `hand_r` `(2, -42)` — 持刀握點（無 slot，見下方說明）
                 - `weapon_guandao` `(0, 0)` → slot `weapon_guandao`（骨原點 = 握點；attachment `scaleX < 0` 鏡像刀刃使刃口朝 +X 前方，rest rotation 0° 直立）
                   - `weapon` *(alias)*
           - `arm_l` `(26, 50)` → slot `arm_upper_l`
             - `arm_l_upper` *(alias)*
             - `forearm_l` `(14, -32)` → slot `forearm_l`
               - `arm_l_lower` *(alias)*
               - `hand_l` `(8, -26)` → slot `hand_l`（`hand_1` 張開手掌原圖為指尖朝上，attachment 旋轉 180° 使其由腕部垂下；預設 attachment `hand_2`，動畫以 attachment timeline 切換 `hand_1..hand_4` 手勢）
         - `thigh_r` `(-16, -6)` → slot `thigh_r`
           - `leg_r_upper` *(alias)*
           - `shin_r` `(-4, -52)` → slot `shin_r`
             - `leg_r_lower` *(alias)*
         - `thigh_l` `(16, -6)` → slot `thigh_l`
           - `leg_l_upper` *(alias)*
           - `shin_l` `(6, -52)` → slot `shin_l`
             - `leg_l_lower` *(alias)*
   - **為何沒有 `hand_r` / `weapon_hand` slot**：原圖 17 島中只有 4 個手型島（`hand_1..hand_4`，皆為左手空手手勢），右手握柄已畫在 `forearm_r` 末端並與關刀柄重疊；draw order 中 `weapon_guandao` 在 `forearm_r` 之下，形成「手握刀柄」的遮擋。若再加一個 `hand_r` slot 會在握點重複繪製且沒有對應素材。`hand_r` 骨仍保留作為武器握點 pivot 與遊戲端武器特效掛點（等同 `weapon_hand` 用途）；日後若美術提供右手握拳部件，可直接在 `hand_r` 上新增 slot（排在 `weapon_guandao` 之上），無須改骨架。
   - 原始設計中的 `hair_front` 骨未實作（原圖頭髮與 `head` 為同一島）。
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
   - `"footstep"`：`{ "int": 1, "float": 0.0, "string": "left" | "right" }`（腳步事件，string 標示左右腳）
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
   - 管理 Hitbox 啟閉（由 `spine_event` 的 `hitbox_on` / `hitbox_off` 驅動）、2.5D 扇區與 Y 軸深度距離判定 (`|dx| <= range_x` 且方向一致、`|dy| <= range_y`，`range_y` 依 `ATTACK_SPECS` 每招設定，範圍 48–80)。
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
   - 自動執行 `tools/auto_rig_spine.py`，斷言產出 17 張非空 RGBA 部件 PNG、`hero.atlas`、`hero.spinescene` 與 `hero.spinejson`。
   - 嚴格檢驗 `hero.spinejson`：`"spine"` 版本為 `"4.2.00"`、`skins` 為 `list`、所有 `rotate` 關鍵幀皆使用 `"value"` 而非 `"angle"`、9 個指定動作與 4 個事件完整存在。
2. **Gate 2 — Headless 純 Lua 單元與整合冒煙測試 (`tools/run-tests.sh`)**：
   - 靜態掃描所有 `.lua` / `.script` / `.gui_script`，禁止 `dofile` / `loadfile` / `io.open` 與非字串常值 `require`。
   - 以 `~/defold-tools/lua test/runner.lua` 執行 FSM、2.5D 移動、N1~N3 連段、C1~C4 派生、Dash 取消、無雙技、Hitbox 2.5D 判定等完整單元與模擬冒煙測試。
3. **Gate 3 — Linux Engine Log Clean-Boot 驗證 (`tools/verify-clean-boot.sh`)**：
   - 使用 `bob.jar` 建置 `x86_64-linux` debug 執行檔並實際啟動引擎，擷取 stdout/stderr，斷言無 `Invalid mass`、`GAMESYS`、`ERROR`、`Failed to` 等執行期初始化錯誤。
4. **Gate 4 — HTML5 (`wasm-web`) Bundle 建置驗證 (`tools/smoke-html5.sh`)**：
   - 使用 `bob.jar --platform wasm-web --archive --variant release --build-server https://build.defold.com --bundle-output dist resolve distclean build bundle` 完成打包，確認 `dist/` 下產出 `.wasm`、`index.html`、`dmloader.js` 與資源壓縮檔。
5. **Gate 5 — GitHub 版控與 GitHub Pages 線上部署驗證 (`tools/deploy-gh-pages.sh`)**：
   - 遠端儲存庫：`https://github.com/hanklord/defold-musou2d`（預設分支 `main`）。
   - 將 `dist/<project_title>/` 內完整的 HTML5 `wasm-web` 打包產物（含 `.nojekyll`、`index.html`、`*.wasm`、`*_wasm.js`、`dmloader.js`、`archive/*`）推送至 `gh-pages` 分支並啟用 GitHub Pages。
   - 驗證 `https://hanklord.github.io/defold-musou2d/` 與 `.wasm` 靜態資源皆回傳 HTTP 200。

