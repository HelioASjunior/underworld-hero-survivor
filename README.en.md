# UnderWorld Hero

![Python](https://img.shields.io/badge/Python-3.12-blue?style=for-the-badge&logo=python)
![Pygame](https://img.shields.io/badge/Pygame-2.6.1-green?style=for-the-badge)
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
- Multiple playable characters with distinct playstyles.
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
  - Pygame 2.6.1
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
