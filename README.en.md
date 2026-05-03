# UnderWorld Hero

![Python](https://img.shields.io/badge/Python-3.12-blue?style=for-the-badge&logo=python)
![Pygame-CE](https://img.shields.io/badge/Pygame--CE-2.5.7-green?style=for-the-badge)
![NumPy](https://img.shields.io/badge/NumPy-2.4.4-013243?style=for-the-badge&logo=numpy)
![Numba](https://img.shields.io/badge/Numba-0.65-00A3E0?style=for-the-badge)
![Status](https://img.shields.io/badge/Status-In_Development-yellow?style=for-the-badge)

A bullet hell survival game built with Python and Pygame-CE, focused on fast-paced combat, upgrade-driven progression, multiple playable heroes, and a multi-layer performance pipeline powered by spatial indexing (NumPy + Numba JIT + optional Cython).

Portuguese version: [README.md](README.md)

## Table of Contents

- [Overview](#overview)
- [Playable Characters](#playable-characters)
- [Enemies and Bosses](#enemies-and-bosses)
- [Game Systems](#game-systems)
- [UI and Medieval Interface](#ui-and-medieval-interface)
- [Project Architecture](#project-architecture)
- [Requirements](#requirements)
- [Installation and Run](#installation-and-run)
- [Performance and Build](#performance-and-build)
- [Distribution](#distribution)
- [Controls](#controls)
- [Settings, Save, and Persistence](#settings-save-and-persistence)
- [Resolution and Compatibility](#resolution-and-compatibility)
- [Performance Debug and Benchmark](#performance-debug-and-benchmark)
- [Folder Structure](#folder-structure)
- [Roadmap](#roadmap)
- [Contributing](#contributing)
- [License](#license)

---

## Overview

UnderWorld Hero is a survivor roguelike where the player faces escalating enemy waves, picks upgrades each level, and tries to survive as long as possible. Each run lets you choose a character, difficulty, pact, and biome — generating distinct challenge and style combinations.

Highlights:

- Real-time combat with high enemy density on screen.
- Level-by-level progression with upgrade selection and synergistic evolutions.
- 7 playable characters with unique playstyles and ultimates.
- 4 difficulty levels and 4 pacts with risk/reward modifiers.
- Daily missions, meta progression, and permanent talent tree.
- 3 independent run slots with full state saved.
- 100% medieval-themed UI with ornate sprites.

---

## Playable Characters

| Character | HP | Speed | Damage | Mana | Ultimate | Unlock |
|---|---|---|---|---|---|---|
| Warrior | 100 | 280 | 25 | 50 | Warrior's Fury | Default |
| Hunter | 63 | 340 | 38 | 75 | Arrow Rain | Default |
| Mage | 75 | 260 | 25 | 200 | Temporal Freeze | Default |
| Vampire | 88 | 300 | 38 | 100 | Shadow Storm | Default |
| Demon | 75 | 290 | 38 | 100 | Infernal Flame | Default |
| Golem | 113 | 240 | 50 | 50 | Earth Strike | Default |
| Skeleton | 95 | 265 | 44 | 75 | Blood Frenzy | Defeat 12 Bosses |

Each character has directional spritesheets (up/down/left/right) with walk, idle, and attack animations loaded via `characters.py`. The Skeleton is unlocked after 12 total boss kills.

---

## Enemies and Bosses

### Enemies — All difficulties

| Type | Base HP | Base Speed | Spawn | Description |
|---|---|---|---|---|
| Bat | 28 | 145 | 0s | Fast, sinusoidal movement |
| Runner | 50 | 150 | 0s | Fast straight-line chaser |
| Tank | 260 | 65 | 30s | High HP, slow, melee |
| Shooter | 80 | 90 | 30s | Ranged projectile attacker |
| Goblin | 80 | 160 | 1 min | Fast with moderate zigzag |
| Beholder | 200 | 85 | 1.5 min | Floating, smooth movement |
| Orc | 300 | 75 | 3 min | Large, tanky melee |
| Elite | 1500 | 85 | 30s+ | Reinforced variant with guaranteed gold drop |

> HP and speed scale with the difficulty multiplier and game time (+20% HP/damage per minute, up to 6×).

### Enemies — Hard / Hardcore only

| Type | Base HP | Base Speed | Spawn | Description |
|---|---|---|---|---|
| Slime | 130 | 110 | 30s | Balanced enemy with dark aura |
| Minotaur | 200 | 130 | 30s | Melee, direct pursuit |
| Rat | 150 | 135 | 2 min | Large (220px), aggressive zigzag |

### Enemies — Volcano Biome exclusive

Only appear when the Volcano biome is selected, starting at 2 minutes.

| Type | Base HP | Base Speed | Spawn | Description |
|---|---|---|---|---|
| Slime Fire | 280 | 125 | 2 min | Fire burst charge (2.8× speed), high contact damage |
| Slime Red | 220 | 110 | 2 min | Tanky, slow, high HP |
| Slime Yellow | 160 | 145 | 2 min | Agile, low HP, fast attacks |

### Enemies — Moon and Volcano Biome exclusive

Appear in both Moon and Volcano biomes, starting at 2 minutes.

| Type | Base HP | Base Speed | Spawn | Description |
|---|---|---|---|---|
| Ghost | 200 | 120 | 2 min | Sinusoidal floating with ghostly dash (2.5× speed); unique death animation |

### Bosses

| Type | Base HP | Spawn | Description |
|---|---|---|---|
| Mini Boss | 6000 | ~10 min | Own health bar, scales with time (+30% × time_scale) |
| Boss | scalable | every 5 min | Multi-phase, grows stronger each wave |
| Agis | 10000 | 15 min (summoning seal) | Slow boss, double-orb + 8-orb area magic every 5s (+25% × time_scale) |

**Agis** is summoned through an animated seal (`doom_agis.png`) appearing near the player ~30s before spawn. Has a basic ranged attack (purple double orb) and an area spell firing 8 orbs in all directions. Drops a chest + 15 coins on death.

Hordes are processed through an async queue (6 enemies/frame), eliminating CPU spikes. Obstacles spawn gradually from the start of the run instead of bulk-spawning during hordes.

---

## Game Systems

### Upgrades and Evolutions

- Pool of **218 upgrades** with 4 rarities: Common, Rare, Epic, Legendary.
- Each level offers **1 of 5 options** (keys 1–5 or mouse).
- Synergy: prior upgrades influence which options appear.
- Evolutions unlock enhanced versions when max level is reached.
- `LUCK CLOVER` improves rarity of upcoming offers.
- Visual notifications with fade-out on upgrade application.

#### Upgrade Categories (218 total)

| Category | Count | Examples |
|---|---|---|
| Damage & Attack | 30 | +damage, +crit, execute, fire rate |
| Projectiles | 25 | +projectiles, pierce, ricochet, speed |
| Defense | 30 | +HP, regen, thorns, lifesteal |
| Speed | 20 | +hero speed, pickup range |
| Magic / Orbs | 25 | orbital orbs, magic explosions, combos |
| Explosion | 15 | explosion radius, area damage |
| Utility | 30 | magnetism, gold, XP bonus, healing |
| Special | 25 | rare abilities and unique combos |
| Classic upgrades | 18 | Demonic Fury, Ice Barrier, etc. |

New run mechanics: **Lifesteal**, **Gold Multiplier**, **XP Bonus**.

### Pacts

Optional modifiers chosen before the run:

| Pact | Effect | Bonus |
|---|---|---|
| No Pact | No modifier | — |
| Pact of Haste | Enemies 50% faster | +50% Gold |
| Fragile Pact | -2 max HP | +30% XP |

### Difficulties

| Difficulty | Enemy HP | Speed | Damage | Gold |
|---|---|---|---|---|
| Easy | 0.7× | 0.8× | 0.5× | 0.8× |
| Normal | 1.0× | 1.0× | 1.0× | 1.0× |
| Hard | 1.5× | 1.15× | 1.5× | 1.4× |
| Hardcore | 2.5× | 1.3× | 2.0× | 2.0× |

Hard and Hardcore are unlocked through specific missions.

### Biomes

| Biome | Decorations | Soundtrack | Exclusive enemies |
|---|---|---|---|
| Dungeon | Animated floor decor (pentagram, dinosaur) via `DungeonDecoManager` | Yes | — |
| Forest | Composite tilemap with animated tiles (campfire, banner) via `ForestDecoManager` | Yes | — |
| Volcano | Rocks, geysers and environment collisions via `VolcanoDecoManager` | Yes | Slime Fire, Slime Red, Slime Yellow, Ghost |
| Moon | Lunar surface decorations via `MoonDecoManager` | Yes | Ghost |

### Item Shop

| Tab | Categories | Items |
|---|---|---|
| Weapons | Swords, Axes, Spears, Bows, Staves | 60 |
| Armors | Helmets (12), Body Armor (12), Legs (12), Boots (10) | 46 |
| Utilities | (in development) | — |
| Sell | All inventory items | — |

Items are purchased with gold, stored in inventory, and can be dragged to equipment slots. Each category has stats balanced to match game progression:

- **Weapons**: increase character ATK.
- **Shields**: increase DEF and contribute to Damage Resistance.
- **Helmets, Body Armor, Legs, Boots**: each piece contributes DEF/600 toward Damage Resistance (total cap 55%).

### Armor System

Each equipped armor piece reduces incoming damage:

```
DAMAGE_RES = min(0.55, shield_def / 600 + sum(armor_def) / 600)
```

The Status panel (C key) displays equipped piece names and the resulting resistance percentage.

### Missions and Talents

- Missions with gold rewards.
- Permanent talent tree with an expanded panel to fit all talents per path.
- Character, difficulty, and cosmetic unlocks through achievements.

---

## UI and Medieval Interface

All UI uses ornate medieval sprites with transparent backgrounds (Photoroom). Text is always rendered dynamically on top — no text is baked into images.

| Element | Sprite |
|---|---|
| All menu buttons | `Barras de interface medieval ornamentada-Photoroom.png` (7 bars) |
| Skill selection cards (level-up) | `skills.png` (3 cards) |
| Title and settings section | `config.png` (large bar + small bar) |
| Character selection panels | `painelguerreiro.png`, `painelcacador.png`, `painelmago.png` |
| Difficulty selection screen | `selecionar_dificuldade.png` |
| Hero Room (hub) | `sala_do_heroi.png` — Shop, Talents, and Ready buttons aligned to image regions |
| Character Status (C) | `status.png` — name, attributes, and equipment aligned to image zones |
| Inventory and equipment (I) | `inventario.png` — item grid + slots for weapon, shield, helmet, armor, legs, boots |

The `AssetLoader` uses recursive caching (`_build_cache`): files can be in any subfolder of `assets/` and are located by name without changing any code call.

---

## Project Architecture

### Core modules

| File | Responsibility |
|---|---|
| `jogo_final.py` | Main loop, game states, UI |
| `balance.py` | Progression formulas: XP curve, enemy scaling, upgrade costs, drop rates |
| `characters.py` | Character classes, skills, and ultimates |
| `enemies.py` | Enemies, directional AI, spritesheets, enemy projectiles |
| `hud.py` | In-game HUD, visual theme, upgrade notifications |
| `upgrades.py` | Upgrade pool, synergy, evolutions |
| `drops.py` | Gems, items, and collection logic |
| `combat/projectiles.py` | Projectiles, slashes, and explosions with frame cache |
| `forest_biome.py` | Forest tilemap and animated decorations |
| `dungeon_biome.py` | Dungeon floor decorations |
| `volcano_biome.py` | Volcano rocks, geysers, and environment collisions |
| `moon_biome.py` | Lunar surface decorations |
| `spatial_index.py` | Spatial indices, grid A* pathfinding, performance metrics |
| `hot_kernels.py` | NumPy + Numba JIT kernels with automatic Cython backend detection |
| `hot_kernels_cy.pyx` | Optional accelerated Cython implementation |

### Technical decisions

- **Horde spawn queue**: producer/consumer (6 enemies/frame) — eliminates CPU spikes.
- **Explosion frame cache**: indexed by `(id(raw_frames), size)` — avoids repeated rescaling.
- **Recursive AssetLoader**: `os.walk` over `assets/` maps stem → full path; moving files never breaks code.
- **Dynamic resolution**: `pygame.display.list_modes()` detects monitor modes at runtime.
- **Gradual obstacle spawn**: decreasing timer from run start instead of bulk spawn during hordes.
- **Layered fallback**: Cython → Numba JIT → NumPy → pure Python, fully automatic.
- **Double buffering**: `pygame.DOUBLEBUF` enabled by default — reduces tearing and enables SDL2 hardware acceleration.

---

## Requirements

- Python 3.12+
- Windows, Linux, or macOS
- Runtime dependencies:
  - `pygame-ce` 2.5.7+ (Community Edition with SDL 2.32.10+)
  - `numpy` 2.4.4+
  - `numba` 0.65+ (JIT for critical kernels; optional but recommended)

> **Note:** The project uses **pygame-ce** (Community Edition), not the original pygame. Installing both simultaneously causes conflicts — uninstall `pygame` before installing `pygame-ce`.

---

## Installation and Run

### 1) Clone repository

```bash
git clone https://github.com/HelioASjunior/underworld-hero-survivor.git
cd underworld-hero-survivor
```

### 2) Create virtual environment

Windows:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Linux/macOS:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

### 3) Install dependencies

```bash
pip install -r requirements.txt
```

This installs:
- `pygame-ce` 2.5.7 (Community Edition)
- `numpy` 2.4.4 (fast array processing for spatial AI)
- `numba` (JIT compiler for the enemy separation kernel)

> If you already have `pygame` (original) installed, remove it first with `pip uninstall pygame`.

### 4) Verify installation

```bash
python -c "import pygame; print(f'Pygame-CE: {pygame.version.vernum}')"
python -c "import numpy; print(f'NumPy: {numpy.__version__}')"
python -c "import hot_kernels; print('NUMBA_ACTIVE =', hot_kernels.NUMBA_ACTIVE)"
```

### 5) Run

```bash
python jogo_final.py
```

On Windows, without activating the venv:

```powershell
.\.venv\Scripts\python.exe jogo_final.py
```

**First run:** The game creates `settings.json` and `save_v2.json` automatically. On first startup with Numba, the separation kernel is compiled and cached to disk (~2s, one-time only).

---

## Performance and Build

### Performance layers

| Layer | Mechanism | Benefit |
|---|---|---|
| Display | `pygame.DOUBLEBUF` enabled by default | Double buffering, reduces tearing |
| Rendering | Pygame-CE with SDL2 | More efficient than original pygame |
| Ground cache | Pre-rendered tilemap surface | ~54 blits/frame → 1 blit/frame for background |
| Frame time | 6-frame moving average on `dt` | Eliminates Windows Scheduler micro-stutters |
| Enemy separation | Numba `@njit(cache=True)` | JIT-compiled kernel for native code |
| Spatial queries | Vectorized NumPy (`EnemyBatchIndex`) | O(n) array searches without Python loops |
| Horde spawning | Async queue (6/frame) | Eliminates CPU spikes when spawning groups |
| Frame cache | Indexed by `(id(raw_frames), size)` | Effect sprites pre-scaled, no per-frame recomputation |

### Optional Cython build (advanced)

Compiling the Cython extension speeds up pathfinding and AI kernels. **Without it, the game runs normally through Numba + NumPy** — compilation is entirely optional.

#### Available kernels

| Kernel | Function | Typical gain |
|---|---|---|
| `radius_indices` | Enemies within radius (projectile collision, pickup range) | 4–6× vs pure Python |
| `nearest_index` | Nearest enemy respecting exclusion mask (targeting) | 4–6× vs pure Python |
| `batch_directions` | Normalized direction for N enemies at once (batch movement) | 6–10× vs pure Python |
| `astar_cy` | A* pathfinding with C-typed internals, no Python attribute overhead | 4–8× vs pure Python |
| `positions_in_rect` | Indices within rectangle for AOE attacks (slash, cone) | 4–6× vs pure Python |
| `enemy_separation` | Separation/repulsion between enemies (Numba `@njit`) | 3–6× vs pure Python |

`hot_kernels.py` automatically detects which backend is available and falls back per-function: Cython → Numba JIT → NumPy → pure Python.

#### Benchmarks (Intel i5, Python 3.12, GCC 15.2 -O3)

| Test | Time |
|---|---|
| `radius_indices` × 1000 calls | ~12.6 ms |
| `batch_directions` × 1000 calls | ~14.5 ms |
| `astar_cy` × 500 calls | ~59.5 ms |

#### Install build dependencies

```bash
pip install -r requirements-dev.txt
```

#### Option A: WinLibs GCC (recommended, ~255 MB)

```powershell
winget install BrechtSanders.WinLibs.POSIX.UCRT
```

Open a new terminal after installing (to refresh PATH), then compile:

```bash
python build_cython.py build_ext --inplace
```

#### Option B: Visual C++ Build Tools

Install **Visual C++ Build Tools 2019+** from the official Microsoft website, then:

```bash
python build_cython.py build_ext --inplace
```

#### Verify active backends

```bash
python -c "import hot_kernels; print('CYTHON_ACTIVE =', hot_kernels.CYTHON_ACTIVE, '| NUMBA_ACTIVE =', hot_kernels.NUMBA_ACTIVE)"
```

---

## Distribution

The project includes two packaging scripts to distribute the game without Python installed.

### PyInstaller — bundles the interpreter (most compatible)

```bash
pip install -r requirements-dev.txt

python build_dist.py              # folder dist/UnderWorldHero/
python build_dist.py --onefile    # single exe dist/UnderWorldHero.exe
python build_dist.py --clean      # clean before packaging
```

**Output:** `dist/UnderWorldHero/UnderWorldHero.exe` or `dist/UnderWorldHero.exe`

### Nuitka — compiles to native binary (faster)

Nuitka converts Python → C → native executable. Faster startup, ~10–30% speed gain over PyInstaller.

**Prerequisite:** C compiler in PATH (WinLibs GCC or Visual C++ Build Tools).

```bash
pip install -r requirements-dev.txt

python build_nuitka.py              # folder dist-nuitka/jogo_final.dist/
python build_nuitka.py --onefile    # single executable
python build_nuitka.py --clean      # clean before compiling
```

**Output:** `dist-nuitka/jogo_final.dist/jogo_final.exe` or `dist-nuitka/jogo_final.exe`

---

## Controls

Rebindable in **Settings → Controls**:

| Action | Default |
|---|---|
| Movement | W A S D |
| Dash | Space |
| Ultimate | E |
| Pause / Resume | P |
| Quick menu | Esc |
| Debug overlay | F3 |
| Select upgrade | 1 / 2 / 3 / 4 / 5 or click |
| Inventory / Equipment | I |
| Character status | C |

---

## Settings, Save, and Persistence

| File | Contents |
|---|---|
| `settings.json` | Video, audio, controls, gameplay, accessibility |
| `save_v2.json` | Global progress: gold, talents, unlocks, statistics |
| `run_slot_1~3.json` | Complete state for each run slot |

Settings sections:

- **Video**: resolution (dynamic), fullscreen, VSync, FPS cap, show FPS.
- **Audio**: music volume, effects volume, mute.
- **Controls**: key remapping.
- **Gameplay**: auto-apply chest reward, off-screen enemy indicators.
- **Accessibility**: extra display options.

---

## Resolution and Compatibility

The resolution list is detected automatically via `pygame.display.list_modes()` when opening settings. No values are hardcoded.

Example detected resolutions (vary by monitor):

```
1280x720  1366x768  1600x900  1920x1080  2560x1440  3840x2160
```

Fallback behavior:

- If saved resolution doesn't fit the current monitor → uses native resolution.
- If monitor doesn't report mode list → uses default list up to 4K.
- If `pygame.display.set_mode` fails with chosen flags → opens in a simple window with double buffering.

---

## Performance Debug and Benchmark

### In-game overlay (F3)

- FPS and average frame time.
- Enemy, projectile, and particle count on screen.
- Spatial queries per frame and A* cache hit rate.
- Active backend: Cython ON / Numba ON / NumPy fallback.

### Offline benchmark

```bash
python benchmark_spatial.py
```

---

## Folder Structure

```text
underworld-hero-survivor/
├── jogo_final.py            # Main loop and game states
├── balance.py               # Balancing and progression formulas
├── characters.py            # Playable characters
├── enemies.py               # Enemies, AI, and animations
├── hud.py                   # HUD and in-game UI
├── upgrades.py              # Upgrades, synergy, and evolutions
├── drops.py                 # Gems and drops
├── forest_biome.py          # Forest biome (tilemap + animated decorations)
├── dungeon_biome.py         # Dungeon biome (floor decorations)
├── volcano_biome.py         # Volcano biome (rocks, geysers, collisions)
├── moon_biome.py            # Moon biome (lunar decorations)
├── spatial_index.py         # Spatial indexing and pathfinding
├── hot_kernels.py           # NumPy / Numba / Cython kernels
├── hot_kernels_cy.pyx       # Optional Cython extension
├── benchmark_spatial.py     # Performance benchmark
├── build_cython.py          # Cython build script
├── build_dist.py            # PyInstaller packaging script
├── build_nuitka.py          # Nuitka native binary compilation script
├── combat/
│   └── projectiles.py       # Projectiles and explosions
├── assets/
│   ├── audio/               # Music and sound effects (.mp3)
│   ├── backgrounds/         # Biome backgrounds
│   ├── characters/          # Character sprites
│   ├── effects/             # Auras, explosions, slashes, orbs
│   ├── enemies/             # Enemy and boss sprites
│   ├── fonts/               # Medieval fonts
│   ├── icons/               # Upgrade and talent icons
│   ├── items/               # Gems and collectible items
│   ├── sprite/
│   │   └── monster/         # Directional monster spritesheets
│   └── ui/
│       ├── buttons/         # Ornate bars, skills.png, config.png
│       ├── chao/            # Floor decorations (dungeon)
│       ├── menu_icons/      # Main menu icons
│       ├── panels/          # Character selection panels
│       ├── tiles/           # Biome tiles (static and animated)
│       └── newItens/        # Armor icons (capacete/, armor/, calças/, botas/)
├── settings.json            # Saved settings
├── save_v2.json             # Global progress
├── requirements.txt         # Runtime dependencies (pygame-ce, numpy, numba)
└── requirements-dev.txt     # Build dependencies (Cython, PyInstaller, Nuitka)
```

---

## Troubleshooting

### "ModuleNotFoundError: No module named 'pygame'" or "pygame-ce"

**Cause:** Virtual environment not activated or pygame-ce not installed.

**Fix:**

```bash
# Activate venv
.\.venv\Scripts\Activate.ps1   # Windows
source .venv/bin/activate       # Linux/macOS

# Reinstall pygame-ce
pip uninstall pygame pygame-ce -y
pip install pygame-ce==2.5.7
```

### "pygame.error: video system not initialized"

**Cause:** Pygame couldn't access the video driver (headless Linux, WSL without display).

**Fix:**

```bash
# Linux: install SDL2
sudo apt-get install libsdl2-2.0-0 libsdl2-dev

# Verify
python -c "import pygame; pygame.init(); print('OK')"
```

### Low FPS or stuttering despite good hardware

1. **Lower resolution** in Settings > Video (try 1280×720).
2. **Disable VSync** if the game stutters inconsistently.
3. **Compile Cython** for faster AI kernels:
   ```bash
   python build_cython.py build_ext --inplace
   ```
4. **Verify Numba is active** (`NUMBA_ACTIVE = True`):
   ```bash
   python -c "import hot_kernels; print(hot_kernels.NUMBA_ACTIVE)"
   ```
5. **Close background apps** (Discord, Chrome, etc.).

### Cython compilation error on Windows

**Quick fix (recommended) — WinLibs GCC ~255 MB:**

```powershell
winget install BrechtSanders.WinLibs.POSIX.UCRT
# Open a new terminal after install so PATH updates
python build_cython.py build_ext --inplace
```

**Alternative — Visual C++ Build Tools ~5 GB:**

Install **Visual C++ Build Tools 2019+** from the official Microsoft website and retry.

**Verify GCC is in PATH:**

```bash
gcc --version
```

---

## Roadmap

- [ ] New biomes with exclusive mechanics.
- [x] Boss Agis — summoning seal, long-range attack, and area magic.
- [ ] New bosses with phases and additional attacks.
- [ ] Achievement system with visual rewards.
- [x] Continuous balance system for progression and economy (`balance.py`).
- [x] Distributable Windows build via PyInstaller (`build_dist.py`) and Nuitka (`build_nuitka.py`).
- [x] Ground cache — pre-rendered tilemap (~54 blits/frame → 1 blit/frame).
- [x] Frame time smoothing — 6-frame moving average eliminates micro-stutters.
- [x] Gamepad support.
- [x] Migrate to Pygame-CE (completed successfully).
- [x] ARMORS shop tab with 46 items across 4 categories (helmets, body armor, legs, boots).
- [x] Armor damage resistance system for all 4 equipment slots.
- [x] Drag-and-drop equip for all 6 equipment slots (weapon, shield, helmet, armor, legs, boots).
- [x] Hero Room, Status panel, and Inventory aligned to image UI zones.
- [x] Expanded talent tree panels to prevent skill overflow.
- [x] 218 upgrades across 8 categories with synergy system.
- [x] 5-option upgrade selection per level-up (keys 1–5).
- [x] New run mechanics: lifesteal, gold multiplier, XP bonus.
- [x] Numba JIT on enemy separation kernel (`hot_kernels.py`).
- [x] Double buffering (`pygame.DOUBLEBUF`) to reduce tearing.
- [x] Volcano biome with decorations, geysers, and exclusive enemies.
- [x] Moon biome with lunar themed decorations.
- [ ] SDL3 when Pygame-CE releases it (GPU acceleration and better performance).
- [ ] Local multiplayer (co-op for 2 players).

---

## Contributing

1. Open an issue describing a bug, improvement, or proposal.
2. Create a branch from `beta`.
3. Open a Pull Request with a description of what changed and how to test it.

Code of conduct: [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)

---

## License

Proprietary Source-Available License.
The source code is provided for viewing and educational purposes only.
Compiling, redistributing, or selling the source code or binaries is prohibited.
All commercial exploitation rights are reserved by the author.
See [LICENSE](LICENSE).

---

## Gameplay

<p align="center">
  <img src="screenshots/gameplay_readme.gif" alt="UnderWorld Hero gameplay" width="900">
</p>
