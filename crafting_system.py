"""crafting_system.py — Dados do sistema de Crafting do Ferreiro."""

# Índices de Lingotes (LINGOT_DEFS em jogo_final.py):
# 0=Obsidiana  1=CristalPuro  2=Esmeralda  3=Sangue  4=Rubi  5=Âmbar  6=Safira
def _i(idx: int, qty: int = 1) -> dict:
    return {"category": "Lingotes", "idx": idx, "qty": qty}


def _w(category: str, idx: int) -> dict:
    """Slot 0: arma de loja específica (não soulbound). category = categoria da loja, idx = índice do item."""
    return {"category": category, "idx": idx, "qty": 1, "shop_weapon": True}


# ── Armas de loja por tier — Espadas ──────────────────────────────────────
# idx 14 = Espada de Sombra   (ATK 160, lv20, 1300g)  → lv25 legendária
# idx 16 = Espada do Caos     (ATK 185, lv25, 1560g)  → lv30 legendária
# idx 17 = Espada das Trevas  (ATK 198, lv25, 1700g)  → lv35 legendária
# idx 18 = Espada do Inferno  (ATK 215, lv30, 1850g)  → lv40 legendária
# idx 19 = Espada do Apocalipse (ATK 250, lv30, 2100g) → lv45 legendária
#
# Machados: idx 6=Rúnico(lv20) | idx 7=Sanguinário(lv20) | idx 8=Berserker(lv30) | idx 9=Destruidor(lv30)
# Hammers:  idx 6=Rúnico(lv20) | idx 7=Ogro(lv20)        | idx 8=Caos(lv30)      | idx 9=Titã(lv30)
# Cajados:  idx 6=Arcano(lv20) | idx 7=PedraRúnica(lv20) | idx 8=Abismo(lv30)    | idx 9=Lich(lv30)


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
CRAFTED_WEAPON_STATS: dict[str, list[dict]] = {
    "Cajados Lendários": [
        {"name": "Cajado das Almas",          "atk": 285, "def":  8, "price": 0, "level": 25},
        {"name": "Cajado do Abismo Eterno",   "atk": 355, "def": 14, "price": 0, "level": 35},
        {"name": "Cajado da Tempestade",      "atk": 282, "def":  6, "price": 0, "level": 25},
        {"name": "Cajado das Brasas",         "atk": 290, "def":  7, "price": 0, "level": 25},
        {"name": "Cajado de Gelo",            "atk": 298, "def":  5, "price": 0, "level": 25},
        {"name": "Cajado do Relâmpago",       "atk": 306, "def":  6, "price": 0, "level": 25},
        {"name": "Cajado da Sombra",          "atk": 314, "def":  9, "price": 0, "level": 30},
        {"name": "Cajado do Vento Sombrio",   "atk": 322, "def":  7, "price": 0, "level": 30},
        {"name": "Cajado do Crepúsculo",      "atk": 330, "def": 10, "price": 0, "level": 30},
        {"name": "Cajado da Lua Negra",       "atk": 338, "def":  8, "price": 0, "level": 30},
        {"name": "Cajado do Trovão",          "atk": 346, "def":  9, "price": 0, "level": 30},
        {"name": "Cajado das Trevas",         "atk": 354, "def": 12, "price": 0, "level": 35},
        {"name": "Cajado do Espectro",        "atk": 362, "def": 10, "price": 0, "level": 35},
        {"name": "Cajado da Bruma",           "atk": 370, "def": 11, "price": 0, "level": 35},
        {"name": "Cajado da Neblina",         "atk": 378, "def": 11, "price": 0, "level": 35},
        {"name": "Cajado do Vácuo",           "atk": 386, "def":  9, "price": 0, "level": 35},
        {"name": "Cajado da Maré Sombria",    "atk": 394, "def": 12, "price": 0, "level": 35},
        {"name": "Cajado do Dragão",          "atk": 402, "def": 11, "price": 0, "level": 40},
        {"name": "Cajado do Caos",            "atk": 410, "def": 13, "price": 0, "level": 40},
        {"name": "Cajado da Tormenta",        "atk": 418, "def": 12, "price": 0, "level": 40},
        {"name": "Cajado do Pesadelo",        "atk": 424, "def": 14, "price": 0, "level": 40},
        {"name": "Cajado das Ruínas",         "atk": 430, "def": 13, "price": 0, "level": 40},
        {"name": "Cajado da Maldição",        "atk": 436, "def": 15, "price": 0, "level": 40},
        {"name": "Cajado dos Mortos",         "atk": 442, "def": 16, "price": 0, "level": 40},
        {"name": "Cajado do Vazio Eterno",    "atk": 448, "def": 15, "price": 0, "level": 45},
        {"name": "Cajado da Aniquilação",     "atk": 455, "def": 17, "price": 0, "level": 45},
    ],
    "Espadas Lendárias": [
        {"name": "Espada da Aurora",           "atk": 300, "def": 15, "price": 0, "level": 25},
        {"name": "Lâmina do Crepúsculo",       "atk": 320, "def": 12, "price": 0, "level": 25},
        {"name": "Gládio do Caos Eterno",      "atk": 350, "def": 10, "price": 0, "level": 30},
        {"name": "Espada do Vazio",            "atk": 375, "def": 18, "price": 0, "level": 30},
        {"name": "Lâmina da Perdição",         "atk": 400, "def": 14, "price": 0, "level": 35},
        {"name": "Espada do Destino Final",    "atk": 430, "def": 22, "price": 0, "level": 40},
        {"name": "Lâmina do Apocalipse",       "atk": 460, "def": 28, "price": 0, "level": 45},
        {"name": "Espada do Fogo",             "atk": 282, "def": 12, "price": 0, "level": 25},
        {"name": "Lâmina Sombria",             "atk": 292, "def": 10, "price": 0, "level": 25},
        {"name": "Espada do Gelo Negro",       "atk": 302, "def": 14, "price": 0, "level": 25},
        {"name": "Espada Elemental",           "atk": 312, "def": 11, "price": 0, "level": 30},
        {"name": "Espada do Dragão",           "atk": 322, "def": 13, "price": 0, "level": 30},
        {"name": "Lâmina Espectral",           "atk": 332, "def": 10, "price": 0, "level": 30},
        {"name": "Espada do Corvo",            "atk": 342, "def": 13, "price": 0, "level": 30},
        {"name": "Lâmina do Trovão",           "atk": 352, "def": 11, "price": 0, "level": 30},
        {"name": "Espada do Cristal",          "atk": 362, "def": 15, "price": 0, "level": 35},
        {"name": "Espada da Tempestade",       "atk": 372, "def": 12, "price": 0, "level": 35},
        {"name": "Lâmina do Fênix",            "atk": 382, "def": 13, "price": 0, "level": 35},
        {"name": "Espada do Abismo",           "atk": 392, "def": 11, "price": 0, "level": 35},
        {"name": "Lâmina do Caos",             "atk": 402, "def": 14, "price": 0, "level": 40},
        {"name": "Espada do Vácuo Sombrio",    "atk": 412, "def": 12, "price": 0, "level": 40},
        {"name": "Lâmina da Predição Negra",   "atk": 420, "def": 15, "price": 0, "level": 40},
        {"name": "Espada dos Deuses Caídos",   "atk": 428, "def": 16, "price": 0, "level": 40},
        {"name": "Lâmina do Purgátório",       "atk": 436, "def": 14, "price": 0, "level": 40},
        {"name": "Espada da Criação",          "atk": 444, "def": 18, "price": 0, "level": 40},
        {"name": "Lâmina do Julgamento",       "atk": 452, "def": 20, "price": 0, "level": 45},
    ],
    "Machados Lendários": [
        {"name": "Machado da Ruína",           "atk": 315, "def":  5, "price": 0, "level": 25},
        {"name": "Machado do Fim dos Tempos",  "atk": 400, "def":  8, "price": 0, "level": 35},
        {"name": "Machado do Trovão",          "atk": 282, "def":  4, "price": 0, "level": 25},
        {"name": "Machado de Gelo",            "atk": 292, "def":  5, "price": 0, "level": 25},
        {"name": "Machado Sangrento",          "atk": 302, "def":  3, "price": 0, "level": 25},
        {"name": "Machado Sombrio",            "atk": 312, "def":  5, "price": 0, "level": 30},
        {"name": "Machado do Dragão",          "atk": 322, "def":  4, "price": 0, "level": 30},
        {"name": "Machado da Tempestade",      "atk": 332, "def":  6, "price": 0, "level": 30},
        {"name": "Machado do Caos",            "atk": 342, "def":  4, "price": 0, "level": 30},
        {"name": "Machado dos Mortos",         "atk": 352, "def":  5, "price": 0, "level": 35},
        {"name": "Machado Espectral",          "atk": 362, "def":  4, "price": 0, "level": 35},
        {"name": "Machado da Bruma",           "atk": 372, "def":  6, "price": 0, "level": 35},
        {"name": "Machado do Abismo",          "atk": 382, "def":  5, "price": 0, "level": 35},
        {"name": "Machado da Ruína Total",     "atk": 392, "def":  7, "price": 0, "level": 35},
        {"name": "Machado do Cataclismo",      "atk": 402, "def":  5, "price": 0, "level": 40},
        {"name": "Machado dos Titãs",          "atk": 412, "def":  6, "price": 0, "level": 40},
        {"name": "Machado do Vácuo",           "atk": 422, "def":  7, "price": 0, "level": 40},
        {"name": "Machado da Destruição",      "atk": 432, "def":  6, "price": 0, "level": 40},
        {"name": "Machado do Vórtice",         "atk": 442, "def":  7, "price": 0, "level": 45},
        {"name": "Machado do Inevitável",      "atk": 452, "def":  8, "price": 0, "level": 45},
    ],
    "Martelos Lendários": [
        {"name": "Martelo da Destruição",      "atk": 310, "def":  6, "price": 0, "level": 25},
        {"name": "Martelo das Eras",           "atk": 370, "def":  9, "price": 0, "level": 35},
        {"name": "Martelo do Ragnarok",        "atk": 440, "def": 12, "price": 0, "level": 45},
        {"name": "Martelo do Trovão",          "atk": 282, "def":  5, "price": 0, "level": 25},
        {"name": "Martelo de Gelo",            "atk": 292, "def":  4, "price": 0, "level": 25},
        {"name": "Martelo Sombrio",            "atk": 302, "def":  6, "price": 0, "level": 25},
        {"name": "Martelo do Dragão",          "atk": 312, "def":  5, "price": 0, "level": 25},
        {"name": "Martelo da Tempestade",      "atk": 322, "def":  4, "price": 0, "level": 30},
        {"name": "Martelo Sagrado",            "atk": 332, "def":  7, "price": 0, "level": 30},
        {"name": "Martelo do Caos",            "atk": 342, "def":  5, "price": 0, "level": 30},
        {"name": "Martelo dos Gigantes",       "atk": 352, "def":  6, "price": 0, "level": 30},
        {"name": "Martelo do Abismo",          "atk": 362, "def":  5, "price": 0, "level": 35},
        {"name": "Martelo Espectral",          "atk": 372, "def":  7, "price": 0, "level": 35},
        {"name": "Martelo da Bruma",           "atk": 382, "def":  6, "price": 0, "level": 35},
        {"name": "Martelo do Cataclismo",      "atk": 392, "def":  7, "price": 0, "level": 35},
        {"name": "Martelo dos Titãs",          "atk": 402, "def":  6, "price": 0, "level": 40},
        {"name": "Martelo da Criação",         "atk": 412, "def":  8, "price": 0, "level": 40},
        {"name": "Martelo do Vácuo",           "atk": 422, "def":  7, "price": 0, "level": 40},
        {"name": "Martelo da Extinção",        "atk": 432, "def":  8, "price": 0, "level": 40},
        {"name": "Martelo dos Deuses",         "atk": 442, "def":  9, "price": 0, "level": 40},
        {"name": "Martelo do Risco Final",     "atk": 452, "def": 10, "price": 0, "level": 45},
        {"name": "Martelo do Universo",        "atk": 460, "def": 11, "price": 0, "level": 45},
    ],
}

# ── Receitas de Craft ──────────────────────────────────────────────────────
# Slot 0 = _w(categoria, idx) — arma ESPECÍFICA da loja (shop_weapon=True)
# Slot 1 = Lingote principal  |  Slot 2 = Lingote secundário
#
# Lingotes: 0=Obsidiana 1=CristalPuro 2=Esmeralda 3=Sangue 4=Rubi 5=Âmbar 6=Safira
# Custo de forja em ouro: ver get_craft_gold_cost()

CRAFT_RECIPES: dict[str, list[list]] = {
    # ── CAJADOS LENDÁRIOS (26 armas) ──────────────────────────────────────
    # Cajado Arcano(6,lv20) → lv25  |  Pedra Rúnica(7,lv20) → lv30
    # Cajado do Abismo(8,lv30) → lv35  |  Cajado do Lich(9,lv30) → lv40/45
    "Cajados Lendários": [
        [_w("Cajados", 6), _i(2),   _i(5)   ],  # 0  Cajado das Almas        (285,lv25)
        [_w("Cajados", 8), _i(1,2), _i(6)   ],  # 1  Cajado do Abismo Eterno (355,lv35)
        [_w("Cajados", 6), _i(6),   _i(5)   ],  # 2  Cajado da Tempestade    (282,lv25)
        [_w("Cajados", 6), _i(4),   _i(5)   ],  # 3  Cajado das Brasas       (290,lv25)
        [_w("Cajados", 6), _i(1),   _i(6)   ],  # 4  Cajado de Gelo          (298,lv25)
        [_w("Cajados", 6), _i(1),   _i(2)   ],  # 5  Cajado do Relâmpago     (306,lv25)
        [_w("Cajados", 7), _i(2),   _i(4)   ],  # 6  Cajado da Sombra        (314,lv30)
        [_w("Cajados", 7), _i(1),   _i(5)   ],  # 7  Cajado do Vento Sombrio (322,lv30)
        [_w("Cajados", 7), _i(4),   _i(6)   ],  # 8  Cajado do Crepúsculo    (330,lv30)
        [_w("Cajados", 7), _i(4),   _i(1)   ],  # 9  Cajado da Lua Negra     (338,lv30)
        [_w("Cajados", 7), _i(4,2), _i(2)   ],  # 10 Cajado do Trovão        (346,lv30)
        [_w("Cajados", 8), _i(0),   _i(5)   ],  # 11 Cajado das Trevas       (354,lv35)
        [_w("Cajados", 8), _i(0),   _i(2)   ],  # 12 Cajado do Espectro      (362,lv35)
        [_w("Cajados", 8), _i(3),   _i(2)   ],  # 13 Cajado da Bruma         (370,lv35)
        [_w("Cajados", 8), _i(3),   _i(6)   ],  # 14 Cajado da Neblina       (378,lv35)
        [_w("Cajados", 8), _i(0),   _i(6)   ],  # 15 Cajado do Vácuo         (386,lv35)
        [_w("Cajados", 8), _i(3),   _i(1)   ],  # 16 Cajado da Maré Sombria  (394,lv35)
        [_w("Cajados", 9), _i(0),   _i(4)   ],  # 17 Cajado do Dragão        (402,lv40)
        [_w("Cajados", 9), _i(3),   _i(4)   ],  # 18 Cajado do Caos          (410,lv40)
        [_w("Cajados", 9), _i(0),   _i(1)   ],  # 19 Cajado da Tormenta      (418,lv40)
        [_w("Cajados", 9), _i(0),   _i(3)   ],  # 20 Cajado do Pesadelo      (424,lv40)
        [_w("Cajados", 9), _i(0,2), _i(2)   ],  # 21 Cajado das Ruínas       (430,lv40)
        [_w("Cajados", 9), _i(0,2), _i(5)   ],  # 22 Cajado da Maldição      (436,lv40)
        [_w("Cajados", 9), _i(0,2), _i(4)   ],  # 23 Cajado dos Mortos       (442,lv40)
        [_w("Cajados", 9), _i(0,2), _i(3)   ],  # 24 Cajado do Vazio Eterno  (448,lv45)
        [_w("Cajados", 9), _i(0,2), _i(3,2) ],  # 25 Cajado da Aniquilação   (455,lv45)
    ],

    # ── ESPADAS LENDÁRIAS (26 armas) ──────────────────────────────────────
    # Sombra(14,lv20)→lv25 | Caos(16,lv25)→lv30 | Trevas(17,lv25)→lv35
    # Inferno(18,lv30)→lv40 | Apocalipse(19,lv30)→lv45
    "Espadas Lendárias": [
        [_w("Espadas", 14), _i(5),   _i(6)   ],  # 0  Espada da Aurora           (300,lv25)
        [_w("Espadas", 14), _i(2),   _i(5)   ],  # 1  Lâmina do Crepúsculo       (320,lv25)
        [_w("Espadas", 16), _i(4),   _i(2)   ],  # 2  Gládio do Caos Eterno      (350,lv30)
        [_w("Espadas", 16), _i(1),   _i(4,2) ],  # 3  Espada do Vazio            (375,lv30)
        [_w("Espadas", 17), _i(0),   _i(2)   ],  # 4  Lâmina da Perdição         (400,lv35)
        [_w("Espadas", 18), _i(0),   _i(4)   ],  # 5  Espada do Destino Final    (430,lv40)
        [_w("Espadas", 19), _i(0,2), _i(3,2) ],  # 6  Lâmina do Apocalipse       (460,lv45)
        [_w("Espadas", 14), _i(4),   _i(5)   ],  # 7  Espada do Fogo             (282,lv25)
        [_w("Espadas", 14), _i(2),   _i(6)   ],  # 8  Lâmina Sombria             (292,lv25)
        [_w("Espadas", 14), _i(1),   _i(6)   ],  # 9  Espada do Gelo Negro       (302,lv25)
        [_w("Espadas", 16), _i(1),   _i(2)   ],  # 10 Espada Elemental           (312,lv30)
        [_w("Espadas", 16), _i(4),   _i(6)   ],  # 11 Espada do Dragão           (322,lv30)
        [_w("Espadas", 16), _i(1),   _i(5)   ],  # 12 Lâmina Espectral           (332,lv30)
        [_w("Espadas", 16), _i(4,2), _i(6)   ],  # 13 Espada do Corvo            (342,lv30)
        [_w("Espadas", 16), _i(1,2), _i(6)   ],  # 14 Lâmina do Trovão           (352,lv30)
        [_w("Espadas", 17), _i(4),   _i(1)   ],  # 15 Espada do Cristal          (362,lv35)
        [_w("Espadas", 17), _i(0),   _i(6)   ],  # 16 Espada da Tempestade       (372,lv35)
        [_w("Espadas", 17), _i(3),   _i(5)   ],  # 17 Lâmina do Fênix            (382,lv35)
        [_w("Espadas", 17), _i(3),   _i(6)   ],  # 18 Espada do Abismo           (392,lv35)
        [_w("Espadas", 18), _i(3),   _i(4)   ],  # 19 Lâmina do Caos             (402,lv40)
        [_w("Espadas", 18), _i(0),   _i(1)   ],  # 20 Espada do Vácuo Sombrio    (412,lv40)
        [_w("Espadas", 18), _i(0),   _i(3)   ],  # 21 Lâmina da Predição Negra   (420,lv40) ★
        [_w("Espadas", 18), _i(0,2), _i(2)   ],  # 22 Espada dos Deuses Caídos   (428,lv40)
        [_w("Espadas", 18), _i(0),   _i(3,2) ],  # 23 Lâmina do Purgátório       (436,lv40)
        [_w("Espadas", 18), _i(0,2), _i(4)   ],  # 24 Espada da Criação          (444,lv40)
        [_w("Espadas", 19), _i(0,2), _i(3)   ],  # 25 Lâmina do Julgamento       (452,lv45)
    ],

    # ── MACHADOS LENDÁRIOS (20 armas) ─────────────────────────────────────
    # Rúnico(6,lv20)→lv25 | Sanguinário(7,lv20)→lv30 | Berserker(8,lv30)→lv35
    # Destruidor(9,lv30)→lv40/45
    "Machados Lendários": [
        [_w("Machados", 6), _i(4),   _i(2)   ],  # 0  Machado da Ruína          (315,lv25)
        [_w("Machados", 8), _i(3),   _i(1)   ],  # 1  Machado do Fim dos Tempos (400,lv35)
        [_w("Machados", 6), _i(6),   _i(2)   ],  # 2  Machado do Trovão         (282,lv25)
        [_w("Machados", 6), _i(1),   _i(6)   ],  # 3  Machado de Gelo           (292,lv25)
        [_w("Machados", 6), _i(4),   _i(5)   ],  # 4  Machado Sangrento         (302,lv25)
        [_w("Machados", 7), _i(2),   _i(5)   ],  # 5  Machado Sombrio           (312,lv30)
        [_w("Machados", 7), _i(4),   _i(6)   ],  # 6  Machado do Dragão         (322,lv30)
        [_w("Machados", 7), _i(1),   _i(2)   ],  # 7  Machado da Tempestade     (332,lv30)
        [_w("Machados", 7), _i(1),   _i(5)   ],  # 8  Machado do Caos           (342,lv30)
        [_w("Machados", 8), _i(1),   _i(4)   ],  # 9  Machado dos Mortos        (352,lv35)
        [_w("Machados", 8), _i(0),   _i(2)   ],  # 10 Machado Espectral         (362,lv35)
        [_w("Machados", 8), _i(3),   _i(5)   ],  # 11 Machado da Bruma          (372,lv35)
        [_w("Machados", 8), _i(0),   _i(5)   ],  # 12 Machado do Abismo         (382,lv35)
        [_w("Machados", 8), _i(3),   _i(6)   ],  # 13 Machado da Ruína Total    (392,lv35)
        [_w("Machados", 9), _i(0),   _i(4)   ],  # 14 Machado do Cataclismo     (402,lv40)
        [_w("Machados", 9), _i(0),   _i(1)   ],  # 15 Machado dos Titãs         (412,lv40)
        [_w("Machados", 9), _i(3),   _i(4)   ],  # 16 Machado do Vácuo          (422,lv40)
        [_w("Machados", 9), _i(0,2), _i(2)   ],  # 17 Machado da Destruição     (432,lv40)
        [_w("Machados", 9), _i(0,2), _i(3)   ],  # 18 Machado do Vórtice        (442,lv45)
        [_w("Machados", 9), _i(0),   _i(3,2) ],  # 19 Machado do Inevitável     (452,lv45)
    ],

    # ── MARTELOS LENDÁRIOS (22 armas) ─────────────────────────────────────
    # Rúnico(6,lv20)→lv25 | Ogro(7,lv20)→lv30 | Caos(8,lv30)→lv35 | Titã(9,lv30)→lv40/45
    "Martelos Lendários": [
        [_w("Hammers", 6), _i(4),   _i(5)   ],  # 0  Martelo da Destruição   (310,lv25)
        [_w("Hammers", 8), _i(0),   _i(6)   ],  # 1  Martelo das Eras        (370,lv35)
        [_w("Hammers", 9), _i(0,2), _i(4)   ],  # 2  Martelo do Ragnarok     (440,lv45)
        [_w("Hammers", 6), _i(6),   _i(5)   ],  # 3  Martelo do Trovão       (282,lv25)
        [_w("Hammers", 6), _i(1),   _i(2)   ],  # 4  Martelo de Gelo         (292,lv25)
        [_w("Hammers", 6), _i(2),   _i(6)   ],  # 5  Martelo Sombrio         (302,lv25)
        [_w("Hammers", 6), _i(4),   _i(2)   ],  # 6  Martelo do Dragão       (312,lv25)
        [_w("Hammers", 7), _i(1),   _i(6)   ],  # 7  Martelo da Tempestade   (322,lv30)
        [_w("Hammers", 7), _i(1),   _i(5)   ],  # 8  Martelo Sagrado         (332,lv30)
        [_w("Hammers", 7), _i(4,2), _i(6)   ],  # 9  Martelo do Caos         (342,lv30)
        [_w("Hammers", 7), _i(1,2), _i(2)   ],  # 10 Martelo dos Gigantes    (352,lv30)
        [_w("Hammers", 8), _i(1),   _i(4)   ],  # 11 Martelo do Abismo       (362,lv35)
        [_w("Hammers", 8), _i(3),   _i(2)   ],  # 12 Martelo Espectral       (372,lv35)
        [_w("Hammers", 8), _i(0),   _i(5)   ],  # 13 Martelo da Bruma        (382,lv35)
        [_w("Hammers", 8), _i(3),   _i(6)   ],  # 14 Martelo do Cataclismo   (392,lv35)
        [_w("Hammers", 9), _i(0),   _i(2)   ],  # 15 Martelo dos Titãs       (402,lv40)
        [_w("Hammers", 9), _i(0),   _i(1)   ],  # 16 Martelo da Criação      (412,lv40)
        [_w("Hammers", 9), _i(3),   _i(4)   ],  # 17 Martelo do Vácuo        (422,lv40)
        [_w("Hammers", 9), _i(3),   _i(1)   ],  # 18 Martelo da Extinção     (432,lv40)
        [_w("Hammers", 9), _i(0),   _i(3)   ],  # 19 Martelo dos Deuses      (442,lv40)
        [_w("Hammers", 9), _i(0,2), _i(3)   ],  # 20 Martelo do Risco Final  (452,lv45)
        [_w("Hammers", 9), _i(0,2), _i(3,2) ],  # 21 Martelo do Universo     (460,lv45)
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
