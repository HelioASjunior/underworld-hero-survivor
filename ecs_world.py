"""Lightweight ECS (Entity-Component-System) world for UnderWorld Hero.

No external dependencies. Entities are integer IDs. Components are pure
dataclass instances stored per-entity. Systems receive (world, dt) each frame.

Usage:
    world = World()
    world.add_system(MySystem())
    eid = world.create_entity(Position(x=0, y=0), Health(hp=100))
    world.context['p_pos'] = player.pos
    world.process(dt)   # runs all registered systems in order
"""

from __future__ import annotations
from typing import Any, Generator, Tuple


class World:
    """Central registry of entities, components, and systems."""

    __slots__ = ("_entities", "_next_id", "_systems", "context")

    def __init__(self) -> None:
        self._entities: dict[int, dict[type, Any]] = {}
        self._next_id: int = 0
        self._systems: list = []
        # Per-frame shared state injected before world.process(dt).
        # Systems read from this dict instead of receiving many positional args.
        self.context: dict[str, Any] = {}

    # ── Entity lifecycle ──────────────────────────────────────────────────────

    def create_entity(self, *components) -> int:
        eid = self._next_id
        self._next_id += 1
        self._entities[eid] = {type(c): c for c in components}
        return eid

    def delete_entity(self, entity_id: int) -> None:
        self._entities.pop(entity_id, None)

    def entity_count(self) -> int:
        return len(self._entities)

    # ── Component access ──────────────────────────────────────────────────────

    def add_component(self, entity_id: int, component: Any) -> None:
        comps = self._entities.get(entity_id)
        if comps is not None:
            comps[type(component)] = component

    def get_component(self, entity_id: int, component_type: type) -> Any:
        comps = self._entities.get(entity_id)
        return comps.get(component_type) if comps is not None else None

    def has_component(self, entity_id: int, component_type: type) -> bool:
        comps = self._entities.get(entity_id)
        return comps is not None and component_type in comps

    # ── Batch query — primary entry point for systems ─────────────────────────

    def get_components(self, *types) -> Generator[Tuple[int, tuple], None, None]:
        """Yield (eid, (comp_a, comp_b, ...)) for every entity that has all types."""
        for eid, comps in self._entities.items():
            if all(t in comps for t in types):
                yield eid, tuple(comps[t] for t in types)

    # ── System management ─────────────────────────────────────────────────────

    def add_system(self, system: Any) -> None:
        self._systems.append(system)

    def clear_systems(self) -> None:
        self._systems.clear()

    # ── Main frame tick ───────────────────────────────────────────────────────

    def process(self, dt: float) -> None:
        """Run all registered systems in order."""
        for system in self._systems:
            system.process(self, dt)

    # ── Lifecycle helpers ─────────────────────────────────────────────────────

    def clear_all(self) -> None:
        """Remove all entities. Called when a run resets."""
        self._entities.clear()

    def register_enemy(self, enemy) -> int:
        """Register an Enemy sprite as a new ECS entity and return its ID.

        Components stored here are lightweight descriptors; the canonical
        state (pos, hp, AI timers …) lives in the component objects that
        Enemy.__init__ creates and stores on self.
        """
        from ecs_components import EnemyTag, Renderable
        eid = self.create_entity(
            EnemyTag(
                kind=enemy.kind,
                is_elite=enemy.is_elite,
                gold_drops=getattr(enemy, "gold_drops", 0),
            ),
            enemy._pos_comp,
            enemy._health_comp,
            enemy._vel_comp,
            enemy._ai_comp,
            enemy._combat_comp,
            enemy._anim_comp,
            Renderable(sprite=enemy),
        )
        enemy._ecs_id = eid
        return eid
