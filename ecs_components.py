"""Pure-data ECS components for UnderWorld Hero.

Components hold ONLY state — no methods, no logic, no pygame calls.
All behaviour that reads or writes these components lives in ecs_systems.py.

Design notes:
- Vector2 fields that must be shared with the Enemy sprite (pos, knockback,
  agis_shot_dir) are stored as mutable pygame.Vector2 objects so both the
  sprite attribute and the component reference the SAME object — no copy/sync.
- Scalar fields (hp, speed, timers, flags) are plain Python values.
  The Enemy sprite exposes them via thin properties for backward compatibility
  with code that accesses enemy.hp, enemy.frozen_timer, etc.
"""

from __future__ import annotations
import math
import random
from dataclasses import dataclass, field

import pygame


# ── Shared-reference Vector2 factories ───────────────────────────────────────

def _vec2_zero() -> pygame.Vector2:
    return pygame.Vector2(0.0, 0.0)


def _vec2_right() -> pygame.Vector2:
    return pygame.Vector2(1.0, 0.0)


# ── Component definitions ─────────────────────────────────────────────────────


@dataclass
class Position:
    """World position. vec is the SAME object stored as Enemy.pos."""
    vec: pygame.Vector2 = field(default_factory=_vec2_zero)


@dataclass
class Health:
    hp: float = 100.0
    max_hp: float = 100.0


@dataclass
class Velocity:
    """Movement speed scalar. Direction is computed per-frame by AISystem."""
    speed: float = 100.0


@dataclass
class EnemyTag:
    """Read-only identity metadata — set once at spawn, never mutated."""
    kind: str = ""
    is_elite: bool = False
    gold_drops: int = 0


@dataclass
class AIState:
    """All per-entity AI bookkeeping extracted from the former Enemy._* attrs.

    knockback is a shared pygame.Vector2 (same object as Enemy.knockback).
    """
    # Shared mutable Vector2 — modified in-place by AISystem and jogo_final.py
    knockback: pygame.Vector2 = field(default_factory=_vec2_zero)

    # Status effects
    frozen_timer: float = 0.0
    flash_timer: float = 0.0

    # Zigzag / sinusoidal phase: bat, goblin, beholder, rat, ghost
    bat_phase: float = field(default_factory=lambda: random.uniform(0.0, math.pi * 2))

    # Flanking pattern: orc
    flank_timer: float = field(default_factory=lambda: random.uniform(1.5, 3.5))
    flank_angle: float = 0.0
    flank_active: bool = False
    flank_active_t: float = 0.0

    # Charge / dash pattern: mini_boss, slime_fire, slime_yellow, ghost, agis
    charge_timer: float = field(default_factory=lambda: random.uniform(3.5, 5.0))
    charge_active_t: float = 0.0
    charging: bool = False

    # Pathfinding cache
    path_recalc_timer: float = 0.0
    cached_path_start_cell: object = None
    cached_path_goal_cell: object = None
    cached_path_dir: object = None


@dataclass
class Combat:
    """Per-entity combat timers and pending-action flags.

    agis_shot_dir is a shared pygame.Vector2 (same object as Enemy.agis_shot_dir).
    """
    # Melee
    melee_dmg: float = 0.0
    melee_range: float = 0.0
    melee_timer: float = 0.0
    pending_melee_hit: bool = False

    # Ranged projectile
    proj_dmg: float = 0.0
    shot_timer: float = 0.0
    shot_cooldown: float = 3.0

    # Agis special attacks
    agis_shot_timer: float = 0.0
    agis_shot_dir: pygame.Vector2 = field(default_factory=_vec2_right)
    pending_agis_shot: bool = False
    agis_area_timer: float = 3.0
    pending_agis_area: bool = False

    # Slime puddle
    puddle_timer: float = 0.0


@dataclass
class AnimationState:
    """Per-entity animation frame tracking and facing direction."""
    frame_idx: int = 0
    anim_timer: float = 0.0
    facing_right: bool = True
    facing_dir: str = "down"

    # Attack animation state
    atk_active: bool = False
    atk_frame_idx: int = 0
    atk_timer: float = 0.0
    atk_frame_speed: float = 0.10


@dataclass
class Renderable:
    """Links an ECS entity to its pygame.sprite.Sprite.

    Systems call helper methods on the sprite (e.g. _get_walk_frame()) and
    write the result to sprite.image / sprite.rect.
    """
    sprite: object = None   # Enemy instance
