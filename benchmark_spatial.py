import random
import time
from dataclasses import dataclass

import numpy as np

from spatial_index import EnemyBatchIndex, ObstacleGridIndex


@dataclass
class MockObstacle:
    hitbox: object


@dataclass
class MockEnemy:
    pos: object
    hp: int = 10

    def alive(self):
        return self.hp > 0


@dataclass
class Vec2:
    x: float
    y: float


@dataclass
class Rect:
    left: int
    top: int
    width: int
    height: int

    @property
    def right(self):
        return self.left + self.width

    @property
    def bottom(self):
        return self.top + self.height

    def collidepoint(self, point):
        return self.left <= point.x <= self.right and self.top <= point.y <= self.bottom


def make_scene(n_obstacles=450, n_enemies=1000, world=8000):
    obstacles = []
    for _ in range(n_obstacles):
        w = random.randint(48, 120)
        h = random.randint(48, 120)
        x = random.randint(-world, world)
        y = random.randint(-world, world)
        obstacles.append(MockObstacle(Rect(x, y, w, h)))

    enemies = []
    for _ in range(n_enemies):
        x = random.uniform(-world, world)
        y = random.uniform(-world, world)
        enemies.append(MockEnemy(Vec2(x, y)))

    return obstacles, enemies


def bench_legacy(obstacles, enemies, frames=500):
    points = [Vec2(random.uniform(-7000, 7000), random.uniform(-7000, 7000)) for _ in range(900)]
    centers = [Vec2(random.uniform(-7000, 7000), random.uniform(-7000, 7000)) for _ in range(frames)]

    t0 = time.perf_counter()
    for i in range(frames):
        p = points[i % len(points)]
        _ = any(obs.hitbox.collidepoint(p) for obs in obstacles)

        c = centers[i]
        rad = 260.0
        _ = [e for e in enemies if ((e.pos.x - c.x) ** 2 + (e.pos.y - c.y) ** 2) <= (rad * rad)]

        near = None
        best = float("inf")
        for e in enemies:
            d2 = (e.pos.x - p.x) ** 2 + (e.pos.y - p.y) ** 2
            if d2 < best:
                best = d2
                near = e
        _ = near

    t1 = time.perf_counter()
    return (t1 - t0) * 1000.0 / frames


def bench_indexed(obstacles, enemies, frames=500):
    obstacle_index = ObstacleGridIndex(cell_size=64)
    obstacle_index.rebuild(obstacles)
    enemy_index = EnemyBatchIndex()
    enemy_index.rebuild(enemies)

    points = [Vec2(random.uniform(-7000, 7000), random.uniform(-7000, 7000)) for _ in range(900)]
    centers = [Vec2(random.uniform(-7000, 7000), random.uniform(-7000, 7000)) for _ in range(frames)]

    t0 = time.perf_counter()
    for i in range(frames):
        p = points[i % len(points)]
        _ = obstacle_index.point_collides(p)

        c = centers[i]
        _ = enemy_index.enemies_in_radius(c, 260.0)
        _ = enemy_index.nearest_enemy(p)
    t1 = time.perf_counter()

    return (t1 - t0) * 1000.0 / frames


def bench_astar(obstacles, frames=250):
    obstacle_index = ObstacleGridIndex(cell_size=64)
    obstacle_index.rebuild(obstacles)

    starts = [Vec2(random.uniform(-6000, 6000), random.uniform(-6000, 6000)) for _ in range(frames)]
    goals = [Vec2(random.uniform(-6000, 6000), random.uniform(-6000, 6000)) for _ in range(frames)]

    t0 = time.perf_counter()
    hits = 0
    for i in range(frames):
        d = obstacle_index.next_direction(starts[i], goals[i])
        if d is not None:
            hits += 1
    t1 = time.perf_counter()

    avg = (t1 - t0) * 1000.0 / frames
    return avg, hits


def main():
    random.seed(42)
    np.random.seed(42)

    obstacles, enemies = make_scene()

    legacy_ms = bench_legacy(obstacles, enemies)
    indexed_ms = bench_indexed(obstacles, enemies)
    astar_ms, astar_hits = bench_astar(obstacles)

    speedup = (legacy_ms / indexed_ms) if indexed_ms > 0 else 0.0

    print("=== Benchmark Espacial (ms/frame médio) ===")
    print(f"Legacy (loops puros): {legacy_ms:.3f} ms/frame")
    print(f"Indexed (NumPy + grid): {indexed_ms:.3f} ms/frame")
    print(f"Ganho aproximado: {speedup:.2f}x")
    print()
    print("=== Benchmark A* Grid ===")
    print(f"A* next_direction: {astar_ms:.3f} ms/chamada")
    print(f"Caminhos válidos: {astar_hits}/{250}")


if __name__ == "__main__":
    main()
