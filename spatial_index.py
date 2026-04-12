import heapq
import math
import time
import collections

import numpy as np

try:
    from hot_kernels import nearest_index  as kernel_nearest_index
    from hot_kernels import radius_indices as kernel_radius_indices
    from hot_kernels import batch_directions as kernel_batch_directions
    from hot_kernels import astar           as kernel_astar
    from hot_kernels import positions_in_rect as kernel_positions_in_rect
    from hot_kernels import CYTHON_ACTIVE   as _CYTHON_ACTIVE
except Exception:
    kernel_nearest_index    = None
    kernel_radius_indices   = None
    kernel_batch_directions = None
    kernel_astar            = None
    kernel_positions_in_rect = None
    _CYTHON_ACTIVE = False


class PerfStats:
    """Coleta métricas por frame para o overlay de debug."""

    _HISTORY = 60

    def __init__(self):
        self.frame_times: collections.deque = collections.deque(maxlen=self._HISTORY)
        self.spatial_queries: int = 0
        self.astar_calls: int = 0
        self.astar_cache_hits: int = 0
        self._frame_start: float = 0.0

    def begin_frame(self):
        self._frame_start = time.perf_counter()
        self.spatial_queries = 0
        self.astar_calls = 0
        self.astar_cache_hits = 0

    def end_frame(self):
        elapsed_ms = (time.perf_counter() - self._frame_start) * 1000.0
        self.frame_times.append(elapsed_ms)

    def record_spatial_query(self):
        self.spatial_queries += 1

    def record_astar(self, cache_hit: bool):
        self.astar_calls += 1
        if cache_hit:
            self.astar_cache_hits += 1

    @property
    def avg_frame_ms(self) -> float:
        if not self.frame_times:
            return 0.0
        return sum(self.frame_times) / len(self.frame_times)

    @property
    def astar_hit_rate(self) -> float:
        if self.astar_calls == 0:
            return 1.0
        return self.astar_cache_hits / self.astar_calls


# Instância global compartilhada por todo o código de performance
PERF = PerfStats()


class ObstacleGridIndex:
    """Índice espacial em grid para colisão ponto-obstáculo."""

    def __init__(self, cell_size=64):
        self.cell_size = max(8, int(cell_size))
        self._bounds = None
        self._grid = np.zeros((0, 0), dtype=np.uint8)
        self._cells = {}
        self._cells_set: set = set()
        self._path_cache = {}

    def clear(self):
        self._bounds = None
        self._grid = np.zeros((0, 0), dtype=np.uint8)
        self._cells.clear()
        self._cells_set: set = set()   # set de chaves para astar_cy
        self._path_cache.clear()

    def rebuild(self, obstacles):
        obstacle_list = list(obstacles)
        if not obstacle_list:
            self.clear()
            return

        min_cx = min(obs.hitbox.left // self.cell_size for obs in obstacle_list)
        max_cx = max(obs.hitbox.right // self.cell_size for obs in obstacle_list)
        min_cy = min(obs.hitbox.top // self.cell_size for obs in obstacle_list)
        max_cy = max(obs.hitbox.bottom // self.cell_size for obs in obstacle_list)

        width = int(max_cx - min_cx + 1)
        height = int(max_cy - min_cy + 1)

        self._bounds = (int(min_cx), int(min_cy), int(max_cx), int(max_cy))
        self._grid = np.zeros((height, width), dtype=np.uint8)
        self._cells = {}
        self._path_cache.clear()

        for obs in obstacle_list:
            left = obs.hitbox.left // self.cell_size
            right = obs.hitbox.right // self.cell_size
            top = obs.hitbox.top // self.cell_size
            bottom = obs.hitbox.bottom // self.cell_size

            gx0 = int(left - min_cx)
            gx1 = int(right - min_cx)
            gy0 = int(top - min_cy)
            gy1 = int(bottom - min_cy)
            self._grid[gy0 : gy1 + 1, gx0 : gx1 + 1] = 1

            for cy in range(top, bottom + 1):
                for cx in range(left, right + 1):
                    self._cells.setdefault((cx, cy), []).append(obs)

        # Set de chaves para astar_cy (lookup O(1) sem overhead de dict values)
        self._cells_set = set(self._cells.keys())

    def point_collides(self, point):
        PERF.record_spatial_query()
        if self._bounds is None or self._grid.size == 0:
            return False

        cx = int(point.x) // self.cell_size
        cy = int(point.y) // self.cell_size
        min_cx, min_cy, max_cx, max_cy = self._bounds

        if cx < min_cx or cx > max_cx or cy < min_cy or cy > max_cy:
            return False

        gx = cx - min_cx
        gy = cy - min_cy
        if self._grid[gy, gx] == 0:
            return False

        for obs in self._cells.get((cx, cy), []):
            if obs.hitbox.collidepoint(point):
                return True
        return False

    def _to_cell(self, point):
        return (int(point.x) // self.cell_size, int(point.y) // self.cell_size)

    def _is_blocked(self, cell):
        return cell in self._cells

    @staticmethod
    def _heuristic(a, b):
        return abs(a[0] - b[0]) + abs(a[1] - b[1])

    @staticmethod
    def _neighbors(cell):
        cx, cy = cell
        yield (cx + 1, cy)
        yield (cx - 1, cy)
        yield (cx, cy + 1)
        yield (cx, cy - 1)

    def _astar(self, start_cell, goal_cell, search_margin=20, max_iters=600):
        """Delega para kernel_astar (Cython) quando disponível, fallback Python."""
        if kernel_astar is not None:
            return kernel_astar(
                self._cells_set,
                start_cell[0], start_cell[1],
                goal_cell[0],  goal_cell[1],
                search_margin, max_iters,
            )

        # ── fallback Python puro ───────────────────────────────────────────
        if start_cell == goal_cell:
            return [start_cell]

        min_x = min(start_cell[0], goal_cell[0]) - search_margin
        max_x = max(start_cell[0], goal_cell[0]) + search_margin
        min_y = min(start_cell[1], goal_cell[1]) - search_margin
        max_y = max(start_cell[1], goal_cell[1]) + search_margin

        open_heap = []
        heapq.heappush(open_heap, (self._heuristic(start_cell, goal_cell), 0, start_cell))
        came_from = {}
        g_score   = {start_cell: 0}
        visited   = set()
        iters     = 0

        while open_heap and iters < max_iters:
            iters += 1
            _, current_g, current = heapq.heappop(open_heap)
            if current in visited:
                continue
            visited.add(current)

            if current == goal_cell:
                path = [current]
                while current in came_from:
                    current = came_from[current]
                    path.append(current)
                path.reverse()
                return path

            for nxt in self._neighbors(current):
                nx, ny = nxt
                if nx < min_x or nx > max_x or ny < min_y or ny > max_y:
                    continue
                if nxt != goal_cell and self._is_blocked(nxt):
                    continue
                tentative_g = current_g + 1
                if tentative_g < g_score.get(nxt, 10**9):
                    came_from[nxt] = current
                    g_score[nxt]   = tentative_g
                    f_score = tentative_g + self._heuristic(nxt, goal_cell)
                    heapq.heappush(open_heap, (f_score, tentative_g, nxt))

        return []

    def next_direction(self, start_point, goal_point):
        if not self._cells:
            return None

        start_cell = self._to_cell(start_point)
        goal_cell = self._to_cell(goal_point)
        cache_key = (start_cell, goal_cell)

        path = self._path_cache.get(cache_key)
        if path is None:
            PERF.record_astar(cache_hit=False)
            path = self._astar(start_cell, goal_cell)
            self._path_cache[cache_key] = path
        else:
            PERF.record_astar(cache_hit=True)

        if not path:
            return None

        next_cell = path[1] if len(path) > 1 else path[0]
        target_x = (next_cell[0] + 0.5) * self.cell_size
        target_y = (next_cell[1] + 0.5) * self.cell_size

        dx = target_x - float(start_point.x)
        dy = target_y - float(start_point.y)
        norm = math.hypot(dx, dy)
        if norm <= 1e-6:
            return None
        return (dx / norm, dy / norm)


class EnemyBatchIndex:
    """Índice vetorizado com NumPy para consultas espaciais de inimigos."""

    def __init__(self):
        self._enemies = []
        self._positions = np.zeros((0, 2), dtype=np.float32)

    def rebuild(self, enemies):
        alive = [enemy for enemy in enemies if enemy.alive() and getattr(enemy, "hp", 0) > 0]
        self._enemies = alive
        if alive:
            self._positions = np.asarray([(enemy.pos.x, enemy.pos.y) for enemy in alive], dtype=np.float32)
        else:
            self._positions = np.zeros((0, 2), dtype=np.float32)

    def enemies_in_radius(self, center, radius):
        PERF.record_spatial_query()
        if self._positions.size == 0:
            return []

        center_x = float(center.x)
        center_y = float(center.y)
        radius_sq = float(radius * radius)

        if kernel_radius_indices is not None:
            idxs = kernel_radius_indices(self._positions, center_x, center_y, radius_sq)
        else:
            center_np = np.asarray((center_x, center_y), dtype=np.float32)
            delta = self._positions - center_np
            dist_sq = (delta[:, 0] * delta[:, 0]) + (delta[:, 1] * delta[:, 1])
            idxs = np.nonzero(dist_sq <= radius_sq)[0]

        return [self._enemies[int(i)] for i in idxs]

    def nearest_enemy(self, point, excluded=None):
        PERF.record_spatial_query()
        if self._positions.size == 0:
            return None

        excluded = excluded or set()
        center_x = float(point.x)
        center_y = float(point.y)
        allowed_mask = np.asarray([id(enemy) not in excluded for enemy in self._enemies], dtype=np.uint8)

        if not allowed_mask.any():
            return None

        if kernel_nearest_index is not None:
            idx = int(kernel_nearest_index(self._positions, center_x, center_y, allowed_mask))
            if idx < 0:
                return None
        else:
            point_np = np.asarray((center_x, center_y), dtype=np.float32)
            delta = self._positions - point_np
            dist_sq = (delta[:, 0] * delta[:, 0]) + (delta[:, 1] * delta[:, 1])
            dist_sq = np.where(allowed_mask > 0, dist_sq, np.inf)
            idx = int(np.argmin(dist_sq))
            if not np.isfinite(dist_sq[idx]):
                return None

        return self._enemies[idx]
