"""crafting_system.py — Dados do sistema de Crafting do Ferreiro."""

# ── Assets por categoria ───────────────────────────────────────────────────
# Cada entrada: folder relativo a assets/ui/itens_craft/, lista de arquivos
CRAFTED_CATEGORIES: dict[str, dict] = {
    "Cajados Lendários": {
        "folder": "cajados",
        "files":  ["Icon44.png", "Icon45.png"],
    },
    "Espadas Lendárias": {
        "folder": "espadas",
        "files":  ["Icon30.png", "Icon31.png", "Icon39.png", "Icon40.png",
                   "Icon42.png", "Icon43.png", "Icon48.png"],
    },
    "Machados Lendários": {
        "folder": "machados",
        "files":  ["Icon42.png", "Icon46.png"],
    },
    "Martelos Lendários": {
        "folder": "hammers",
        "files":  ["Icon34.png", "Icon36.png", "Icon45.png"],
    },
}

# ── Stats das Armas Lendárias ──────────────────────────────────────────────
# Superiores aos melhores itens da loja (max ~250 ATQ).
# price=0 indica que não podem ser vendidas.
CRAFTED_WEAPON_STATS: dict[str, list[dict]] = {
    "Cajados Lendários": [
        {"name": "Cajado das Almas",          "atk": 285, "def":  8, "price": 0, "level": 40},
        {"name": "Cajado do Abismo Eterno",   "atk": 355, "def": 14, "price": 0, "level": 50},
    ],
    "Espadas Lendárias": [
        {"name": "Espada da Aurora",           "atk": 300, "def": 15, "price": 0, "level": 40},
        {"name": "Lâmina do Crepúsculo",       "atk": 320, "def": 12, "price": 0, "level": 40},
        {"name": "Gládio do Caos Eterno",      "atk": 350, "def": 10, "price": 0, "level": 45},
        {"name": "Espada do Vazio",            "atk": 375, "def": 18, "price": 0, "level": 45},
        {"name": "Lâmina da Perdição",         "atk": 400, "def": 14, "price": 0, "level": 50},
        {"name": "Espada do Destino Final",    "atk": 430, "def": 22, "price": 0, "level": 55},
        {"name": "Lâmina do Apocalipse",       "atk": 460, "def": 28, "price": 0, "level": 60},
    ],
    "Machados Lendários": [
        {"name": "Machado da Ruína",           "atk": 315, "def":  5, "price": 0, "level": 40},
        {"name": "Machado do Fim dos Tempos",  "atk": 400, "def":  8, "price": 0, "level": 50},
    ],
    "Martelos Lendários": [
        {"name": "Martelo da Destruição",      "atk": 310, "def":  6, "price": 0, "level": 40},
        {"name": "Martelo das Eras",           "atk": 370, "def":  9, "price": 0, "level": 50},
        {"name": "Martelo do Ragnarok",        "atk": 440, "def": 12, "price": 0, "level": 60},
    ],
}

# ── Receitas de Craft ──────────────────────────────────────────────────────
# Formato de cada slot: {"category": str, "idx": int, "qty": int} ou None (vazio)
# Deixados em branco (None) para configurar depois.
CRAFT_RECIPES: dict[str, list[list]] = {
    "Cajados Lendários": [
        [None, None, None],   # Icon44 — Cajado das Almas
        [None, None, None],   # Icon45 — Cajado do Abismo Eterno
    ],
    "Espadas Lendárias": [
        [None, None, None],   # Icon30 — Espada da Aurora
        [None, None, None],   # Icon31 — Lâmina do Crepúsculo
        [None, None, None],   # Icon39 — Gládio do Caos Eterno
        [None, None, None],   # Icon40 — Espada do Vazio
        [None, None, None],   # Icon42 — Lâmina da Perdição
        [None, None, None],   # Icon43 — Espada do Destino Final
        [None, None, None],   # Icon48 — Lâmina do Apocalipse
    ],
    "Machados Lendários": [
        [None, None, None],   # Icon42 — Machado da Ruína
        [None, None, None],   # Icon46 — Machado do Fim dos Tempos
    ],
    "Martelos Lendários": [
        [None, None, None],   # Icon34 — Martelo da Destruição
        [None, None, None],   # Icon36 — Martelo das Eras
        [None, None, None],   # Icon45 — Martelo do Ragnarok
    ],
}

# Ordem de exibição das categorias no painel de crafting
CRAFT_CATEGORY_ORDER = [
    "Espadas Lendárias",
    "Machados Lendários",
    "Martelos Lendários",
    "Cajados Lendários",
]
