"""Sistema de mineração para a Sala de Recompensa."""
import random
import os
import pygame

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_ASSET_DIR = os.path.join(_BASE_DIR, "assets")

# ── Definições dos minérios ────────────────────────────────────────────────
ORE_DEFS = [
    {"name": "Cristal Negro",            "file": "Black_crystal1.png",        "color": (40,  40,  40 ), "weight": 2},
    {"name": "Cristal Azul",             "file": "Blue_crystal1.png",         "color": (60,  100, 200), "weight": 5},
    {"name": "Cristal Vermelho Escuro",  "file": "Dark_red_ crystal1.png",    "color": (140, 20,  20 ), "weight": 2},
    {"name": "Cristal Verde",            "file": "Green_crystal1.png",        "color": (40,  160, 40 ), "weight": 5},
    {"name": "Cristal Vermelho",         "file": "Red_crystal1.png",          "color": (220, 40,  40 ), "weight": 3},
    {"name": "Cristal Branco",           "file": "White_crystal1.png",        "color": (220, 220, 220), "weight": 3},
    {"name": "Cristal Amarelo",          "file": "Yellow_crystal1.png",       "color": (220, 200, 40 ), "weight": 5},
]

_ORE_WEIGHTS = [d["weight"] for d in ORE_DEFS]

ORE_SPRITE_SIZE = 72          # px — maior e visível
MINE_RADIUS_SQ  = 90 * 90     # pixels² — sem sqrt (raio ajustado para sprite maior)
MINE_DURATION   = 5.0         # segundos para minerar
_ORE_SEP_DIST   = ORE_SPRITE_SIZE * 1.35  # distância mínima entre centros


# ── Funções de escala por dificuldade ──────────────────────────────────────

def _spawn_count(difficulty: str, hardcore_stage: int) -> int:
    d = difficulty.upper()
    if d in ("FÁCIL", "FACIL"):
        return random.randint(2, 3)
    if d in ("MÉDIO", "MEDIO"):
        return random.randint(4, 6)
    if d in ("DIFÍCIL", "DIFICIL"):
        return random.randint(7, 10)
    lo = 10 + hardcore_stage * 2
    return random.randint(lo, lo + 2)


def _success_chance(difficulty: str, hardcore_stage: int) -> float:
    d = difficulty.upper()
    if d in ("FÁCIL", "FACIL"):
        return 0.85
    if d in ("MÉDIO", "MEDIO"):
        return 0.65
    if d in ("DIFÍCIL", "DIFICIL"):
        return 0.45
    t = max(0.0, min(1.0, (hardcore_stage - 1) / 9.0))
    return 0.40 - t * 0.20


# ── Nó de minério ─────────────────────────────────────────────────────────

class OreNode:
    __slots__ = ("idx", "pos", "image", "rect", "mined", "fail_timer", "dying")

    def __init__(self, idx: int, pos: pygame.Vector2, image: pygame.Surface):
        self.idx        = idx
        self.pos        = pygame.Vector2(pos)
        self.image      = image
        self.rect       = image.get_rect(center=(int(pos.x), int(pos.y)))
        self.mined      = False   # True → vai para inventário
        self.dying      = False   # True → falhou, fade-out e some
        self.fail_timer = 0.0     # > 0 → exibe "Falhou!" com fade


# ── Sistema principal ──────────────────────────────────────────────────────

class MiningSystem:
    def __init__(self, screen_w: int, screen_h: int,
                 difficulty: str, hardcore_stage: int):
        self.screen_w        = screen_w
        self.screen_h        = screen_h
        self.difficulty      = difficulty
        self.hardcore_stage  = hardcore_stage
        self.success_chance  = _success_chance(difficulty, hardcore_stage)
        self.ores: list      = []
        self.mining_target   = None
        self.mine_progress   = 0.0
        self._img_cache: dict = {}

    # ── Assets ────────────────────────────────────────────────────────────

    def _load_ore_image(self, idx: int, size: int = ORE_SPRITE_SIZE):
        key = (idx, size)
        if key in self._img_cache:
            return self._img_cache[key]
        fname = ORE_DEFS[idx]["file"]
        path  = os.path.join(_ASSET_DIR, "Teste", "recompensa", "minérios", fname)
        surf  = None
        try:
            raw  = pygame.image.load(path).convert_alpha()
            surf = pygame.transform.smoothscale(raw, (size, size))
        except Exception:
            surf = pygame.Surface((size, size), pygame.SRCALPHA)
            c    = ORE_DEFS[idx]["color"]
            surf.fill((c[0], c[1], c[2], 210))
            pygame.draw.rect(surf, (255, 255, 255, 80), surf.get_rect(), 1)
        self._img_cache[key] = surf
        return surf

    # ── Spawn + separação física ───────────────────────────────────────────

    def spawn_ores(self):
        """Gera minérios e aplica separação para evitar sobreposição."""
        count  = _spawn_count(self.difficulty, self.hardcore_stage)
        margin = ORE_SPRITE_SIZE // 2 + 12
        x_min  = int(self.screen_w * 0.12) + margin
        x_max  = int(self.screen_w * 0.88) - margin
        y_min  = int(self.screen_h * 0.30) + margin
        y_max  = int(self.screen_h * 0.72) - margin
        self.ores.clear()
        self.mining_target = None
        self.mine_progress = 0.0
        for _ in range(count):
            idx = random.choices(range(len(ORE_DEFS)), weights=_ORE_WEIGHTS, k=1)[0]
            img = self._load_ore_image(idx)
            px  = random.randint(x_min, x_max)
            py  = random.randint(y_min, y_max)
            self.ores.append(OreNode(idx, pygame.Vector2(px, py), img))
        self._separate(x_min, x_max, y_min, y_max, iterations=80)

    def _separate(self, x_min: int, x_max: int, y_min: int, y_max: int,
                  iterations: int = 80):
        """Empurra ores sobrepostos para eliminar colisões. O(n²) — n ≤ 32."""
        ores = self.ores
        min_d = _ORE_SEP_DIST
        min_d_sq = min_d * min_d
        for _ in range(iterations):
            any_overlap = False
            for i in range(len(ores)):
                for j in range(i + 1, len(ores)):
                    dx = ores[j].pos.x - ores[i].pos.x
                    dy = ores[j].pos.y - ores[i].pos.y
                    d_sq = dx * dx + dy * dy
                    if d_sq < min_d_sq and d_sq > 0.01:
                        d    = d_sq ** 0.5
                        push = (min_d - d) * 0.5
                        nx   = dx / d;  ny = dy / d
                        ores[i].pos.x -= nx * push
                        ores[i].pos.y -= ny * push
                        ores[j].pos.x += nx * push
                        ores[j].pos.y += ny * push
                        any_overlap = True
                # Mantém dentro dos limites após cada iteração
                ores[i].pos.x = max(x_min, min(x_max, ores[i].pos.x))
                ores[i].pos.y = max(y_min, min(y_max, ores[i].pos.y))
            if not any_overlap:
                break
        # Sincroniza rects
        for ore in ores:
            ore.rect.center = (int(ore.pos.x), int(ore.pos.y))

    # ── Update ─────────────────────────────────────────────────────────────

    def update(self, dt: float, player_pos: pygame.Vector2):
        for ore in self.ores:
            if ore.fail_timer > 0:
                ore.fail_timer = max(0.0, ore.fail_timer - dt)

        if self.mining_target is None:
            return

        if self.mining_target not in self.ores or self.mining_target.mined or self.mining_target.dying:
            self.mining_target = None
            self.mine_progress = 0.0
            return

        ore = self.mining_target
        dx  = player_pos.x - ore.pos.x
        dy  = player_pos.y - ore.pos.y
        if dx * dx + dy * dy > MINE_RADIUS_SQ * 4:
            self.mining_target = None
            self.mine_progress = 0.0
            return

        self.mine_progress += dt
        if self.mine_progress >= MINE_DURATION:
            self._resolve_mining()

    def _resolve_mining(self):
        ore = self.mining_target
        self.mining_target = None
        self.mine_progress = 0.0
        if ore is None:
            return
        if random.random() < self.success_chance:
            ore.mined = True
        else:
            # Falhou: inicia fade-out → some do chão sem ir ao inventário
            ore.dying      = True
            ore.fail_timer = 2.0

    # ── Input ──────────────────────────────────────────────────────────────

    def try_start_mining(self, player_pos: pygame.Vector2) -> bool:
        if self.mining_target is not None:
            return False
        best_ore = None
        best_dsq = MINE_RADIUS_SQ
        for ore in self.ores:
            if ore.mined or ore.dying:
                continue
            dx  = player_pos.x - ore.pos.x
            dy  = player_pos.y - ore.pos.y
            dsq = dx * dx + dy * dy
            if dsq <= best_dsq:
                best_dsq = dsq
                best_ore = ore
        if best_ore is None:
            return False
        self.mining_target = best_ore
        self.mine_progress = 0.0
        return True

    def cancel_mining(self):
        self.mining_target = None
        self.mine_progress = 0.0

    # ── Inventário ─────────────────────────────────────────────────────────

    @staticmethod
    def add_to_inventory(inventory: list, ore_idx: int) -> None:
        for slot in inventory:
            if (slot.get("category") == "Minérios"
                    and slot.get("idx") == ore_idx
                    and slot.get("qty", 1) < 20):
                slot["qty"] = slot.get("qty", 1) + 1
                return
        inventory.append({"category": "Minérios", "idx": ore_idx, "qty": 1})

    def collect_mined_ores(self, inventory: list) -> int:
        """Remove ores concluídos: adiciona ao inventário se mined=True,
        ou descarta silenciosamente se dying=True e fail_timer expirou."""
        to_collect = [o for o in self.ores if o.mined]
        to_discard = [o for o in self.ores if o.dying and o.fail_timer <= 0]
        for ore in to_collect:
            self.add_to_inventory(inventory, ore.idx)
        for ore in to_collect + to_discard:
            if ore in self.ores:
                self.ores.remove(ore)
        return len(to_collect)

    # ── Utilitário ─────────────────────────────────────────────────────────

    def nearest_interactable(self, player_pos: pygame.Vector2):
        best_ore = None
        best_dsq = MINE_RADIUS_SQ
        for ore in self.ores:
            if ore.mined or ore.dying:
                continue
            dx  = player_pos.x - ore.pos.x
            dy  = player_pos.y - ore.pos.y
            dsq = dx * dx + dy * dy
            if dsq <= best_dsq:
                best_dsq = dsq
                best_ore = ore
        return best_ore

    # ── Render ─────────────────────────────────────────────────────────────

    def render(self, screen: pygame.Surface, player_pos: pygame.Vector2,
               font_s: pygame.font.Font, font_m: pygame.font.Font):
        nearest = self.nearest_interactable(player_pos)

        for ore in self.ores:
            if ore.mined:
                continue

            if ore.dying:
                # Fade-out progressivo + label "Falhou!"
                alpha = int(min(255, (ore.fail_timer / 2.0) * 255))
                img_fade = ore.image.copy()
                img_fade.set_alpha(alpha)
                screen.blit(img_fade, ore.rect)
                if ore.fail_timer > 0.3:
                    txt = font_s.render("Falhou!", True, (230, 60, 60))
                    txt.set_alpha(alpha)
                    screen.blit(txt, txt.get_rect(centerx=ore.rect.centerx,
                                                   bottom=ore.rect.top - 4))
                continue

            screen.blit(ore.image, ore.rect)

            if ore is nearest:
                if self.mining_target is ore:
                    self._draw_progress(screen, ore, font_s)
                else:
                    self._draw_prompt(screen, ore, font_s)

    def _draw_prompt(self, screen: pygame.Surface, ore: "OreNode",
                     font: pygame.font.Font):
        ore_name = ORE_DEFS[ore.idx]["name"]
        line1    = font.render("[F] Minerar", True, (240, 220, 140))
        line2    = font.render(ore_name,      True, (180, 200, 220))
        pad_x, pad_y = 10, 5
        w  = max(line1.get_width(), line2.get_width()) + pad_x * 2
        h  = line1.get_height() + line2.get_height() + pad_y * 3
        bg = pygame.Surface((w, h), pygame.SRCALPHA)
        bg.fill((8, 6, 4, 175))
        r  = bg.get_rect(centerx=ore.rect.centerx, bottom=ore.rect.top - 6)
        screen.blit(bg, r)
        pygame.draw.rect(screen, (180, 150, 40), r, 1, border_radius=3)
        screen.blit(line1, line1.get_rect(centerx=r.centerx, top=r.top + pad_y))
        screen.blit(line2, line2.get_rect(centerx=r.centerx,
                                           top=r.top + pad_y + line1.get_height() + 2))

    def _draw_progress(self, screen: pygame.Surface, ore: "OreNode",
                       font: pygame.font.Font):
        pct    = min(1.0, self.mine_progress / MINE_DURATION)
        bw, bh = 90, 11
        bx     = ore.rect.centerx - bw // 2
        by     = ore.rect.top - 32

        pygame.draw.rect(screen, (20, 16, 12), (bx - 1, by - 1, bw + 2, bh + 2), border_radius=4)
        fill = (60, 190, 80) if pct < 0.75 else (200, 190, 50)
        pygame.draw.rect(screen, fill, (bx, by, int(bw * pct), bh), border_radius=3)
        pygame.draw.rect(screen, (140, 120, 50), (bx - 1, by - 1, bw + 2, bh + 2), 1, border_radius=4)

        txt = font.render("Minerando...", True, (200, 190, 150))
        screen.blit(txt, txt.get_rect(centerx=ore.rect.centerx, bottom=by - 2))
