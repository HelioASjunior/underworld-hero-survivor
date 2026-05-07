"""crafting_system.py — Dados do sistema de Crafting do Ferreiro."""

# ── Assets por categoria ───────────────────────────────────────────────────
# Cada entrada: folder relativo a assets/ui/itens_craft/, lista de arquivos
# Itens existentes mantidos nos índices originais; novos itens appended.
CRAFTED_CATEGORIES: dict[str, dict] = {
    "Cajados Lendários": {
        "folder": "cajados",
        "files": [
            # ── existentes ──
            "Icon44.png", "Icon45.png",
            # ── novos (ATQ crescente) ──
            "Icon1.png",  "Icon3.png",  "Icon5.png",  "Icon7.png",
            "Icon8.png",  "Icon9.png",  "Icon10.png", "Icon12.png",
            "Icon14.png", "Icon16.png", "Icon18.png", "Icon20.png",
            "Icon21.png", "Icon23.png", "Icon24.png", "Icon25.png",
            "Icon27.png", "Icon28.png", "Icon30.png", "Icon38.png",
            "Icon40.png", "Icon41.png", "Icon42.png", "Icon47.png",
        ],
    },
    "Espadas Lendárias": {
        "folder": "espadas",
        "files": [
            # ── existentes ──
            "Icon30.png", "Icon31.png", "Icon39.png", "Icon40.png",
            "Icon42.png", "Icon43.png", "Icon48.png",
            # ── novos (ATQ crescente) ──
            "Icon2.png",  "Icon3.png",  "Icon4.png",  "Icon6.png",
            "Icon7.png",  "Icon8.png",  "Icon9.png",  "Icon10.png",
            "Icon11.png", "Icon14.png", "Icon16.png", "Icon18.png",
            "Icon23.png", "Icon28.png", "Icon29.png", "Icon34.png",
            "Icon35.png", "Icon36.png", "Icon38.png",
        ],
    },
    "Machados Lendários": {
        "folder": "machados",
        "files": [
            # ── existentes ──
            "Icon42.png", "Icon46.png",
            # ── novos (ATQ crescente) ──
            "Icon1.png",  "Icon2.png",  "Icon3.png",  "Icon4.png",
            "Icon9.png",  "Icon10.png", "Icon11.png", "Icon12.png",
            "Icon13.png", "Icon14.png", "Icon15.png", "Icon16.png",
            "Icon17.png", "Icon24.png", "Icon25.png", "Icon26.png",
            "Icon27.png", "Icon28.png",
        ],
    },
    "Martelos Lendários": {
        "folder": "hammers",
        "files": [
            # ── existentes ──
            "Icon34.png", "Icon36.png", "Icon45.png",
            # ── novos (ATQ crescente) ──
            "Icon1.png",  "Icon2.png",  "Icon3.png",  "Icon4.png",
            "Icon5.png",  "Icon6.png",  "Icon7.png",  "Icon8.png",
            "Icon9.png",  "Icon10.png", "Icon11.png", "Icon12.png",
            "Icon13.png", "Icon14.png", "Icon35.png", "Icon37.png",
            "Icon46.png", "Icon47.png", "Icon48.png",
        ],
    },
}

# ── Stats das Armas Lendárias ──────────────────────────────────────────────
# price=0 → não podem ser vendidas (soulbound).
CRAFTED_WEAPON_STATS: dict[str, list[dict]] = {
    "Cajados Lendários": [
        # ── existentes ──
        {"name": "Cajado das Almas",          "atk": 285, "def":  8, "price": 0, "level": 40},
        {"name": "Cajado do Abismo Eterno",   "atk": 355, "def": 14, "price": 0, "level": 50},
        # ── novos ──
        {"name": "Cajado da Tempestade",      "atk": 282, "def":  6, "price": 0, "level": 40},
        {"name": "Cajado das Brasas",         "atk": 290, "def":  7, "price": 0, "level": 40},
        {"name": "Cajado de Gelo",            "atk": 298, "def":  5, "price": 0, "level": 40},
        {"name": "Cajado do Relâmpago",       "atk": 306, "def":  6, "price": 0, "level": 40},
        {"name": "Cajado da Sombra",          "atk": 314, "def":  9, "price": 0, "level": 45},
        {"name": "Cajado do Vento Sombrio",   "atk": 322, "def":  7, "price": 0, "level": 45},
        {"name": "Cajado do Crepúsculo",      "atk": 330, "def": 10, "price": 0, "level": 45},
        {"name": "Cajado da Lua Negra",       "atk": 338, "def":  8, "price": 0, "level": 45},
        {"name": "Cajado do Trovão",          "atk": 346, "def":  9, "price": 0, "level": 45},
        {"name": "Cajado das Trevas",         "atk": 354, "def": 12, "price": 0, "level": 50},
        {"name": "Cajado do Espectro",        "atk": 362, "def": 10, "price": 0, "level": 50},
        {"name": "Cajado da Bruma",           "atk": 370, "def": 11, "price": 0, "level": 50},
        {"name": "Cajado da Neblina",         "atk": 378, "def": 11, "price": 0, "level": 50},
        {"name": "Cajado do Vácuo",           "atk": 386, "def":  9, "price": 0, "level": 50},
        {"name": "Cajado da Maré Sombria",    "atk": 394, "def": 12, "price": 0, "level": 50},
        {"name": "Cajado do Dragão",          "atk": 402, "def": 11, "price": 0, "level": 55},
        {"name": "Cajado do Caos",            "atk": 410, "def": 13, "price": 0, "level": 55},
        {"name": "Cajado da Tormenta",        "atk": 418, "def": 12, "price": 0, "level": 55},
        {"name": "Cajado do Pesadelo",        "atk": 424, "def": 14, "price": 0, "level": 55},
        {"name": "Cajado das Ruínas",         "atk": 430, "def": 13, "price": 0, "level": 55},
        {"name": "Cajado da Maldição",        "atk": 436, "def": 15, "price": 0, "level": 55},
        {"name": "Cajado dos Mortos",         "atk": 442, "def": 16, "price": 0, "level": 55},
        {"name": "Cajado do Vazio Eterno",    "atk": 448, "def": 15, "price": 0, "level": 60},
        {"name": "Cajado da Aniquilação",     "atk": 455, "def": 17, "price": 0, "level": 60},
    ],
    "Espadas Lendárias": [
        # ── existentes ──
        {"name": "Espada da Aurora",           "atk": 300, "def": 15, "price": 0, "level": 40},
        {"name": "Lâmina do Crepúsculo",       "atk": 320, "def": 12, "price": 0, "level": 40},
        {"name": "Gládio do Caos Eterno",      "atk": 350, "def": 10, "price": 0, "level": 45},
        {"name": "Espada do Vazio",            "atk": 375, "def": 18, "price": 0, "level": 45},
        {"name": "Lâmina da Perdição",         "atk": 400, "def": 14, "price": 0, "level": 50},
        {"name": "Espada do Destino Final",    "atk": 430, "def": 22, "price": 0, "level": 55},
        {"name": "Lâmina do Apocalipse",       "atk": 460, "def": 28, "price": 0, "level": 60},
        # ── novos ──
        {"name": "Espada do Fogo",             "atk": 282, "def": 12, "price": 0, "level": 40},
        {"name": "Lâmina Sombria",             "atk": 292, "def": 10, "price": 0, "level": 40},
        {"name": "Espada do Gelo Negro",       "atk": 302, "def": 14, "price": 0, "level": 40},
        {"name": "Espada Elemental",           "atk": 312, "def": 11, "price": 0, "level": 45},
        {"name": "Espada do Dragão",           "atk": 322, "def": 13, "price": 0, "level": 45},
        {"name": "Lâmina Espectral",           "atk": 332, "def": 10, "price": 0, "level": 45},
        {"name": "Espada do Corvo",            "atk": 342, "def": 13, "price": 0, "level": 45},
        {"name": "Lâmina do Trovão",           "atk": 352, "def": 11, "price": 0, "level": 45},
        {"name": "Espada do Cristal",          "atk": 362, "def": 15, "price": 0, "level": 50},
        {"name": "Espada da Tempestade",       "atk": 372, "def": 12, "price": 0, "level": 50},
        {"name": "Lâmina do Fênix",            "atk": 382, "def": 13, "price": 0, "level": 50},
        {"name": "Espada do Abismo",           "atk": 392, "def": 11, "price": 0, "level": 50},
        {"name": "Lâmina do Caos",             "atk": 402, "def": 14, "price": 0, "level": 55},
        {"name": "Espada do Vácuo Sombrio",    "atk": 412, "def": 12, "price": 0, "level": 55},
        {"name": "Lâmina da Predição Negra",   "atk": 420, "def": 15, "price": 0, "level": 55},
        {"name": "Espada dos Deuses Caídos",   "atk": 428, "def": 16, "price": 0, "level": 55},
        {"name": "Lâmina do Purgátório",       "atk": 436, "def": 14, "price": 0, "level": 55},
        {"name": "Espada da Criação",          "atk": 444, "def": 18, "price": 0, "level": 55},
        {"name": "Lâmina do Julgamento",       "atk": 452, "def": 20, "price": 0, "level": 60},
    ],
    "Machados Lendários": [
        # ── existentes ──
        {"name": "Machado da Ruína",           "atk": 315, "def":  5, "price": 0, "level": 40},
        {"name": "Machado do Fim dos Tempos",  "atk": 400, "def":  8, "price": 0, "level": 50},
        # ── novos ──
        {"name": "Machado do Trovão",          "atk": 282, "def":  4, "price": 0, "level": 40},
        {"name": "Machado de Gelo",            "atk": 292, "def":  5, "price": 0, "level": 40},
        {"name": "Machado Sangrento",          "atk": 302, "def":  3, "price": 0, "level": 40},
        {"name": "Machado Sombrio",            "atk": 312, "def":  5, "price": 0, "level": 45},
        {"name": "Machado do Dragão",          "atk": 322, "def":  4, "price": 0, "level": 45},
        {"name": "Machado da Tempestade",      "atk": 332, "def":  6, "price": 0, "level": 45},
        {"name": "Machado do Caos",            "atk": 342, "def":  4, "price": 0, "level": 45},
        {"name": "Machado dos Mortos",         "atk": 352, "def":  5, "price": 0, "level": 50},
        {"name": "Machado Espectral",          "atk": 362, "def":  4, "price": 0, "level": 50},
        {"name": "Machado da Bruma",           "atk": 372, "def":  6, "price": 0, "level": 50},
        {"name": "Machado do Abismo",          "atk": 382, "def":  5, "price": 0, "level": 50},
        {"name": "Machado da Ruína Total",     "atk": 392, "def":  7, "price": 0, "level": 50},
        {"name": "Machado do Cataclismo",      "atk": 402, "def":  5, "price": 0, "level": 55},
        {"name": "Machado dos Titãs",          "atk": 412, "def":  6, "price": 0, "level": 55},
        {"name": "Machado do Vácuo",           "atk": 422, "def":  7, "price": 0, "level": 55},
        {"name": "Machado da Destruição",      "atk": 432, "def":  6, "price": 0, "level": 55},
        {"name": "Machado do Vórtice",         "atk": 442, "def":  7, "price": 0, "level": 60},
        {"name": "Machado do Inevitável",      "atk": 452, "def":  8, "price": 0, "level": 60},
    ],
    "Martelos Lendários": [
        # ── existentes ──
        {"name": "Martelo da Destruição",      "atk": 310, "def":  6, "price": 0, "level": 40},
        {"name": "Martelo das Eras",           "atk": 370, "def":  9, "price": 0, "level": 50},
        {"name": "Martelo do Ragnarok",        "atk": 440, "def": 12, "price": 0, "level": 60},
        # ── novos ──
        {"name": "Martelo do Trovão",          "atk": 282, "def":  5, "price": 0, "level": 40},
        {"name": "Martelo de Gelo",            "atk": 292, "def":  4, "price": 0, "level": 40},
        {"name": "Martelo Sombrio",            "atk": 302, "def":  6, "price": 0, "level": 40},
        {"name": "Martelo do Dragão",          "atk": 312, "def":  5, "price": 0, "level": 40},
        {"name": "Martelo da Tempestade",      "atk": 322, "def":  4, "price": 0, "level": 45},
        {"name": "Martelo Sagrado",            "atk": 332, "def":  7, "price": 0, "level": 45},
        {"name": "Martelo do Caos",            "atk": 342, "def":  5, "price": 0, "level": 45},
        {"name": "Martelo dos Gigantes",       "atk": 352, "def":  6, "price": 0, "level": 45},
        {"name": "Martelo do Abismo",          "atk": 362, "def":  5, "price": 0, "level": 50},
        {"name": "Martelo Espectral",          "atk": 372, "def":  7, "price": 0, "level": 50},
        {"name": "Martelo da Bruma",           "atk": 382, "def":  6, "price": 0, "level": 50},
        {"name": "Martelo do Cataclismo",      "atk": 392, "def":  7, "price": 0, "level": 50},
        {"name": "Martelo dos Titãs",          "atk": 402, "def":  6, "price": 0, "level": 55},
        {"name": "Martelo da Criação",         "atk": 412, "def":  8, "price": 0, "level": 55},
        {"name": "Martelo do Vácuo",           "atk": 422, "def":  7, "price": 0, "level": 55},
        {"name": "Martelo da Extinção",        "atk": 432, "def":  8, "price": 0, "level": 55},
        {"name": "Martelo dos Deuses",         "atk": 442, "def":  9, "price": 0, "level": 60},
        {"name": "Martelo do Risco Final",     "atk": 452, "def": 10, "price": 0, "level": 60},
        {"name": "Martelo do Universo",        "atk": 460, "def": 11, "price": 0, "level": 60},
    ],
}

# ── Receitas de Craft ──────────────────────────────────────────────────────
# Formato de cada slot: {"category": str, "idx": int, "qty": int} ou None
# Todos em branco para configurar depois.
def _empty(n: int) -> list:
    return [[None, None, None] for _ in range(n)]

CRAFT_RECIPES: dict[str, list[list]] = {
    "Cajados Lendários":   _empty(len(CRAFTED_CATEGORIES["Cajados Lendários"]["files"])),
    "Espadas Lendárias":   _empty(len(CRAFTED_CATEGORIES["Espadas Lendárias"]["files"])),
    "Machados Lendários":  _empty(len(CRAFTED_CATEGORIES["Machados Lendários"]["files"])),
    "Martelos Lendários":  _empty(len(CRAFTED_CATEGORIES["Martelos Lendários"]["files"])),
}

# Ordem de exibição das categorias no painel de crafting
CRAFT_CATEGORY_ORDER = [
    "Espadas Lendárias",
    "Machados Lendários",
    "Martelos Lendários",
    "Cajados Lendários",
]
