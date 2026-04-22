"""
profile_manager.py — Sistema de Perfis de Jogador

Estrutura de arquivos:
  profiles/
    profiles.json       # índice de todos os perfis
    {profile_id}/
      save_v2.json
      run_slot_1.json
      run_slot_2.json
      run_slot_3.json
      achievements.json
"""

import json
import os
import shutil
import uuid
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROFILES_DIR = os.path.join(BASE_DIR, "profiles")
PROFILES_INDEX = os.path.join(PROFILES_DIR, "profiles.json")

COUNTRIES = [
    ("BR", "Brasil"),
    ("US", "EUA"),
    ("PT", "Portugal"),
    ("AR", "Argentina"),
    ("MX", "México"),
    ("ES", "Espanha"),
    ("JP", "Japão"),
    ("DE", "Alemanha"),
    ("FR", "França"),
    ("GB", "Reino Unido"),
    ("IT", "Itália"),
    ("CN", "China"),
    ("KR", "Coreia do Sul"),
    ("AU", "Austrália"),
    ("CA", "Canadá"),
    ("RU", "Rússia"),
    ("IN", "Índia"),
    ("PL", "Polônia"),
    ("NL", "Holanda"),
    ("SE", "Suécia"),
    ("OTHER", "Outro"),
]

COUNTRY_BY_CODE = {c: n for c, n in COUNTRIES}


class ProfileManager:
    def __init__(self):
        self._profiles: list[dict] = []
        self._active_id: str | None = None
        os.makedirs(PROFILES_DIR, exist_ok=True)
        self._load_index()

    # ── Index ──────────────────────────────────────────────────────────────

    def _load_index(self):
        if os.path.exists(PROFILES_INDEX):
            try:
                with open(PROFILES_INDEX, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._profiles = data.get("profiles", [])
                self._active_id = data.get("last_active")
            except Exception:
                self._profiles = []
                self._active_id = None
        self._migrate_legacy()
        # Se há perfis mas nenhum ativo, auto-seleciona o primeiro
        if self._profiles and (self._active_id is None or
                               not any(p["id"] == self._active_id for p in self._profiles)):
            self._active_id = self._profiles[0]["id"]

    def _save_index(self):
        data = {
            "version": 1,
            "last_active": self._active_id,
            "profiles": self._profiles,
        }
        with open(PROFILES_INDEX, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _migrate_legacy(self):
        """Se save_v2.json existir na raiz e não houver perfis, migra automaticamente."""
        old_save = os.path.join(BASE_DIR, "save_v2.json")
        if self._profiles or not os.path.exists(old_save):
            return
        profile = self._create_profile_internal("Jogador 1", "BR", 0)
        self._active_id = profile["id"]
        profile_dir = self.get_profile_dir(profile["id"])
        try:
            shutil.copy2(old_save, os.path.join(profile_dir, "save_v2.json"))
            for i in range(1, 4):
                src = os.path.join(BASE_DIR, f"run_slot_{i}.json")
                if os.path.exists(src):
                    shutil.copy2(src, os.path.join(profile_dir, f"run_slot_{i}.json"))
        except Exception:
            pass
        self._save_index()

    # ── Perfis ────────────────────────────────────────────────────────────

    def _create_profile_internal(self, nickname: str, country: str, avatar_char: int) -> dict:
        existing_ids = {p["id"] for p in self._profiles}
        n = len(self._profiles) + 1
        profile_id = f"p{n}"
        while profile_id in existing_ids:
            n += 1
            profile_id = f"p{n}"

        profile = {
            "id": profile_id,
            "uuid": str(uuid.uuid4()),
            "nickname": nickname.strip()[:20],
            "country": country,
            "avatar_char": avatar_char,
            "created_at": datetime.now().isoformat(),
            "total_playtime": 0.0,
        }
        self._profiles.append(profile)
        os.makedirs(self.get_profile_dir(profile_id), exist_ok=True)
        return profile

    def create_profile(self, nickname: str, country: str, avatar_char: int = 0) -> dict:
        profile = self._create_profile_internal(nickname, country, avatar_char)
        self._active_id = profile["id"]
        self._save_index()
        return profile

    def select_profile(self, profile_id: str) -> bool:
        if any(p["id"] == profile_id for p in self._profiles):
            self._active_id = profile_id
            self._save_index()
            return True
        return False

    def delete_profile(self, profile_id: str) -> bool:
        idx = next((i for i, p in enumerate(self._profiles) if p["id"] == profile_id), None)
        if idx is None:
            return False
        profile_dir = self.get_profile_dir(profile_id)
        if os.path.exists(profile_dir):
            shutil.rmtree(profile_dir)
        self._profiles.pop(idx)
        if self._active_id == profile_id:
            self._active_id = self._profiles[0]["id"] if self._profiles else None
        self._save_index()
        return True

    def update_playtime(self, seconds: float):
        """Adiciona tempo de jogo ao perfil ativo."""
        p = self.get_active_profile()
        if p is not None:
            p["total_playtime"] = p.get("total_playtime", 0.0) + seconds
            self._save_index()

    def update_nickname(self, profile_id: str, nickname: str):
        p = self.get_profile_by_id(profile_id)
        if p:
            p["nickname"] = nickname.strip()[:20]
            self._save_index()

    # ── Getters ───────────────────────────────────────────────────────────

    def get_all_profiles(self) -> list[dict]:
        return list(self._profiles)

    def get_active_profile(self) -> dict | None:
        if self._active_id is None:
            return None
        return next((p for p in self._profiles if p["id"] == self._active_id), None)

    def get_profile_by_id(self, profile_id: str) -> dict | None:
        return next((p for p in self._profiles if p["id"] == profile_id), None)

    def has_profiles(self) -> bool:
        return len(self._profiles) > 0

    def has_active_profile(self) -> bool:
        return self._active_id is not None and self.get_active_profile() is not None

    # ── Caminhos ──────────────────────────────────────────────────────────

    def get_profile_dir(self, profile_id: str | None = None) -> str:
        pid = profile_id or self._active_id
        if pid is None:
            raise ValueError("Nenhum perfil ativo")
        return os.path.join(PROFILES_DIR, pid)

    def get_save_path(self, filename: str, profile_id: str | None = None) -> str:
        """Retorna o caminho completo de um arquivo de save no perfil ativo (ou especificado)."""
        return os.path.join(self.get_profile_dir(profile_id), filename)

    # ── Placar Online (estrutura para implementação futura) ───────────────

    def get_leaderboard_entry(self, stats: dict | None = None) -> dict | None:
        """Retorna dados do perfil formatados para o placar online."""
        p = self.get_active_profile()
        if not p:
            return None
        entry = {
            "profile_uuid": p.get("uuid"),
            "nickname": p.get("nickname"),
            "country": p.get("country"),
            "total_playtime": p.get("total_playtime", 0.0),
            "game_version": None,
        }
        if stats:
            entry.update({
                "total_kills": stats.get("total_kills", 0),
                "boss_kills": stats.get("boss_kills", 0),
                "max_level_reached": stats.get("max_level_reached", 0),
                "games_played": stats.get("games_played", 0),
            })
        return entry

    @staticmethod
    def format_playtime(seconds: float) -> str:
        """Formata segundos em 'Xh Ym' ou 'Zm'."""
        total_m = int(seconds // 60)
        h = total_m // 60
        m = total_m % 60
        if h > 0:
            return f"{h}h {m:02d}m"
        return f"{m}m"
