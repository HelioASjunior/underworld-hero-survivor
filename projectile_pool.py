"""
Object pool para Projectile e MeleeSlash — elimina alloc/GC repetitivo durante o combate.

Uso:
    from projectile_pool import ProjectilePool, MeleeSlashPool
    _projectile_pool = ProjectilePool()
    _melee_pool = MeleeSlashPool()
    
    # Em vez de: projectile = CoreProjectile(pos, vel, dmg, frames)
    # Use: projectile = _projectile_pool.spawn(pos, vel, dmg, frames)
"""

from collections import deque
import pygame


class ProjectilePool:
    """
    Mantém uma fila de Projectile inativos e os reutiliza.
    Não chama __init__ em sprites reciclados — apenas _reset().
    """
    __slots__ = ("_free", "_max_free", "_ProjectileClass", "_group")

    def __init__(self, max_free: int = 256):
        self._free: deque = deque()
        self._max_free = max_free
        self._ProjectileClass = None
        self._group = None  # referência ao grupo de projéteis

    def set_projectile_class(self, cls):
        """Define a classe Projectile a ser usada no pool."""
        self._ProjectileClass = cls

    def set_group(self, group):
        """Define o grupo de sprites onde os projéteis serão adicionados."""
        self._group = group

    def spawn(self, pos, vel, dmg, frames, pierce=0, ricochet=0, screen_size_getter=None):
        """Obtém um Projectile do pool (ou cria novo) e adiciona ao group."""
        if self._ProjectileClass is None:
            raise RuntimeError("ProjectileClass não foi definida. Use set_projectile_class().")
        if self._group is None:
            raise RuntimeError("Group não foi definida. Use set_group().")

        if self._free:
            p = self._free.popleft()
            # Reseta o projétil com novos valores
            p._reset(pos, vel, dmg, frames, pierce, ricochet, screen_size_getter)
        else:
            # Cria novo projétil
            p = self._ProjectileClass.__new__(self._ProjectileClass)
            pygame.sprite.Sprite.__init__(p)
            p._pool = self
            p._reset(pos, vel, dmg, frames, pierce, ricochet, screen_size_getter)
        
        self._group.add(p)
        return p

    def release(self, p):
        """Chamado pelo Projectile quando deve ser reciclado."""
        p.remove(*list(p.groups()))
        if len(self._free) < self._max_free:
            self._free.append(p)


class MeleeSlashPool:
    """
    Mantém uma fila de MeleeSlash inativos e os reutiliza.
    """
    __slots__ = ("_free", "_max_free", "_MeleeSlashClass", "_group")

    def __init__(self, max_free: int = 128):
        self._free: deque = deque()
        self._max_free = max_free
        self._MeleeSlashClass = None
        self._group = None

    def set_melee_class(self, cls):
        """Define a classe MeleeSlash a ser usada no pool."""
        self._MeleeSlashClass = cls

    def set_group(self, group):
        """Define o grupo de sprites onde os golpes serão adicionados."""
        self._group = group

    def spawn(self, player, target_dir, dmg, frames):
        """Obtém um MeleeSlash do pool (ou cria novo) e adiciona ao group."""
        if self._MeleeSlashClass is None:
            raise RuntimeError("MeleeSlashClass não foi definida. Use set_melee_class().")
        if self._group is None:
            raise RuntimeError("Group não foi definida. Use set_group().")

        if self._free:
            m = self._free.popleft()
            m._reset(player, target_dir, dmg, frames)
        else:
            m = self._MeleeSlashClass.__new__(self._MeleeSlashClass)
            pygame.sprite.Sprite.__init__(m)
            m._pool = self
            m._reset(player, target_dir, dmg, frames)
        
        self._group.add(m)
        return m

    def release(self, m):
        """Chamado pelo MeleeSlash quando termina sua animação."""
        m.remove(*list(m.groups()))
        if len(self._free) < self._max_free:
            self._free.append(m)


# Pools globais (inicializados no main)
projectile_pool: ProjectilePool | None = None
melee_slash_pool: MeleeSlashPool | None = None


def init_pools():
    """Inicializa os pools globais. Chamado uma vez no início do jogo."""
    global projectile_pool, melee_slash_pool
    projectile_pool = ProjectilePool(max_free=256)
    melee_slash_pool = MeleeSlashPool(max_free=128)
