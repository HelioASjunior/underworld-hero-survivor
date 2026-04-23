"""
achievements.py — Sistema de Conquistas

Séries:
  gold_1  … gold_10     — ouro acumulado (total_gold_accumulated)
  forte_1 … forte_10    — abates totais  (total_kills)
  hardcore_1 … hardcore_10 — fases Hardcore desbloqueadas
"""

import json
import os
from datetime import datetime

# ── Thresholds ────────────────────────────────────────────────────────────

_GOLD_THRESHOLDS = [
    1_000, 5_000, 10_000, 25_000, 50_000,
    100_000, 250_000, 500_000, 1_000_000, 5_000_000,
]

_FORTE_THRESHOLDS = [
    100, 500, 1_000, 2_500, 5_000,
    10_000, 25_000, 50_000, 100_000, 500_000,
]

# ── Definições ────────────────────────────────────────────────────────────

ACHIEVEMENT_DEFS: list[dict] = []

_gold_names = [
    "Primeiras Riquezas", "Saqueador", "Comerciante", "Mercador Rico", "Magnata",
    "Barão do Ouro", "Rei dos Tesouros", "Imperador", "Lendário da Fortuna", "Deus da Fortuna",
]
for _i, (_thresh, _name) in enumerate(zip(_GOLD_THRESHOLDS, _gold_names), 1):
    ACHIEVEMENT_DEFS.append({
        "id": f"gold_{_i}",
        "series": "gold",
        "index": _i,
        "icon": f"gold{_i}.png",
        "name": _name,
        "desc": f"Acumule {_thresh:,} de ouro no total".replace(",", "."),
        "check": lambda s, t=_thresh: s.get("total_gold_accumulated", 0.0) >= t,
    })

_hc_names = [
    "Iniciado Hardcore", "Sobrevivente Hardcore", "Guerreiro Hardcore",
    "Veterano Hardcore", "Elite Hardcore", "Mestre Hardcore",
    "Lendário Hardcore", "Terror do Abismo", "Conquista das Sombras", "Rei do Inferno",
]
for _i, _name in enumerate(_hc_names, 1):
    ACHIEVEMENT_DEFS.append({
        "id": f"hardcore_{_i}",
        "series": "hardcore",
        "index": _i,
        "icon": f"hardcore{_i}.png",
        "name": _name,
        "desc": f"Desbloqueie a Fase {_i} no Modo Hardcore",
        "check": lambda s, stage=_i: s.get("hardcore_stages_unlocked", 1) >= stage,
    })

_forte_names = [
    "Primeiro Sangue", "Caçador Nato", "Guerreiro", "Destruidor", "Matador de Elite",
    "Campeão da Batalha", "Lendário das Guerras", "Ceifador de Almas", "Flagelo dos Monstros", "O Inevitável",
]
for _i, (_thresh, _name) in enumerate(zip(_FORTE_THRESHOLDS, _forte_names), 1):
    ACHIEVEMENT_DEFS.append({
        "id": f"forte_{_i}",
        "series": "forte",
        "index": _i,
        "icon": f"forte{_i}.png",
        "name": _name,
        "desc": f"Elimine {_thresh:,} inimigos no total".replace(",", "."),
        "check": lambda s, t=_thresh: s.get("total_kills", 0) >= t,
    })

ACHIEVEMENT_BY_ID: dict[str, dict] = {a["id"]: a for a in ACHIEVEMENT_DEFS}

# Ordenados por série para exibição
SERIES_ORDER = ["gold", "forte", "hardcore"]

# ── Persistência ──────────────────────────────────────────────────────────

def _default_data() -> dict:
    return {
        "unlocked": [],
        "total_gold_accumulated": 0.0,
        "hardcore_stages_unlocked": 1,
    }


def load_achievements(profile_dir: str) -> dict:
    path = os.path.join(profile_dir, "achievements.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            defaults = _default_data()
            defaults.update(data)
            return defaults
        except Exception:
            pass
    return _default_data()


def save_achievements(profile_dir: str, data: dict):
    os.makedirs(profile_dir, exist_ok=True)
    path = os.path.join(profile_dir, "achievements.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ── Verificação ───────────────────────────────────────────────────────────

def check_new_achievements(combined_stats: dict, ach_data: dict) -> list[dict]:
    """
    Verifica conquistas novas.
    combined_stats deve ter: total_kills, total_gold_accumulated,
                             hardcore_stages_unlocked.
    Modifica ach_data in-place (adiciona entradas em 'unlocked').
    Retorna lista de defs de conquistas recém-desbloqueadas.
    """
    unlocked_ids = {a["id"] for a in ach_data.get("unlocked", [])}
    new_unlocks = []
    now = datetime.now().isoformat()

    for ach in ACHIEVEMENT_DEFS:
        if ach["id"] not in unlocked_ids and ach["check"](combined_stats):
            new_unlocks.append(ach)
            ach_data["unlocked"].append({"id": ach["id"], "unlocked_at": now})
            unlocked_ids.add(ach["id"])

    return new_unlocks


def get_unlocked_set(ach_data: dict) -> set[str]:
    return {a["id"] for a in ach_data.get("unlocked", [])}


def count_by_series(ach_data: dict) -> dict[str, tuple[int, int]]:
    """Retorna {série: (desbloqueadas, total)} para cada série."""
    unlocked = get_unlocked_set(ach_data)
    result = {}
    for series in SERIES_ORDER:
        defs = [a for a in ACHIEVEMENT_DEFS if a["series"] == series]
        result[series] = (sum(1 for a in defs if a["id"] in unlocked), len(defs))
    return result
