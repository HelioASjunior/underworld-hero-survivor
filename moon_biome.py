"""
moon_biome.py — Chão e decorações do bioma Moon.

Assets: assets/backgrounds/moon/
  tiles.png          → 53 tiles 32×32 (probabilidades do moon_tiles.json)
  oil.png            → poças de óleo animadas (8 frames, 32×32 cada)
  mountain_big.png   → 2 rochas grandes (strip 64×64)
  mountain_medium.png→ 2 rochas médias  (strip 48×48)
  mountain_small.png → 2 rochas pequenas(strip 32×32)
  mountain_tall.png  → 1 rocha alta     (48×64)
  mountain_wide.png  → 1 rocha larga    (64×48)

Decorações extras (assets/ui/chao/) — mesmos assets e tamanhos do dungeon:
  pentagrama1/2.png, BDS1/2.png, dinosaur.png, statue.png, espinhos.png
"""

import os
import random

import pygame

_MOON = os.path.join("backgrounds", "moon")

# ---------------------------------------------------------------------------
# Probabilidades dos tiles (moon_tiles.json) — 53 tiles
# ---------------------------------------------------------------------------
_TILE_PROBS = [
    9.00, 0.20, 0.90, 0.05, 0.50, 1.10, 0.10, 0.20, 0.20, 0.90,
    1.20, 0.10, 0.06, 0.90, 1.20, 0.05, 0.05, 0.06, 0.06, 0.02,
    0.02, 0.02, 0.09, 0.09, 0.06, 0.10, 0.10, 0.10, 0.10, 0.06,
    0.10, 0.10, 0.02, 0.02, 0.02, 0.05, 0.05, 0.05, 0.04, 1.10,
    0.80, 0.15, 0.10, 0.90, 1.40, 0.10, 0.10, 0.10, 1.20, 0.40,
    0.08, 0.80, 0.30,
]
_TILE_COUNT  = len(_TILE_PROBS)   # 53
_TILE_SIZE   = 32
_GROUND_SIZE = 256
_TILES_SIDE  = _GROUND_SIZE // _TILE_SIZE  # 8


# ---------------------------------------------------------------------------
# Chão
# ---------------------------------------------------------------------------

def build_moon_ground(loader):
    """Surface 256×256 composta por tiles do moon/tiles.png."""
    frames = loader.load_spritesheet(
        os.path.join(_MOON, "tiles"),
        _TILE_SIZE, _TILE_SIZE,
        _TILE_COUNT,
        None,
    )
    if not frames:
        surf = pygame.Surface((_GROUND_SIZE, _GROUND_SIZE))
        surf.fill((15, 18, 30))
        return surf

    ground  = pygame.Surface((_GROUND_SIZE, _GROUND_SIZE))
    rng     = random.Random(9173)
    total_w = sum(_TILE_PROBS)
    for row in range(_TILES_SIDE):
        for col in range(_TILES_SIDE):
            r = rng.random() * total_w
            acc = 0.0; chosen = 0
            for i, p in enumerate(_TILE_PROBS):
                acc += p
                if r < acc:
                    chosen = i; break
            if 0 <= chosen < len(frames):
                ground.blit(frames[chosen], (col * _TILE_SIZE, row * _TILE_SIZE))
    return ground


# ---------------------------------------------------------------------------
# Configs bioma-específicas (óleo + rochas)
# ---------------------------------------------------------------------------
_BIOME_DECO_CFGS = [
    # ── Poças de óleo animadas ────────────────────────────────────────────
    dict(kind="oil", grid=700, prob=0.13, spd=0.10, size=(170, 170),
         rel="oil.png", fw=32, fh=32, collide=False),
    # ── Rochas / montanhas ────────────────────────────────────────────────
    dict(kind="mtn_big",   grid=1200, prob=0.22, spd=0.0, size=(256, 256),
         rel="mountain_big.png",    fw=64, fh=64, collide=True),
    dict(kind="mtn_med",   grid=950,  prob=0.28, spd=0.0, size=(192, 192),
         rel="mountain_medium.png", fw=48, fh=48, collide=True),
    dict(kind="mtn_small", grid=760,  prob=0.35, spd=0.0, size=(128, 128),
         rel="mountain_small.png",  fw=32, fh=32, collide=True),
    dict(kind="mtn_tall",  grid=1050, prob=0.20, spd=0.0, size=(128, 192),
         rel="mountain_tall.png",   fw=48, fh=64, collide=True),
    dict(kind="mtn_wide",  grid=880,  prob=0.24, spd=0.0, size=(192, 144),
         rel="mountain_wide.png",   fw=64, fh=48, collide=True),
]

# ---------------------------------------------------------------------------
# Configs extras do chao dungeon (assets/ui/chao/) — mesmos tamanhos
# ---------------------------------------------------------------------------
_CHAO_DECO_CFGS = [
    dict(kind="chao_pentagrama", grid=640,  prob=0.52, spd=0.55, size=(210, 210),
         files=["pentagrama1.png", "pentagrama2.png"], collide=False),
    dict(kind="chao_bds",        grid=950,  prob=0.28, spd=0.80, size=(190, 190),
         files=["BDS1.png", "BDS2.png"], collide=True),
    dict(kind="chao_dinosaur",   grid=1200, prob=0.26, spd=0.0,  size=(290, 290),
         files=["dinosaur.png"], collide=False),
    dict(kind="chao_statue",     grid=1100, prob=0.22, spd=0.18, size=(210, 210),
         sheet="statue.png", fw=80, fh=80, collide=True),
    dict(kind="chao_espinhos",   grid=850,  prob=0.28, spd=0.16, size=(160, 135),
         sheet="espinhos.png", fw=48, fh=64, collide=True),
]

_MOUNTAIN_KINDS = {"mtn_big", "mtn_med", "mtn_small", "mtn_tall", "mtn_wide"}


# ---------------------------------------------------------------------------
# Carregamento de sprites
# ---------------------------------------------------------------------------

def _load_strip(path, fw, fh, display_size, frame_count=None):
    """Carrega strip/grid de frames de largura fixa, opcional limite de frames."""
    if not os.path.exists(path):
        print(f"[MoonBiome] nao encontrado: {path}")
        return []
    try:
        raw   = pygame.image.load(path)
        sheet = raw.convert_alpha() if (raw.get_bitsize() == 32 and raw.get_masks()[3]) else raw.convert()
        sw, sh = sheet.get_size()
        cols   = max(1, sw // fw)
        rows_  = max(1, sh // fh)
        frames = []
        for r in range(rows_):
            for c in range(cols):
                if frame_count and len(frames) >= frame_count:
                    break
                sub = sheet.subsurface((c * fw, r * fh, fw, fh)).copy()
                if display_size:
                    sub = pygame.transform.smoothscale(sub, display_size)
                frames.append(sub)
            if frame_count and len(frames) >= frame_count:
                break
        return frames
    except Exception as e:
        print(f"[MoonBiome] erro {path}: {e}")
        return []


def _load_multi_file(paths, display_size):
    """Carrega uma lista de arquivos PNG, um frame por arquivo."""
    frames = []
    for path in paths:
        if not os.path.exists(path):
            continue
        try:
            img = pygame.image.load(path).convert_alpha()
            if display_size:
                img = pygame.transform.smoothscale(img, display_size)
            frames.append(img)
        except Exception as e:
            print(f"[MoonBiome] erro {path}: {e}")
    return frames


# ---------------------------------------------------------------------------
# Decoração individual
# ---------------------------------------------------------------------------

class _MoonDeco:
    def __init__(self, world_pos, frames, anim_speed, collide, start_frame=0, kind=""):
        self.world_pos  = pygame.Vector2(world_pos)
        self.frames     = frames
        self.anim_speed = anim_speed
        self.collide    = collide
        self.kind       = kind
        self.frame_idx  = start_frame % len(frames) if frames else 0
        self.timer      = 0.0
        self.image      = frames[self.frame_idx]
        self.rect       = self.image.get_rect()
        self._refresh_world_rect()

    def _refresh_world_rect(self):
        hw = self.image.get_width()  // 4
        hh = self.image.get_height() // 4
        self.world_rect = pygame.Rect(
            int(self.world_pos.x) - hw,
            int(self.world_pos.y) - hh,
            hw * 2, hh * 2,
        )

    def update(self, dt, cam):
        if self.anim_speed > 0 and len(self.frames) > 1:
            self.timer += dt
            if self.timer >= self.anim_speed:
                self.timer     = 0.0
                self.frame_idx = (self.frame_idx + 1) % len(self.frames)
                self.image     = self.frames[self.frame_idx]
        sp = self.world_pos + cam
        self.rect.center = (int(sp.x), int(sp.y))
        self._refresh_world_rect()

    def on_screen(self, sw, sh):
        m = max(self.image.get_width(), self.image.get_height()) + 32
        return -m < self.rect.centerx < sw + m and -m < self.rect.centery < sh + m


# ---------------------------------------------------------------------------
# Gerenciador principal
# ---------------------------------------------------------------------------

class MoonDecoManager:
    """
    Decorações do bioma Moon.
    Combina decorações específicas da lua (óleo, rochas) com os
    mesmos efeitos de chão do bioma Dungeon (pentagrama, BDS, etc.).
    """

    def __init__(self, asset_dir):
        self._asset_dir = asset_dir
        self._frames:   dict[str, list]       = {}
        self._active:   dict[tuple, _MoonDeco] = {}
        self._all_cfgs: list[dict]            = []

    def load_frames(self):
        moon_dir = os.path.join(self._asset_dir, "backgrounds", "moon")
        chao_dir = os.path.join(self._asset_dir, "ui", "chao")

        # ── Decorações específicas da lua ───────────────────────────────────
        for cfg in _BIOME_DECO_CFGS:
            kind   = cfg["kind"]
            path   = os.path.join(moon_dir, cfg["rel"])
            frames = _load_strip(path, cfg["fw"], cfg["fh"], cfg["size"])
            self._frames[kind] = frames
            print(f"[MoonBiome] {kind}: {len(frames)} frames" if frames else f"[MoonBiome] {kind}: FALHOU")

        # ── Decorações do chao (dungeon) ────────────────────────────────────
        for cfg in _CHAO_DECO_CFGS:
            kind = cfg["kind"]
            if "files" in cfg:
                paths  = [os.path.join(chao_dir, f) for f in cfg["files"]]
                frames = _load_multi_file(paths, cfg["size"])
            else:
                path   = os.path.join(chao_dir, cfg["sheet"])
                frames = _load_strip(path, cfg["fw"], cfg["fh"], cfg["size"])
            self._frames[kind] = frames
            print(f"[MoonBiome] {kind}: {len(frames)} frames" if frames else f"[MoonBiome] {kind}: FALHOU")

        self._all_cfgs = _BIOME_DECO_CFGS + _CHAO_DECO_CFGS

    # ------------------------------------------------------------------ #

    def _cell_rng(self, gx, gy, kind):
        return random.Random((gx * 71348293) ^ (gy * 43918271) ^ hash(kind))

    def _should_place(self, gx, gy, kind, prob):
        return self._cell_rng(gx, gy, kind).random() < prob

    def _cell_world_pos(self, gx, gy, grid, kind):
        rng = self._cell_rng(gx, gy, kind)
        jit = grid // 3
        base = pygame.Vector2(gx * grid, gy * grid)
        return base + pygame.Vector2(rng.randint(-jit, jit), rng.randint(-jit, jit))

    def _cell_start_frame(self, gx, gy, kind, n):
        rng = random.Random((gx * 55291847) ^ (gy * 72834901) ^ hash(kind) ^ 0xC0DE)
        return rng.randint(0, max(0, n - 1))

    # ------------------------------------------------------------------ #

    def update(self, dt, cam, screen_w, screen_h, player_pos):
        active_keys = set()

        for cfg in self._all_cfgs:
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
                        sf = self._cell_start_frame(gx, gy, kind, len(frames))
                        self._active[key] = _MoonDeco(wp, frames, spd, col, sf, kind)

        for key in list(self._active.keys()):
            if key not in active_keys:
                del self._active[key]

        for deco in self._active.values():
            deco.update(dt, cam)

    def push_player(self, player):
        """Empurra jogador para fora de obstáculos com collide=True."""
        player_rect = pygame.Rect(player.pos.x - 16, player.pos.y - 16, 32, 32)
        for deco in self._active.values():
            if not deco.collide:
                continue
            if not deco.world_rect.colliderect(player_rect):
                continue
            dx_l = player_rect.right  - deco.world_rect.left
            dx_r = deco.world_rect.right - player_rect.left
            dy_u = player_rect.bottom - deco.world_rect.top
            dy_d = deco.world_rect.bottom - player_rect.top
            m = min(dx_l, dx_r, dy_u, dy_d)
            if   m == dx_l: player.pos.x -= dx_l
            elif m == dx_r: player.pos.x += dx_r
            elif m == dy_u: player.pos.y -= dy_u
            else:           player.pos.y += dy_d

    def draw_floor(self, screen, screen_w, screen_h):
        """
        Duas passagens: tudo exceto montanhas (chão) → montanhas (em cima).
        Cada passagem ordenada por Y para pseudo-profundidade.
        """
        visible = [d for d in self._active.values() if d.on_screen(screen_w, screen_h)]

        for deco in sorted(
            (d for d in visible if d.kind not in _MOUNTAIN_KINDS),
            key=lambda d: d.rect.bottom,
        ):
            screen.blit(deco.image, deco.rect)

        for deco in sorted(
            (d for d in visible if d.kind in _MOUNTAIN_KINDS),
            key=lambda d: d.rect.bottom,
        ):
            screen.blit(deco.image, deco.rect)
