# Musou2D — 2D 無雙動作系統與角色立繪自動拆圖 Spine 骨骼管線

基於 **Defold 1.13.2** 與 **extension-spine 4.9.4 (Spine 4.2 Runtime)** 打造的 2D 無雙遊戲第一階段核心專案。

- **線上遊玩 (GitHub Pages HTML5 WebAssembly)**：<https://hanklord.github.io/defold-musou2d/>
- **架構設計文件**：[`docs/PHASE1_ARCHITECTURE.md`](docs/PHASE1_ARCHITECTURE.md)

---

## 核心功能

### 1. 角色立繪自動拆圖與 Spine 4.2 骨骼動畫自動生成管線 (`tools/auto_rig_spine.py`)
- **一鍵執行**：
  ```bash
  python3 tools/auto_rig_spine.py \
    --input assets/raw/musou2d_hero_input.jpg \
    --output-dir assets/spine \
    --name hero
  ```
- **處理流程**：
  1. 自動檢測背景色去背轉透明 RGBA（含邊緣防灰邊處理）。
  2. 透過連通區塊標記（Connected-Component Labeling）自動切分三國古風關刀武將 **17 個獨立分離部件 Island**（頭盔紅纓、胸甲、腰裙、披風、左右上臂/前臂、4 組替換手型、左右大腿/小腿戰靴、長柄關刀），並支援單體角色立繪解剖比例切分與關節圓弧補邊。
  3. 自動生成 Defold `assets/spine/hero.atlas`、`assets/spine/hero.spinescene` 與相容於 `extension-spine` 4.9.4 (Spine 4.2 C Runtime) 之 `assets/spine/hero.spinejson`。
  4. 內建 **9 大無雙基礎動作** 與 **4 大動畫事件**：
     - 動作：`idle`、`run`、`attack_1` (N1)、`attack_2` (N2)、`attack_3` (N3)、`charge_attack` (C1~C4 重擊)、`dash` (閃避取消)、`musou_skill` (無雙亂舞)、`hit` (受擊硬直)。
     - 事件：`hitbox_on`、`hitbox_off`、`footstep`、`musou_burst`。

### 2. Defold 2.5D 無雙人物動作系統 (`shared/`, `player/`, `enemy/`, `hud/`)
- **2.5D 八向平面移動與 Y-Sorting 縱深排序** (`shared/movement.lua`)
- **FSM 角色狀態機與輸入緩衝** (`shared/fsm.lua`)：
  - 輕攻擊連段：`N1` → `N2` → `N3`
  - C 技重擊派生：`C1`（單發破防）、`N1→C2`（浮空挑斬）、`N2→C3`（橫掃連擊）、`N3→C4`（大範圍霸王震波）
  - **Dash 閃避取消**：普攻與重擊收招期間可隨時閃避取消並獲得無敵幀 (`0.25s`)
  - **無雙亂舞 (`musou_skill`)**：消耗 100 無雙值發動全程霸體多段高速斬擊與終結震波
- **Hitbox 打擊判定與沙盒訓練木樁** (`shared/combat.lua`, `enemy/dummy.script`)
- **即時戰鬥 HUD** (`hud/hud.gui_script`)：HP 條、無雙量表、Combo 連擊計數、當前 FSM 狀態與招式提示

---

## 操作方式 (Controls)

| 按鍵 | 動作 |
| :--- | :--- |
| `W / A / S / D` 或 `方向鍵` | 2.5D 八向平面移動 |
| `J` / `Z` / `滑鼠左鍵` | 輕攻擊連段 (`N1` → `N2` → `N3`) |
| `K` / `X` / `滑鼠右鍵` | C 技重擊派生 (`C1` / `C2` / `C3` / `C4`) |
| `L` / `Space` | Dash 閃避衝刺（可取消攻擊動作，附帶無敵幀） |
| `U` / `C` | 施放「無雙亂舞」必殺技（需無雙值 100%） |
| `H` | 沙盒自測受擊硬直 (`hit`) |

---

## 自動化驗證與建置腳本

```bash
# 1. 靜態規則檢查 + Spine 管線驗證 + Headless 純 Lua 單元與連段冒煙測試
./tools/run-tests.sh

# 2. Linux Debug Engine 實際啟動日誌 Clean-Boot 驗證
./tools/verify-clean-boot.sh

# 3. HTML5 (wasm-web) Cloud Extender 打包驗證
./tools/smoke-html5.sh

# 4. 部署 HTML5 Bundle 至 GitHub Pages (gh-pages 分支)
./tools/deploy-gh-pages.sh
```
