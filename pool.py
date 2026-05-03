"""
Object pool para Particle — elimina alloc/GC repetitivo no late-game.

Uso:
    from pool import ParticlePool
    _pool = ParticlePool()
    _pool.spawn(particles_group, pos, color, size, speed, life)
"""
from collections import deque
import math
import random
import pygame


class ParticlePool:
    """
    Mantém uma fila de Particle inativos e os reutiliza via _reset().
    Nunca chama Particle.__init__ em sprites reciclados — apenas _reset().
    """
    __slots__ = ("_free", "_max_free", "_Particle")

    def __init__(self, max_free: int = 800):
        self._free: deque = deque()
        self._max_free = max_free
        self._Particle = None          # preenchido em _ensure_class()

    # ------------------------------------------------------------------
    def _ensure_class(self):
        if self._Particle is None:
            import jogo_final as _jf
            self._Particle = _jf.Particle

    # ------------------------------------------------------------------
    def spawn(self, group, pos, color, size, speed, life):
        """Obtém um Particle do pool (ou cria novo) e adiciona ao group."""
        self._ensure_class()
        if self._free:
            p = self._free.popleft()
        else:
            p = self._Particle.__new__(self._Particle)
            pygame.sprite.Sprite.__init__(p)
            p._pool = self
        p._reset(pos, color, size, speed, life)
        group.add(p)

    # ------------------------------------------------------------------
    def release(self, p):
        """Chamado pelo Particle quando expira — remove de todos os groups."""
        p.remove(*list(p.groups()))
        if len(self._free) < self._max_free:
            self._free.append(p)
