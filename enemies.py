import math
import random

import pygame

from ecs_components import (
    Position, Health, Velocity, EnemyTag,
    AIState, Combat, AnimationState,
)

# Vetor zero reutilizável — evita alocação por inimigo por frame no branch ranged
_VEC2_ZERO = pygame.Vector2(0, 0)


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
    """Sprite de inimigo — armazena dados de sprite e referências a componentes ECS.

    Todo o comportamento (movimento, IA, combate, animação) é processado em batch
    pelos sistemas ECS registrados em ecs_world (EnemyAISystem, EnemyCombatSystem,
    EnemyAnimationSystem, EnemyRenderSystem). O método update() é um stub vazio.
    """

    # Referência ao mundo ECS ativo — definida em jogo_final.py no início de cada run.
    _ecs_world = None

    # ── Propriedades para acesso externo retrocompatível ─────────────────────
    # Scalars: delegam ao componente correto.

    @property
    def hp(self) -> float:
        return self._health_comp.hp

    @hp.setter
    def hp(self, v: float) -> None:
        self._health_comp.hp = v

    @property
    def max_hp(self) -> float:
        return self._health_comp.max_hp

    @max_hp.setter
    def max_hp(self, v: float) -> None:
        self._health_comp.max_hp = v

    @property
    def speed(self) -> float:
        return self._vel_comp.speed

    @speed.setter
    def speed(self, v: float) -> None:
        self._vel_comp.speed = v

    @property
    def frozen_timer(self) -> float:
        return self._ai_comp.frozen_timer

    @frozen_timer.setter
    def frozen_timer(self, v: float) -> None:
        self._ai_comp.frozen_timer = v

    @property
    def flash_timer(self) -> float:
        return self._ai_comp.flash_timer

    @flash_timer.setter
    def flash_timer(self, v: float) -> None:
        self._ai_comp.flash_timer = v

    # AnimationState scalars — accessed by helper methods and indirectly by systems.

    @property
    def facing_right(self) -> bool:
        return self._anim_comp.facing_right

    @facing_right.setter
    def facing_right(self, v: bool) -> None:
        self._anim_comp.facing_right = v

    @property
    def facing_dir(self) -> str:
        return self._anim_comp.facing_dir

    @facing_dir.setter
    def facing_dir(self, v: str) -> None:
        self._anim_comp.facing_dir = v

    @property
    def frame_idx(self) -> int:
        return self._anim_comp.frame_idx

    @frame_idx.setter
    def frame_idx(self, v: int) -> None:
        self._anim_comp.frame_idx = v

    @property
    def anim_timer(self) -> float:
        return self._anim_comp.anim_timer

    @anim_timer.setter
    def anim_timer(self, v: float) -> None:
        self._anim_comp.anim_timer = v

    # Combat flags — written by ECS systems, read/reset by jogo_final.py.

    @property
    def pending_melee_hit(self) -> bool:
        return self._combat_comp.pending_melee_hit

    @pending_melee_hit.setter
    def pending_melee_hit(self, v: bool) -> None:
        self._combat_comp.pending_melee_hit = v

    @property
    def melee_dmg(self) -> float:
        return self._combat_comp.melee_dmg

    @property
    def pending_agis_shot(self) -> bool:
        return self._combat_comp.pending_agis_shot

    @pending_agis_shot.setter
    def pending_agis_shot(self, v: bool) -> None:
        self._combat_comp.pending_agis_shot = v

    @property
    def pending_agis_area(self) -> bool:
        return self._combat_comp.pending_agis_area

    @pending_agis_area.setter
    def pending_agis_area(self, v: bool) -> None:
        self._combat_comp.pending_agis_area = v

    # ── Constructor ───────────────────────────────────────────────────────────

    def __init__(self, kind, pos, loader, diff_mults, screen_size_getter,
                 time_scale=1.0, boss_tier=1, is_elite=False, boss_max_hp=500):
        super().__init__()

        # ── Cria stubs de componentes ANTES de qualquer property setter ──────
        self._health_comp = Health()
        self._vel_comp    = Velocity()
        self._ai_comp     = AIState()
        self._combat_comp = Combat()
        self._anim_comp   = AnimationState()
        self._ecs_id      = -1

        # ── Identidade (atributos diretos — imutáveis após construção) ───────
        self.kind               = kind
        self.is_elite           = is_elite
        self.screen_size_getter = screen_size_getter

        # Vector2 compartilhados: self.X e componente.X são o MESMO objeto.
        self.knockback     = self._ai_comp.knockback         # Vector2(0,0)
        self.agis_shot_dir = self._combat_comp.agis_shot_dir # Vector2(1,0)

        # ── Dados de sprite direcional ────────────────────────────────────────
        self.use_directional    = False
        self._dir_walk_frames   = {}
        self._dir_white_frames  = {}
        self._dir_frozen_frames = {}
        self._dir_atk_frames    = {}
        self._morte_frames      = {}
        self._atk_frames_flat         = []
        self._atk_frames_flat_flipped = []
        self._atk_range   = 0
        self._atk_overlay = False   # True = overlay; False = substitui walk

        # ── Drop metadata ─────────────────────────────────────────────────────
        self.gold_drops = 0

        # ── Ajuste do charge_timer por tipo (AIState default = 3.5–5.0 s) ────
        if kind == "slime_fire":
            self._ai_comp.charge_timer = random.uniform(2.5, 4.5)
        elif kind == "slime_yellow":
            self._ai_comp.charge_timer = random.uniform(1.8, 3.2)
        elif kind == "ghost":
            self._ai_comp.charge_timer = random.uniform(3.0, 5.0)

        # ── Carrega sprites ───────────────────────────────────────────────────
        cfg = SPRITESHEET_CONFIGS.get(kind)
        if cfg:
            self._init_spritesheet_enemy(kind, loader, cfg)
        else:
            self._init_legacy_enemy(kind, loader, boss_max_hp)

        self._combat_comp.shot_cooldown = self._resolve_shot_cooldown(kind)

        self.image = self.anim_frames[0]
        self.rect  = self.image.get_rect()

        # Posição: Position.vec é o MESMO Vector2 que self.pos — sem cópia.
        _spawn        = pos if isinstance(pos, pygame.Vector2) else pygame.Vector2(pos)
        self._pos_comp = Position(vec=pygame.Vector2(_spawn.x, _spawn.y))
        self.pos       = self._pos_comp.vec

        # ── Stats base ────────────────────────────────────────────────────────
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
            _hp = base_hp * diff_mults["hp_mult"] * time_scale * boss_tier
        elif kind == "mini_boss":
            _hp = base_hp * diff_mults["hp_mult"] * (1.0 + time_scale * 0.3)
        elif kind == "agis":
            _hp = base_hp * diff_mults["hp_mult"] * (1.0 + time_scale * 0.25)
        else:
            _hp = base_hp * diff_mults["hp_mult"] * time_scale

        if kind == "agis":
            _spd = base_spd * diff_mults["spd_mult"] * min(1.1, time_scale)
        else:
            _spd = base_spd * diff_mults["spd_mult"] * min(1.5, time_scale)

        self._health_comp.hp     = _hp
        self._health_comp.max_hp = _hp
        self._vel_comp.speed     = _spd

        # ── Stats de combate ──────────────────────────────────────────────────
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
        self._combat_comp.melee_dmg = _base_melee.get(kind, 8.0) * _dmg_m
        if kind == "mini_boss":
            self._combat_comp.melee_range = 155

        self._combat_comp.proj_dmg = 1.0
        if kind == "shooter":
            self._combat_comp.proj_dmg = 15.0 * _dmg_m
        elif kind == "boss":
            self._combat_comp.proj_dmg = 10.0 * _dmg_m

        if kind == "agis":
            self._combat_comp.agis_area_timer = 3.0  # não dispara imediatamente

        # ── Registra no mundo ECS ─────────────────────────────────────────────
        if Enemy._ecs_world is not None:
            Enemy._ecs_world.register_enemy(self)

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
                return frames[self._anim_comp.atk_frame_idx % len(frames)]
        if self._atk_frames_flat:
            pool = self._atk_frames_flat if self.facing_right else self._atk_frames_flat_flipped
            return pool[self._anim_comp.atk_frame_idx % len(pool)]
        return None

    def _count_atk_frames(self):
        if self._dir_atk_frames:
            frames = self._dir_atk_frames.get(self.facing_dir, [])
            return len(frames) if frames else 1
        return len(self._atk_frames_flat) if self._atk_frames_flat else 1

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
    # Update principal — lógica movida para ECS systems
    # ------------------------------------------------------------------

    def update(self, dt=None, *args, **kwargs):
        pass

    def kill(self):
        if Enemy._ecs_world is not None and self._ecs_id >= 0:
            Enemy._ecs_world.delete_entity(self._ecs_id)
        super().kill()
