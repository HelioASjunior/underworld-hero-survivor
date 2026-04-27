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
        "size": (140, 140),
        "attack_range": 140,
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
    "runner": {
        # runner.png: 384x512 → 3 frames × 4 linhas, frame 128×128
        # Linhas: baixo=0, esquerda=1, direita=2, cima=3
        "walk_sheet":  "sprite/monster/runner",
        "atk_sheet":   None,
        "frame_w": 128, "frame_h": 128,
        "walk_frames": 3,
        "atk_frames":  0,
        "dir_rows": {"down": 0, "left": 1, "right": 2, "up": 3},
        "size": (96, 96),
        "attack_range": 0,
        "gold_drops": 0,
    },
    "minotauro": {
        # Mino2.png: 582x407 → 6 colunas × 4 linhas, frame 97×101
        # Padrão do orc: usa apenas os 3 primeiros frames de caminhada por direção
        # Linhas: baixo=0, esquerda=1, direita=2, cima=3
        "walk_sheet":  "sprite/monster/Mino2",
        "atk_sheet":   None,
        "frame_w": 97, "frame_h": 101,
        "sheet_cols": 6,
        "walk_frames": 3,
        "atk_frames":  0,
        "dir_rows": {"down": 0, "left": 1, "right": 2, "up": 3},
        "size": (100, 100),
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
    "tank": {
        # Mino1.png: 437x395 → 3 frames × 4 linhas, frame 145×98
        # Linhas: baixo=0, esquerda=1, direita=2, cima=3
        "walk_sheet":  "sprite/monster/Mino1",
        "atk_sheet":   None,
        "frame_w": 145, "frame_h": 98,
        "walk_frames": 3,
        "atk_frames":  0,
        "dir_rows": {"down": 0, "left": 1, "right": 2, "up": 3},
        "size": (168, 168),
        "attack_range": 0,
        "gold_drops": 0,
    },
    "goblin": {
        # goblin_move.png: 512×256 → 8 cols × 4 rows, frame 64×64
        # goblin_att.png:  512×256 → 8 cols × 4 rows, frame 64×64
        # Linhas: baixo=0, cima=1, esquerda=2, direita=3
        "walk_sheet":  "sprite/monster/New Monster/goblin_move",
        "atk_sheet":   "sprite/monster/New Monster/goblin_att",
        "frame_w": 64, "frame_h": 64,
        "walk_frames": 8,
        "atk_frames":  8,
        "dir_rows": {"down": 0, "up": 1, "left": 2, "right": 3},
        "size": (130, 130),
        "attack_range": 110,
        "gold_drops": 1,
    },
    "beholder": {
        # bh_run.png: 512×256 → 8 cols × 4 rows, frame 64×64
        # Rows 0-1 contêm o Beholder; rows 2-3 são criaturas diferentes no mesmo sheet.
        # Tratado como não-direcional: usa só o row 0 (8 frames de animação).
        # bh_ataque.png: 768×256 → 12 cols × 4 rows, frame 64×64 (row 0 = 12 frames)
        "walk_sheet":  "sprite/monster/New Monster/bh_run",
        "atk_sheet":   "sprite/monster/New Monster/bh_ataque",
        "frame_w": 64, "frame_h": 64,
        "walk_frames": 8,
        "atk_frames":  12,
        "dir_rows": None,
        "size": (145, 145),
        "attack_range": 140,
        "gold_drops": 2,
    },
    "rat": {
        # rat_run.png: 768×512 → 6 cols × 4 rows, frame 128×128
        # rat_att.png: 1024×512 → 8 cols × 4 rows, frame 128×128
        # Linhas: baixo=0, cima=1, esquerda=2, direita=3
        "walk_sheet":  "sprite/monster/New Monster/rat_run",
        "atk_sheet":   "sprite/monster/New Monster/rat_att",
        "frame_w": 128, "frame_h": 128,
        "walk_frames": 6,
        "atk_frames":  8,
        "dir_rows": {"down": 0, "up": 1, "left": 2, "right": 3},
        "size": (220, 220),
        "attack_range": 145,
        "gold_drops": 2,
    },
    "agis": {
        # agis.png: 3360×240 → 15 frames de 224×240, linha única (sem direção)
        #   Verificado: bordas exatas em x=224,448,...,3360 (zero pixels)
        # Ataque a distância — projétil criado em jogo_final.py usando agis_att.png
        "walk_sheet":  "sprite/monster/boss/agis",
        "atk_sheet":   None,
        "frame_w": 224, "frame_h": 240,
        "walk_frames": 15,
        "atk_frames":  0,
        "dir_rows": None,
        "size": (230, 230),
        "attack_range": 0,
        "gold_drops": 15,
    },
    "slime_fire": {
        # mapa_volcano/slimefire_movimento.png: 512×256 → 8 cols × 4 rows, frame 64×64
        # mapa_volcano/slimefire_ataque.png:    576×256 → 9 cols × 4 rows, frame 64×64
        # Linhas: baixo=0, cima=1, esquerda=2, direita=3
        "walk_sheet":     "sprite/monster/New Monster/mapa_volcano/slimefire_movimento",
        "atk_sheet":      "sprite/monster/New Monster/mapa_volcano/slimefire_ataque",
        "frame_w": 64, "frame_h": 64,
        "walk_frames": 8,
        "atk_frames":  9,
        "atk_sheet_cols": 9,
        "dir_rows": {"down": 0, "up": 1, "left": 2, "right": 3},
        "size": (145, 145),
        "attack_range": 120,
        "gold_drops": 2,
    },
    "slime_red": {
        # mapa_volcano/slime3_movimento.png: 512×256 → 8 cols × 4 rows, frame 64×64
        # mapa_volcano/slime3_ataque.png:    640×256 → 10 cols × 4 rows, frame 64×64
        # Linhas: baixo=0, cima=1, esquerda=2, direita=3
        "walk_sheet":  "sprite/monster/New Monster/mapa_volcano/slime3_movimento",
        "atk_sheet":   "sprite/monster/New Monster/mapa_volcano/slime3_ataque",
        "frame_w": 64, "frame_h": 64,
        "walk_frames": 8,
        "atk_frames":  10,
        "atk_sheet_cols": 10,
        "dir_rows": {"down": 0, "up": 1, "left": 2, "right": 3},
        "size": (135, 135),
        "attack_range": 110,
        "gold_drops": 2,
    },
    "slime_yellow": {
        # mapa_volcano/slime2_movimento.png: 512×256 → 8 cols × 4 rows, frame 64×64
        # mapa_volcano/slime2_ataque.png:    640×256 → 10 cols × 4 rows, frame 64×64
        # Linhas: baixo=0, cima=1, esquerda=2, direita=3
        "walk_sheet":  "sprite/monster/New Monster/mapa_volcano/slime2_movimento",
        "atk_sheet":   "sprite/monster/New Monster/mapa_volcano/slime2_ataque",
        "frame_w": 64, "frame_h": 64,
        "walk_frames": 8,
        "atk_frames":  10,
        "atk_sheet_cols": 10,
        "dir_rows": {"down": 0, "up": 1, "left": 2, "right": 3},
        "size": (130, 130),
        "attack_range": 110,
        "gold_drops": 1,
    },
    "ghost": {
        # ghost.run.png:    384×256 → 6 cols × 4 rows, frame 64×64
        # ghost.ataque.png: 768×256 → 12 cols × 4 rows, frame 64×64
        # ghost.dt.png:     576×256 → 9 cols × 4 rows, frame 64×64
        # Linhas: baixo=0, cima=1, esquerda=2, direita=3
        "walk_sheet":   "sprite/monster/New Monster/ghost.run",
        "atk_sheet":    "sprite/monster/New Monster/ghost.ataque",
        "morte_sheet":  "sprite/monster/New Monster/ghost.dt",
        "frame_w": 64, "frame_h": 64,
        "walk_frames": 6,
        "atk_frames":  12,
        "morte_frames": 9,
        "atk_sheet_cols": 12,
        "dir_rows": {"down": 0, "up": 1, "left": 2, "right": 3},
        "size": (130, 130),
        "attack_range": 115,
        "gold_drops": 2,
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


class EnemyDeathAnim(pygame.sprite.Sprite):
    """Reproduz a animação de morte de um inimigo uma vez e se remove."""

    FRAME_SPEED = 0.08  # segundos por frame

    def __init__(self, pos, frames):
        super().__init__()
        self.frames    = frames
        self.frame_idx = 0
        self.timer     = 0.0
        self.image     = frames[0]
        self.rect      = self.image.get_rect()
        self.pos       = pygame.Vector2(pos)

    def update(self, dt, cam):
        self.timer += dt
        if self.timer >= self.FRAME_SPEED:
            self.timer = 0.0
            self.frame_idx += 1
            if self.frame_idx >= len(self.frames):
                self.kill()
                return
            self.image = self.frames[self.frame_idx]
        self.rect.center = self.pos + cam


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
        self._morte_frames      = {}
        self._atk_frames_flat         = []
        self._atk_frames_flat_flipped = []
        self._atk_active      = False
        self._atk_frame_idx   = 0
        self._atk_timer       = 0.0
        self._atk_frame_speed = 0.10
        self._atk_range       = 0
        self._atk_overlay     = False   # True = sobreposição; False = substitui walk

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
        # HP aumentado ~2x para manter equilíbrio com bônus de itens equipados
        stats = {
            "runner":     (50,    150),
            "tank":       (260,    65),
            "elite":      (1500,   85),
            "shooter":    (80,     90),
            "boss":       (boss_max_hp, 95),
            "slime":      (130,   110),
            "minotauro":  (200,   130),
            "bat":        (28,    145),
            "orc":        (300,    75),
            "mini_boss":  (6000,   85),
            "goblin":     (80,    160),
            "beholder":   (200,    85),
            "rat":        (150,   135),
            "agis":       (10000,  45),
            "slime_fire":   (280,   125),
            "slime_red":    (220,   110),
            "slime_yellow": (160,   145),
            "ghost":        (200,   120),
        }
        base_hp, base_spd = stats.get(kind, (2, 100))

        if kind == "boss":
            self.hp = base_hp * diff_mults["hp_mult"] * time_scale * boss_tier
        elif kind == "mini_boss":
            self.hp = base_hp * diff_mults["hp_mult"] * (1.0 + time_scale * 0.3)
        elif kind == "agis":
            self.hp = base_hp * diff_mults["hp_mult"] * (1.0 + time_scale * 0.25)
        else:
            self.hp = base_hp * diff_mults["hp_mult"] * time_scale

        if kind == "agis":
            # Agis é lento — speed quase não escala com o tempo
            self.speed = base_spd * diff_mults["spd_mult"] * min(1.1, time_scale)
        else:
            self.speed = base_spd * diff_mults["spd_mult"] * min(1.5, time_scale)
        self.max_hp = self.hp

        # Dano corpo-a-corpo por tipo (escala com dificuldade)
        _dmg_m = diff_mults.get("dmg_mult", 1.0)
        _base_melee = {
            "runner":     8.0,
            "tank":       18.0,
            "elite":      30.0,
            "slime":      10.0,
            "minotauro":  22.0,
            "bat":         6.0,
            "orc":        20.0,
            "goblin":      8.0,
            "beholder":   14.0,
            "rat":         6.0,
            "mini_boss":  30.0,
            "slime_fire":   18.0,
            "slime_red":    16.0,
            "slime_yellow": 14.0,
            "ghost":        15.0,
        }
        self.melee_dmg = _base_melee.get(kind, 8.0) * _dmg_m
        if kind == "mini_boss":
            self.melee_range = 155

        # Dano de projétil para shooter / boss (escala com dificuldade)
        self.proj_dmg = 1.0
        if kind == "shooter":
            self.proj_dmg = 15.0 * _dmg_m
        elif kind == "boss":
            self.proj_dmg = 10.0 * _dmg_m

        # Agis — ataque a distância + magia em área (projéteis criados em jogo_final.py)
        if kind == "agis":
            self.agis_shot_timer   = 0.0
            self.agis_shot_dir     = pygame.Vector2(1, 0)
            self.pending_agis_shot = False
            self.agis_area_timer   = 3.0   # começa com 3 s para não disparar na hora
            self.pending_agis_area = False

    # ------------------------------------------------------------------
    # Inicialização interna
    # ------------------------------------------------------------------

    def _resolve_shot_cooldown(self, kind):
        return {
            "boss":     3.0,
        }.get(kind, 3.0)

    def _init_legacy_enemy(self, kind, loader, boss_max_hp):
        configs = {
            "boss":    (((50, 0, 0), (0, 0, 0)),    (250, 250), 4),
            "shooter": (((200,50,200),(120,0,120)),  (110, 95), 11),
            "tank":    (((50,200,50),(0,120,0)),     (100, 90), 11),
            "elite":   (((255,200,0),(150,100,0)),   (100, 90), 11),
            "slime":   (((20,20,20),(50,100,50)),    (90,  80), 10),
            "minotauro": (((100,100,150),(50,50,100)), (100,100),  4),
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
        sheet_cols = cfg.get("sheet_cols", cfg.get("walk_frames", 1))
        self.gold_drops = cfg.get("gold_drops", 0)
        self._atk_range = cfg.get("attack_range", 0)

        if dir_rows:
            self.use_directional = True
            fpd = cfg["walk_frames"]
            for dir_name, row_idx in dir_rows.items():
                row_start = row_idx * sheet_cols
                indices = [row_start + i for i in range(fpd)]
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

        # Modo overlay: efeito de ataque desenhado sobre o walk (não substitui)
        self._atk_overlay = cfg.get("atk_overlay", False)

        atk_sheet = cfg.get("atk_sheet")
        if atk_sheet:
            atk_fw   = cfg.get("atk_frame_w", fw)
            atk_fh   = cfg.get("atk_frame_h", fh)
            atk_size = cfg.get("atk_size", size)   # tamanho de saída dos frames de ataque
            if dir_rows and cfg.get("atk_frames", 0) > 0:
                fpd = cfg["atk_frames"]
                atk_sheet_cols = cfg.get("atk_sheet_cols", sheet_cols)
                for dir_name, row_idx in dir_rows.items():
                    row_start = row_idx * atk_sheet_cols
                    indices   = [row_start + i for i in range(fpd)]
                    atk_frames = loader.load_spritesheet(atk_sheet, atk_fw, atk_fh,
                                                         len(indices), atk_size, frame_indices=indices)
                    if atk_frames:
                        self._dir_atk_frames[dir_name] = atk_frames
            elif cfg.get("atk_frames", 0) > 0:
                atk_frames = loader.load_spritesheet(atk_sheet, atk_fw, atk_fh,
                                                     cfg["atk_frames"], atk_size)
                if atk_frames:
                    self._atk_frames_flat = atk_frames
                    self._atk_frames_flat_flipped = [
                        pygame.transform.flip(f, True, False) for f in atk_frames]

        # Animação de morte (morte_sheet) — direcional quando dir_rows está presente
        morte_sheet = cfg.get("morte_sheet")
        if morte_sheet and dir_rows and cfg.get("morte_frames", 0) > 0:
            morte_fpd = cfg["morte_frames"]
            morte_fw  = cfg.get("morte_frame_w", fw)
            morte_fh  = cfg.get("morte_frame_h", fh)
            morte_size = cfg.get("morte_size", size)
            for dir_name, row_idx in dir_rows.items():
                row_start = row_idx * morte_fpd
                indices   = [row_start + i for i in range(morte_fpd)]
                m_frames  = loader.load_spritesheet(morte_sheet, morte_fw, morte_fh,
                                                    len(indices), morte_size, frame_indices=indices)
                if m_frames:
                    self._morte_frames[dir_name] = m_frames

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

    def get_morte_frames(self):
        """Retorna os frames de morte para a direção atual, ou None se indisponível."""
        if not self._morte_frames:
            return None
        return (self._morte_frames.get(self.facing_dir)
                or self._morte_frames.get("down")
                or next(iter(self._morte_frames.values()), None))

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
            is_ranged  = self.kind in ["shooter"]
            stop_dist  = 450

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

                # GOBLIN — zigzag rápido e agressivo, perseguição frenética
                elif self.kind == "goblin":
                    self._bat_phase += dt * 4.5
                    perp = pygame.Vector2(-move_dir.y, move_dir.x)
                    amplitude = 0.55 if dist > 150 else 0.22
                    move_dir  = move_dir + perp * math.sin(self._bat_phase) * amplitude
                    if move_dir.length_squared() > 0:
                        move_dir = move_dir.normalize()

                # BEHOLDER — flutuação suave e oscilação lenta ao redor do alvo
                elif self.kind == "beholder":
                    self._bat_phase += dt * 1.8
                    perp = pygame.Vector2(-move_dir.y, move_dir.x)
                    amplitude = 0.40 if dist > 180 else 0.15
                    move_dir  = move_dir + perp * math.sin(self._bat_phase) * amplitude
                    if move_dir.length_squared() > 0:
                        move_dir = move_dir.normalize()

                # RAT — perseguição direta com pequeno zigzag nervoso
                elif self.kind == "rat":
                    self._bat_phase += dt * 3.0
                    perp = pygame.Vector2(-move_dir.y, move_dir.x)
                    amplitude = 0.30 if dist > 200 else 0.12
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

                # SLIME FIRE — arrancada de fogo: periodicamente triplica velocidade
                elif self.kind == "slime_fire":
                    self._charge_timer -= dt
                    if self._charge_timer <= 0 and not self._charging:
                        self._charge_timer    = random.uniform(2.5, 4.5)
                        self._charging        = True
                        self._charge_active_t = random.uniform(0.35, 0.55)
                    if self._charging:
                        self._charge_active_t -= dt
                        if self._charge_active_t <= 0:
                            self._charging = False
                        else:
                            move_speed *= 2.8
                            if not self._atk_active:
                                self._trigger_atk_anim()

                # SLIME YELLOW — arrancada rápida e breve
                elif self.kind == "slime_yellow":
                    self._charge_timer -= dt
                    if self._charge_timer <= 0 and not self._charging:
                        self._charge_timer    = random.uniform(1.8, 3.2)
                        self._charging        = True
                        self._charge_active_t = random.uniform(0.25, 0.40)
                    if self._charging:
                        self._charge_active_t -= dt
                        if self._charge_active_t <= 0:
                            self._charging = False
                        else:
                            move_speed *= 3.0
                            if not self._atk_active:
                                self._trigger_atk_anim()

                # GHOST — flutuação senoidal lenta com arrancada fantasmal periódica
                elif self.kind == "ghost":
                    self._bat_phase += dt * 2.2
                    perp = pygame.Vector2(-move_dir.y, move_dir.x)
                    amplitude = 0.50 if dist > 160 else 0.20
                    move_dir  = move_dir + perp * math.sin(self._bat_phase) * amplitude
                    if move_dir.length_squared() > 0:
                        move_dir = move_dir.normalize()
                    self._charge_timer -= dt
                    if self._charge_timer <= 0 and not self._charging:
                        self._charge_timer    = random.uniform(3.0, 5.0)
                        self._charging        = True
                        self._charge_active_t = random.uniform(0.30, 0.50)
                    if self._charging:
                        self._charge_active_t -= dt
                        if self._charge_active_t <= 0:
                            self._charging = False
                        else:
                            move_speed *= 2.5
                            if not self._atk_active:
                                self._trigger_atk_anim()

                # AGIS — avanço lento com arrancada ocasional
                elif self.kind == "agis":
                    self._charge_timer -= dt
                    if self._charge_timer <= 0 and not self._charging:
                        self._charge_timer    = random.uniform(5.0, 8.0)
                        self._charging        = True
                        self._charge_active_t = 0.6
                    if self._charging:
                        self._charge_active_t -= dt
                        if self._charge_active_t <= 0:
                            self._charging = False
                        else:
                            move_speed *= 2.5
                            if not self._atk_active:
                                self._trigger_atk_anim()

                # Pathfinding para inimigos menores
                can_pathfind = (
                    obstacle_grid_index is not None
                    and self.kind not in ["boss", "mini_boss", "shooter"]
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
                        self.path_recalc_timer      = 0.28
                        if pd is not None:
                            move_dir = pygame.Vector2(pd[0], pd[1])

                move = move_dir * move_speed * dt

            if move.length_squared() > 0:
                self.pos += move
                if self.kind not in ["boss", "mini_boss"]:
                    if obstacle_grid_index is not None:
                        if obstacle_grid_index.point_collides(self.pos):
                            self.pos -= move
                    else:
                        for obs in obstacles:
                            if obs.hitbox.collidepoint(self.pos):
                                self.pos -= move

            anim_spd = 0.15 if self.kind in ["boss", "mini_boss", "agis"] else 0.10
            self.anim_timer += dt
            if self.anim_timer > anim_spd:
                self.anim_timer = 0
                walk_len = len(
                    self._dir_walk_frames.get(self.facing_dir, self.anim_frames)
                    if self.use_directional else self.anim_frames
                )
                self.frame_idx = (self.frame_idx + 1) % walk_len

        # ================================================================
        # Disparo para shooter / boss   (mini_boss e minotauro são MELEE)
        # ================================================================
        if self.kind in ["shooter", "boss"]:
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
                            enemy_projectile_cls(self.pos, vel, self.proj_dmg, loader, shooter_proj_image))
                else:
                    rl  = 500 if self.kind == "shooter" else 450
                    sp  = 300.0 if self.kind == "shooter" else 150.0
                    if 0 < dist < rl:
                        vel = (direction / dist) * sp
                        enemy_projectiles.add(
                            enemy_projectile_cls(self.pos, vel, self.proj_dmg, loader, shooter_proj_image))

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

        # ================================================================
        # Agis — disparo de projétil a longa distância
        # ================================================================
        if self.kind == "agis":
            # Ataque básico — projétil direto ao jogador
            self.agis_shot_timer += dt
            shot_cd = 2.2 if self.hp >= self.max_hp * 0.5 else 1.4
            if self.agis_shot_timer >= shot_cd and 0 < dist <= 600:
                self.agis_shot_timer   = 0.0
                self.agis_shot_dir     = direction / dist
                self.pending_agis_shot = True

            # Magia em área — orbes em todas as direções a cada 5 s
            self.agis_area_timer += dt
            if self.agis_area_timer >= 5.0:
                self.agis_area_timer   = 0.0
                self.pending_agis_area = True

        # BAT / GOBLIN / BEHOLDER / RAT / SLIME_FIRE / SLIME_RED / SLIME_YELLOW — dispara animação de ataque por proximidade
        if self.kind in ("bat", "goblin", "beholder", "rat", "slime_fire", "slime_red", "slime_yellow") and self._atk_range > 0 and not self._atk_active:
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
        if self._atk_active and self._atk_overlay:
            # Modo overlay: personagem sempre visível; efeito de ataque desenhado por cima
            walk_frame = (self._get_white_frame() if self.flash_timer > 0
                          else self._get_walk_frame())
            af = self._get_atk_frame()
            if af:
                w_size = walk_frame.get_size()
                composite = pygame.Surface(w_size, pygame.SRCALPHA)
                composite.blit(walk_frame, (0, 0))
                # Centraliza o efeito de ataque sobre o personagem
                ox = (w_size[0] - af.get_width())  // 2
                oy = (w_size[1] - af.get_height()) // 2
                composite.blit(af, (ox, oy))
                self.image = composite
            else:
                self.image = walk_frame
        elif self._atk_active:
            af = self._get_atk_frame()
            self.image = af if af else self._get_walk_frame()
        elif self.flash_timer > 0:
            self.image = self._get_white_frame()
        else:
            self.image = self._get_walk_frame()

        # Aura de elite — Surface cacheada por tamanho para não alocar a cada frame
        if self.is_elite:
            sz = self.image.get_size()
            if getattr(self, "_elite_aura_size", None) != sz:
                self._elite_aura_size = sz
                self._elite_aura = pygame.Surface(sz, pygame.SRCALPHA)
                pygame.draw.ellipse(self._elite_aura, (255, 215, 0, 100), self._elite_aura.get_rect(), 3)
            self.image = self.image.copy()
            self.image.blit(self._elite_aura, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)

        self.rect.center = self.pos + cam
