"""
dungeon_biome.py — Decorações do bioma Dungeon.

Objetos:
  pentagrama  — efeito de chão animado (pentagrama1 ↔ pentagrama2), sem colisão
  bds         — obstáculo de chão animado (BDS1 ↔ BDS2), COM colisão
  dinosaur    — fóssil de chão estático, sem colisão

Uso:
    mgr = DungeonDecoManager(asset_dir)
    mgr.load_frames()

    # a cada frame:
    mgr.update(dt, cam, screen_w, screen_h, player_pos)
    mgr.draw_floor(screen, screen_w, screen_h)   # antes dos sprites
    mgr.push_player(player)                       # empurra jogador de BDS
"""

import os
import random

import pygame


# ---------------------------------------------------------------------------
# Configuração dos tipos de decoração
# ---------------------------------------------------------------------------
# kind         → identificador único
# grid         → espaçamento em px entre células da grade
# prob         → probabilidade de spawn por célula
# spd          → segundos por frame de animação (0 = estático)
# display_size → (w, h) de exibição
# files        → lista de arquivos (1 arquivo = estático, 2+ = animado ciclicamente)
# collide      → True se bloqueia movimento do jogador

_DUNGEON_DECO_CFGS = [
    dict(
        kind    = "pentagrama",
        grid    = 750,
        prob    = 0.45,
        spd     = 0.55,
        size    = (160, 160),
        files   = ["pentagrama1.png", "pentagrama2.png"],
        collide = False,
    ),
    dict(
        kind    = "bds",
        grid    = 1100,
        prob    = 0.22,
        spd     = 0.80,
        size    = (140, 140),
        files   = ["BDS1.png", "BDS2.png"],
        collide = True,
    ),
    dict(
        kind    = "dinosaur",
        grid    = 1400,
        prob    = 0.20,
        spd     = 0.0,   # estático
        size    = (220, 220),
        files   = ["dinosaur.png"],
        collide = False,
    ),
]


# ---------------------------------------------------------------------------
# Classe de decoração individual
# ---------------------------------------------------------------------------

class _DungeonDeco:
    """Decoração animada (ou estática) em posição fixa no mundo dungeon."""

    def __init__(self, world_pos, frames, anim_speed, collide):
        self.world_pos  = pygame.Vector2(world_pos)
        self.frames     = frames
        self.anim_speed = anim_speed
        self.collide    = collide
        self.frame_idx  = 0
        self.timer      = 0.0
        self.image      = frames[0]
        self.rect       = self.image.get_rect()
        self.world_rect = pygame.Rect(0, 0,
                                      self.image.get_width() // 2,
                                      self.image.get_height() // 2)

    def update(self, dt, cam):
        # Animação
        if self.anim_speed > 0 and len(self.frames) > 1:
            self.timer += dt
            if self.timer >= self.anim_speed:
                self.timer     = 0.0
                self.frame_idx = (self.frame_idx + 1) % len(self.frames)
                self.image     = self.frames[self.frame_idx]

        # Posição na tela
        screen_pos = self.world_pos + cam
        self.rect.center = (int(screen_pos.x), int(screen_pos.y))

        # Rect de colisão no mundo (metade do tamanho visual, centralizado)
        hw = self.image.get_width()  // 4
        hh = self.image.get_height() // 4
        self.world_rect.width  = hw * 2
        self.world_rect.height = hh * 2
        self.world_rect.center = (int(self.world_pos.x), int(self.world_pos.y))

    def on_screen(self, sw, sh):
        margin = max(self.image.get_width(), self.image.get_height()) + 32
        return (
            -margin < self.rect.centerx < sw + margin
            and -margin < self.rect.centery < sh + margin
        )


# ---------------------------------------------------------------------------
# Funções auxiliares
# ---------------------------------------------------------------------------

def _load_image(path, display_size):
    """Carrega uma imagem única e escala para display_size."""
    if not os.path.exists(path):
        print(f"[DungeonBiome] Arquivo não encontrado: {path}")
        return None
    try:
        raw = pygame.image.load(path)
        has_alpha = raw.get_bitsize() == 32 and raw.get_masks()[3] != 0
        raw = raw.convert_alpha() if has_alpha else raw.convert()
        return pygame.transform.scale(raw, display_size)
    except Exception as e:
        print(f"[DungeonBiome] Erro ao carregar {path}: {e}")
        return None


# ---------------------------------------------------------------------------
# Gerenciador principal
# ---------------------------------------------------------------------------

class DungeonDecoManager:
    """
    Gerencia decorações do bioma Dungeon em mundo infinito.

    Cada tipo de deco tem grade própria. Células visíveis são instanciadas
    dinamicamente; células fora de vista são descartadas.
    BDS expõe world_rect para colisão com o jogador.
    """

    def __init__(self, asset_dir):
        self._asset_dir = asset_dir
        self._frames: dict[str, list]          = {}
        self._active: dict[tuple, _DungeonDeco] = {}
        self._cfg_map: dict[str, dict]          = {}

    def load_frames(self):
        """Carrega imagens de cada tipo. Deve ser chamado após pygame.init()."""
        chao_dir = os.path.join(self._asset_dir, "ui", "chao")
        for cfg in _DUNGEON_DECO_CFGS:
            kind   = cfg["kind"]
            frames = []
            for fname in cfg["files"]:
                path = os.path.join(chao_dir, fname)
                img  = _load_image(path, cfg["size"])
                if img:
                    frames.append(img)

            self._frames[kind]  = frames
            self._cfg_map[kind] = cfg
            status = f"{len(frames)} frames" if frames else "FALHOU"
            print(f"[DungeonBiome] {kind}: {status}")

    # ------------------------------------------------------------------ #

    def _cell_rng(self, gx, gy, kind):
        return random.Random((gx * 83492791) ^ (gy * 29400467) ^ hash(kind))

    def _should_place(self, gx, gy, kind, prob):
        return self._cell_rng(gx, gy, kind).random() < prob

    def _cell_world_pos(self, gx, gy, grid, kind):
        rng  = self._cell_rng(gx, gy, kind)
        jit  = grid // 3
        base = pygame.Vector2(gx * grid, gy * grid)
        return base + pygame.Vector2(rng.randint(-jit, jit), rng.randint(-jit, jit))

    # ------------------------------------------------------------------ #

    def update(self, dt, cam, screen_w, screen_h, player_pos):
        """Atualiza ciclo de vida e posição das decorações."""
        active_keys = set()

        for cfg in _DUNGEON_DECO_CFGS:
            kind   = cfg["kind"]
            frames = self._frames.get(kind)
            if not frames:
                continue

            grid   = cfg["grid"]
            prob   = cfg["prob"]
            spd    = cfg["spd"]
            col    = cfg["collide"]
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
                        self._active[key] = _DungeonDeco(wp, frames, spd, col)

        # Remove decos fora de alcance
        for key in list(self._active.keys()):
            if key not in active_keys:
                del self._active[key]

        # Atualiza todas as ativas
        for deco in self._active.values():
            deco.update(dt, cam)

    def push_player(self, player):
        """
        Empurra o jogador para fora de obstáculos BDS colisores.
        Chame após player.update() e antes do draw.
        """
        player_rect = pygame.Rect(
            player.pos.x - 16, player.pos.y - 16, 32, 32
        )
        for deco in self._active.values():
            if not deco.collide:
                continue
            if not deco.world_rect.colliderect(player_rect):
                continue

            # Empurra para o lado de menor sobreposição
            dx_left  = player_rect.right  - deco.world_rect.left
            dx_right = deco.world_rect.right - player_rect.left
            dy_up    = player_rect.bottom - deco.world_rect.top
            dy_down  = deco.world_rect.bottom - player_rect.top

            min_push = min(dx_left, dx_right, dy_up, dy_down)
            if min_push == dx_left:
                player.pos.x -= dx_left
            elif min_push == dx_right:
                player.pos.x += dx_right
            elif min_push == dy_up:
                player.pos.y -= dy_up
            else:
                player.pos.y += dy_down

    def draw_floor(self, screen, screen_w, screen_h):
        """
        Desenha decorações visíveis ordenadas por Y.
        Chame ANTES dos sprites do jogo (chão visualmente abaixo dos personagens).
        """
        visible = sorted(
            (d for d in self._active.values() if d.on_screen(screen_w, screen_h)),
            key=lambda d: d.rect.bottom,
        )
        for deco in visible:
            screen.blit(deco.image, deco.rect)
