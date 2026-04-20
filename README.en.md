# UnderWorld Hero

![Python](https://img.shields.io/badge/Python-3.12-blue?style=for-the-badge&logo=python)
![Pygame-CE](https://img.shields.io/badge/Pygame--CE-2.5.7-green?style=for-the-badge)
![NumPy](https://img.shields.io/badge/NumPy-2.4.4-013243?style=for-the-badge&logo=numpy)
![Status](https://img.shields.io/badge/Status-In_Development-yellow?style=for-the-badge)

A bullet hell survival game built with Python and Pygame, focused on fast-paced combat, upgrade-driven progression, multiple playable heroes, and a performance pipeline powered by spatial indexing (NumPy + optional Cython).

Versao em portugues: [README.md](README.md)

## Table of Contents

- [Overview](#overview)
- [Highlights](#highlights)
- [Project Architecture](#project-architecture)
- [Requirements](#requirements)
- [Installation and Run](#installation-and-run)
- [Optional Cython Build](#optional-cython-build)
- [Controls](#controls)
- [Settings, Save, and Persistence](#settings-save-and-persistence)
- [Performance Debug and Benchmark](#performance-debug-and-benchmark)
- [Folder Structure](#folder-structure)
- [Roadmap](#roadmap)
- [Contributing](#contributing)
- [License](#license)

## Overview

UnderWorld Hero combines:

- Real-time combat with high enemy density on screen.
- Level progression, upgrade picks, and evolutions.
- 6 playable characters with distinct playstyles and ultimates.
- Scalable difficulties and unlock systems.
- Daily missions, meta progression, and run slots.

The project is actively evolving and aims to balance gameplay quality with clean, maintainable code.

## Highlights

- Modular character system in `characters.py`.
- Enemy AI and type-specific behavior in `enemies.py`.
- Decoupled combat logic in `combat/projectiles.py`.
- Grid spatial indexing + vectorized queries in `spatial_index.py`.
- Hot kernels with automatic fallback (`hot_kernels.py` -> `hot_kernels_cy.pyx`).
- Persistent video/audio/controls/accessibility settings in `settings.json`.
- Global save + run slots in `save_v2.json` and `run_slot_*.json`.
- Real-time performance debug overlay (F3).
- Item shop with 4 tabs: Weapons, Armors, Utilities, Sell — including 46 armor pieces across 4 slots.
- Full drag-and-drop equip system for weapons, shields, helmets, body armor, legs, and boots.
- Armor damage resistance system: each equipped piece reduces incoming damage (DEF / 600, capped at 55%).
- All UI panels (Hero Room, Status, Inventory) aligned precisely to their image zones.
- Expanded talent tree panels to fit all talents without overflow.
- **218 upgrades** across 9 categories; each level-up shows **5 options** to choose from (keys 1–5).
- New run mechanics: lifesteal, gold multiplier, XP bonus.

## Item Shop

The shop has four main tabs:

| Tab | Categories | Items |
|---|---|---|
| Weapons | Swords, Axes, Spears, Bows, Staves | 60 |
| Armors | Helmets (12), Body Armor (12), Legs (12), Boots (10) | 46 |
| Utilities | (in development) | — |
| Sell | All inventory items | — |

### Armor System

Each equipped armor piece reduces incoming damage:

```
DAMAGE_RES = min(0.55, shield_def / 600 + sum(armor_def) / 600)
```

The Status panel (C key) displays equipped piece names and the resulting resistance percentage.

## Upgrades and Evolutions

Pool of **218 upgrades** with 4 rarities: Common, Rare, Epic, Legendary. Each level-up offers **1 of 5 options** (keys 1–5 or mouse). Synergy system influences which options appear based on your current build.

### Upgrade Categories

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

## Playable Characters

| Character | HP | Speed | Damage | Mana | Ultimate |
|---|---|---|---|---|---|
| Warrior | 100 | 280 | 25 | 50 | Warrior's Fury |
| Hunter | 63 | 340 | 38 | 75 | Arrow Rain |
| Mage | 75 | 260 | 25 | 200 | Temporal Freeze |
| Vampire | 88 | 300 | 38 | 100 | Shadow Storm |
| Demon | 75 | 290 | 38 | 100 | Infernal Flame |
| Golem | 113 | 240 | 50 | 50 | Earth Strike |

All characters are unlocked by default.

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
| Slime Fire | 280 | 125 | 2 min | Fire burst charges (2.8× speed), high contact damage |
| Elite | 1500 | 85 | 30s+ | Reinforced variant with guaranteed gold drop |

> HP and speed scale with the difficulty multiplier and game time (+20% HP/damage per minute up to 6×).

### Enemies — Hard / Hardcore only

| Type | Base HP | Base Speed | Spawn | Description |
|---|---|---|---|---|
| Slime | 130 | 110 | 30s | Balanced enemy with dark aura |
| Minotaur | 200 | 130 | 30s | Melee, direct pursuit |
| Rat | 150 | 135 | 2 min | Large (220px), aggressive zigzag |

### Bosses

| Type | Base HP | Spawn | Description |
|---|---|---|---|
| Mini Boss | 6000 | ~10 min | Own health bar, scales with time (+30% × time_scale) |
| Boss | scalable | 5 min (every 5 min) | Multi-phase, grows stronger each wave |
| Agis | 10000 | 15 min (summoning seal) | Slow boss, double-orb attack + 8-orb area magic every 5s (+25% × time_scale) |

**Agis** is summoned through an animated seal (`doom_agis.png`) that appears near the player before spawning. Has a basic ranged projectile (purple double orb) and an area spell that fires 8 orbs in all directions. Drops a chest + 15 coins on death.

## Project Architecture

### Core modules

- `jogo_final.py`: entry point and main game loop.
- `balance.py`: progression formulas — XP curve, enemy scaling, upgrade costs, drop rates.
- `characters.py`: character classes, skills, and ultimates.
- `enemies.py`: enemies, AI, animations, and enemy projectiles.
- `hud.py`: HUD, visual theme, and UI components.
- `spatial_index.py`: spatial indices, grid A*, and performance metrics.
- `hot_kernels.py`: NumPy kernels + Cython backend detection.
- `hot_kernels_cy.pyx`: optional accelerated implementation.
- `benchmark_spatial.py`: synthetic before/after benchmark.

### Design principles

- Modularization to reduce main-loop coupling.
- Safe fallback when native acceleration is unavailable.
- JSON persistence for easier debugging and quick iteration.

## Requirements

- Python 3.12
- OS: Windows, Linux, or macOS
- Runtime dependencies:
  - Pygame-CE 2.5.7 (Community Edition)
  - NumPy 2.4.4

Optional Cython build dependencies are listed in `requirements-dev.txt`.

## Installation and Run

### 1) Clone repository

```bash
git clone https://github.com/HelioASjunior/underworld-hero-survivor.git
cd underworld-hero-survivor
```

### 2) Create virtual environment

Windows (recommended):

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

### 4) Run game

```bash
python jogo_final.py
```

On Windows, without activating the venv:

```powershell
.\.venv\Scripts\python.exe jogo_final.py
```

## Optional Cython Build

The Cython build speeds up spatial kernels and is optional. Without it, the game still runs through NumPy.

### Build dependencies

```bash
pip install -r requirements-dev.txt
```

### Compile extension

```bash
python build_cython.py build_ext --inplace
```

### Verify active backend

```bash
python -c "import hot_kernels; print('CYTHON_ACTIVE =', hot_kernels.CYTHON_ACTIVE)"
```

Expected: `CYTHON_ACTIVE = True`

On Windows, Visual C++ Build Tools are required to compile native extensions.

## Controls

Default controls (rebindable in settings):

| Action | Default key |
| --- | --- |
| Movement | W A S D |
| Dash | Space |
| Ultimate | E |
| Pause | P |
| Quick pause menu | Esc |
| Debug overlay | F3 |
| Upgrade selection | 1 / 2 / 3 / 4 / 5 / Enter |
| Inventory / Equipment | I |
| Character status | C |

## Settings, Save, and Persistence

Main persistence files:

- `settings.json`: video, audio, controls, gameplay, accessibility.
- `save_v2.json`: global progress (gold, permanent upgrades, stats, unlocks).
- `run_slot_1.json`, `run_slot_2.json`, `run_slot_3.json`: per-slot run state.

The game resolves paths based on the script directory (`os.path.abspath(__file__)`), reducing relative-path issues when launched outside the project root.

## Performance Debug and Benchmark

### In-game overlay (F3)

Shows in real time:

- FPS and average frame time.
- Spatial queries per frame.
- A* calls per frame and cache hit rate.
- Active kernel backend (Cython ON or NumPy fallback).

### Offline benchmark

```bash
python benchmark_spatial.py
```

On Windows, without activating the venv:

```powershell
.\.venv\Scripts\python.exe benchmark_spatial.py
```

## Folder Structure

```text
underworld-hero-survivor/
|- jogo_final.py
|- balance.py
|- characters.py
|- enemies.py
|- spatial_index.py
|- hot_kernels.py
|- hot_kernels_cy.pyx
|- benchmark_spatial.py
|- build_cython.py
|- combat/
|  |- projectiles.py
|- assets/
|  |- fonts/
|  |- sprite/
|  |- ui/
|     |- itens/          # Weapon and shield icons
|     |- newItens/       # Armor icons
|        |- capacete/    # h.png to h11.png
|        |- armor/       # a.png to a11.png
|        |- calças/      # c.png to c11.png
|        |- botas/       # b1.png to b10.png
|- settings.json
|- save_v2.json
|- requirements.txt
|- requirements-dev.txt
```

## Roadmap

- [ ] Expand biomes and enemy variation.
- [x] Boss Agis — summoning seal, long-range attack, and area magic.
- [ ] Add new bosses and combat phases.
- [x] Balance system for progression and economy (`balance.py`).
- [x] ARMORS shop tab with 46 items across 4 categories (helmets, body armor, legs, boots).
- [x] Armor damage resistance system for all 4 equip slots.
- [x] Drag-and-drop equip for all 6 equipment slots (weapon, shield, helmet, armor, legs, boots).
- [x] Hero Room, Status panel, and Inventory aligned to image UI zones.
- [x] Expanded talent tree panels to prevent skill overflow.
- [x] 218 upgrades across 9 categories with synergy system.
- [x] 5-option upgrade selection per level-up (keys 1–5).
- [x] New run mechanics: lifesteal, gold multiplier, XP bonus.
- [ ] Publish a distributable Windows build.

## Contributing

Contributions are welcome.

1. Open an issue describing a bug, improvement, or proposal.
2. Create a branch for your changes.
3. Open a Pull Request with technical context and manual test notes.

Code of conduct: [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)

## License

Proprietary Source-Available License.
The source code is provided for viewing and educational purposes only.
Compiling, redistributing, or selling the source code or binaries is prohibited.
All commercial exploitation rights are reserved by the author.
See [LICENSE](LICENSE).

## Gameplay (GIF)

<p align="center">
  <img src="screenshots/gameplay_readme.gif" alt="UnderWorld Hero gameplay" width="900">
</p>
