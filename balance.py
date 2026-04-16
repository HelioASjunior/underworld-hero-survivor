"""
balance.py — Sistema de balanceamento e progressão para UnderWorldHero-Game.

Todas as constantes ficam em BalanceConfig.
Todas as fórmulas usam primitivos int/float e evitam ** para compatibilidade
com Cython (use x*x em vez de x**2).

Uso:
    from balance import BalanceConfig as Cfg, xp_to_level, enemy_scale,
                        upgrade_cost, drop_rate

"""


# ---------------------------------------------------------------------------
# Constantes centralizadas
# ---------------------------------------------------------------------------

class BalanceConfig:
    # ── XP ──────────────────────────────────────────────────────────────────
    XP_BASE: int   = 80    # XP necessário para passar do nível 1 → 2
    XP_LINEAR: int = 22    # incremento linear por nível
    XP_EXP_A: float = 6.0 # coeficiente da componente exponencial
    XP_EXP_E: float = 1.12 # expoente (use _pow_f() internamente)

    GEM_XP_BASE: int = 10  # XP por gema coletada (base, sem modificadores)

    # ── Escala de inimigos por tempo ─────────────────────────────────────────
    SCALE_PER_MIN: float = 0.20  # +20 % de HP/DMG por minuto de jogo
    SCALE_MIN: float     = 1.0   # mínimo (nunca enfraquece)
    SCALE_MAX: float     = 6.0   # teto para não tornar o fim impraticável

    # ── Spawn ────────────────────────────────────────────────────────────────
    SPAWN_BASE:  float = 0.20    # intervalo inicial entre spawns (s)
    SPAWN_MIN:   float = 0.10    # intervalo mínimo (pico do caos)
    SPAWN_DECAY: float = 500.0   # divisor: spawn_t = BASE - game_time/DECAY

    # ── Upgrades permanentes (loja do Hub) ───────────────────────────────────
    UPGRADE_COST_BASE:  int   = 300   # custo do nível 1
    UPGRADE_COST_EXP:   float = 1.55  # fator multiplicativo por nível
    UPGRADE_COST_CAP:   int   = 9999  # custo máximo por nível

    # ── Drops ────────────────────────────────────────────────────────────────
    DROP_GOLD_BASE:    float = 0.15   # chance base de ouro ao matar inimigo
    DROP_GOLD_DEF_BONUS: float = 0.10 # bônus máximo de chance via DEF do jogador
    DROP_GOLD_DEF_SCALE: int  = 200   # DEF total para atingir bônus máximo

    DROP_GEM_BASE:     float = 0.40   # chance base de gema
    DROP_GEM_ATK_BONUS: float = 0.20  # bônus máximo de chance via ATK
    DROP_GEM_ATK_SCALE: int   = 80    # ATK total para atingir bônus máximo

    DROP_ITEM_BASE:    float = 0.05   # chance base de item de equipamento
    DROP_ITEM_LUCK:    float = 0.03   # bônus por ponto de sorte (stat futuro)

    # ── Pacto: FRÁGIL ────────────────────────────────────────────────────────
    PACT_FRAGIL_XP_MULT: float = 1.30  # +30 % XP
    PACT_VELOC_GOLD_MULT: float = 1.50 # +50 % Ouro


# ---------------------------------------------------------------------------
# Funções de progressão de XP
# ---------------------------------------------------------------------------

def _pow_f(base: float, exp: float) -> float:
    """Potência via math.exp/log — evita ** para compatibilidade Cython."""
    import math
    if base <= 0.0:
        return 0.0
    return math.exp(exp * math.log(base))


def xp_to_level(level: int) -> int:
    """
    XP necessário para passar do `level` atual para o próximo.

    Fórmula: XP_BASE + (n * XP_LINEAR) + XP_EXP_A * n^XP_EXP_E
    onde n = level - 1.

    Exemplos (padrão):
        nível  1 →  80 XP
        nível  5 → 198 XP
        nível 10 → 322 XP
        nível 20 → 593 XP
    """
    c = BalanceConfig
    n: int = level - 1
    if n < 0:
        n = 0
    linear_part: int = n * c.XP_LINEAR
    exp_part: float  = c.XP_EXP_A * _pow_f(float(n), c.XP_EXP_E)
    return int(c.XP_BASE + linear_part + exp_part)


def gem_xp(pact: str) -> int:
    """XP concedido por gema, ajustado pelo pacto ativo."""
    base: int = BalanceConfig.GEM_XP_BASE
    if pact == "FRÁGIL":
        return int(base * BalanceConfig.PACT_FRAGIL_XP_MULT)
    return base


# ---------------------------------------------------------------------------
# Escala de inimigos por tempo de jogo
# ---------------------------------------------------------------------------

def enemy_scale(game_time: float) -> float:
    """
    Multiplicador de HP e dano dos inimigos baseado no tempo de jogo (segundos).

    Cresce linearmente +20 % por minuto, limitado entre SCALE_MIN e SCALE_MAX.

        scale(0 s)   = 1.00
        scale(60 s)  = 1.20
        scale(300 s) = 2.00
        scale(750 s) = 3.50  (≈ 12,5 min)
    """
    c = BalanceConfig
    raw: float = c.SCALE_MIN + (game_time / 60.0) * c.SCALE_PER_MIN
    if raw < c.SCALE_MIN:
        return c.SCALE_MIN
    if raw > c.SCALE_MAX:
        return c.SCALE_MAX
    return raw


def spawn_interval(game_time: float) -> float:
    """
    Intervalo entre spawns em segundos. Reduz linearmente até o mínimo.

        interval(0 s)   = 0.20 s
        interval(500 s) = 0.10 s  (mínimo, mantido daí em diante)
    """
    c = BalanceConfig
    raw: float = c.SPAWN_BASE - game_time / c.SPAWN_DECAY
    if raw < c.SPAWN_MIN:
        return c.SPAWN_MIN
    return raw


# ---------------------------------------------------------------------------
# Custo de upgrades permanentes
# ---------------------------------------------------------------------------

def upgrade_cost(base_cost: int, current_level: int) -> int:
    """
    Custo para comprar o próximo nível de um upgrade permanente.

    Usa `base_cost` definido por skill (e.g. [300, 600, 1200]) — se a lista de
    custos fixos estiver disponível, use-a diretamente; esta função serve como
    fallback dinâmico para skills sem lista pré-definida.

    Fórmula: base_cost * UPGRADE_COST_EXP ^ current_level
    (current_level = 0 → primeiro nível, custo = base_cost)
    """
    c = BalanceConfig
    if current_level <= 0:
        raw: int = base_cost
    else:
        raw = int(base_cost * _pow_f(c.UPGRADE_COST_EXP, float(current_level)))
    return min(raw, c.UPGRADE_COST_CAP)


# ---------------------------------------------------------------------------
# Taxas de drop
# ---------------------------------------------------------------------------

def _clamp01(v: float) -> float:
    if v < 0.0:
        return 0.0
    if v > 1.0:
        return 1.0
    return v


def drop_gold_chance(player_def: int) -> float:
    """
    Chance de dropar ouro ao matar um inimigo.

    Aumenta com a defesa do jogador (equipamentos) até um bônus máximo.
    Defesa alta reflete "saque de armadura" — mais resistência, mais recursos.
    """
    c = BalanceConfig
    bonus: float = c.DROP_GOLD_DEF_BONUS * _clamp01(float(player_def) / float(c.DROP_GOLD_DEF_SCALE))
    return _clamp01(c.DROP_GOLD_BASE + bonus)


def drop_gem_chance(player_atk: int) -> float:
    """
    Chance de dropar gema de XP ao matar um inimigo.

    Aumenta com o ATK do jogador (inimigos mortos mais rápido "soltam mais XP").
    """
    c = BalanceConfig
    bonus: float = c.DROP_GEM_ATK_BONUS * _clamp01(float(player_atk) / float(c.DROP_GEM_ATK_SCALE))
    return _clamp01(c.DROP_GEM_BASE + bonus)


def drop_item_chance(luck: int = 0) -> float:
    """
    Chance de dropar item de equipamento ao matar um inimigo.

    `luck` é um stat reservado para expansão futura.
    """
    c = BalanceConfig
    return _clamp01(c.DROP_ITEM_BASE + luck * c.DROP_ITEM_LUCK)


# ---------------------------------------------------------------------------
# Gold multiplicador por pacto
# ---------------------------------------------------------------------------

def gold_mult(pact: str) -> float:
    """Multiplicador de ouro coletado para o pacto ativo."""
    if pact == "VELOCIDADE":
        return BalanceConfig.PACT_VELOC_GOLD_MULT
    return 1.0
