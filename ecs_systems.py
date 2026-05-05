"""ECS systems for UnderWorld Hero.

Each system processes all matching entities in a single batch pass, replacing
the per-entity Enemy.update() callback that previously drove game logic.

Processing order per frame (registered in jogo_final.py):
    1. EnemyAISystem        — knockback, frozen check, AI movement, pathfinding
    2. EnemyCombatSystem    — shooting / melee / Agis / puddle timers
    3. EnemyAnimationSystem — frame advancement and image selection
    4. EnemyRenderSystem    — rect.center sync

All context required by systems (player pos, cam, groups, etc.) is injected
into world.context before world.process(dt) is called each frame.
"""

from __future__ import annotations
import math
import random

import pygame

from ecs_components import (
    Position, Health, Velocity, EnemyTag,
    AIState, Combat, AnimationState, Renderable,
)

_VEC2_ZERO = pygame.Vector2(0, 0)


# ── 1. AI + Movement ──────────────────────────────────────────────────────────

class EnemyAISystem:
    """Handles knockback, frozen-state skip, per-kind AI movement, pathfinding,
    and obstacle collision.  Implements the same LOD (Level-of-Detail) throttle
    that was previously in jogo_final.py's enemy update loop.

    Reads from context: p_pos, cam, obstacles, selected_pact,
                        obstacle_grid_index, lod_dist_sq, sep_frame.
    """

    def process(self, world, dt: float) -> None:
        ctx = world.context
        p_pos: pygame.Vector2    = ctx["p_pos"]
        obstacles                = ctx["obstacles"]
        selected_pact: str       = ctx.get("selected_pact", "")
        obstacle_grid_index      = ctx.get("obstacle_grid_index")
        lod_dist_sq: float       = ctx.get("lod_dist_sq", 1_440_000)
        sep_frame: int           = ctx.get("sep_frame", 0)

        for _eid, (pos_c, health_c, vel_c, ai_c, tag_c, anim_c, rend_c) in world.get_components(
            Position, Health, Velocity, AIState, EnemyTag, AnimationState, Renderable
        ):
            enemy = rend_c.sprite
            kind  = tag_c.kind

            # ── LOD throttle ────────────────────────────────────────────────
            if (kind not in ("boss", "mini_boss", "agis")
                    and sep_frame != 0
                    and (enemy.pos - p_pos).length_squared() >= lod_dist_sq):
                continue

            # ── Knockback decay ──────────────────────────────────────────────
            enemy.pos   += ai_c.knockback
            ai_c.knockback *= 0.85

            # ── Timers ───────────────────────────────────────────────────────
            if ai_c.path_recalc_timer > 0:
                ai_c.path_recalc_timer -= dt
            if ai_c.flash_timer > 0:
                ai_c.flash_timer -= dt

            # ── Frozen: early exit (image + rect handled by other systems) ──
            if ai_c.frozen_timer > 0:
                ai_c.frozen_timer -= dt
                continue

            # ── Direction to player ──────────────────────────────────────────
            direction = p_pos - enemy.pos
            dist      = direction.length()

            enemy._update_facing(direction, dist)

            can_move = ai_c.knockback.length() < 3.0

            if dist > 0 and can_move:
                is_ranged = kind in ("shooter",)
                stop_dist = 450

                if is_ranged and dist < stop_dist:
                    move = _VEC2_ZERO
                else:
                    move_speed = vel_c.speed
                    if selected_pact == "VELOCIDADE":
                        move_speed *= 1.5

                    # Boss rage at low HP
                    if kind == "boss":
                        if   health_c.hp < health_c.max_hp * 0.25: move_speed *= 2.0
                        elif health_c.hp < health_c.max_hp * 0.50: move_speed *= 1.5

                    move_dir = direction / dist

                    # ── Per-kind AI movement patterns ────────────────────────

                    if kind == "bat":
                        ai_c.bat_phase += dt * 3.5
                        perp = pygame.Vector2(-move_dir.y, move_dir.x)
                        amplitude = 0.75 if dist > 200 else 0.35
                        move_dir  = move_dir + perp * math.sin(ai_c.bat_phase) * amplitude
                        if move_dir.length_squared() > 0:
                            move_dir = move_dir.normalize()

                    elif kind == "goblin":
                        ai_c.bat_phase += dt * 4.5
                        perp = pygame.Vector2(-move_dir.y, move_dir.x)
                        amplitude = 0.55 if dist > 150 else 0.22
                        move_dir  = move_dir + perp * math.sin(ai_c.bat_phase) * amplitude
                        if move_dir.length_squared() > 0:
                            move_dir = move_dir.normalize()

                    elif kind == "beholder":
                        ai_c.bat_phase += dt * 1.8
                        perp = pygame.Vector2(-move_dir.y, move_dir.x)
                        amplitude = 0.40 if dist > 180 else 0.15
                        move_dir  = move_dir + perp * math.sin(ai_c.bat_phase) * amplitude
                        if move_dir.length_squared() > 0:
                            move_dir = move_dir.normalize()

                    elif kind == "rat":
                        ai_c.bat_phase += dt * 3.0
                        perp = pygame.Vector2(-move_dir.y, move_dir.x)
                        amplitude = 0.30 if dist > 200 else 0.12
                        move_dir  = move_dir + perp * math.sin(ai_c.bat_phase) * amplitude
                        if move_dir.length_squared() > 0:
                            move_dir = move_dir.normalize()

                    elif kind == "orc":
                        ai_c.flank_timer -= dt
                        if ai_c.flank_timer <= 0:
                            ai_c.flank_timer    = random.uniform(2.0, 4.5)
                            ai_c.flank_angle    = random.choice([-55, -40, 40, 55])
                            ai_c.flank_active   = True
                            ai_c.flank_active_t = random.uniform(0.5, 0.9)
                        if ai_c.flank_active:
                            ai_c.flank_active_t -= dt
                            if ai_c.flank_active_t <= 0:
                                ai_c.flank_active = False
                            else:
                                rad = math.radians(ai_c.flank_angle)
                                cx, cy = math.cos(rad), math.sin(rad)
                                move_dir = pygame.Vector2(
                                    move_dir.x * cx - move_dir.y * cy,
                                    move_dir.x * cy + move_dir.y * cx,
                                )

                    elif kind == "mini_boss":
                        ai_c.charge_timer -= dt
                        if ai_c.charge_timer <= 0 and not ai_c.charging:
                            ai_c.charge_timer    = random.uniform(3.5, 5.5)
                            ai_c.charging        = True
                            ai_c.charge_active_t = 0.8
                        if ai_c.charging:
                            ai_c.charge_active_t -= dt
                            if ai_c.charge_active_t <= 0:
                                ai_c.charging = False
                            else:
                                move_speed *= 3.5
                                if not anim_c.atk_active:
                                    anim_c.atk_active    = True
                                    anim_c.atk_frame_idx = 0
                                    anim_c.atk_timer     = 0.0

                    elif kind == "slime_fire":
                        ai_c.charge_timer -= dt
                        if ai_c.charge_timer <= 0 and not ai_c.charging:
                            ai_c.charge_timer    = random.uniform(2.5, 4.5)
                            ai_c.charging        = True
                            ai_c.charge_active_t = random.uniform(0.35, 0.55)
                        if ai_c.charging:
                            ai_c.charge_active_t -= dt
                            if ai_c.charge_active_t <= 0:
                                ai_c.charging = False
                            else:
                                move_speed *= 2.8
                                if not anim_c.atk_active:
                                    anim_c.atk_active    = True
                                    anim_c.atk_frame_idx = 0
                                    anim_c.atk_timer     = 0.0

                    elif kind == "slime_yellow":
                        ai_c.charge_timer -= dt
                        if ai_c.charge_timer <= 0 and not ai_c.charging:
                            ai_c.charge_timer    = random.uniform(1.8, 3.2)
                            ai_c.charging        = True
                            ai_c.charge_active_t = random.uniform(0.25, 0.40)
                        if ai_c.charging:
                            ai_c.charge_active_t -= dt
                            if ai_c.charge_active_t <= 0:
                                ai_c.charging = False
                            else:
                                move_speed *= 3.0
                                if not anim_c.atk_active:
                                    anim_c.atk_active    = True
                                    anim_c.atk_frame_idx = 0
                                    anim_c.atk_timer     = 0.0

                    elif kind == "ghost":
                        ai_c.bat_phase += dt * 2.2
                        perp = pygame.Vector2(-move_dir.y, move_dir.x)
                        amplitude = 0.50 if dist > 160 else 0.20
                        move_dir  = move_dir + perp * math.sin(ai_c.bat_phase) * amplitude
                        if move_dir.length_squared() > 0:
                            move_dir = move_dir.normalize()
                        ai_c.charge_timer -= dt
                        if ai_c.charge_timer <= 0 and not ai_c.charging:
                            ai_c.charge_timer    = random.uniform(3.0, 5.0)
                            ai_c.charging        = True
                            ai_c.charge_active_t = random.uniform(0.30, 0.50)
                        if ai_c.charging:
                            ai_c.charge_active_t -= dt
                            if ai_c.charge_active_t <= 0:
                                ai_c.charging = False
                            else:
                                move_speed *= 2.5
                                if not anim_c.atk_active:
                                    anim_c.atk_active    = True
                                    anim_c.atk_frame_idx = 0
                                    anim_c.atk_timer     = 0.0

                    elif kind == "agis":
                        ai_c.charge_timer -= dt
                        if ai_c.charge_timer <= 0 and not ai_c.charging:
                            ai_c.charge_timer    = random.uniform(5.0, 8.0)
                            ai_c.charging        = True
                            ai_c.charge_active_t = 0.6
                        if ai_c.charging:
                            ai_c.charge_active_t -= dt
                            if ai_c.charge_active_t <= 0:
                                ai_c.charging = False
                            else:
                                move_speed *= 2.5
                                if not anim_c.atk_active:
                                    anim_c.atk_active    = True
                                    anim_c.atk_frame_idx = 0
                                    anim_c.atk_timer     = 0.0

                    # ── Pathfinding for smaller enemies ──────────────────────
                    can_pathfind = (
                        obstacle_grid_index is not None
                        and kind not in ("boss", "mini_boss", "shooter")
                    )
                    if can_pathfind:
                        cs = obstacle_grid_index.cell_size
                        sc = (int(enemy.pos.x) // cs, int(enemy.pos.y) // cs)
                        gc = (int(p_pos.x)     // cs, int(p_pos.y)     // cs)
                        cache_ok = (
                            ai_c.cached_path_dir is not None
                            and ai_c.cached_path_start_cell == sc
                            and ai_c.cached_path_goal_cell  == gc
                        )
                        if cache_ok and ai_c.path_recalc_timer > 0:
                            pd = ai_c.cached_path_dir
                            move_dir = pygame.Vector2(pd[0], pd[1])
                        elif ai_c.path_recalc_timer <= 0:
                            pd = obstacle_grid_index.next_direction(enemy.pos, p_pos)
                            ai_c.cached_path_start_cell = sc
                            ai_c.cached_path_goal_cell  = gc
                            ai_c.cached_path_dir        = pd
                            ai_c.path_recalc_timer      = 0.28
                            if pd is not None:
                                move_dir = pygame.Vector2(pd[0], pd[1])

                    _msc = move_speed * dt
                    move_dir.x *= _msc
                    move_dir.y *= _msc
                    move = move_dir

                # ── Apply movement and obstacle collision ─────────────────────
                if move.x != 0 or move.y != 0:
                    enemy.pos += move
                    if kind not in ("boss", "mini_boss"):
                        if obstacle_grid_index is not None:
                            if obstacle_grid_index.point_collides(enemy.pos):
                                enemy.pos -= move
                        else:
                            for obs in obstacles:
                                if obs.hitbox.collidepoint(enemy.pos):
                                    enemy.pos -= move

                # ── Walk animation timer ──────────────────────────────────────
                anim_spd = 0.15 if kind in ("boss", "mini_boss", "agis") else 0.10
                anim_c.anim_timer += dt
                if anim_c.anim_timer > anim_spd:
                    anim_c.anim_timer = 0.0
                    walk_frames = (
                        enemy._dir_walk_frames.get(anim_c.facing_dir, enemy.anim_frames)
                        if enemy.use_directional else enemy.anim_frames
                    )
                    anim_c.frame_idx = (anim_c.frame_idx + 1) % len(walk_frames)


# ── 2. Combat ─────────────────────────────────────────────────────────────────

class EnemyCombatSystem:
    """Handles all combat timers and pending-action flags.

    Reads from context: p_pos, enemy_projectiles, puddles, loader,
                        enemy_projectile_cls, puddle_cls, shooter_proj_image.
    """

    def process(self, world, dt: float) -> None:
        ctx = world.context
        p_pos               = ctx["p_pos"]
        enemy_projectiles   = ctx["enemy_projectiles"]
        puddles             = ctx["puddles"]
        loader              = ctx["loader"]
        enemy_projectile_cls = ctx["enemy_projectile_cls"]
        puddle_cls          = ctx["puddle_cls"]
        shooter_proj_image  = ctx["shooter_proj_image"]

        for _eid, (pos_c, health_c, combat_c, tag_c, ai_c, anim_c, rend_c) in world.get_components(
            Position, Health, Combat, EnemyTag, AIState, AnimationState, Renderable
        ):
            if ai_c.frozen_timer > 0:
                continue

            enemy = rend_c.sprite
            kind  = tag_c.kind

            direction = p_pos - enemy.pos
            dist      = direction.length()

            # ── Shooter / Boss ranged attack ─────────────────────────────────
            if kind in ("shooter", "boss"):
                combat_c.shot_timer += dt
                cd = combat_c.shot_cooldown
                if kind == "boss":
                    if   health_c.hp < health_c.max_hp * 0.25: cd *= 0.4
                    elif health_c.hp < health_c.max_hp * 0.50: cd *= 0.7

                if combat_c.shot_timer >= cd:
                    combat_c.shot_timer = 0.0
                    if kind == "boss":
                        num = 8
                        if   health_c.hp < health_c.max_hp * 0.25: num = 16
                        elif health_c.hp < health_c.max_hp * 0.50: num = 12
                        for i in range(num):
                            angle = (360 / num) * i
                            vel   = pygame.Vector2(1, 0).rotate(angle) * 350.0
                            enemy_projectiles.add(
                                enemy_projectile_cls(enemy.pos, vel, combat_c.proj_dmg, loader, shooter_proj_image))
                    else:
                        rl = 500 if kind == "shooter" else 450
                        sp = 300.0 if kind == "shooter" else 150.0
                        if 0 < dist < rl:
                            vel = (direction / dist) * sp
                            enemy_projectiles.add(
                                enemy_projectile_cls(enemy.pos, vel, combat_c.proj_dmg, loader, shooter_proj_image))

            # ── Mini-boss melee ──────────────────────────────────────────────
            if kind == "mini_boss":
                combat_c.melee_timer += dt
                melee_cd = 1.0 if health_c.hp >= health_c.max_hp * 0.5 else 0.65
                if combat_c.melee_timer >= melee_cd:
                    if dist <= combat_c.melee_range:
                        combat_c.melee_timer       = 0.0
                        combat_c.pending_melee_hit = True
                        if not anim_c.atk_active:
                            anim_c.atk_active    = True
                            anim_c.atk_frame_idx = 0
                            anim_c.atk_timer     = 0.0

            # ── Agis special attacks ─────────────────────────────────────────
            if kind == "agis":
                combat_c.agis_shot_timer += dt
                shot_cd = 2.2 if health_c.hp >= health_c.max_hp * 0.5 else 1.4
                if combat_c.agis_shot_timer >= shot_cd and 0 < dist <= 600:
                    combat_c.agis_shot_timer = 0.0
                    if dist > 0:
                        d = direction / dist
                        combat_c.agis_shot_dir.x = d.x
                        combat_c.agis_shot_dir.y = d.y
                    combat_c.pending_agis_shot = True

                combat_c.agis_area_timer += dt
                if combat_c.agis_area_timer >= 5.0:
                    combat_c.agis_area_timer   = 0.0
                    combat_c.pending_agis_area = True

            # ── Proximity attack animation triggers ──────────────────────────
            if (kind in ("bat", "goblin", "beholder", "rat",
                         "slime_fire", "slime_red", "slime_yellow")
                    and enemy._atk_range > 0
                    and not anim_c.atk_active
                    and dist < enemy._atk_range):
                anim_c.atk_active    = True
                anim_c.atk_frame_idx = 0
                anim_c.atk_timer     = 0.0

            # ── Slime puddle ─────────────────────────────────────────────────
            if kind == "slime":
                combat_c.puddle_timer += dt
                if combat_c.puddle_timer >= 2.5:
                    combat_c.puddle_timer = 0.0
                    puddles.add(puddle_cls(enemy.pos, loader))


# ── 3. Animation ──────────────────────────────────────────────────────────────

class EnemyAnimationSystem:
    """Advances frame timers and writes the current frame to sprite.image.

    The sprite's helper methods (_get_walk_frame, _get_white_frame, etc.) still
    live in the Enemy class and access self._anim_comp directly, so they require
    no signature changes.
    """

    def process(self, world, dt: float) -> None:
        for _eid, (ai_c, anim_c, tag_c, rend_c) in world.get_components(
            AIState, AnimationState, EnemyTag, Renderable
        ):
            enemy = rend_c.sprite

            # ── Frozen: just show frozen frame (no anim advancement) ─────────
            if ai_c.frozen_timer > 0:
                enemy.image = enemy._get_frozen_frame()
                continue

            # ── Advance attack animation ─────────────────────────────────────
            if anim_c.atk_active:
                anim_c.atk_timer += dt
                if anim_c.atk_timer >= anim_c.atk_frame_speed:
                    anim_c.atk_timer     = 0.0
                    anim_c.atk_frame_idx += 1
                    max_f = enemy._count_atk_frames()
                    if anim_c.atk_frame_idx >= max_f:
                        anim_c.atk_active    = False
                        anim_c.atk_frame_idx = 0

            # ── Select final frame ───────────────────────────────────────────
            if anim_c.atk_active and enemy._atk_overlay:
                walk_frame = (enemy._get_white_frame() if ai_c.flash_timer > 0
                              else enemy._get_walk_frame())
                af = enemy._get_atk_frame()
                if af:
                    w_size    = walk_frame.get_size()
                    composite = pygame.Surface(w_size, pygame.SRCALPHA)
                    composite.blit(walk_frame, (0, 0))
                    ox = (w_size[0] - af.get_width())  // 2
                    oy = (w_size[1] - af.get_height()) // 2
                    composite.blit(af, (ox, oy))
                    enemy.image = composite
                else:
                    enemy.image = walk_frame
            elif anim_c.atk_active:
                af = enemy._get_atk_frame()
                enemy.image = af if af else enemy._get_walk_frame()
            elif ai_c.flash_timer > 0:
                enemy.image = enemy._get_white_frame()
            else:
                enemy.image = enemy._get_walk_frame()

            # ── Elite aura overlay ───────────────────────────────────────────
            if tag_c.is_elite:
                sz = enemy.image.get_size()
                if getattr(enemy, "_elite_aura_size", None) != sz:
                    enemy._elite_aura_size = sz
                    enemy._elite_aura = pygame.Surface(sz, pygame.SRCALPHA)
                    pygame.draw.ellipse(
                        enemy._elite_aura, (255, 215, 0, 100),
                        enemy._elite_aura.get_rect(), 3,
                    )
                enemy.image = enemy.image.copy()
                enemy.image.blit(enemy._elite_aura, (0, 0),
                                 special_flags=pygame.BLEND_RGBA_ADD)


# ── 4. Render ─────────────────────────────────────────────────────────────────

class EnemyRenderSystem:
    """Syncs sprite.rect.center from world-space position + camera offset.

    Must run LAST so that image is already set by EnemyAnimationSystem.
    Reads from context: cam.
    """

    def process(self, world, dt: float) -> None:
        cam: pygame.Vector2 = world.context["cam"]

        for _eid, (rend_c,) in world.get_components(Renderable):
            enemy = rend_c.sprite
            enemy.rect.center = enemy.pos + cam
