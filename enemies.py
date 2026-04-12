import math
import random

import pygame


# ---------------------------------------------------------------------------
# Configuração de sprites para inimigos baseados em spritesheet direcional.
# ---------------------------------------------------------------------------
SPRITESHEET_CONFIGS = {
    "bat": {
        "walk_sheet":  "sprite/monster/bat_run",
        "atk_sheet":   "sprite/monster/bat_att",
        "frame_w": 64, "frame_h": 64,
        "walk_frames": 8,
        "atk_frames":  8,
        "dir_rows": None,
        "size": (110, 110),
        "attack_range": 110,
        "gold_drops": 0,
    },
    "orc": {
        # orc.png: 384x512 → 3 frames × 4 linhas, frame 128×128
        # Linhas: baixo=0, esquerda=1, direita=2, cima=3
        # Orcs são criaturas grandes e brutais — tamanho aumentado proporcionalmente
        "walk_sheet":  "sprite/monster/orc",
        "atk_sheet":   None,
        "frame_w": 128, "frame_h": 128,
        "walk_frames": 3,
        "atk_frames":  0,
        "dir_rows": {"down": 0, "left": 1, "right": 2, "up": 3},
        "size": (168, 168),    # era (112,112) — 50% maior, pois orcs devem impressionar
        "attack_range": 0,
        "gold_drops": 0,
    },
    "mini_boss": {
        # boss.png / boss_attack.png: 640x256 → 10 frames × 4 linhas, frame 64×64
        # Linhas: cima=0, esquerda=1, direita=2, baixo=3
        "walk_sheet": "sprite/monster/boss/boss",
        "atk_sheet":  "sprite/monster/boss/boss_attack",
        "frame_w": 64, "frame_h": 64,
        "walk_frames": 10,
        "atk_frames":  10,
        "dir_rows": {"up": 0, "left": 1, "right": 2, "down": 3},
        "size": (192, 192),
        "attack_range": 0,
        "gold_drops": 5,
    },
}


def _make_effect_variants(frames):
    """Gera variantes branca (hit-flash) e azul (congelado) de uma lista de frames."""
    white_list, frozen_list = [], []
    for frame in frames:
        mask = pygame.mask.from_surface(frame)
        ws = mask.to_surface(setcolor=(255, 255, 255, 255), unsetcolor=(0, 0, 0, 0))
        white_list.append(ws)
        bs = mask.to_surface(setcolor=(0, 255, 255, 150), unsetcolor=(0, 0, 0, 0))
        combined = frame.copy()
        combined.blit(bs, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)
        frozen_list.append(combined)
    return white_list, frozen_list


class EnemyProjectile(pygame.sprite.Sprite):
    """Projétil de inimigo modularizado."""

    @staticmethod
    def _prepare_frame(frame, target_size):
        bbox = frame.get_bounding_rect(min_alpha=1)
        if bbox.width > 0 and bbox.height > 0:
            frame = frame.subsurface(bbox).copy()
        return pygame.transform.smoothscale(frame, target_size)

    def __init__(self, pos, vel, dmg, loader, img_name):
        super().__init__()
        raw_frames = loader.load_animation(img_name, 4, None, fallback_colors=((255, 120, 0), (200, 50, 0)))
        base_frames = [self._prepare_frame(frame, (36, 36)) for frame in raw_frames]
        shoot_angle = math.degrees(math.atan2(-vel.y, vel.x))
        self.anim_frames = [pygame.transform.rotate(frame, shoot_angle) for frame in base_frames]
        self.frame_idx = 0
        self.anim_timer = 0
        self.image = self.anim_frames[0]
        self.rect = self.image.get_rect()
        self.pos = pygame.Vector2(pos.x, pos.y)
        self.vel = vel
        self.dmg = dmg

    def update(self, dt, cam, screen_w, screen_h):
        self.pos += self.vel * dt
        self.anim_timer += dt
        if self.anim_timer > 0.05:
            self.anim_timer = 0
            self.frame_idx = (self.frame_idx + 1) % len(self.anim_frames)
            self.image = self.anim_frames[self.frame_idx]
        self.rect.center = self.pos + cam
        world_rect = pygame.Rect(-1000, -1000, screen_w + 2000, screen_h + 2000)
        if not world_rect.collidepoint(self.rect.center):
            self.kill()


class Enemy(pygame.sprite.Sprite):
    """Classe de inimigo modularizada com suporte a IA aprimorada."""

    def __init__(self, kind, pos, loader, diff_mults, screen_size_getter,
                 time_scale=1.0, boss_tier=1, is_elite=False, boss_max_hp=500):
        super().__init__()
        self.kind       = kind
        self.is_elite   = is_elite
        self.screen_size_getter = screen_size_getter

        self.knockback    = pygame.Vector2(0, 0)
        self.flash_timer  = 0.0
        self.frozen_timer = 0.0

        # --- Animação direcional (novos inimigos) ---
        self.use_directional    = False
        self.facing_dir         = "down"
        self._dir_walk_frames   = {}
        self._dir_white_frames  = {}
        self._dir_frozen_frames = {}
        self._dir_atk_frames    = {}
        self._atk_frames_flat         = []
        self._atk_frames_flat_flipped = []
        self._atk_active      = False
        self._atk_frame_idx   = 0
        self._atk_timer       = 0.0
        self._atk_frame_speed = 0.10
        self._atk_range       = 0

        # --- Drop extra (mini_boss) ---
        self.gold_drops = 0

        # --- Melee (mini_boss) ---
        self.melee_range       = 0
        self.melee_timer       = 0.0
        self.pending_melee_hit = False
        self.melee_dmg         = 0.0

        # ================================================================
        # IA aprimorada — atributos por tipo
        # ================================================================
        # Bat: zigzag sinusoidal
        self._bat_phase = random.uniform(0, math.pi * 2)

        # Orc: flanqueamento periódico
        self._flank_timer    = random.uniform(1.5, 3.5)
        self._flank_angle    = 0.0
        self._flank_active   = False
        self._flank_active_t = 0.0

        # Mini_boss: fase de carga + fase de raiva
        self._charge_cooldown = random.uniform(3.5, 5.0)
        self._charge_timer    = self._charge_cooldown
        self._charging        = False
        self._charge_active_t = 0.0

        # ================================================================
        # Carrega sprites
        # ================================================================
        cfg = SPRITESHEET_CONFIGS.get(kind)
        if cfg:
            self._init_spritesheet_enemy(kind, loader, cfg)
        else:
            self._init_legacy_enemy(kind, loader, boss_max_hp)

        # --- Timers de animação / projéteis ---
        self.frame_idx    = 0
        self.anim_timer   = 0.0
        self.facing_right = True
        self.shot_timer   = 0.0
        self.shot_cooldown = self._resolve_shot_cooldown(kind)
        self.puddle_timer = 0.0
        self.path_recalc_timer      = 0.0
        self.cached_path_start_cell = None
        self.cached_path_goal_cell  = None
        self.cached_path_dir        = None

        self.image = self.anim_frames[0]
        self.rect  = self.image.get_rect()
        self.pos   = pos

        # --- Stats base ---
        stats = {
            "runner":    (2,   150),
            "tank":      (10,   65),
            "elite":     (60,   85),
            "shooter":   (3,    90),
            "boss":      (boss_max_hp, 95),
            "slime":     (5,   110),
            "robot":     (8,   130),
            "bat":       (1,   145),
            "orc":       (12,   75),
            "mini_boss": (300,  85),
        }
        base_hp, base_spd = stats.get(kind, (2, 100))

        if kind == "boss":
            self.hp = base_hp * diff_mults["hp_mult"] * time_scale * boss_tier
        elif kind == "mini_boss":
            self.hp = base_hp * diff_mults["hp_mult"] * (1.0 + time_scale * 0.3)
        else:
            self.hp = base_hp * diff_mults["hp_mult"] * time_scale

        self.speed  = base_spd * diff_mults["spd_mult"] * min(1.5, time_scale)
        self.max_hp = self.hp

        # Melee do mini_boss
        if kind == "mini_boss":
            self.melee_range = 155
            self.melee_dmg   = 1.5 * diff_mults.get("dmg_mult", 1.0)

    # ------------------------------------------------------------------
    # Inicialização interna
    # ------------------------------------------------------------------

    def _resolve_shot_cooldown(self, kind):
        return {
            "robot":    1.0,
            "boss":     3.0,
        }.get(kind, 3.0)

    def _init_legacy_enemy(self, kind, loader, boss_max_hp):
        configs = {
            "boss":    (((50, 0, 0), (0, 0, 0)),    (250, 250), 4),
            "shooter": (((200,50,200),(120,0,120)),  (110, 95), 11),
            "tank":    (((50,200,50),(0,120,0)),     (100, 90), 11),
            "elite":   (((255,200,0),(150,100,0)),   (100, 90), 11),
            "slime":   (((20,20,20),(50,100,50)),    (90,  80), 10),
            "robot":   (((100,100,150),(50,50,100)), (100,100),  4),
        }
        color, size, frames = configs.get(kind, (((255,100,100),(150,0,0)), (100,100), 11))

        self.anim_frames    = loader.load_animation(kind, frames, size, fallback_colors=color)
        self.flipped_frames = [pygame.transform.flip(f, True, False) for f in self.anim_frames]
        self.white_frames, self.frozen_frames = _make_effect_variants(self.anim_frames)
        self.flipped_white_frames  = [pygame.transform.flip(f, True, False) for f in self.white_frames]
        self.flipped_frozen_frames = [pygame.transform.flip(f, True, False) for f in self.frozen_frames]

    def _init_spritesheet_enemy(self, kind, loader, cfg):
        size     = cfg["size"]
        fw, fh   = cfg["frame_w"], cfg["frame_h"]
        dir_rows = cfg.get("dir_rows")
        self.gold_drops = cfg.get("gold_drops", 0)
        self._atk_range = cfg.get("attack_range", 0)

        if dir_rows:
            self.use_directional = True
            fpd = cfg["walk_frames"]
            for dir_name, row_idx in dir_rows.items():
                indices = list(range(row_idx * fpd, (row_idx + 1) * fpd))
                frames  = loader.load_spritesheet(cfg["walk_sheet"], fw, fh,
                                                  len(indices), size, frame_indices=indices)
                if frames:
                    wf, ff = _make_effect_variants(frames)
                    self._dir_walk_frames[dir_name]   = frames
                    self._dir_white_frames[dir_name]  = wf
                    self._dir_frozen_frames[dir_name] = ff

            default_dir    = "down" if "down" in self._dir_walk_frames else (
                list(self._dir_walk_frames.keys())[0] if self._dir_walk_frames else None)
            fallback_frames = self._dir_walk_frames.get(default_dir, []) if default_dir else []
            if not fallback_frames:
                fallback_frames = loader.load_animation(kind, 4, size,
                                                        fallback_colors=((100,100,100),(50,50,50)))
        else:
            frames = loader.load_spritesheet(cfg["walk_sheet"], fw, fh, cfg["walk_frames"], size)
            if not frames:
                frames = loader.load_animation(kind, 4, size,
                                               fallback_colors=((80,0,80),(40,0,40)))
            fallback_frames = frames

        self.anim_frames    = fallback_frames
        self.flipped_frames = [pygame.transform.flip(f, True, False) for f in self.anim_frames]
        self.white_frames, self.frozen_frames = _make_effect_variants(self.anim_frames)
        self.flipped_white_frames  = [pygame.transform.flip(f, True, False) for f in self.white_frames]
        self.flipped_frozen_frames = [pygame.transform.flip(f, True, False) for f in self.frozen_frames]

        atk_sheet = cfg.get("atk_sheet")
        if atk_sheet:
            if dir_rows and cfg.get("atk_frames", 0) > 0:
                fpd = cfg["atk_frames"]
                for dir_name, row_idx in dir_rows.items():
                    indices   = list(range(row_idx * fpd, (row_idx + 1) * fpd))
                    atk_frames = loader.load_spritesheet(atk_sheet, fw, fh,
                                                         len(indices), size, frame_indices=indices)
                    if atk_frames:
                        self._dir_atk_frames[dir_name] = atk_frames
            elif cfg.get("atk_frames", 0) > 0:
                atk_frames = loader.load_spritesheet(atk_sheet, fw, fh, cfg["atk_frames"], size)
                if atk_frames:
                    self._atk_frames_flat = atk_frames
                    self._atk_frames_flat_flipped = [
                        pygame.transform.flip(f, True, False) for f in atk_frames]

    # ------------------------------------------------------------------
    # Helpers de render
    # ------------------------------------------------------------------

    def _get_walk_frame(self):
        if self.use_directional and self._dir_walk_frames:
            frames = self._dir_walk_frames.get(self.facing_dir, self.anim_frames)
            return frames[self.frame_idx % len(frames)]
        base = self.anim_frames if self.facing_right else self.flipped_frames
        return base[self.frame_idx % len(base)]

    def _get_white_frame(self):
        if self.use_directional and self._dir_white_frames:
            frames = self._dir_white_frames.get(self.facing_dir, self.white_frames)
            return frames[self.frame_idx % len(frames)]
        base = self.white_frames if self.facing_right else self.flipped_white_frames
        return base[self.frame_idx % len(base)]

    def _get_frozen_frame(self):
        if self.use_directional and self._dir_frozen_frames:
            frames = self._dir_frozen_frames.get(self.facing_dir, self.frozen_frames)
            return frames[self.frame_idx % len(frames)]
        base = self.frozen_frames if self.facing_right else self.flipped_frozen_frames
        return base[self.frame_idx % len(base)]

    def _get_atk_frame(self):
        if self._dir_atk_frames:
            frames = self._dir_atk_frames.get(self.facing_dir, [])
            if frames:
                return frames[self._atk_frame_idx % len(frames)]
        if self._atk_frames_flat:
            pool = self._atk_frames_flat if self.facing_right else self._atk_frames_flat_flipped
            return pool[self._atk_frame_idx % len(pool)]
        return None

    def _advance_atk_anim(self, dt):
        if not self._atk_active:
            return False
        self._atk_timer += dt
        if self._atk_timer >= self._atk_frame_speed:
            self._atk_timer = 0.0
            self._atk_frame_idx += 1
            max_f = self._count_atk_frames()
            if self._atk_frame_idx >= max_f:
                self._atk_active    = False
                self._atk_frame_idx = 0
        return self._atk_active

    def _count_atk_frames(self):
        if self._dir_atk_frames:
            frames = self._dir_atk_frames.get(self.facing_dir, [])
            return len(frames) if frames else 1
        return len(self._atk_frames_flat) if self._atk_frames_flat else 1

    def _trigger_atk_anim(self):
        self._atk_active    = True
        self._atk_frame_idx = 0
        self._atk_timer     = 0.0

    # ------------------------------------------------------------------
    # Helper: atualiza facing_dir com base na direção ao jogador
    # ------------------------------------------------------------------

    def _update_facing(self, direction, dist):
        """Atualiza facing_right e facing_dir com base em direction (vetor jogador - inimigo)."""
        if dist <= 0:
            return
        self.facing_right = direction.x >= 0
        if self.use_directional:
            ax, ay = abs(direction.x), abs(direction.y)
            if ax >= ay:
                self.facing_dir = "right" if direction.x >= 0 else "left"
            else:
                self.facing_dir = "down"  if direction.y >= 0 else "up"

    # ------------------------------------------------------------------
    # Update principal
    # ------------------------------------------------------------------

    def update(self, dt, p_pos, cam, obstacles, enemy_projectiles, puddles,
               loader, selected_pact, enemy_projectile_cls, puddle_cls,
               shooter_proj_image, obstacle_grid_index=None):

        self.pos      += self.knockback
        self.knockback *= 0.85
        if self.path_recalc_timer > 0:
            self.path_recalc_timer -= dt
        if self.flash_timer > 0:
            self.flash_timer -= dt

        # --- Congelado ---
        if self.frozen_timer > 0:
            self.frozen_timer -= dt
            self.image = self._get_frozen_frame()
            self.rect.center = self.pos + cam
            return

        direction = p_pos - self.pos
        dist      = direction.length()

        # Atualiza facing sempre (resolve ataque na direção errada)
        self._update_facing(direction, dist)

        can_move = self.knockback.length() < 3.0

        if dist > 0 and can_move:
            is_ranged  = self.kind in ["shooter", "robot"]
            stop_dist  = 450 if self.kind == "shooter" else 300

            if is_ranged and dist < stop_dist:
                move = pygame.Vector2(0, 0)
            else:
                move_speed = self.speed
                if selected_pact == "VELOCIDADE":
                    move_speed *= 1.5

                # Boss enraivecido em baixo HP
                if self.kind == "boss":
                    if   self.hp < self.max_hp * 0.25: move_speed *= 2.0
                    elif self.hp < self.max_hp * 0.50: move_speed *= 1.5

                move_dir = direction / dist  # direção normalizada

                # ============================================================
                # IA aprimorada por tipo
                # ============================================================

                # BAT — zigzag sinusoidal perpendicular ao alvo
                if self.kind == "bat":
                    self._bat_phase += dt * 3.5
                    perp = pygame.Vector2(-move_dir.y, move_dir.x)
                    amplitude = 0.75 if dist > 200 else 0.35
                    move_dir  = move_dir + perp * math.sin(self._bat_phase) * amplitude
                    if move_dir.length_squared() > 0:
                        move_dir = move_dir.normalize()

                # ORC — flanqueamento periódico
                elif self.kind == "orc":
                    self._flank_timer -= dt
                    if self._flank_timer <= 0:
                        self._flank_timer    = random.uniform(2.0, 4.5)
                        self._flank_angle    = random.choice([-55, -40, 40, 55])
                        self._flank_active   = True
                        self._flank_active_t = random.uniform(0.5, 0.9)
                    if self._flank_active:
                        self._flank_active_t -= dt
                        if self._flank_active_t <= 0:
                            self._flank_active = False
                        else:
                            move_dir = pygame.Vector2(
                                move_dir.x * math.cos(math.radians(self._flank_angle))
                                - move_dir.y * math.sin(math.radians(self._flank_angle)),
                                move_dir.x * math.sin(math.radians(self._flank_angle))
                                + move_dir.y * math.cos(math.radians(self._flank_angle)),
                            )

                # MINI_BOSS — fases de carga
                elif self.kind == "mini_boss":
                    self._charge_timer -= dt
                    if self._charge_timer <= 0 and not self._charging:
                        self._charge_timer    = random.uniform(3.5, 5.5)
                        self._charging        = True
                        self._charge_active_t = 0.8
                    if self._charging:
                        self._charge_active_t -= dt
                        if self._charge_active_t <= 0:
                            self._charging = False
                        else:
                            # Carga: velocidade triplicada em direção direta ao alvo
                            move_speed *= 3.5
                            # Dispara ataque visual na carga
                            if not self._atk_active:
                                self._trigger_atk_anim()

                # Pathfinding para inimigos menores
                can_pathfind = (
                    obstacle_grid_index is not None
                    and self.kind not in ["boss", "mini_boss", "shooter", "robot"]
                )
                if can_pathfind:
                    cs   = obstacle_grid_index.cell_size
                    sc   = (int(self.pos.x) // cs, int(self.pos.y) // cs)
                    gc   = (int(p_pos.x)    // cs, int(p_pos.y)    // cs)
                    ok   = (
                        self.cached_path_dir is not None
                        and self.cached_path_start_cell == sc
                        and self.cached_path_goal_cell  == gc
                    )
                    if ok and self.path_recalc_timer > 0:
                        move_dir = pygame.Vector2(self.cached_path_dir[0], self.cached_path_dir[1])
                    elif self.path_recalc_timer <= 0:
                        pd = obstacle_grid_index.next_direction(self.pos, p_pos)
                        self.cached_path_start_cell = sc
                        self.cached_path_goal_cell  = gc
                        self.cached_path_dir        = pd
                        self.path_recalc_timer      = 0.20
                        if pd is not None:
                            move_dir = pygame.Vector2(pd[0], pd[1])

                move = move_dir * move_speed * dt

            if move.length_squared() > 0:
                self.pos += move
                if self.kind not in ["boss", "mini_boss"]:
                    for obs in obstacles:
                        if obs.hitbox.collidepoint(self.pos):
                            self.pos -= move

            anim_spd = 0.15 if self.kind in ["boss", "mini_boss"] else 0.10
            self.anim_timer += dt
            if self.anim_timer > anim_spd:
                self.anim_timer = 0
                walk_len = len(
                    self._dir_walk_frames.get(self.facing_dir, self.anim_frames)
                    if self.use_directional else self.anim_frames
                )
                self.frame_idx = (self.frame_idx + 1) % walk_len

        # ================================================================
        # Disparo para shooter / robot / boss   (mini_boss agora é MELEE)
        # ================================================================
        if self.kind in ["shooter", "robot", "boss"]:
            self.shot_timer += dt
            cd = self.shot_cooldown
            if self.kind == "boss":
                if   self.hp < self.max_hp * 0.25: cd *= 0.4
                elif self.hp < self.max_hp * 0.50: cd *= 0.7

            if self.shot_timer >= cd:
                self.shot_timer = 0.0
                if self.kind == "boss":
                    num = 8
                    if   self.hp < self.max_hp * 0.25: num = 16
                    elif self.hp < self.max_hp * 0.50: num = 12
                    for i in range(num):
                        angle = (360 / num) * i
                        vel   = pygame.Vector2(1, 0).rotate(angle) * 350.0
                        enemy_projectiles.add(
                            enemy_projectile_cls(self.pos, vel, 1.0, loader, shooter_proj_image))
                else:
                    rl  = 500 if self.kind == "shooter" else 450
                    sp  = 300.0 if self.kind == "shooter" else 150.0
                    if 0 < dist < rl:
                        vel = (direction / dist) * sp
                        enemy_projectiles.add(
                            enemy_projectile_cls(self.pos, vel, 0.5, loader, shooter_proj_image))

        # ================================================================
        # Melee do mini_boss
        # ================================================================
        if self.kind == "mini_boss":
            self.melee_timer += dt
            melee_cd = 1.0 if self.hp >= self.max_hp * 0.5 else 0.65
            if self.melee_timer >= melee_cd:
                if dist <= self.melee_range:
                    self.melee_timer       = 0.0
                    self.pending_melee_hit = True
                    if not self._atk_active:
                        self._trigger_atk_anim()

        # BAT — dispara animação de ataque por proximidade
        if self.kind == "bat" and self._atk_range > 0 and not self._atk_active:
            if dist < self._atk_range:
                self._trigger_atk_anim()

        # Slime — deixa poças
        if self.kind == "slime":
            self.puddle_timer += dt
            if self.puddle_timer >= 2.5:
                self.puddle_timer = 0.0
                puddles.add(puddle_cls(self.pos, loader))

        # --- Avança animação de ataque ---
        self._advance_atk_anim(dt)

        # --- Seleciona frame final ---
        if self._atk_active:
            af = self._get_atk_frame()
            self.image = af if af else self._get_walk_frame()
        elif self.flash_timer > 0:
            self.image = self._get_white_frame()
        else:
            self.image = self._get_walk_frame()

        # Aura de elite
        if self.is_elite:
            aura = pygame.Surface(self.image.get_size(), pygame.SRCALPHA)
            pygame.draw.ellipse(aura, (255, 215, 0, 100), aura.get_rect(), 3)
            self.image = self.image.copy()
            self.image.blit(aura, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)

        self.rect.center = self.pos + cam
