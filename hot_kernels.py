"""
hot_kernels.py – Fachada para kernels de performance do UnderWorld Hero.

Tenta carregar hot_kernels_cy (Cython compilado). Se não estiver disponível,
cai automaticamente em implementações NumPy equivalentes.

Funções públicas:
    radius_indices(positions, cx, cy, radius_sq)  → ndarray[int64]
    nearest_index(positions, cx, cy, allowed_mask) → int
    batch_directions(positions, tx, ty, out)       → None  (escreve em out)
    astar(blocked_set, sx, sy, gx, gy, ...)       → list[(int,int)]
    positions_in_rect(positions, rx, ry, rw, rh)  → ndarray[int64]

CYTHON_ACTIVE: bool — True quando a extensão nativa está em uso.
"""

import heapq
import math
import importlib
import importlib.util

import numpy as np

# ─── Detecção do backend ──────────────────────────────────────────────────────

CYTHON_ACTIVE = False
_cy = None

# Flags individuais por kernel — o módulo compilado pode ser uma versão antiga
# que só tem radius_indices / nearest_index mas não os kernels novos.
_has_radius_indices     = False
_has_nearest_index      = False
_has_batch_directions   = False
_has_astar_cy           = False
_has_positions_in_rect  = False

try:
    spec = importlib.util.find_spec("hot_kernels_cy")
    if spec is not None:
        _cy = importlib.import_module("hot_kernels_cy")
        CYTHON_ACTIVE           = True
        _has_radius_indices     = hasattr(_cy, "radius_indices")
        _has_nearest_index      = hasattr(_cy, "nearest_index")
        _has_batch_directions   = hasattr(_cy, "batch_directions")
        _has_astar_cy           = hasattr(_cy, "astar_cy")
        _has_positions_in_rect  = hasattr(_cy, "positions_in_rect")
except Exception:
    pass


# ─── 1. radius_indices ────────────────────────────────────────────────────────

def radius_indices(positions, center_x: float, center_y: float, radius_sq: float):
    """Índices das posições dentro do raio² ao redor de (center_x, center_y)."""
    if _has_radius_indices:
        return _cy.radius_indices(positions, center_x, center_y, radius_sq)

    center = np.asarray((center_x, center_y), dtype=np.float32)
    delta  = positions - center
    dist_sq = delta[:, 0] * delta[:, 0] + delta[:, 1] * delta[:, 1]
    return np.nonzero(dist_sq <= radius_sq)[0]


# ─── 2. nearest_index ─────────────────────────────────────────────────────────

def nearest_index(positions, center_x: float, center_y: float, allowed_mask):
    """Índice do elemento mais próximo respeitando allowed_mask."""
    if _has_nearest_index:
        return _cy.nearest_index(positions, center_x, center_y, allowed_mask)

    if positions.size == 0 or not np.any(allowed_mask):
        return -1

    center  = np.asarray((center_x, center_y), dtype=np.float32)
    delta   = positions - center
    dist_sq = delta[:, 0] * delta[:, 0] + delta[:, 1] * delta[:, 1]
    dist_sq = np.where(allowed_mask > 0, dist_sq, np.inf)
    idx = int(np.argmin(dist_sq))
    return idx if np.isfinite(dist_sq[idx]) else -1


# ─── 3. batch_directions ──────────────────────────────────────────────────────

def batch_directions(positions, target_x: float, target_y: float, out):
    """
    Escreve em `out` a direção normalizada de cada posição em direção a (tx, ty).
    `out` deve ser np.zeros((n, 2), dtype=np.float32) alocado pelo chamador.
    """
    if _has_batch_directions:
        _cy.batch_directions(positions, target_x, target_y, out)
        return

    dx = target_x - positions[:, 0]
    dy = target_y - positions[:, 1]
    norm = np.sqrt(dx * dx + dy * dy)
    mask = norm > 1e-6
    out[mask, 0] = dx[mask] / norm[mask]
    out[mask, 1] = dy[mask] / norm[mask]
    out[~mask, :] = 0.0


# ─── 4. astar ─────────────────────────────────────────────────────────────────

def astar(blocked_set: set,
          sx: int, sy: int,
          gx: int, gy: int,
          margin: int = 20,
          max_iters: int = 600):
    """
    A* de (sx,sy) até (gx,gy) evitando células em blocked_set.
    Usa Cython quando disponível, fallback Python puro caso contrário.
    Retorna lista de tuplas (int, int) ou [] se não encontrar caminho.
    """
    if _has_astar_cy:
        return _cy.astar_cy(blocked_set, sx, sy, gx, gy, margin, max_iters)

    # ── fallback Python ────────────────────────────────────────────────────
    if sx == gx and sy == gy:
        return [(sx, sy)]

    min_x, max_x = min(sx, gx) - margin, max(sx, gx) + margin
    min_y, max_y = min(sy, gy) - margin, max(sy, gy) + margin

    h_start = abs(sx - gx) + abs(sy - gy)
    open_heap = [(h_start, 0, sx, sy)]
    came_from: dict = {}
    g_score   = {(sx, sy): 0}
    visited: set   = set()
    goal = (gx, gy)
    iters = 0

    while open_heap and iters < max_iters:
        iters += 1
        _, curr_g, cx, cy = heapq.heappop(open_heap)
        cell = (cx, cy)
        if cell in visited:
            continue
        visited.add(cell)

        if cell == goal:
            path = [cell]
            while cell in came_from:
                cell = came_from[cell]
                path.append(cell)
            path.reverse()
            return path

        for nx, ny in ((cx+1,cy),(cx-1,cy),(cx,cy+1),(cx,cy-1)):
            if nx < min_x or nx > max_x or ny < min_y or ny > max_y:
                continue
            nxt = (nx, ny)
            if nxt != goal and nxt in blocked_set:
                continue
            tg = curr_g + 1
            if tg < g_score.get(nxt, 10**9):
                came_from[nxt] = cell
                g_score[nxt]   = tg
                h = abs(nx - gx) + abs(ny - gy)
                heapq.heappush(open_heap, (tg + h, tg, nx, ny))

    return []


# ─── 5. positions_in_rect ─────────────────────────────────────────────────────

def positions_in_rect(positions, rx: float, ry: float, rw: float, rh: float):
    """Índices das posições dentro do retângulo (rx, ry, rw, rh)."""
    if _has_positions_in_rect:
        return _cy.positions_in_rect(positions, rx, ry, rw, rh)

    mask = ((positions[:, 0] >= rx) & (positions[:, 0] <= rx + rw) &
            (positions[:, 1] >= ry) & (positions[:, 1] <= ry + rh))
    return np.nonzero(mask)[0]
