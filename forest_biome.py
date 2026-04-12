"""
forest_biome.py — Sistema de chão e decorações animadas para o bioma Forest.

Responsabilidades:
  - build_forest_ground(loader) → Surface 256×256 composta por tiles 32×32
  - ForestDecoManager           → Decorações animadas (bandeiras e fogueiras) no mundo

ARQUITETURA DE DECORAÇÕES:
  Cada arquivo numerado nas pastas 1 Flag / 2 Campfire é um TIPO de objeto
  independente com sua própria grade de spawn determinística.
  Cada arquivo contém um strip horizontal de frames que formam a animação
  daquele objeto específico (ex: flag_1 oscila com 3 frames do arquivo 1.png).
"""

import os
import math
import random

import pygame

TILE_SIZE      = 32    # tamanho de cada tile nativo (px)
GROUND_SIZE    = 256   # tamanho da superfície de chão repetida (px)
TILES_PER_SIDE = GROUND_SIZE // TILE_SIZE  # 8

TILE_WEIGHTS = [
    (0, 8), (1, 8), (2, 6), (3, 6), (4, 5), (5, 5), (6, 4), (7, 4),
    (8, 6), (9, 6), (10, 4), (11, 4), (12, 3), (13, 3), (14, 2), (15, 2),
    (16, 3), (17, 3), (18, 2), (19, 2), (20, 2), (21, 1), (22, 1), (23, 1),
    (24, 2), (25, 2), (26, 2), (27, 1), (28, 1), (29, 1), (30, 1), (31, 1),
]

ACCENT_TILES = [32, 33, 40, 41, 48, 49]


def build_forest_ground(loader):
    """
    Constrói uma Surface 256×256 composta por tiles 32×32 do FieldsTileset.
    Usa semente fixa para garantir consistência entre sessões.
    """
    sheet_frames = loader.load_spritesheet(
        "ui/tiles/FieldsTileset",
        TILE_SIZE, TILE_SIZE,
        64,
        None,
    )

    if not sheet_frames:
        surf = pygame.Surface((GROUND_SIZE, GROUND_SIZE))
        surf.fill((80, 110, 50))
        return surf

    ground = pygame.Surface((GROUND_SIZE, GROUND_SIZE))
    rng    = random.Random(1337)

    indices, weights = zip(*TILE_WEIGHTS)
    total_weight = sum(weights)

    for row in range(TILES_PER_SIDE):
        for col in range(TILES_PER_SIDE):
            r = rng.random() * total_weight
            acc = 0
            tile_idx = indices[0]
            for idx, w in zip(indices, weights):
                acc += w
                if r < acc:
                    tile_idx = idx
                    break

            if rng.random() < 0.08:
                tile_idx = rng.choice(ACCENT_TILES)

            if 0 <= tile_idx < len(sheet_frames):
                ground.blit(sheet_frames[tile_idx], (col * TILE_SIZE, row * TILE_SIZE))

    return ground


# ---------------------------------------------------------------------------
# Configuração de tipos de decoração da floresta
# ---------------------------------------------------------------------------
# Cada entrada define um tipo de objeto independente:
#   kind      → identificador único (usado como chave no grid)
#   grid      → espaçamento em px entre células da grade
#   prob      → probabilidade de spawn numa célula (0–1)
#   spd       → segundos por frame de animação
#   size      → (w, h) de exibição em px (maior = mais visível no mundo)
#   rel       → caminho relativo ao folder de assets animados
#   fw        → largura de cada frame no strip horizontal (px)

_FOREST_DECO_CFGS = [
    # --- Bandeiras (5 estilos independentes) ---
    dict(kind="flag_1", grid=900,  prob=0.30, spd=0.18, size=(128, 128), rel=os.path.join("1 Flag", "1.png"), fw=64),
    dict(kind="flag_2", grid=950,  prob=0.30, spd=0.18, size=(128, 128), rel=os.path.join("1 Flag", "2.png"), fw=64),
    dict(kind="flag_3", grid=1000, prob=0.28, spd=0.20, size=(128, 128), rel=os.path.join("1 Flag", "3.png"), fw=64),
    dict(kind="flag_4", grid=870,  prob=0.28, spd=0.16, size=(128, 128), rel=os.path.join("1 Flag", "4.png"), fw=64),
    dict(kind="flag_5", grid=920,  prob=0.25, spd=0.22, size=(128, 128), rel=os.path.join("1 Flag", "5.png"), fw=64),
    # --- Fogueiras (2 estilos independentes) ---
    dict(kind="fire_1", grid=720,  prob=0.38, spd=0.14, size=(128, 128), rel=os.path.join("2 Campfire", "1.png"), fw=64),
    dict(kind="fire_2", grid=760,  prob=0.38, spd=0.10, size=(128,  96), rel=os.path.join("2 Campfire", "2.png"), fw=64),
]


# ---------------------------------------------------------------------------
# Decoração animada individual
# ---------------------------------------------------------------------------

class _AnimDeco:
    """Decoração animada em posição fixa no mundo."""

    def __init__(self, world_pos, frames, anim_speed, anchor="midbottom"):
        self.world_pos  = pygame.Vector2(world_pos)
        self.frames     = frames
        self.anim_speed = anim_speed
        self.anchor     = anchor
        self.frame_idx  = 0
        self.timer      = 0.0
        self.image      = frames[0]
        self.rect       = self.image.get_rect()

    def update(self, dt, cam):
        self.timer += dt
        if self.timer >= self.anim_speed:
            self.timer     = 0.0
            self.frame_idx = (self.frame_idx + 1) % len(self.frames)
            self.image     = self.frames[self.frame_idx]

        screen_pos = self.world_pos + cam
        setattr(self.rect, self.anchor,
                (int(screen_pos.x), int(screen_pos.y)))

    def on_screen(self, sw, sh):
        margin = max(self.image.get_width(), self.image.get_height()) + 32
        return (
            -margin < self.rect.centerx < sw + margin
            and -margin < self.rect.centery < sh + margin
        )


# ---------------------------------------------------------------------------
# Funções auxiliares de carregamento
# ---------------------------------------------------------------------------

def _load_strip_frames(path, frame_w, display_size):
    """
    Carrega todos os frames de um strip horizontal e escala para display_size.
    Retorna lista de Surfaces ou [] se arquivo não encontrado.
    """
    if not os.path.exists(path):
        print(f"[ForestBiome] Arquivo não encontrado: {path}")
        return []
    frames = []
    try:
        raw = pygame.image.load(path)
        has_alpha = raw.get_bitsize() == 32 and raw.get_masks()[3] != 0
        raw = raw.convert_alpha() if has_alpha else raw.convert()

        total_w = raw.get_width()
        fh      = raw.get_height()
        n       = max(1, total_w // frame_w)

        for i in range(n):
            sub    = raw.subsurface((i * frame_w, 0, frame_w, fh)).copy()
            scaled = pygame.transform.scale(sub, display_size)
            frames.append(scaled)
    except Exception as e:
        print(f"[ForestBiome] Erro ao carregar {path}: {e}")
    return frames


# ---------------------------------------------------------------------------
# Gerenciador de decorações da floresta
# ---------------------------------------------------------------------------

class ForestDecoManager:
    """
    Gerencia decorações animadas espalhadas pelo mundo infinito da floresta.

    Cada tipo de decoração (flag_1 … flag_5, fire_1, fire_2) tem sua própria
    grade determinística. Células visíveis são instanciadas dinamicamente;
    células fora de tela são descartadas.
    """

    def __init__(self, asset_dir):
        self._asset_dir = asset_dir
        # Mapeia kind → lista de frames já escalados
        self._frames: dict[str, list] = {}
        # Instâncias ativas: (gx, gy, kind) → _AnimDeco
        self._active: dict[tuple, _AnimDeco] = {}

    def load_frames(self):
        """Carrega frames de cada tipo. Deve ser chamado após pygame.init()."""
        anim_base = os.path.join(self._asset_dir, "ui", "tiles", "animated")
        for cfg in _FOREST_DECO_CFGS:
            path   = os.path.join(anim_base, cfg["rel"])
            frames = _load_strip_frames(path, cfg["fw"], cfg["size"])
            self._frames[cfg["kind"]] = frames
            status = f"{len(frames)} frames" if frames else "FALHOU"
            print(f"[ForestBiome] {cfg['kind']}: {status}")

    # ------------------------------------------------------------------ #

    def _cell_rng(self, gx, gy, kind):
        return random.Random((gx * 73856093) ^ (gy * 19349663) ^ hash(kind))

    def _should_place(self, gx, gy, kind, prob):
        return self._cell_rng(gx, gy, kind).random() < prob

    def _cell_world_pos(self, gx, gy, grid, kind):
        rng  = self._cell_rng(gx, gy, kind)
        jit  = grid // 3
        base = pygame.Vector2(gx * grid, gy * grid)
        return base + pygame.Vector2(rng.randint(-jit, jit), rng.randint(-jit, jit))

    # ------------------------------------------------------------------ #

    def update(self, dt, cam, screen_w, screen_h, player_pos):
        """Atualiza ciclo de vida das decorações."""
        active_keys = set()

        for cfg in _FOREST_DECO_CFGS:
            kind   = cfg["kind"]
            frames = self._frames.get(kind)
            if not frames:
                continue

            grid   = cfg["grid"]
            prob   = cfg["prob"]
            spd    = cfg["spd"]
            margin = max(screen_w, screen_h) // 2 + grid

            gx_min = int((player_pos.x - margin) // grid) - 1
            gx_max = int((player_pos.x + margin) // grid) + 1
            gy_min = int((player_pos.y - margin) // grid) - 1
            gy_max = int((player_pos.y + margin) // grid) + 1

            for gx in range(gx_min, gx_max + 1):
                for gy in range(gy_min, gy_max + 1):
                    if not self._should_place(gx, gy, kind, prob):
                        continue
                    key = (gx, gy, kind)
                    active_keys.add(key)
                    if key not in self._active:
                        wp = self._cell_world_pos(gx, gy, grid, kind)
                        self._active[key] = _AnimDeco(wp, frames, spd)

        # Remove decos fora de vista
        for key in list(self._active.keys()):
            if key not in active_keys:
                del self._active[key]

        # Atualiza posição e frame das ativas
        for deco in self._active.values():
            deco.update(dt, cam)

    def draw(self, screen, screen_w, screen_h):
        """Desenha decorações visíveis ordenadas por Y (pseudo-profundidade)."""
        visible = sorted(
            (d for d in self._active.values() if d.on_screen(screen_w, screen_h)),
            key=lambda d: d.rect.bottom,
        )
        for deco in visible:
            screen.blit(deco.image, deco.rect)
