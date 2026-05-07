"""
hub_room.py — Sistema de Hub Multi-Mapa

Mapas gerenciados:
  exterior    — área externa do prédio (Exterior.tmx)
  interior_1  — primeiro andar interno  (Interior_1st_floor.tmx)
  interior_2  — segundo andar interno   (Interior_2nd_floor.tmx)

Transições:
  exterior → interior_1  : entrar no prédio (porta sul)
  interior_1 → exterior  : sair pelo sul do piso
  interior_1 → interior_2: usar a escada
  interior_2 → interior_1: usar a escada (volta)

Uso:
    scene = HubScene(tmx_dir)
    scene.load_all()
    scene.load_surfaces_and_bake()
    scene.setup_player()
    scene.apply_char_frames(...)

    # a cada frame:
    scene.update(dt, keys, screen_w, screen_h)
    scene.draw(screen)
"""

import os
import xml.etree.ElementTree as ET

import pygame

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

SCALE = 4   # tiles 16px → 64px na tela

# Camadas cujos tiles são renderizados ACIMA do jogador
_TOP_LAYER_KEYWORDS = ("top", "roof", "ladder")

# Camadas que definem colisão de parede
_WALL_LAYER_KEYWORDS = ("wall", "walls")

# Tilesets cujas animações devem ser SUPRIMIDAS (exibir frame 0 estático)
# walk → personagens andando (NPC estacionário)
# window / door → Windows_doors.png (animações falsas: todos os frames são iguais)
_STATIC_TILESET_KEYWORDS = ("walk", "window", "door")


# ---------------------------------------------------------------------------
# Tile animado — instância única de um tile com animação no mundo
# ---------------------------------------------------------------------------

class _AnimTileInstance:
    __slots__ = ("px", "py", "frames", "is_top", "frame_idx", "elapsed_ms")

    def __init__(self, px: int, py: int, frames: list, is_top: bool):
        self.px         = px       # pixel x no espaço do mapa
        self.py         = py       # pixel y no espaço do mapa
        self.frames     = frames   # list de (pygame.Surface, duration_ms)
        self.is_top     = is_top
        self.frame_idx  = 0
        self.elapsed_ms = 0.0

    def update(self, dt: float):
        self.elapsed_ms += dt * 1000.0
        dur = self.frames[self.frame_idx][1]
        while self.elapsed_ms >= dur:
            self.elapsed_ms -= dur
            self.frame_idx   = (self.frame_idx + 1) % len(self.frames)
            dur = self.frames[self.frame_idx][1]

    @property
    def image(self) -> pygame.Surface:
        return self.frames[self.frame_idx][0]


# ---------------------------------------------------------------------------
# Carregador de mapa TMX (formato infinite do Tiled)
# ---------------------------------------------------------------------------

class HubMap:
    """Carrega, bake e renderiza um mapa TMX infinite."""

    def __init__(self, tmx_path: str):
        self._dir      = os.path.dirname(os.path.abspath(tmx_path))
        self._tmx_path = tmx_path
        self.tile_w    = 16
        self.tile_h    = 16

        self.map_tiles_w = 0
        self.map_tiles_h = 0
        self.origin_x    = 0
        self.origin_y    = 0

        self._tilesets:   list[dict] = []
        self._layers:     list[dict] = []
        self._tile_cache: dict       = {}

        self._anim_lookup: dict[int, list[tuple[int, int]]] = {}

        self._base_surf: pygame.Surface | None = None
        self._top_surf:  pygame.Surface | None = None

        self._anim_instances: list[_AnimTileInstance] = []

        self.wall_grid: set[tuple[int, int]] = set()
        self._content_center: pygame.Vector2 | None = None
        self._content_rect:   pygame.Rect    | None = None

        # Obstáculos customizados (móveis, mesas, etc.)
        self.custom_obstacles: list[pygame.Rect] = []

    # ------------------------------------------------------------------ #
    # Carregamento                                                          #
    # ------------------------------------------------------------------ #

    def load(self):
        """Parseia XML do TMX. Não requer pygame inicializado."""
        tree = ET.parse(self._tmx_path)
        root = tree.getroot()

        self.tile_w = int(root.get("tilewidth", 16))
        self.tile_h = int(root.get("tileheight", 16))

        # 1. Tilesets + dados de animação
        for ts_elem in root.findall("tileset"):
            firstgid  = int(ts_elem.get("firstgid", 1))
            tilecount = int(ts_elem.get("tilecount", 0))
            columns   = int(ts_elem.get("columns", 1))
            img_elem  = ts_elem.find("image")
            if img_elem is None:
                continue
            src      = img_elem.get("source", "")
            img_path = os.path.normpath(os.path.join(self._dir, src))
            self._tilesets.append({
                "firstgid": firstgid,
                "path":     img_path,
                "columns":  columns,
                "surface":  None,
            })

            for tile_elem in ts_elem.findall("tile"):
                tid       = int(tile_elem.get("id", 0))
                anim_elem = tile_elem.find("animation")
                if anim_elem is None:
                    continue
                frames = []
                for f in anim_elem.findall("frame"):
                    fgid = firstgid + int(f.get("tileid", 0))
                    dur  = int(f.get("duration", 150))
                    frames.append((fgid, dur))
                if frames:
                    self._anim_lookup[firstgid + tid] = frames

        # 2. Layers + chunks → calcular bounds do mapa
        all_xs, all_ys = [], []
        raw_layers: list[dict] = []

        # iter("layer") percorre recursivamente grupos <group> e camadas aninhadas
        for layer_elem in root.iter("layer"):
            data_elem = layer_elem.find("data")
            if data_elem is None:
                continue
            name    = layer_elem.get("name", "layer")
            visible = layer_elem.get("visible", "1") != "0"
            chunks  = []
            for chunk in data_elem.findall("chunk"):
                cx = int(chunk.get("x"))
                cy = int(chunk.get("y"))
                cw = int(chunk.get("width"))
                ch = int(chunk.get("height"))
                all_xs += [cx, cx + cw]
                all_ys += [cy, cy + ch]
                raw = chunk.text.strip() if chunk.text else ""
                gids = [int(v) for v in raw.replace("\n", ",").split(",") if v.strip()]
                chunks.append({"cx": cx, "cy": cy, "cw": cw, "ch": ch, "gids": gids})
            raw_layers.append({"name": name, "visible": visible, "chunks": chunks})

        if not all_xs:
            return

        self.origin_x    = min(all_xs)
        self.origin_y    = min(all_ys)
        self.map_tiles_w = max(all_xs) - self.origin_x
        self.map_tiles_h = max(all_ys) - self.origin_y

        # 3. Grid 2D por camada
        for rl in raw_layers:
            grid = [[0] * self.map_tiles_w for _ in range(self.map_tiles_h)]
            for chunk in rl["chunks"]:
                for row in range(chunk["ch"]):
                    for col in range(chunk["cw"]):
                        idx = row * chunk["cw"] + col
                        if idx >= len(chunk["gids"]):
                            continue
                        gid = chunk["gids"][idx]
                        tx  = chunk["cx"] - self.origin_x + col
                        ty  = chunk["cy"] - self.origin_y + row
                        if 0 <= tx < self.map_tiles_w and 0 <= ty < self.map_tiles_h:
                            grid[ty][tx] = gid
            self._layers.append({"name": rl["name"], "visible": rl["visible"], "grid": grid})

        # 4. Wall grid
        for layer in self._layers:
            n      = layer["name"].lower()
            is_wall = any(k in n for k in _WALL_LAYER_KEYWORDS)
            is_top  = any(k in n for k in _TOP_LAYER_KEYWORDS)
            if is_wall and not is_top:
                for ty in range(self.map_tiles_h):
                    for tx in range(self.map_tiles_w):
                        if layer["grid"][ty][tx] != 0:
                            self.wall_grid.add((tx, ty))

        # 5. Centro do conteúdo (spawn padrão)
        content_xs, content_ys = [], []
        for layer in self._layers:
            n = layer["name"].lower()
            if any(k in n for k in _WALL_LAYER_KEYWORDS):
                continue
            for ty in range(self.map_tiles_h):
                for tx in range(self.map_tiles_w):
                    if layer["grid"][ty][tx] != 0:
                        content_xs.append(tx)
                        content_ys.append(ty)
        if content_xs:
            min_tx, max_tx = min(content_xs), max(content_xs)
            min_ty, max_ty = min(content_ys), max(content_ys)
            cx_t = (min_tx + max_tx) / 2.0
            cy_t = (min_ty + max_ty) / 2.0
            self._content_center = pygame.Vector2(
                cx_t * self.tile_w * SCALE,
                cy_t * self.tile_h * SCALE,
            )
            self._content_rect = pygame.Rect(
                int(min_tx * self.tile_w * SCALE),
                int(min_ty * self.tile_h * SCALE),
                int((max_tx - min_tx + 1) * self.tile_w * SCALE),
                int((max_ty - min_ty + 1) * self.tile_h * SCALE),
            )

    def load_surfaces(self):
        """Carrega imagens dos tilesets. Requer pygame inicializado."""
        for ts in self._tilesets:
            path = ts["path"]
            if not os.path.exists(path):
                print(f"[HubMap] Tileset não encontrado: {os.path.basename(path)}")
                ts["surface"] = None
                continue
            try:
                ts["surface"] = pygame.image.load(path).convert_alpha()
                print(f"[HubMap] OK {os.path.basename(path)}")
            except Exception as e:
                print(f"[HubMap] Erro {os.path.basename(path)}: {e}")
                ts["surface"] = None

    # ------------------------------------------------------------------ #
    # Bake                                                                  #
    # ------------------------------------------------------------------ #

    def _is_tileset_animated(self, gid: int) -> bool:
        """Retorna False se o tileset do gid contém palavras-chave estáticas."""
        for ts in reversed(self._tilesets):
            if gid >= ts["firstgid"]:
                name = os.path.basename(ts["path"]).lower()
                return not any(k in name for k in _STATIC_TILESET_KEYWORDS)
        return True

    def bake(self):
        """Pré-renderiza tiles estáticos; coleta instâncias de tiles realmente animados."""
        pw = self.map_tiles_w * self.tile_w * SCALE
        ph = self.map_tiles_h * self.tile_h * SCALE

        base = pygame.Surface((pw, ph), pygame.SRCALPHA)
        base.fill((30, 22, 16))
        top  = pygame.Surface((pw, ph), pygame.SRCALPHA)

        self._anim_instances.clear()

        tw = self.tile_w * SCALE
        th = self.tile_h * SCALE

        for layer in self._layers:
            if not layer["visible"]:
                continue
            n      = layer["name"].lower()
            is_top = any(k in n for k in _TOP_LAYER_KEYWORDS)
            target = top if is_top else base
            grid   = layer["grid"]

            for ty, row in enumerate(grid):
                for tx, gid in enumerate(row):
                    if gid == 0:
                        continue

                    px = tx * tw
                    py = ty * th

                    if gid in self._anim_lookup and self._is_tileset_animated(gid):
                        # Tile verdadeiramente animado (NPC, fogo, bandeiras…)
                        anim_frames = self._anim_lookup[gid]
                        frames_surf = []
                        for (fgid, dur) in anim_frames:
                            surf = self._get_tile(fgid)
                            if surf:
                                frames_surf.append((surf, dur))
                        if frames_surf:
                            self._anim_instances.append(
                                _AnimTileInstance(px, py, frames_surf, is_top)
                            )
                        # Bake frame 0 sob a animação (fallback visual)
                        f0 = self._get_tile(anim_frames[0][0])
                        if f0:
                            target.blit(f0, (px, py))
                    else:
                        # Estático — bake frame 0 (ou tile simples)
                        gid0 = self._anim_lookup[gid][0][0] if gid in self._anim_lookup else gid
                        tile = self._get_tile(gid0)
                        if tile:
                            target.blit(tile, (px, py))

        self._base_surf = base
        self._top_surf  = top
        n_anim   = len(self._anim_instances)
        n_static = len(self._tile_cache)
        print(f"[HubMap] Bake: {os.path.basename(self._tmx_path)} — "
              f"{pw}x{ph}px | {n_static} tiles | {n_anim} animados")

    def _get_tile(self, gid: int) -> pygame.Surface | None:
        if gid in self._tile_cache:
            return self._tile_cache[gid]

        ts = None
        for t in reversed(self._tilesets):
            if gid >= t["firstgid"]:
                ts = t
                break
        if ts is None or ts["surface"] is None:
            self._tile_cache[gid] = None
            return None

        local_id = gid - ts["firstgid"]
        col = local_id % ts["columns"]
        row = local_id // ts["columns"]
        src = pygame.Rect(col * self.tile_w, row * self.tile_h, self.tile_w, self.tile_h)

        raw = pygame.Surface((self.tile_w, self.tile_h), pygame.SRCALPHA)
        raw.blit(ts["surface"], (0, 0), src)
        scaled = pygame.transform.scale(raw, (self.tile_w * SCALE, self.tile_h * SCALE))
        self._tile_cache[gid] = scaled
        return scaled

    # ------------------------------------------------------------------ #
    # Update / Draw                                                         #
    # ------------------------------------------------------------------ #

    def update(self, dt: float):
        for inst in self._anim_instances:
            inst.update(dt)

    def draw_base(self, screen: pygame.Surface, cam: pygame.Vector2):
        if self._base_surf:
            screen.blit(self._base_surf, (int(cam.x), int(cam.y)))
        for inst in self._anim_instances:
            if not inst.is_top:
                screen.blit(inst.image, (inst.px + int(cam.x), inst.py + int(cam.y)))

    def draw_top(self, screen: pygame.Surface, cam: pygame.Vector2):
        if self._top_surf:
            screen.blit(self._top_surf, (int(cam.x), int(cam.y)))
        for inst in self._anim_instances:
            if inst.is_top:
                screen.blit(inst.image, (inst.px + int(cam.x), inst.py + int(cam.y)))

    # ------------------------------------------------------------------ #
    # Colisão e propriedades                                               #
    # ------------------------------------------------------------------ #

    def is_wall(self, world_x: float, world_y: float) -> bool:
        tx = int(world_x / (self.tile_w * SCALE))
        ty = int(world_y / (self.tile_h * SCALE))
        if (tx, ty) in self.wall_grid:
            return True
        for rect in self.custom_obstacles:
            if rect.collidepoint(world_x, world_y):
                return True
        return False

    @property
    def pixel_width(self) -> int:
        return self.map_tiles_w * self.tile_w * SCALE

    @property
    def pixel_height(self) -> int:
        return self.map_tiles_h * self.tile_h * SCALE

    @property
    def spawn_pos(self) -> pygame.Vector2:
        if self._content_center:
            return pygame.Vector2(self._content_center)
        return pygame.Vector2(self.pixel_width / 2, self.pixel_height / 2)

    @property
    def content_center(self) -> "pygame.Vector2 | None":
        return self._content_center

    @property
    def content_rect(self) -> "pygame.Rect | None":
        return self._content_rect


# ---------------------------------------------------------------------------
# Jogador do Hub — sprites direcionais walk/idle, sem combate
# ---------------------------------------------------------------------------

class HubPlayer:
    """Jogador simplificado para o hub: só movimento e animação direcional."""

    SPEED = 180  # px/s

    def __init__(self, hub_map: HubMap):
        self.map = hub_map
        self.pos = pygame.Vector2(hub_map.spawn_pos)

        self._dir_walk_frames: dict[str, list[pygame.Surface]] = {}
        self._dir_idle_frames: dict[str, list[pygame.Surface]] = {}
        self._walk_frames:     list[pygame.Surface] = []
        self._idle_frames:     list[pygame.Surface] = []

        self._facing_dir   = "down"
        self._facing_right = True
        self._is_moving    = False

        self.draw_scale = 1.0   # escala do sprite; 1.5 no interior, 1.0 no exterior

        self._frame_idx       = 0
        self._idle_frame_idx  = 0
        self._anim_timer      = 0.0
        self._idle_anim_timer = 0.0
        self._anim_spd        = 0.10
        self._idle_anim_spd   = 0.13

        self._size = self.map.tile_w * SCALE

    def set_char_frames(
        self,
        dir_walk:      dict[str, list[pygame.Surface]],
        dir_idle:      dict[str, list[pygame.Surface]],
        walk_fallback: list[pygame.Surface] | None = None,
        idle_fallback: list[pygame.Surface] | None = None,
        anim_spd:      float = 0.10,
        idle_anim_spd: float = 0.13,
    ):
        self._dir_walk_frames = dir_walk or {}
        self._dir_idle_frames = dir_idle or {}
        self._walk_frames     = walk_fallback or []
        self._idle_frames     = idle_fallback or []
        self._anim_spd        = anim_spd
        self._idle_anim_spd   = idle_anim_spd

    def update(self, dt: float, keys):
        dx = dy = 0
        if keys[pygame.K_w] or keys[pygame.K_UP]:    dy -= 1
        if keys[pygame.K_s] or keys[pygame.K_DOWN]:  dy += 1
        if keys[pygame.K_a] or keys[pygame.K_LEFT]:  dx -= 1
        if keys[pygame.K_d] or keys[pygame.K_RIGHT]: dx += 1

        moving = dx != 0 or dy != 0
        self._is_moving = moving

        if moving:
            if dx > 0:
                self._facing_right = True
                self._facing_dir   = "right"
            elif dx < 0:
                self._facing_right = False
                self._facing_dir   = "left"
            elif dy > 0:
                self._facing_dir = "down"
            elif dy < 0:
                self._facing_dir = "up"

            length = (dx * dx + dy * dy) ** 0.5
            step   = self.SPEED * dt / length
            nx     = self.pos.x + dx * step
            ny     = self.pos.y + dy * step

            r = self._size // 2
            if not self._collides(nx, self.pos.y, r):
                self.pos.x = nx
            if not self._collides(self.pos.x, ny, r):
                self.pos.y = ny

            self._anim_timer += dt
            if self._anim_timer >= self._anim_spd:
                self._anim_timer = 0.0
                n = self._walk_count()
                self._frame_idx = (self._frame_idx + 1) % max(1, n)
            self._idle_frame_idx  = 0
            self._idle_anim_timer = 0.0
        else:
            self._frame_idx = 0
            self._idle_anim_timer += dt
            if self._idle_anim_timer >= self._idle_anim_spd:
                self._idle_anim_timer = 0.0
                n = self._idle_count()
                self._idle_frame_idx = (self._idle_frame_idx + 1) % max(1, n)

        # Clampar ao conteúdo do mapa (impede sair pela porta/borda)
        cr = self.map.content_rect
        if cr:
            m = self._size // 2
            self.pos.x = max(cr.left + m, min(cr.right  - m, self.pos.x))
            self.pos.y = max(cr.top  + m, min(cr.bottom - m, self.pos.y))
        else:
            margin = self.map.tile_w * SCALE * 2
            self.pos.x = max(margin, min(self.map.pixel_width  - margin, self.pos.x))
            self.pos.y = max(margin, min(self.map.pixel_height - margin, self.pos.y))

    def _walk_count(self) -> int:
        if self._dir_walk_frames:
            return len(self._dir_walk_frames.get(self._facing_dir)
                       or next(iter(self._dir_walk_frames.values())))
        return len(self._walk_frames)

    def _idle_count(self) -> int:
        if self._dir_idle_frames:
            return len(self._dir_idle_frames.get(self._facing_dir)
                       or next(iter(self._dir_idle_frames.values())))
        return len(self._idle_frames)

    def _current_image(self) -> pygame.Surface | None:
        if self._is_moving:
            if self._dir_walk_frames:
                frames = (self._dir_walk_frames.get(self._facing_dir)
                          or next(iter(self._dir_walk_frames.values())))
                return frames[self._frame_idx % len(frames)]
            if self._walk_frames:
                img = self._walk_frames[self._frame_idx % len(self._walk_frames)]
                return img if self._facing_right else pygame.transform.flip(img, True, False)
        else:
            if self._dir_idle_frames:
                frames = (self._dir_idle_frames.get(self._facing_dir)
                          or next(iter(self._dir_idle_frames.values())))
                return frames[self._idle_frame_idx % len(frames)]
            if self._idle_frames:
                img = self._idle_frames[self._idle_frame_idx % len(self._idle_frames)]
                return img if self._facing_right else pygame.transform.flip(img, True, False)
        return None

    def _collides(self, wx: float, wy: float, r: int) -> bool:
        for px, py in [(wx - r, wy - r), (wx + r, wy - r),
                       (wx - r, wy + r), (wx + r, wy + r)]:
            if self.map.is_wall(px, py):
                return True
        return False

    def draw(self, screen: pygame.Surface, cam: pygame.Vector2):
        sx  = int(self.pos.x + cam.x)
        sy  = int(self.pos.y + cam.y)
        img = self._current_image()
        if img:
            if self.draw_scale != 1.0:
                nw = max(1, int(img.get_width()  * self.draw_scale))
                nh = max(1, int(img.get_height() * self.draw_scale))
                img = pygame.transform.scale(img, (nw, nh))
            screen.blit(img, img.get_rect(center=(sx, sy)))
        else:
            r = int(22 * self.draw_scale)
            pygame.draw.circle(screen, (100, 220, 100), (sx, sy), r)
            pygame.draw.circle(screen, (200, 255, 200), (sx, sy), r, 2)


# ---------------------------------------------------------------------------
# Câmera simples clampeada ao mapa
# ---------------------------------------------------------------------------

def compute_camera(
    player_pos: pygame.Vector2,
    map_pw: int,
    map_ph: int,
    screen_w: int,
    screen_h: int,
) -> pygame.Vector2:
    cx = screen_w / 2 - player_pos.x
    cy = screen_h / 2 - player_pos.y
    cx = max(screen_w  - map_pw, min(0, cx))
    cy = max(screen_h - map_ph, min(0, cy))
    return pygame.Vector2(cx, cy)


def compute_camera_fixed(
    content_center: pygame.Vector2,
    screen_w: int,
    screen_h: int,
) -> pygame.Vector2:
    """Câmera fixa: centraliza o conteúdo do mapa na tela independente da posição do jogador."""
    cx = screen_w / 2 - content_center.x
    cy = screen_h / 2 - content_center.y
    return pygame.Vector2(cx, cy)


# ---------------------------------------------------------------------------
# HubScene — gerencia os 3 mapas conectados e as transições
# ---------------------------------------------------------------------------

# Coordenadas em pixel (SCALE=4, tile=16px, origin=(-16,-16) para todos os mapas)
# Fórmula: pixel = (tile_coord + 16) * 64
#
# Interior 1st floor — Floor: x=[256,1472] y=[704,1344]  Ladder: x=[384,640] y=[1088,1280]
# Exterior           — House: x=[768,1408] y=[704,1216]  Sign:   x=[896,1280] y=[960,1088]

# ---------------------------------------------------------------------------
# Obstáculos customizados por mapa (móveis sem colisão no TMX)
# Rects em coordenadas de pixel do mundo (SCALE=4, tile=16px → 64px)
# ---------------------------------------------------------------------------

# Interior 1º andar — sem obstáculos customizados (spawn em (896,864) fica na área da mesa)
INTERIOR_1_TABLE_RECTS: list[pygame.Rect] = []

# Interior 2º andar — balcão central (Objects2, linha y=832)
# Spawn do 2º andar é em (512,1050), fora do rect abaixo.
# Bloqueia a faixa y=896-928 no centro, impedindo o jogador de atravessar o balcão.
INTERIOR_2_TABLE_RECTS: list[pygame.Rect] = [
    pygame.Rect(440, 896, 544, 32),    # borda inferior do balcão x=440-984, y=896-928
]

# Baú no 1º andar — perto da porta de cima (abs tile x=-1,0 / y=-6 a -4 → world x=960-1088)
# Ponto de interação = centro-x do baú (1024), primeiro y walkable abaixo (abs y=-2, world y=896)
INTERIOR_1_CHEST_POS    = pygame.Vector2(1024, 896)  # ponto de interação do baú em px
CHEST_INTERACT_RADIUS   = 150                         # raio de interação em px

# Ferreiro NPC no Mercado — Trader_weapon (stall direito), tiles (20-21,14-15), origin=(-16,-16)
# Centro do sprite 2×2: world x=(20+1)*64=1344, y=(14+1)*64=960
FERREIRO_NPC_POS         = pygame.Vector2(1344, 960)
FERREIRO_INTERACT_RADIUS = 200

# Loja de Itens NPC no Mercado — Trader_magic (stall3 esquerdo), origin=(-16,-16)
# Centro do sprite 3×3: world x=608, y=992
LOJA_NPC_POS         = pygame.Vector2(608, 992)
LOJA_INTERACT_RADIUS = 200

# Talentos NPC no Mercado — Trader_drinks (stall5), origin=(-16,-16)
# Centro do sprite 2×2: world x=(16+3+1)*64=1280, y=(16+2+1)*64=1216
TALENTOS_NPC_POS         = pygame.Vector2(1280, 1216)
TALENTOS_INTERACT_RADIUS = 200


_ZONES: dict[str, list[dict]] = {
    # Zona no exterior: entrar no prédio (frente da casa)
    "exterior": [
        {
            "rect":  pygame.Rect(850, 1155, 400, 80),   # frente da porta sul
            "to":    "interior_1",
            "spawn": "interior_1_from_exterior",
        },
    ],
    # Zona no 1º andar: apenas escada (sobe para 2º andar)
    # Transição para o exterior removida — sair pelo ESC ou botão PRONTO
    "interior_1": [
        {
            "rect":  pygame.Rect(384, 1088, 256, 192),  # camada Ladder exata
            "to":    "interior_2",
            "spawn": "interior_2_from_1st",
        },
    ],
    # Zona no 2º andar: escada (desce para 1º andar)
    "interior_2": [
        {
            "rect":  pygame.Rect(384, 1088, 256, 192),  # mesma posição da escada
            "to":    "interior_1",
            "spawn": "interior_1_from_2nd",
        },
    ],
}

_SPAWNS: dict[str, pygame.Vector2] = {
    # Exterior — área aberta ao sul do prédio
    "exterior_default":          pygame.Vector2(1056, 1500),
    # Exterior — aparece perto da porta ao voltar do interior
    "exterior_from_interior":    pygame.Vector2(1056, 1260),
    # Interior 1º — spawn padrão ao entrar no hub (perto do baú/guilda)
    "interior_1_default":        pygame.Vector2(896,  864),
    # Interior 1º — aparece próximo à entrada sul
    "interior_1_from_exterior":  pygame.Vector2(864,  1260),
    # Interior 1º — aparece à direita da escada (fora de Walls_top) ao descer do 2º
    "interior_1_from_2nd":       pygame.Vector2(760,  1200),
    # Interior 2º — aparece logo acima da escada (fora da zona) ao subir do 1º
    "interior_2_from_1st":       pygame.Vector2(512,  1050),
}

_MAP_FILES: dict[str, str] = {
    "exterior":   "Exterior.tmx",
    "interior_1": "Interior_1st_floor.tmx",
    "interior_2": "Interior_2nd_floor.tmx",
}

_SPAWN_MAP: dict[str, str] = {
    "exterior_default":         "exterior",
    "exterior_from_interior":   "exterior",
    "interior_1_default":       "interior_1",
    "interior_1_from_exterior": "interior_1",
    "interior_1_from_2nd":      "interior_1",
    "interior_2_from_1st":      "interior_2",
}


class HubScene:
    """
    Gerencia os três mapas do hub (exterior, interior_1, interior_2)
    e as transições entre eles.
    """

    def __init__(self, tmx_dir: str):
        self._tmx_dir   = tmx_dir
        self._maps:     dict[str, HubMap]   = {}
        self._cur_key   = "exterior"
        self._player:   HubPlayer | None    = None
        self._cooldown  = 0.0               # segundos até próxima transição
        self._cam       = pygame.Vector2(0, 0)

    # ------------------------------------------------------------------ #
    # Carregamento                                                          #
    # ------------------------------------------------------------------ #

    def load_all(self):
        """Parseia todos os TMX. Não requer pygame inicializado."""
        for key, fname in _MAP_FILES.items():
            path = os.path.join(self._tmx_dir, fname)
            if not os.path.exists(path):
                print(f"[HubScene] Arquivo não encontrado: {path}")
                continue
            m = HubMap(path)
            m.load()
            self._maps[key] = m
        print(f"[HubScene] {len(self._maps)}/3 mapas carregados.")

    def load_surfaces_and_bake(self):
        """Carrega imagens e bake de todos os mapas. Requer pygame inicializado."""
        for key, m in self._maps.items():
            m.load_surfaces()
            m.bake()
            # Registra obstáculos customizados por mapa
            if key == "interior_1":
                m.custom_obstacles = list(INTERIOR_1_TABLE_RECTS)
            elif key == "interior_2":
                m.custom_obstacles = list(INTERIOR_2_TABLE_RECTS)

    def setup_player(self, spawn_key: str = "exterior_default"):
        """Cria o jogador no mapa e posição de spawn indicados."""
        map_key = _SPAWN_MAP.get(spawn_key, "exterior")
        m = self._maps.get(map_key)
        if m is None:
            # fallback: qualquer mapa disponível
            if not self._maps:
                return
            map_key = next(iter(self._maps))
            m = self._maps[map_key]
        self._cur_key = map_key
        self._player  = HubPlayer(m)
        pos = _SPAWNS.get(spawn_key)
        if pos:
            self._player.pos = pygame.Vector2(pos)

    def apply_char_frames(
        self,
        dir_walk:      dict,
        dir_idle:      dict,
        walk_fallback: list | None = None,
        idle_fallback: list | None = None,
        anim_spd:      float = 0.10,
        idle_anim_spd: float = 0.13,
    ):
        if self._player:
            self._player.set_char_frames(
                dir_walk, dir_idle, walk_fallback, idle_fallback, anim_spd, idle_anim_spd
            )

    # ------------------------------------------------------------------ #
    # Propriedades                                                          #
    # ------------------------------------------------------------------ #

    @property
    def current_map(self) -> HubMap | None:
        return self._maps.get(self._cur_key)

    @property
    def player(self) -> "HubPlayer | None":
        return self._player

    @property
    def cam(self) -> pygame.Vector2:
        return self._cam

    @property
    def current_map_name(self) -> str:
        return self._cur_key

    @property
    def player_near_chest(self) -> bool:
        """True quando o jogador está perto do baú no 1º andar interior."""
        if self._cur_key != "interior_1" or self._player is None:
            return False
        return self._player.pos.distance_to(INTERIOR_1_CHEST_POS) <= CHEST_INTERACT_RADIUS

    @property
    def chest_screen_pos(self) -> "pygame.Vector2":
        """Posição do baú em coordenadas de tela (para desenhar o texto 'Press F')."""
        return pygame.Vector2(
            INTERIOR_1_CHEST_POS.x + self._cam.x,
            INTERIOR_1_CHEST_POS.y + self._cam.y,
        )

    # ------------------------------------------------------------------ #
    # Update                                                                #
    # ------------------------------------------------------------------ #

    def update(self, dt: float, keys, screen_w: int, screen_h: int,
               suppress_transitions: bool = False):
        m = self.current_map
        if m is None or self._player is None:
            return

        self._player.update(dt, keys)
        m.update(dt)

        # Câmera fixa para quartos internos — centraliza o quarto, não segue o jogador
        if self._cur_key in ("interior_1", "interior_2") and m.content_center:
            self._cam = compute_camera_fixed(m.content_center, screen_w, screen_h)
        else:
            self._cam = compute_camera(
                self._player.pos, m.pixel_width, m.pixel_height, screen_w, screen_h
            )

        # Cooldown de transição (evita re-trigger imediato)
        if self._cooldown > 0:
            self._cooldown -= dt
            return

        # Não verifica transições quando o inventário está aberto
        if suppress_transitions:
            return

        # Verifica zonas de transição
        px = self._player.pos.x
        py = self._player.pos.y
        for zone in _ZONES.get(self._cur_key, []):
            if zone["rect"].collidepoint(px, py):
                self._transition(zone["to"], zone["spawn"])
                return

    def _transition(self, to_key: str, spawn_key: str):
        target = self._maps.get(to_key)
        if target is None:
            print(f"[HubScene] Mapa '{to_key}' não carregado — transição ignorada.")
            return

        print(f"[HubScene] {self._cur_key} → {to_key}  (spawn: {spawn_key})")
        self._cur_key      = to_key
        self._player.map   = target
        pos = _SPAWNS.get(spawn_key)
        if pos:
            self._player.pos = pygame.Vector2(pos)
        self._cooldown = 1.2   # s — previne re-trigger imediato

    # ------------------------------------------------------------------ #
    # Draw                                                                  #
    # ------------------------------------------------------------------ #

    def draw(self, screen: pygame.Surface):
        m = self.current_map
        if m is None or self._player is None:
            return
        # Heróis maiores dentro dos quartos internos
        self._player.draw_scale = 1.5 if self._cur_key in ("interior_1", "interior_2") else 1.0
        m.draw_base(screen, self._cam)
        self._player.draw(screen, self._cam)
        m.draw_top(screen, self._cam)


# ---------------------------------------------------------------------------
# MarketScene — mercado exterior com NPCs animados
# ---------------------------------------------------------------------------

class MarketScene:
    """
    Cena do Mercado: combina Market_square.tmx (ambiente) e
    Characters.tmx (NPCs animados) numa área externa percorrível.
    """

    def __init__(self, ferreiro_dir: str):
        self._dir = ferreiro_dir
        self._market_map: HubMap | None = None
        self._chars_map:  HubMap | None = None
        self._player:     HubPlayer | None = None
        self._cam = pygame.Vector2(0, 0)

    def load_all(self):
        """Parseia Market_square.tmx. Não requer pygame inicializado."""
        path = os.path.join(self._dir, "Market_square.tmx")
        if os.path.exists(path):
            self._market_map = HubMap(path)
            self._market_map.load()
        else:
            print(f"[MarketScene] Arquivo não encontrado: Market_square.tmx")

    def load_surfaces_and_bake(self):
        """Carrega imagens e bake. Requer pygame inicializado."""
        if self._market_map is not None:
            self._market_map.load_surfaces()
            self._market_map.bake()

    def setup_player(self):
        """Cria o jogador no centro do mapa do mercado."""
        if self._market_map is None:
            return
        self._player = HubPlayer(self._market_map)
        if self._market_map.content_center:
            self._player.pos = pygame.Vector2(self._market_map.content_center)

    def apply_char_frames(
        self,
        dir_walk:      dict,
        dir_idle:      dict,
        walk_fallback: list | None = None,
        idle_fallback: list | None = None,
        anim_spd:      float = 0.10,
        idle_anim_spd: float = 0.13,
    ):
        if self._player:
            self._player.set_char_frames(
                dir_walk, dir_idle, walk_fallback, idle_fallback, anim_spd, idle_anim_spd
            )

    @property
    def player(self) -> "HubPlayer | None":
        return self._player

    @property
    def cam(self) -> pygame.Vector2:
        return self._cam

    @property
    def player_near_ferreiro(self) -> bool:
        if self._player is None:
            return False
        return self._player.pos.distance_to(FERREIRO_NPC_POS) <= FERREIRO_INTERACT_RADIUS

    @property
    def ferreiro_screen_pos(self) -> pygame.Vector2:
        return pygame.Vector2(
            FERREIRO_NPC_POS.x + self._cam.x,
            FERREIRO_NPC_POS.y + self._cam.y,
        )

    @property
    def player_near_loja(self) -> bool:
        if self._player is None:
            return False
        return self._player.pos.distance_to(LOJA_NPC_POS) <= LOJA_INTERACT_RADIUS

    @property
    def loja_screen_pos(self) -> pygame.Vector2:
        return pygame.Vector2(
            LOJA_NPC_POS.x + self._cam.x,
            LOJA_NPC_POS.y + self._cam.y,
        )

    @property
    def player_near_talentos(self) -> bool:
        if self._player is None:
            return False
        return self._player.pos.distance_to(TALENTOS_NPC_POS) <= TALENTOS_INTERACT_RADIUS

    @property
    def talentos_screen_pos(self) -> pygame.Vector2:
        return pygame.Vector2(
            TALENTOS_NPC_POS.x + self._cam.x,
            TALENTOS_NPC_POS.y + self._cam.y,
        )

    def update(self, dt: float, keys, screen_w: int, screen_h: int):
        if self._market_map is None or self._player is None:
            return
        self._player.update(dt, keys)
        self._market_map.update(dt)
        if self._market_map.content_center:
            self._cam = compute_camera_fixed(self._market_map.content_center, screen_w, screen_h)
        else:
            self._cam = compute_camera(
                self._player.pos,
                self._market_map.pixel_width,
                self._market_map.pixel_height,
                screen_w, screen_h,
            )

    def draw(self, screen: pygame.Surface):
        if self._market_map is None or self._player is None:
            return
        self._market_map.draw_base(screen, self._cam)
        self._player.draw(screen, self._cam)
        self._market_map.draw_top(screen, self._cam)


# ---------------------------------------------------------------------------
# BlacksmithScene — interior da ferraria (Blacksmith_house_interior.tmx)
# ---------------------------------------------------------------------------

# Posição do NPC Ferreiro (Smith_anvil layer, centro do sprite 3×4 tiles)
# origin=(-16,-16): tile (1,-4) → norm_tile (17,12) → pixel (1088,768)
# Centro do sprite 3×4 → (1088 + 64, 768 + 128) = (1088, 896)
BLACKSMITH_FERREIRO_POS    = pygame.Vector2(1088, 896)
BLACKSMITH_FERREIRO_RADIUS = 220


class BlacksmithScene:
    """
    Cena do interior da ferraria.
    Câmera segue o jogador (compute_camera), colisão via camada 'Walls'.
    """

    def __init__(self, blacksmith_dir: str):
        self._dir    = blacksmith_dir
        self._map:    HubMap | None    = None
        self._player: HubPlayer | None = None
        self._cam     = pygame.Vector2(0, 0)

    def load_all(self):
        path = os.path.join(self._dir, "Blacksmith_house_interior.tmx")
        if os.path.exists(path):
            self._map = HubMap(path)
            self._map.load()
        else:
            print(f"[BlacksmithScene] Arquivo não encontrado: {path}")

    def load_surfaces_and_bake(self):
        if self._map is not None:
            self._map.load_surfaces()
            self._map.bake()

    def setup_player(self):
        if self._map is None:
            return
        self._player = HubPlayer(self._map)
        # Spawn perto da entrada (parte inferior do mapa)
        self._player.pos = pygame.Vector2(1088, 1200)

    def reset_spawn(self):
        """Reposiciona o jogador na entrada sem recriar instância."""
        if self._player is None or self._map is None:
            return
        self._player.pos = pygame.Vector2(1088, 1200)

    def apply_char_frames(
        self,
        dir_walk:      dict,
        dir_idle:      dict,
        walk_fallback: list | None = None,
        idle_fallback: list | None = None,
        anim_spd:      float = 0.10,
        idle_anim_spd: float = 0.13,
    ):
        if self._player:
            self._player.set_char_frames(
                dir_walk, dir_idle, walk_fallback, idle_fallback, anim_spd, idle_anim_spd
            )

    @property
    def player(self) -> "HubPlayer | None":
        return self._player

    @property
    def cam(self) -> pygame.Vector2:
        return self._cam

    @property
    def player_near_ferreiro(self) -> bool:
        if self._player is None:
            return False
        return self._player.pos.distance_to(BLACKSMITH_FERREIRO_POS) <= BLACKSMITH_FERREIRO_RADIUS

    @property
    def ferreiro_screen_pos(self) -> pygame.Vector2:
        return pygame.Vector2(
            BLACKSMITH_FERREIRO_POS.x + self._cam.x,
            BLACKSMITH_FERREIRO_POS.y + self._cam.y,
        )

    def update(self, dt: float, keys, screen_w: int, screen_h: int):
        if self._map is None or self._player is None:
            return
        self._player.update(dt, keys)
        self._map.update(dt)
        if self._map.content_center:
            self._cam = compute_camera_fixed(self._map.content_center, screen_w, screen_h)
        else:
            self._cam = compute_camera(
                self._player.pos,
                self._map.pixel_width,
                self._map.pixel_height,
                screen_w, screen_h,
            )

    def draw(self, screen: pygame.Surface):
        if self._map is None or self._player is None:
            return
        self._player.draw_scale = 1.5
        self._map.draw_base(screen, self._cam)
        self._player.draw(screen, self._cam)
        self._map.draw_top(screen, self._cam)
