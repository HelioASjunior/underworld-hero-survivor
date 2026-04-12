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

## Playable Characters

| Character | HP | Speed | Playstyle | Ultimate |
|---|---|---|---|---|
| Warrior | 8 | 280 | Melee + mid-range projectiles | Fury: increased fire rate and damage |
| Hunter | 5 | 340 | Fast projectiles, high crit | Burst: cone spread shot |
| Mage | 6 | 260 | Magic orbs + area aura | Temporal Freeze: freezes all nearby enemies |
| Vampire | 7 | 300 | Projectiles + life steal | Vampirism |
| Demon | 6 | 290 | Multi-projectile burst | Abyss Flames |
| Golem | 9 | 240 | Pure melee, highest HP | Earth Strike: 16 melee slashes in two rings |

All characters are unlocked by default.

## Enemies and Bosses

### Enemies — All difficulties

| Type | HP | Speed | Spawn | Description |
|---|---|---|---|---|
| Bat | 1 | 145 | 0s | Fast, sinusoidal movement |
| Runner | 2 | 150 | 0s | Fast straight-line chaser |
| Tank | 10 | 65 | 30s | High HP, slow, melee |
| Shooter | 3 | 90 | 30s | Ranged projectile attacker |
| Goblin | 3 | 160 | 1 min | Fast with moderate zigzag |
| Beholder | 8 | 85 | 1.5 min | Floating, smooth movement |
| Orc | 12 | 75 | 3 min | Large (168px), tanky melee |
| Elite | +50% | base | 30s+ | Reinforced variant with guaranteed gold drop |

### Enemies — Hard / Hardcore only

| Type | HP | Speed | Spawn | Description |
|---|---|---|---|---|
| Slime | 5 | 110 | 30s | Balanced standard enemy |
| Minotaur | 8 | 130 | 30s | Melee, direct pursuit |
| Rat | 6 | 135 | 2 min | Large (220px), aggressive zigzag |

### Bosses

| Type | HP | Spawn | Description |
|---|---|---|---|
| Mini Boss | 300+ | ~10s | Own health bar, scales with time |
| Boss | scalable | 5 min (every 5 min) | Multi-phase, grows stronger each wave |
| Agis | 800+ | 2 min (summoning seal) | Slow boss, long-range double-orb attack + area magic every 5s |

**Agis** is summoned through an animated seal (`doom_agis.png`) that appears near the player before spawning. Has a basic ranged projectile (purple double orb) and an area spell that fires 8 orbs in all directions. Drops a chest + 15 coins on death.

## Project Architecture

### Core modules

- `jogo_final.py`: entry point and main game loop.
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
| Upgrade selection | 1 / 2 / 3 / Enter |

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
|- settings.json
|- save_v2.json
|- requirements.txt
|- requirements-dev.txt
```

## Roadmap

- Expand biomes and enemy variation.
- [x] Boss Agis — summoning seal, long-range attack, and area magic.
- Add new bosses and combat phases.
- Refine progression and upgrade economy balancing.
- Publish a distributable Windows build.

## Contributing

Contributions are welcome.

1. Open an issue describing a bug, improvement, or proposal.
2. Create a branch for your changes.
3. Open a Pull Request with technical context and manual test notes.

Code of conduct: [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)

## License

Distributed under the MIT License. See [LICENSE](LICENSE).

## Gameplay (GIF)

<p align="center">
  <img src="screenshots/gameplay_readme.gif" alt="UnderWorld Hero gameplay" width="900">
</p>
