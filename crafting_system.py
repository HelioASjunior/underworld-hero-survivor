"""crafting_system.py — Dados do sistema de Crafting do Ferreiro."""

# Índices de Lingotes (LINGOT_DEFS em jogo_final.py):
# 0=Obsidiana  1=CristalPuro  2=Esmeralda  3=Sangue  4=Rubi  5=Âmbar  6=Safira
def _i(idx: int, qty: int = 1) -> dict:
    return {"category": "Lingotes", "idx": idx, "qty": qty}


def _w(category: str) -> dict:
    """Slot 0 da receita: qualquer arma da categoria de loja indicada (não soulbound)."""
    return {"category": category, "idx": None, "qty": 1}


# Mapeamento: categoria craftada → categoria de arma de loja exigida no slot 0
CRAFT_BASE_WEAPON: dict[str, str] = {
    "Espadas Lendárias":  "Espadas",
    "Machados Lendários": "Machados",
    "Martelos Lendários": "Hammers",
    "Cajados Lendários":  "Cajados",
}


# ── Assets por categoria ───────────────────────────────────────────────────
CRAFTED_CATEGORIES: dict[str, dict] = {
    "Cajados Lendários": {
        "folder": "cajados",
        "files": [
            "Icon44.png", "Icon45.png",
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
            "Icon30.png", "Icon31.png", "Icon39.png", "Icon40.png",
            "Icon42.png", "Icon43.png", "Icon48.png",
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
            "Icon42.png", "Icon46.png",
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
            "Icon34.png", "Icon36.png", "Icon45.png",
            "Icon1.png",  "Icon2.png",  "Icon3.png",  "Icon4.png",
            "Icon5.png",  "Icon6.png",  "Icon7.png",  "Icon8.png",
            "Icon9.png",  "Icon10.png", "Icon11.png", "Icon12.png",
            "Icon13.png", "Icon14.png", "Icon35.png", "Icon37.png",
            "Icon46.png", "Icon47.png", "Icon48.png",
        ],
    },
}

# ── Stats das Armas Lendárias ──────────────────────────────────────────────
# Níveis rebalanceados: 40→25 | 45→30 | 50→35 | 55→40 | 60→45
# price=0 → soulbound (não podem ser vendidas).
CRAFTED_WEAPON_STATS: dict[str, list[dict]] = {
    "Cajados Lendários": [
        # idx 0
        {"name": "Cajado das Almas",          "atk": 285, "def":  8, "price": 0, "level": 25},
        # idx 1
        {"name": "Cajado do Abismo Eterno",   "atk": 355, "def": 14, "price": 0, "level": 35},
        # idx 2
        {"name": "Cajado da Tempestade",      "atk": 282, "def":  6, "price": 0, "level": 25},
        # idx 3
        {"name": "Cajado das Brasas",         "atk": 290, "def":  7, "price": 0, "level": 25},
        # idx 4
        {"name": "Cajado de Gelo",            "atk": 298, "def":  5, "price": 0, "level": 25},
        # idx 5
        {"name": "Cajado do Relâmpago",       "atk": 306, "def":  6, "price": 0, "level": 25},
        # idx 6
        {"name": "Cajado da Sombra",          "atk": 314, "def":  9, "price": 0, "level": 30},
        # idx 7
        {"name": "Cajado do Vento Sombrio",   "atk": 322, "def":  7, "price": 0, "level": 30},
        # idx 8
        {"name": "Cajado do Crepúsculo",      "atk": 330, "def": 10, "price": 0, "level": 30},
        # idx 9
        {"name": "Cajado da Lua Negra",       "atk": 338, "def":  8, "price": 0, "level": 30},
        # idx 10
        {"name": "Cajado do Trovão",          "atk": 346, "def":  9, "price": 0, "level": 30},
        # idx 11
        {"name": "Cajado das Trevas",         "atk": 354, "def": 12, "price": 0, "level": 35},
        # idx 12
        {"name": "Cajado do Espectro",        "atk": 362, "def": 10, "price": 0, "level": 35},
        # idx 13
        {"name": "Cajado da Bruma",           "atk": 370, "def": 11, "price": 0, "level": 35},
        # idx 14
        {"name": "Cajado da Neblina",         "atk": 378, "def": 11, "price": 0, "level": 35},
        # idx 15
        {"name": "Cajado do Vácuo",           "atk": 386, "def":  9, "price": 0, "level": 35},
        # idx 16
        {"name": "Cajado da Maré Sombria",    "atk": 394, "def": 12, "price": 0, "level": 35},
        # idx 17
        {"name": "Cajado do Dragão",          "atk": 402, "def": 11, "price": 0, "level": 40},
        # idx 18
        {"name": "Cajado do Caos",            "atk": 410, "def": 13, "price": 0, "level": 40},
        # idx 19
        {"name": "Cajado da Tormenta",        "atk": 418, "def": 12, "price": 0, "level": 40},
        # idx 20
        {"name": "Cajado do Pesadelo",        "atk": 424, "def": 14, "price": 0, "level": 40},
        # idx 21
        {"name": "Cajado das Ruínas",         "atk": 430, "def": 13, "price": 0, "level": 40},
        # idx 22
        {"name": "Cajado da Maldição",        "atk": 436, "def": 15, "price": 0, "level": 40},
        # idx 23
        {"name": "Cajado dos Mortos",         "atk": 442, "def": 16, "price": 0, "level": 40},
        # idx 24
        {"name": "Cajado do Vazio Eterno",    "atk": 448, "def": 15, "price": 0, "level": 45},
        # idx 25
        {"name": "Cajado da Aniquilação",     "atk": 455, "def": 17, "price": 0, "level": 45},
    ],
    "Espadas Lendárias": [
        # idx 0
        {"name": "Espada da Aurora",           "atk": 300, "def": 15, "price": 0, "level": 25},
        # idx 1
        {"name": "Lâmina do Crepúsculo",       "atk": 320, "def": 12, "price": 0, "level": 25},
        # idx 2
        {"name": "Gládio do Caos Eterno",      "atk": 350, "def": 10, "price": 0, "level": 30},
        # idx 3
        {"name": "Espada do Vazio",            "atk": 375, "def": 18, "price": 0, "level": 30},
        # idx 4
        {"name": "Lâmina da Perdição",         "atk": 400, "def": 14, "price": 0, "level": 35},
        # idx 5
        {"name": "Espada do Destino Final",    "atk": 430, "def": 22, "price": 0, "level": 40},
        # idx 6
        {"name": "Lâmina do Apocalipse",       "atk": 460, "def": 28, "price": 0, "level": 45},
        # idx 7
        {"name": "Espada do Fogo",             "atk": 282, "def": 12, "price": 0, "level": 25},
        # idx 8
        {"name": "Lâmina Sombria",             "atk": 292, "def": 10, "price": 0, "level": 25},
        # idx 9
        {"name": "Espada do Gelo Negro",       "atk": 302, "def": 14, "price": 0, "level": 25},
        # idx 10
        {"name": "Espada Elemental",           "atk": 312, "def": 11, "price": 0, "level": 30},
        # idx 11
        {"name": "Espada do Dragão",           "atk": 322, "def": 13, "price": 0, "level": 30},
        # idx 12
        {"name": "Lâmina Espectral",           "atk": 332, "def": 10, "price": 0, "level": 30},
        # idx 13
        {"name": "Espada do Corvo",            "atk": 342, "def": 13, "price": 0, "level": 30},
        # idx 14
        {"name": "Lâmina do Trovão",           "atk": 352, "def": 11, "price": 0, "level": 30},
        # idx 15
        {"name": "Espada do Cristal",          "atk": 362, "def": 15, "price": 0, "level": 35},
        # idx 16
        {"name": "Espada da Tempestade",       "atk": 372, "def": 12, "price": 0, "level": 35},
        # idx 17
        {"name": "Lâmina do Fênix",            "atk": 382, "def": 13, "price": 0, "level": 35},
        # idx 18
        {"name": "Espada do Abismo",           "atk": 392, "def": 11, "price": 0, "level": 35},
        # idx 19
        {"name": "Lâmina do Caos",             "atk": 402, "def": 14, "price": 0, "level": 40},
        # idx 20
        {"name": "Espada do Vácuo Sombrio",    "atk": 412, "def": 12, "price": 0, "level": 40},
        # idx 21
        {"name": "Lâmina da Predição Negra",   "atk": 420, "def": 15, "price": 0, "level": 40},
        # idx 22
        {"name": "Espada dos Deuses Caídos",   "atk": 428, "def": 16, "price": 0, "level": 40},
        # idx 23
        {"name": "Lâmina do Purgátório",       "atk": 436, "def": 14, "price": 0, "level": 40},
        # idx 24
        {"name": "Espada da Criação",          "atk": 444, "def": 18, "price": 0, "level": 40},
        # idx 25
        {"name": "Lâmina do Julgamento",       "atk": 452, "def": 20, "price": 0, "level": 45},
    ],
    "Machados Lendários": [
        # idx 0
        {"name": "Machado da Ruína",           "atk": 315, "def":  5, "price": 0, "level": 25},
        # idx 1
        {"name": "Machado do Fim dos Tempos",  "atk": 400, "def":  8, "price": 0, "level": 35},
        # idx 2
        {"name": "Machado do Trovão",          "atk": 282, "def":  4, "price": 0, "level": 25},
        # idx 3
        {"name": "Machado de Gelo",            "atk": 292, "def":  5, "price": 0, "level": 25},
        # idx 4
        {"name": "Machado Sangrento",          "atk": 302, "def":  3, "price": 0, "level": 25},
        # idx 5
        {"name": "Machado Sombrio",            "atk": 312, "def":  5, "price": 0, "level": 30},
        # idx 6
        {"name": "Machado do Dragão",          "atk": 322, "def":  4, "price": 0, "level": 30},
        # idx 7
        {"name": "Machado da Tempestade",      "atk": 332, "def":  6, "price": 0, "level": 30},
        # idx 8
        {"name": "Machado do Caos",            "atk": 342, "def":  4, "price": 0, "level": 30},
        # idx 9
        {"name": "Machado dos Mortos",         "atk": 352, "def":  5, "price": 0, "level": 35},
        # idx 10
        {"name": "Machado Espectral",          "atk": 362, "def":  4, "price": 0, "level": 35},
        # idx 11
        {"name": "Machado da Bruma",           "atk": 372, "def":  6, "price": 0, "level": 35},
        # idx 12
        {"name": "Machado do Abismo",          "atk": 382, "def":  5, "price": 0, "level": 35},
        # idx 13
        {"name": "Machado da Ruína Total",     "atk": 392, "def":  7, "price": 0, "level": 35},
        # idx 14
        {"name": "Machado do Cataclismo",      "atk": 402, "def":  5, "price": 0, "level": 40},
        # idx 15
        {"name": "Machado dos Titãs",          "atk": 412, "def":  6, "price": 0, "level": 40},
        # idx 16
        {"name": "Machado do Vácuo",           "atk": 422, "def":  7, "price": 0, "level": 40},
        # idx 17
        {"name": "Machado da Destruição",      "atk": 432, "def":  6, "price": 0, "level": 40},
        # idx 18
        {"name": "Machado do Vórtice",         "atk": 442, "def":  7, "price": 0, "level": 45},
        # idx 19
        {"name": "Machado do Inevitável",      "atk": 452, "def":  8, "price": 0, "level": 45},
    ],
    "Martelos Lendários": [
        # idx 0
        {"name": "Martelo da Destruição",      "atk": 310, "def":  6, "price": 0, "level": 25},
        # idx 1
        {"name": "Martelo das Eras",           "atk": 370, "def":  9, "price": 0, "level": 35},
        # idx 2
        {"name": "Martelo do Ragnarok",        "atk": 440, "def": 12, "price": 0, "level": 45},
        # idx 3
        {"name": "Martelo do Trovão",          "atk": 282, "def":  5, "price": 0, "level": 25},
        # idx 4
        {"name": "Martelo de Gelo",            "atk": 292, "def":  4, "price": 0, "level": 25},
        # idx 5
        {"name": "Martelo Sombrio",            "atk": 302, "def":  6, "price": 0, "level": 25},
        # idx 6
        {"name": "Martelo do Dragão",          "atk": 312, "def":  5, "price": 0, "level": 25},
        # idx 7
        {"name": "Martelo da Tempestade",      "atk": 322, "def":  4, "price": 0, "level": 30},
        # idx 8
        {"name": "Martelo Sagrado",            "atk": 332, "def":  7, "price": 0, "level": 30},
        # idx 9
        {"name": "Martelo do Caos",            "atk": 342, "def":  5, "price": 0, "level": 30},
        # idx 10
        {"name": "Martelo dos Gigantes",       "atk": 352, "def":  6, "price": 0, "level": 30},
        # idx 11
        {"name": "Martelo do Abismo",          "atk": 362, "def":  5, "price": 0, "level": 35},
        # idx 12
        {"name": "Martelo Espectral",          "atk": 372, "def":  7, "price": 0, "level": 35},
        # idx 13
        {"name": "Martelo da Bruma",           "atk": 382, "def":  6, "price": 0, "level": 35},
        # idx 14
        {"name": "Martelo do Cataclismo",      "atk": 392, "def":  7, "price": 0, "level": 35},
        # idx 15
        {"name": "Martelo dos Titãs",          "atk": 402, "def":  6, "price": 0, "level": 40},
        # idx 16
        {"name": "Martelo da Criação",         "atk": 412, "def":  8, "price": 0, "level": 40},
        # idx 17
        {"name": "Martelo do Vácuo",           "atk": 422, "def":  7, "price": 0, "level": 40},
        # idx 18
        {"name": "Martelo da Extinção",        "atk": 432, "def":  8, "price": 0, "level": 40},
        # idx 19
        {"name": "Martelo dos Deuses",         "atk": 442, "def":  9, "price": 0, "level": 40},
        # idx 20
        {"name": "Martelo do Risco Final",     "atk": 452, "def": 10, "price": 0, "level": 45},
        # idx 21
        {"name": "Martelo do Universo",        "atk": 460, "def": 11, "price": 0, "level": 45},
    ],
}

# ── Receitas de Craft ──────────────────────────────────────────────────────
# Slot 0 = arma base da loja (_w) — qualquer item não-soulbound da categoria
# Slot 1 = Lingote principal
# Slot 2 = Lingote secundário
#
# Lingotes: 0=Obsidiana 1=CristalPuro 2=Esmeralda 3=Sangue 4=Rubi 5=Âmbar 6=Safira
# Raridade: Obsidiana/Sangue=Raro | CristalPuro/Rubi=Incomum | Esmeralda/Âmbar/Safira=Comum
# Custo de Forja em ouro: ver get_craft_gold_cost()

CRAFT_RECIPES: dict[str, list[list]] = {
    # ── CAJADOS LENDÁRIOS (26 armas) ──────────────────────────────────────
    "Cajados Lendários": [
        [_w("Cajados"), _i(2),    _i(5)   ],  # 0  Cajado das Almas        (285 ATK, lv25)
        [_w("Cajados"), _i(1,2),  _i(6)   ],  # 1  Cajado do Abismo Eterno (355 ATK, lv35)
        [_w("Cajados"), _i(6),    _i(5)   ],  # 2  Cajado da Tempestade    (282 ATK, lv25)
        [_w("Cajados"), _i(4),    _i(5)   ],  # 3  Cajado das Brasas       (290 ATK, lv25)
        [_w("Cajados"), _i(1),    _i(6)   ],  # 4  Cajado de Gelo          (298 ATK, lv25)
        [_w("Cajados"), _i(1),    _i(2)   ],  # 5  Cajado do Relâmpago     (306 ATK, lv25)
        [_w("Cajados"), _i(2),    _i(4)   ],  # 6  Cajado da Sombra        (314 ATK, lv30)
        [_w("Cajados"), _i(1),    _i(5)   ],  # 7  Cajado do Vento Sombrio (322 ATK, lv30)
        [_w("Cajados"), _i(4),    _i(6)   ],  # 8  Cajado do Crepúsculo    (330 ATK, lv30)
        [_w("Cajados"), _i(4),    _i(1)   ],  # 9  Cajado da Lua Negra     (338 ATK, lv30)
        [_w("Cajados"), _i(4,2),  _i(2)   ],  # 10 Cajado do Trovão        (346 ATK, lv30)
        [_w("Cajados"), _i(0),    _i(5)   ],  # 11 Cajado das Trevas       (354 ATK, lv35)
        [_w("Cajados"), _i(0),    _i(2)   ],  # 12 Cajado do Espectro      (362 ATK, lv35)
        [_w("Cajados"), _i(3),    _i(2)   ],  # 13 Cajado da Bruma         (370 ATK, lv35)
        [_w("Cajados"), _i(3),    _i(6)   ],  # 14 Cajado da Neblina       (378 ATK, lv35)
        [_w("Cajados"), _i(0),    _i(6)   ],  # 15 Cajado do Vácuo         (386 ATK, lv35)
        [_w("Cajados"), _i(3),    _i(1)   ],  # 16 Cajado da Maré Sombria  (394 ATK, lv35)
        [_w("Cajados"), _i(0),    _i(4)   ],  # 17 Cajado do Dragão        (402 ATK, lv40)
        [_w("Cajados"), _i(3),    _i(4)   ],  # 18 Cajado do Caos          (410 ATK, lv40)
        [_w("Cajados"), _i(0),    _i(1)   ],  # 19 Cajado da Tormenta      (418 ATK, lv40)
        [_w("Cajados"), _i(0),    _i(3)   ],  # 20 Cajado do Pesadelo      (424 ATK, lv40)
        [_w("Cajados"), _i(0,2),  _i(2)   ],  # 21 Cajado das Ruínas       (430 ATK, lv40)
        [_w("Cajados"), _i(0,2),  _i(5)   ],  # 22 Cajado da Maldição      (436 ATK, lv40)
        [_w("Cajados"), _i(0,2),  _i(4)   ],  # 23 Cajado dos Mortos       (442 ATK, lv40)
        [_w("Cajados"), _i(0,2),  _i(3)   ],  # 24 Cajado do Vazio Eterno  (448 ATK, lv45)
        [_w("Cajados"), _i(0,2),  _i(3,2) ],  # 25 Cajado da Aniquilação   (455 ATK, lv45)
    ],

    # ── ESPADAS LENDÁRIAS (26 armas) ──────────────────────────────────────
    "Espadas Lendárias": [
        [_w("Espadas"), _i(5),    _i(6)   ],  # 0  Espada da Aurora           (300 ATK, lv25)
        [_w("Espadas"), _i(2),    _i(5)   ],  # 1  Lâmina do Crepúsculo       (320 ATK, lv25)
        [_w("Espadas"), _i(4),    _i(2)   ],  # 2  Gládio do Caos Eterno      (350 ATK, lv30)
        [_w("Espadas"), _i(1),    _i(4,2) ],  # 3  Espada do Vazio            (375 ATK, lv30)
        [_w("Espadas"), _i(0),    _i(2)   ],  # 4  Lâmina da Perdição         (400 ATK, lv35)
        [_w("Espadas"), _i(0),    _i(4)   ],  # 5  Espada do Destino Final    (430 ATK, lv40)
        [_w("Espadas"), _i(0,2),  _i(3,2) ],  # 6  Lâmina do Apocalipse       (460 ATK, lv45)
        [_w("Espadas"), _i(4),    _i(5)   ],  # 7  Espada do Fogo             (282 ATK, lv25)
        [_w("Espadas"), _i(2),    _i(6)   ],  # 8  Lâmina Sombria             (292 ATK, lv25)
        [_w("Espadas"), _i(1),    _i(6)   ],  # 9  Espada do Gelo Negro       (302 ATK, lv25)
        [_w("Espadas"), _i(1),    _i(2)   ],  # 10 Espada Elemental           (312 ATK, lv30)
        [_w("Espadas"), _i(4),    _i(6)   ],  # 11 Espada do Dragão           (322 ATK, lv30)
        [_w("Espadas"), _i(1),    _i(5)   ],  # 12 Lâmina Espectral           (332 ATK, lv30)
        [_w("Espadas"), _i(4,2),  _i(6)   ],  # 13 Espada do Corvo            (342 ATK, lv30)
        [_w("Espadas"), _i(1,2),  _i(6)   ],  # 14 Lâmina do Trovão           (352 ATK, lv30)
        [_w("Espadas"), _i(4),    _i(1)   ],  # 15 Espada do Cristal          (362 ATK, lv35)
        [_w("Espadas"), _i(0),    _i(6)   ],  # 16 Espada da Tempestade       (372 ATK, lv35)
        [_w("Espadas"), _i(3),    _i(5)   ],  # 17 Lâmina do Fênix            (382 ATK, lv35)
        [_w("Espadas"), _i(3),    _i(6)   ],  # 18 Espada do Abismo           (392 ATK, lv35)
        [_w("Espadas"), _i(3),    _i(4)   ],  # 19 Lâmina do Caos             (402 ATK, lv40)
        [_w("Espadas"), _i(0),    _i(1)   ],  # 20 Espada do Vácuo Sombrio    (412 ATK, lv40)
        [_w("Espadas"), _i(0),    _i(3)   ],  # 21 Lâmina da Predição Negra   (420 ATK, lv40) ★
        [_w("Espadas"), _i(0,2),  _i(2)   ],  # 22 Espada dos Deuses Caídos   (428 ATK, lv40)
        [_w("Espadas"), _i(0),    _i(3,2) ],  # 23 Lâmina do Purgátório       (436 ATK, lv40)
        [_w("Espadas"), _i(0,2),  _i(4)   ],  # 24 Espada da Criação          (444 ATK, lv40)
        [_w("Espadas"), _i(0,2),  _i(3)   ],  # 25 Lâmina do Julgamento       (452 ATK, lv45)
    ],

    # ── MACHADOS LENDÁRIOS (20 armas) ─────────────────────────────────────
    "Machados Lendários": [
        [_w("Machados"), _i(4),   _i(2)   ],  # 0  Machado da Ruína          (315 ATK, lv25)
        [_w("Machados"), _i(3),   _i(1)   ],  # 1  Machado do Fim dos Tempos (400 ATK, lv35)
        [_w("Machados"), _i(6),   _i(2)   ],  # 2  Machado do Trovão         (282 ATK, lv25)
        [_w("Machados"), _i(1),   _i(6)   ],  # 3  Machado de Gelo           (292 ATK, lv25)
        [_w("Machados"), _i(4),   _i(5)   ],  # 4  Machado Sangrento         (302 ATK, lv25)
        [_w("Machados"), _i(2),   _i(5)   ],  # 5  Machado Sombrio           (312 ATK, lv30)
        [_w("Machados"), _i(4),   _i(6)   ],  # 6  Machado do Dragão         (322 ATK, lv30)
        [_w("Machados"), _i(1),   _i(2)   ],  # 7  Machado da Tempestade     (332 ATK, lv30)
        [_w("Machados"), _i(1),   _i(5)   ],  # 8  Machado do Caos           (342 ATK, lv30)
        [_w("Machados"), _i(1),   _i(4)   ],  # 9  Machado dos Mortos        (352 ATK, lv35)
        [_w("Machados"), _i(0),   _i(2)   ],  # 10 Machado Espectral         (362 ATK, lv35)
        [_w("Machados"), _i(3),   _i(5)   ],  # 11 Machado da Bruma          (372 ATK, lv35)
        [_w("Machados"), _i(0),   _i(5)   ],  # 12 Machado do Abismo         (382 ATK, lv35)
        [_w("Machados"), _i(3),   _i(6)   ],  # 13 Machado da Ruína Total    (392 ATK, lv35)
        [_w("Machados"), _i(0),   _i(4)   ],  # 14 Machado do Cataclismo     (402 ATK, lv40)
        [_w("Machados"), _i(0),   _i(1)   ],  # 15 Machado dos Titãs         (412 ATK, lv40)
        [_w("Machados"), _i(3),   _i(4)   ],  # 16 Machado do Vácuo          (422 ATK, lv40)
        [_w("Machados"), _i(0,2), _i(2)   ],  # 17 Machado da Destruição     (432 ATK, lv40)
        [_w("Machados"), _i(0,2), _i(3)   ],  # 18 Machado do Vórtice        (442 ATK, lv45)
        [_w("Machados"), _i(0),   _i(3,2) ],  # 19 Machado do Inevitável     (452 ATK, lv45)
    ],

    # ── MARTELOS LENDÁRIOS (22 armas) ─────────────────────────────────────
    "Martelos Lendários": [
        [_w("Hammers"), _i(4),    _i(5)   ],  # 0  Martelo da Destruição   (310 ATK, lv25)
        [_w("Hammers"), _i(0),    _i(6)   ],  # 1  Martelo das Eras        (370 ATK, lv35)
        [_w("Hammers"), _i(0,2),  _i(4)   ],  # 2  Martelo do Ragnarok     (440 ATK, lv45)
        [_w("Hammers"), _i(6),    _i(5)   ],  # 3  Martelo do Trovão       (282 ATK, lv25)
        [_w("Hammers"), _i(1),    _i(2)   ],  # 4  Martelo de Gelo         (292 ATK, lv25)
        [_w("Hammers"), _i(2),    _i(6)   ],  # 5  Martelo Sombrio         (302 ATK, lv25)
        [_w("Hammers"), _i(4),    _i(2)   ],  # 6  Martelo do Dragão       (312 ATK, lv25)
        [_w("Hammers"), _i(1),    _i(6)   ],  # 7  Martelo da Tempestade   (322 ATK, lv30)
        [_w("Hammers"), _i(1),    _i(5)   ],  # 8  Martelo Sagrado         (332 ATK, lv30)
        [_w("Hammers"), _i(4,2),  _i(6)   ],  # 9  Martelo do Caos         (342 ATK, lv30)
        [_w("Hammers"), _i(1,2),  _i(2)   ],  # 10 Martelo dos Gigantes    (352 ATK, lv30)
        [_w("Hammers"), _i(1),    _i(4)   ],  # 11 Martelo do Abismo       (362 ATK, lv35)
        [_w("Hammers"), _i(3),    _i(2)   ],  # 12 Martelo Espectral       (372 ATK, lv35)
        [_w("Hammers"), _i(0),    _i(5)   ],  # 13 Martelo da Bruma        (382 ATK, lv35)
        [_w("Hammers"), _i(3),    _i(6)   ],  # 14 Martelo do Cataclismo   (392 ATK, lv35)
        [_w("Hammers"), _i(0),    _i(2)   ],  # 15 Martelo dos Titãs       (402 ATK, lv40)
        [_w("Hammers"), _i(0),    _i(1)   ],  # 16 Martelo da Criação      (412 ATK, lv40)
        [_w("Hammers"), _i(3),    _i(4)   ],  # 17 Martelo do Vácuo        (422 ATK, lv40)
        [_w("Hammers"), _i(3),    _i(1)   ],  # 18 Martelo da Extinção     (432 ATK, lv40)
        [_w("Hammers"), _i(0),    _i(3)   ],  # 19 Martelo dos Deuses      (442 ATK, lv40)
        [_w("Hammers"), _i(0,2),  _i(3)   ],  # 20 Martelo do Risco Final  (452 ATK, lv45)
        [_w("Hammers"), _i(0,2),  _i(3,2) ],  # 21 Martelo do Universo     (460 ATK, lv45)
    ],
}

# Ordem de exibição das categorias no painel de crafting
CRAFT_CATEGORY_ORDER = [
    "Espadas Lendárias",
    "Machados Lendários",
    "Martelos Lendários",
    "Cajados Lendários",
]


def get_craft_gold_cost(weapon_def: dict) -> int:
    """Custo simbólico em ouro para forjar, baseado no nível requerido da arma."""
    lv = weapon_def.get("level", 25)
    if lv <= 25: return 100
    if lv <= 30: return 200
    if lv <= 35: return 350
    if lv <= 40: return 500
    return 750
