# cython: language_level=3, boundscheck=False, wraparound=False, cdivision=True
# ─────────────────────────────────────────────────────────────────────────────
# hot_kernels_cy.pyx  –  Extensões Cython para UnderWorld Hero
#
# Compilar:  python build_cython.py build_ext --inplace
#
# Funções exportadas:
#   radius_indices      – inimigos dentro de raio (colisão de projeteis)
#   nearest_index       – inimigo mais próximo (targeting)
#   batch_directions    – direções normalizadas para N inimigos em batch
#   astar_cy            – A* com tipos C, sem overhead de atributos Python
#   positions_in_rect   – contagem/índices dentro de retângulo (ataques AOE)
# ─────────────────────────────────────────────────────────────────────────────

import numpy as np
cimport numpy as cnp
from libc.math cimport sqrt, fabs
import heapq


# ── 1. radius_indices ─────────────────────────────────────────────────────────
# Retorna índices das posições dentro do raio ao redor de (center_x, center_y).
# Usada para: colisão projetil→inimigos, coleta de gemas, pick-up range.

def radius_indices(cnp.ndarray[cnp.float32_t, ndim=2] positions,
                   float center_x, float center_y, float radius_sq):
    cdef Py_ssize_t i, n = positions.shape[0]
    cdef float dx, dy
    cdef list out = []

    for i in range(n):
        dx = positions[i, 0] - center_x
        dy = positions[i, 1] - center_y
        if dx * dx + dy * dy <= radius_sq:
            out.append(i)

    return np.asarray(out, dtype=np.int64)


# ── 2. nearest_index ──────────────────────────────────────────────────────────
# Retorna índice do inimigo mais próximo respeitando máscara de exclusão.
# Usada para: targeting de personagens com habilidades de foco.

def nearest_index(cnp.ndarray[cnp.float32_t, ndim=2] positions,
                  float center_x, float center_y,
                  cnp.ndarray[cnp.uint8_t, ndim=1] allowed_mask):
    cdef Py_ssize_t i, n = positions.shape[0]
    cdef float dx, dy, d2
    cdef float best = 3.4028235e+38
    cdef int best_i = -1

    for i in range(n):
        if allowed_mask[i] == 0:
            continue
        dx = positions[i, 0] - center_x
        dy = positions[i, 1] - center_y
        d2 = dx * dx + dy * dy
        if d2 < best:
            best = d2
            best_i = i

    return best_i


# ── 3. batch_directions ───────────────────────────────────────────────────────
# Calcula direção normalizada de N posições em direção a um alvo.
# Escrito em out_directions (mesmo shape que positions, alocado pelo chamador).
# Usada para: movimento em batch de inimigos sem obstáculos.
# Ganho: elimina loop Python + sqrt Python por inimigo → C puro.

def batch_directions(cnp.ndarray[cnp.float32_t, ndim=2] positions,
                     float target_x, float target_y,
                     cnp.ndarray[cnp.float32_t, ndim=2] out_directions):
    cdef Py_ssize_t i, n = positions.shape[0]
    cdef float dx, dy, norm

    for i in range(n):
        dx = target_x - positions[i, 0]
        dy = target_y - positions[i, 1]
        norm = sqrt(dx * dx + dy * dy)
        if norm > 1e-6:
            out_directions[i, 0] = dx / norm
            out_directions[i, 1] = dy / norm
        else:
            out_directions[i, 0] = 0.0
            out_directions[i, 1] = 0.0


# ── 4. astar_cy ───────────────────────────────────────────────────────────────
# A* Cython-acelerado: variáveis internas com tipos C, sem lookups de atributo.
# Aceita um set Python de tuplas (cx, cy) como células bloqueadas — lookup O(1).
# Usada por: ObstacleGridIndex.next_direction quando Cython está ativo.
# Ganho típico: 4-8x vs implementação Python pura (heapq já é C, o resto não).

def astar_cy(object blocked_set,
             int sx, int sy,
             int gx, int gy,
             int margin=20,
             int max_iters=600):
    """
    A* de célula (sx,sy) até (gx,gy) evitando células em blocked_set.
    blocked_set: Python set de (int, int).
    Retorna lista de (int, int) ou [] se caminho não encontrado.
    """
    if sx == gx and sy == gy:
        return [(sx, sy)]

    cdef int min_x = sx - margin if sx < gx else gx - margin
    cdef int max_x = sx + margin if sx > gx else gx + margin
    cdef int min_y = sy - margin if sy < gy else gy - margin
    cdef int max_y = sy + margin if sy > gy else gy + margin

    cdef int iters = 0
    cdef int cx, cy, nx, ny
    cdef int tentative_g, curr_g, h, f

    h = abs(sx - gx) + abs(sy - gy)
    open_heap = [(h, 0, sx, sy)]
    came_from  = {}
    g_score    = {(sx, sy): 0}
    visited    = set()
    goal       = (gx, gy)

    while open_heap and iters < max_iters:
        iters += 1
        f, curr_g, cx, cy = heapq.heappop(open_heap)
        cell = (cx, cy)

        if cell in visited:
            continue
        visited.add(cell)

        if cx == gx and cy == gy:
            path = [cell]
            while cell in came_from:
                cell = came_from[cell]
                path.append(cell)
            path.reverse()
            return path

        for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
            if nx < min_x or nx > max_x or ny < min_y or ny > max_y:
                continue
            nxt = (nx, ny)
            if nxt != goal and nxt in blocked_set:
                continue
            tentative_g = curr_g + 1
            if tentative_g < g_score.get(nxt, 2147483647):
                came_from[nxt] = cell
                g_score[nxt]   = tentative_g
                h = abs(nx - gx) + abs(ny - gy)
                heapq.heappush(open_heap, (tentative_g + h, tentative_g, nx, ny))

    return []


# ── 5. positions_in_rect ──────────────────────────────────────────────────────
# Retorna índices das posições dentro do retângulo (rx, ry, rw, rh).
# Usada para: ataques AOE retangulares (slash do Guerreiro, cone do Caçador).

def positions_in_rect(cnp.ndarray[cnp.float32_t, ndim=2] positions,
                      float rx, float ry, float rw, float rh):
    cdef Py_ssize_t i, n = positions.shape[0]
    cdef float px, py
    cdef list out = []

    for i in range(n):
        px = positions[i, 0]
        py = positions[i, 1]
        if px >= rx and px <= rx + rw and py >= ry and py <= ry + rh:
            out.append(i)

    return np.asarray(out, dtype=np.int64)
