import math
import random
import pygame
import os
import json
import threading
import webbrowser
from datetime import datetime, timedelta
from pool import ParticlePool
import balance as _bal
from profile_manager import ProfileManager, COUNTRIES, COUNTRY_BY_CODE
import achievements as _ach

from characters import CharacterCombatContext, CharacterDependencies, create_player
import hud as dark_hud
from forest_biome import build_forest_ground, ForestDecoManager
from dungeon_biome import DungeonDecoManager
from volcano_biome import build_volcano_ground, VolcanoDecoManager
from moon_biome import build_moon_ground, MoonDecoManager
from hub_room import HubScene, MarketScene
from drops import Drop as ModularDrop
from enemies import Enemy as ModularEnemy, EnemyProjectile as ModularEnemyProjectile, EnemyDeathAnim
from ecs_world import World as ECSWorld
from ecs_systems import (
    EnemyAISystem, EnemyCombatSystem, EnemyAnimationSystem, EnemyRenderSystem,
)
from upgrades import (
    get_upgrade_description as get_upgrade_description_mod,
    pick_upgrades_with_synergy as pick_upgrades_with_synergy_mod,
)
from combat.projectiles import (
    MeleeSlash as CoreMeleeSlash,
    Projectile as CoreProjectile,
    projectile_enemy_collision as core_projectile_enemy_collision,
)
import numpy as np
from spatial_index import EnemyBatchIndex, ObstacleGridIndex, PERF, _CYTHON_ACTIVE
from hot_kernels import enemy_separation, NUMBA_ACTIVE
from projectile_pool import ProjectilePool, MeleeSlashPool, init_pools as init_projectile_pools, projectile_pool, melee_slash_pool
from ui_scaler import init_ui_scaler, Anchor
from performance import frame_profiler, profile_section
from mining_system import MiningSystem, ORE_DEFS as MINING_ORE_DEFS
from crafting_system import CRAFTED_CATEGORIES, CRAFTED_WEAPON_STATS, CRAFT_RECIPES, CRAFT_CATEGORY_ORDER

# =========================================================
# CONFIGURAÇÕES DE PERSISTÊNCIA -SETTINGS.JSON-
# =========================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(BASE_DIR, "settings.json")

def load_settings(force_default=False):
    default_settings = {
        "video": {
            "resolution": "1920x1080",
            "fullscreen": "Off",
            "vsync": "Off",
            "fps_limit": 60,
            "show_fps": "Off"
        },
        "audio": {
            "music": 70,
            "sfx": 80,
            "mute": "Off"
        },
        "controls": {
            "up": "w",
            "down": "s",
            "left": "a",
            "right": "d",
            "dash": "space",
            "ultimate": "e",
            "pause": "p"
        },
        "gameplay": {
            "auto_pickup_chest": "On",
            "auto_apply_chest_reward": "On",
            "show_offscreen_arrows": "On",
        },
        "accessibility": {
            "screen_shake": 100,
            "ui_size": 100,
            "high_contrast": "Off"
        }
    }

    if force_default:
        return json.loads(json.dumps(default_settings))

    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f:
                loaded = json.load(f)

            # Migra formatos antigos (flat) para o formato atual por categoria.
            if "video" not in loaded:
                loaded = {
                    "video": {
                        "resolution": f"{loaded.get('resolution', [1920, 1080])[0]}x{loaded.get('resolution', [1920, 1080])[1]}",
                        "fullscreen": "On" if loaded.get("fullscreen", False) else "Off",
                        "vsync": "Off",
                        "fps_limit": 60,
                        "show_fps": "Off"
                    },
                    "audio": {
                        "music": int(loaded.get("music_volume", 0.7) * 100),
                        "sfx": int(loaded.get("sfx_volume", 0.8) * 100),
                        "mute": "Off"
                    },
                    "controls": default_settings["controls"],
                    "gameplay": default_settings["gameplay"],
                    "accessibility": {
                        "screen_shake": 100 if loaded.get("screen_shake", True) else 0,
                        "ui_size": 100,
                        "high_contrast": "Off"
                    }
                }

            merged = json.loads(json.dumps(default_settings))
            for cat, values in loaded.items():
                if cat in merged and isinstance(values, dict):
                    merged[cat].update(values)
            return merged
        except Exception:
            return json.loads(json.dumps(default_settings))

    return load_settings(force_default=True)


def save_settings(settings):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f, indent=4)


def _deepcopy_settings(src):
    return json.loads(json.dumps(src))


def get_control_key_code(action_name):
    if not settings or "controls" not in settings:
        return pygame.K_UNKNOWN
    key_name = settings["controls"].get(action_name, "")
    try:
        return pygame.key.key_code(key_name)
    except Exception:
        return pygame.K_UNKNOWN


def is_control_pressed(keys, action_name):
    key_code = get_control_key_code(action_name)
    if key_code != pygame.K_UNKNOWN and keys[key_code]:
        return True
    return _gamepad_action(action_name)


# ─── Gamepad ─────────────────────────────────────────────────────────────────
_joy = None
GAMEPAD_DEADZONE = 0.25


def _gamepad_connect(device_index=0):
    global _joy
    try:
        j = pygame.joystick.Joystick(device_index)
        j.init()
        _joy = j
    except Exception:
        _joy = None


def _gamepad_disconnect():
    global _joy
    if _joy:
        try:
            _joy.quit()
        except Exception:
            pass
    _joy = None


def _joy_axis(axis):
    if _joy is None or axis >= _joy.get_numaxes():
        return 0.0
    v = _joy.get_axis(axis)
    return v if abs(v) > GAMEPAD_DEADZONE else 0.0


def _joy_hat():
    if _joy is None or _joy.get_numhats() == 0:
        return (0, 0)
    return _joy.get_hat(0)


def _gamepad_action(action):
    """Retorna True se o gamepad está pressionando a ação de movimento indicada."""
    if _joy is None:
        return False
    ax_x, ax_y = _joy_axis(0), _joy_axis(1)
    hx, hy = _joy_hat()
    if action == "left":  return ax_x < 0 or hx < 0
    if action == "right": return ax_x > 0 or hx > 0
    if action == "up":    return ax_y < 0 or hy > 0
    if action == "down":  return ax_y > 0 or hy < 0
    return False


def apply_audio_runtime(settings_dict):
    global MUSIC_VOLUME, SFX_VOLUME
    MUSIC_VOLUME = settings_dict["audio"].get("music", 100) / 100.0
    SFX_VOLUME = settings_dict["audio"].get("sfx", 100) / 100.0
    if settings_dict["audio"].get("mute") == "On":
        pygame.mixer.music.set_volume(0.0)
    else:
        pygame.mixer.music.set_volume(MUSIC_VOLUME)

def _native_resolution():
    """Detecta a resolução nativa do monitor principal de forma segura."""
    info = pygame.display.Info()
    w = info.current_w if info.current_w > 100 else 1920
    h = info.current_h if info.current_h > 100 else 1080
    return (max(800, min(w, 7680)), max(600, min(h, 4320)))

_resolution_cache: list[str] | None = None

def _get_available_resolutions() -> list[str]:
    """Retorna resoluções estáveis para o menu de vídeo.
    Evita modos exóticos que quebram o layout (ex.: 1128x634)."""
    global _resolution_cache
    if _resolution_cache is not None:
        return _resolution_cache

    native_w, native_h = _native_resolution()
    min_w, min_h = 1280, 720
    if native_w < min_w or native_h < min_h:
        min_w, min_h = 800, 600

    curated_modes = [
        (1280, 720), (1280, 800), (1280, 960), (1280, 1024),
        (1360, 768), (1366, 768), (1440, 900),
        (1600, 900), (1600, 1200), (1680, 1050),
        (1920, 1080), (1920, 1200),
        (2560, 1080), (2560, 1440), (2560, 1600),
        (3440, 1440), (3840, 2160),
    ]

    accepted: set[tuple[int, int]] = set()

    for w, h in curated_modes:
        if min_w <= w <= native_w and min_h <= h <= native_h:
            accepted.add((w, h))

    try:
        modes = pygame.display.list_modes()
        if modes and modes != -1:
            for w, h in modes:
                if min_w <= w <= native_w and min_h <= h <= native_h:
                    accepted.add((w, h))
    except Exception:
        pass

    native_key = f"{native_w}x{native_h}"
    result = [f"{w}x{h}" for (w, h) in sorted(accepted, key=lambda m: (m[0] * m[1], m[0], m[1]))]

    if native_key not in result:
        result.append(native_key)

    if "1920x1080" not in result and native_w >= 1920 and native_h >= 1080:
        result.append("1920x1080")

    if not result:
        result = [native_key]

    _resolution_cache = result
    print(f"[Resoluções] Nativa: {native_w}x{native_h} | Detectadas: {len(result)} resoluções")
    return result

def apply_settings(settings_dict):
    global SCREEN_W, SCREEN_H, screen, FPS, MUSIC_VOLUME, SFX_VOLUME

    # Resolução: usa a salva, mas sanitiza contra a lista suportada
    raw_res = settings_dict["video"].get("resolution", "auto")
    native_w, native_h = _native_resolution()
    fullscreen = settings_dict["video"].get("fullscreen") == "On"

    # Em fullscreen usa sempre a nativa para evitar distorção/corte de UI
    if fullscreen:
        res_w, res_h = native_w, native_h
    else:
        available = _get_available_resolutions()
        if raw_res == "auto":
            res_w, res_h = native_w, native_h
        elif raw_res in available:
            try:
                res_w, res_h = map(int, raw_res.split('x'))
            except ValueError:
                res_w, res_h = native_w, native_h
        else:
            # Fallback seguro para resolução inválida salva em arquivo
            fallback = "1920x1080" if "1920x1080" in available else f"{native_w}x{native_h}"
            try:
                res_w, res_h = map(int, fallback.split('x'))
            except ValueError:
                res_w, res_h = native_w, native_h
            settings_dict["video"]["resolution"] = fallback

    SCREEN_W, SCREEN_H = res_w, res_h

    vsync      = settings_dict["video"].get("vsync")     == "On"

    # Monta flags progressivamente com fallback para garantir que o jogo abre
    flags = pygame.DOUBLEBUF  # double buffering reduz tearing e habilita aceleração HW
    if fullscreen:
        flags |= pygame.FULLSCREEN
    if vsync:
        flags |= pygame.SCALED   # SCALED + vsync é mais compatível que HWSURFACE em HW antigo
    try:
        screen = pygame.display.set_mode((SCREEN_W, SCREEN_H), flags)
    except pygame.error:
        # Fallback seguro: janela sem flags especiais na resolução nativa
        SCREEN_W, SCREEN_H = _native_resolution()
        screen = pygame.display.set_mode((SCREEN_W, SCREEN_H), pygame.DOUBLEBUF)

    FPS = int(settings_dict["video"].get("fps_limit", 60))
    apply_audio_runtime(settings_dict)

# =========================================================
# VARIÁVEIS GLOBAIS E INICIAIS (DO ORIGINAL)
# =========================================================
# =========================================================
# CONFIGURAÇÕES INICIAIS
# =========================================================
SCREEN_W, SCREEN_H = 1920, 1080
FPS = 60
ASSET_DIR = os.path.join(BASE_DIR, "assets")
FONT_DARK_PATH = os.path.join(ASSET_DIR, "fonts", "Catholicon.ttf")
GAME_VERSION = "1.1.0"
BUILD_TYPE = "META"

UI_THEME = dark_hud.UI_THEME
ITEM_COLORS = dark_hud.ITEM_COLORS


def load_dark_font(size, bold=False):
    return dark_hud.load_dark_font(size, bold=bold, asset_dir=ASSET_DIR)


def load_title_font(size, bold=False):
    """Fonte gótica pesada (Blackletter) — títulos, cabeçalhos e menus."""
    return dark_hud.load_title_font(size, bold=bold, asset_dir=ASSET_DIR)


def load_body_font(size, bold=False):
    """Fonte medieval (PfefferMediaeval) — descrições de itens e corpo de texto."""
    return dark_hud.load_body_font(size, bold=bold, asset_dir=ASSET_DIR)


def load_number_font(size, bold=False):
    """Fonte dedicada para números e valores numéricos (Catholicon)."""
    return dark_hud.load_number_font(size, bold=bold, asset_dir=ASSET_DIR)

# =========================================================
# META-PROGRESSÃO, SAVE E CONQUISTAS
# =========================================================
SAVE_FILE = os.path.join(BASE_DIR, "save_v2.json")
RUN_SLOT_FILES = [
    os.path.join(BASE_DIR, "run_slot_1.json"),
    os.path.join(BASE_DIR, "run_slot_2.json"),
    os.path.join(BASE_DIR, "run_slot_3.json"),
]

# Itens que começam desbloqueados
DEFAULT_UNLOCKS = [
    "DANO ++", "VELOCIDADE ++", "VIDA MÁXIMA", "TIRO RÁPIDO", "CURA",
    "CHAR_0", "CHAR_1", "CHAR_2", "CHAR_3", "CHAR_4", "CHAR_5", "CHAR_6", "CHAR_7", "DIFF_FÁCIL", "DIFF_MÉDIO"
]

save_data = {
    "gold": 0,
    "perm_upgrades": {
        "crit_dmg": 0, "exp_size": 0, "chaos_bolt": 0,
        "regen": 0, "aura_res": 0, "thorns": 0,
        "fire_dmg": 0, "burn_area": 0, "inferno": 0
    },
    "stats": {
        "total_kills": 0,
        "total_time": 0,
        "boss_kills": 0,
        "deaths": 0,
        "games_played": 0,
        "max_level_reached": 0
    },
    "unlocks": list(DEFAULT_UNLOCKS),
    "daily_missions": {
        "last_reset": "", # Data do último reset (YYYY-MM-DD)
        "active": []      # Lista de missões ativas hoje
    },
    # Itens comprados na loja (rastreamento de propriedade para a loja)
    "purchased_items": [],
    # Itens no baú (movidos para cá ao comprar; podem ser transferidos ao inventário do personagem)
    "chest_items": [],
    # Inventário por personagem — {str(char_id): [{category, idx}]}
    "char_inventories": {},
    # Equipamentos por personagem — {str(char_id): {slot: {category,idx}|None}}
    "char_equipped": {},
    # Progressão de fases do Modo Hardcore
    "hardcore_stages": {"unlocked": 1},
    # Dificuldades completadas (boss derrubado) — desbloqueiam Hardcore quando todas 3 concluídas
    "beaten_difficulties": [],
}

# Definição das Missões Diárias
DAILY_MISSIONS_POOL = [
    {"id": "kill_250",   "name": "EXTERMINADOR",      "desc": "Mate 250 inimigos em uma partida",    "goal": 250,  "reward": 800,  "type": "kills"},
    {"id": "kill_500",   "name": "CEIFADOR",           "desc": "Mate 500 inimigos em uma partida",    "goal": 500,  "reward": 1500, "type": "kills"},
    {"id": "kill_800",   "name": "LORDE DA MORTE",     "desc": "Mate 800 inimigos em uma partida",    "goal": 800,  "reward": 2500, "type": "kills"},
    {"id": "survive_8m", "name": "RESISTENTE",         "desc": "Sobreviva por 8 minutos",             "goal": 480,  "reward": 1200, "type": "time"},
    {"id": "survive_12m","name": "IMORTAL",            "desc": "Sobreviva por 12 minutos",            "goal": 720,  "reward": 2000, "type": "time"},
    {"id": "survive_18m","name": "ETERNO",             "desc": "Sobreviva por 18 minutos",            "goal": 1080, "reward": 3200, "type": "time"},
    {"id": "boss_2",     "name": "CAÇADOR DE CHEFÕES", "desc": "Derrote 2 Chefões numa partida",      "goal": 2,    "reward": 2200, "type": "boss"},
    {"id": "boss_4",     "name": "TERROR DOS TITÃS",   "desc": "Derrote 4 Chefões numa partida",      "goal": 4,    "reward": 4000, "type": "boss"},
    {"id": "level_20",   "name": "VETERANO",           "desc": "Alcance o Nível 20 numa partida",     "goal": 20,   "reward": 1600, "type": "level"},
    {"id": "level_30",   "name": "LENDA",              "desc": "Alcance o Nível 30 numa partida",     "goal": 30,   "reward": 3000, "type": "level"},
    {"id": "gold_600",   "name": "SAQUEADOR",          "desc": "Colete 600 de Ouro em uma partida",   "goal": 600,  "reward": 1000, "type": "gold"},
    {"id": "gold_1500",  "name": "MAGNATA",            "desc": "Colete 1500 de Ouro em uma partida",  "goal": 1500, "reward": 2400, "type": "gold"},
]

# Definição das Conquistas e Requisitos
ACHIEVEMENTS = {
    "CHAR_1": {"type": "char", "name": "CAÇADOR", "desc": "Mate 500 inimigos no total", "req": lambda s: s["total_kills"] >= 500},
    "CHAR_2": {"type": "char", "name": "MAGO", "desc": "Derrote 1 Chefão", "req": lambda s: s["boss_kills"] >= 1},
    "CHAR_3": {"type": "char", "name": "VAMPIRE", "desc": "Derrote 3 Chefões", "req": lambda s: s["boss_kills"] >= 3},
    "CHAR_4": {"type": "char", "name": "DEMÔNIO", "desc": "Derrote 5 Chefões", "req": lambda s: s["boss_kills"] >= 5},
    "CHAR_5": {"type": "char", "name": "GOLEM", "desc": "Derrote 8 Chefões", "req": lambda s: s["boss_kills"] >= 8},
    "CHAR_6": {"type": "char", "name": "ESQUELETO", "desc": "Derrote 12 Chefões", "req": lambda s: s["boss_kills"] >= 12},
    "CHAR_7": {"type": "char", "name": "FURACÃO", "desc": "Derrote 15 Chefões", "req": lambda s: s["boss_kills"] >= 15},

    "DIFF_DIFÍCIL": {"type": "diff", "name": "DIFÍCIL", "desc": "Sobreviva 10 min (total)", "req": lambda s: s["total_time"] >= 600},
    "DIFF_HARDCORE": {"type": "diff", "name": "HARDCORE", "desc": "Complete Fácil, Médio e Difícil", "req": lambda s: len({"FÁCIL", "MÉDIO", "DIFÍCIL"} & set(save_data.get("beaten_difficulties", []))) >= 3},

    "TIRO MÚLTIPLO": {"type": "upg", "name": "TIRO MÚLTIPLO", "desc": "Alcance Nível 10 em uma partida", "req": lambda s: s["max_level_reached"] >= 10},
    "CHAMA ARDENTE": {"type": "upg", "name": "CHAMA ARDENTE", "desc": "Colete 200 Ouro no total", "req": lambda s: True},
    "EXPLOSÃO": {"type": "upg", "name": "EXPLOSÃO", "desc": "Mate 1000 inimigos no total", "req": lambda s: s["total_kills"] >= 1000},
    "ORBES MÁGICOS": {"type": "upg", "name": "ORBES MÁGICOS", "desc": "Jogue 3 partidas", "req": lambda s: s["games_played"] >= 3},
    "PERFURAÇÃO": {"type": "upg", "name": "PERFURAÇÃO", "desc": "Mate 1500 inimigos", "req": lambda s: s["total_kills"] >= 1500},
    "SORTE": {"type": "upg", "name": "SORTE", "desc": "Morra 1 vez (Piedade)", "req": lambda s: s["deaths"] >= 1},
    "RICOCHE": {"type": "upg", "name": "RICOCHE", "desc": "Desbloqueie o Caçador", "req": lambda s: "CHAR_1" in save_data["unlocks"]},
    "EXECUÇÃO": {"type": "upg", "name": "EXECUÇÃO", "desc": "Derrote 3 Chefões", "req": lambda s: s["boss_kills"] >= 3},
    "FÚRIA": {"type": "upg", "name": "FÚRIA", "desc": "Chegue a 10% de HP (em uma run)", "req": lambda s: True}, # Lógica especial ingame
    "ÍMÃ DE XP": {"type": "upg", "name": "ÍMÃ DE XP", "desc": "Sobreviva 5 min totais", "req": lambda s: s["total_time"] >= 300},
}

# ── Sistema de Perfis ─────────────────────────────────────────────────────
profile_mgr: "ProfileManager | None" = None
achievements_data: dict = {}
_achievement_notifs: list = []   # [[ach_def, remaining_seconds], ...]
_ach_icon_cache: dict = {}       # {filename: pygame.Surface}
_avatar_icon_cache: dict = {}    # {(idx, size): pygame.Surface}
_select_perfil_img = None        # Cached background image for profile select screen
_perfilnovo_img_cache = None     # Cached profile widget background (perfilnovo.png)

# XP por minuto sobrevivido por dificuldade
PROFILE_XP_RATES = {"FÁCIL": 10, "MÉDIO": 20, "DIFÍCIL": 35, "HARDCORE": 55}

def _active_save_file() -> str:
    if profile_mgr is not None and profile_mgr.has_active_profile():
        return profile_mgr.get_save_path("save_v2.json")
    return SAVE_FILE

def _active_run_slot_file(slot_index: int) -> str:
    if profile_mgr is not None and profile_mgr.has_active_profile():
        return profile_mgr.get_save_path(f"run_slot_{slot_index + 1}.json")
    idx = max(0, min(len(RUN_SLOT_FILES) - 1, slot_index))
    return RUN_SLOT_FILES[idx]

def _reload_achievements():
    global achievements_data
    if profile_mgr is not None and profile_mgr.has_active_profile():
        achievements_data = _ach.load_achievements(profile_mgr.get_profile_dir())
        # Sync hardcore stage from save_data
        achievements_data["hardcore_stages_unlocked"] = max(
            achievements_data.get("hardcore_stages_unlocked", 1),
            save_data["hardcore_stages"].get("unlocked", 1),
        )
    else:
        achievements_data = _ach._default_data()

def _check_achievements():
    global achievements_data, _achievement_notifs
    if not (profile_mgr and profile_mgr.has_active_profile()):
        return
    combined = {
        **save_data["stats"],
        "total_gold_accumulated": achievements_data.get("total_gold_accumulated", 0.0),
        "hardcore_stages_unlocked": achievements_data.get("hardcore_stages_unlocked", 1),
    }
    new = _ach.check_new_achievements(combined, achievements_data)
    if new:
        for a in new:
            _achievement_notifs.append([a, 5.0])
        _ach.save_achievements(profile_mgr.get_profile_dir(), achievements_data)

def load_save():
    global save_data
    _path = _active_save_file()
    if os.path.exists(_path):
        try:
            with open(_path, "r") as f:
                loaded = json.load(f)
                # Merge seguro para não perder chaves novas em updates
                if "gold" in loaded: save_data["gold"] = loaded["gold"]
                if "perm_upgrades" in loaded: save_data["perm_upgrades"].update(loaded["perm_upgrades"])
                if "stats" in loaded: save_data["stats"].update(loaded["stats"])
                if "unlocks" in loaded:
                    for u in loaded["unlocks"]:
                        if u not in save_data["unlocks"]: save_data["unlocks"].append(u)
                if "daily_missions" in loaded:
                    save_data["daily_missions"].update(loaded["daily_missions"])
                if "purchased_items" in loaded:
                    save_data["purchased_items"] = loaded["purchased_items"]
                # chest_items: migrar de purchased_items se não existir ainda
                if "chest_items" in loaded:
                    save_data["chest_items"] = loaded["chest_items"]
                elif save_data["chest_items"] == []:
                    save_data["chest_items"] = list(save_data["purchased_items"])
                if "char_inventories" in loaded:
                    save_data["char_inventories"] = loaded["char_inventories"]
                if "hardcore_stages" in loaded:
                    save_data["hardcore_stages"].update(loaded["hardcore_stages"])
                if "beaten_difficulties" in loaded:
                    save_data["beaten_difficulties"] = loaded["beaten_difficulties"]
                if "char_equipped" in loaded:
                    save_data["char_equipped"] = loaded["char_equipped"]
                elif "equipped_items" in loaded:
                    # Migrar formato antigo (equipped_items global) → char 0
                    ei = loaded["equipped_items"]
                    save_data["char_equipped"]["0"] = {
                        "helmet": None, "armor": None, "legs": None, "boots": None,
                        "weapon": ei.get("weapon"), "shield": ei.get("shield"),
                    }
        except: pass
    check_daily_reset()

def check_daily_reset():
    global save_data
    today = datetime.now().strftime("%Y-%m-%d")
    if save_data["daily_missions"]["last_reset"] != today:
        save_data["daily_missions"]["last_reset"] = today
        new_missions = random.sample(DAILY_MISSIONS_POOL, 6)
        save_data["daily_missions"]["active"] = []
        for m in new_missions:
            m_copy = m.copy()
            m_copy["progress"] = 0
            m_copy["completed"] = False
            m_copy["claimed"] = False
            save_data["daily_missions"]["active"].append(m_copy)
        save_game()

_EMPTY_EQUIPPED = lambda: {
    "helmet": None, "armor": None, "legs": None,
    "boots": None, "weapon": None, "shield": None,
}

def get_char_inventory(cid: int) -> list:
    """Retorna (e garante existência de) o inventário do personagem cid."""
    k = str(cid)
    if k not in save_data["char_inventories"]:
        save_data["char_inventories"][k] = []
    return save_data["char_inventories"][k]

def get_char_equipped(cid: int) -> dict:
    """Retorna (e garante existência de) o dict de equipamentos do personagem cid."""
    k = str(cid)
    if k not in save_data["char_equipped"]:
        save_data["char_equipped"][k] = _EMPTY_EQUIPPED()
    return save_data["char_equipped"][k]

# Categorias que vão para slot de arma
_WEAPON_CATEGORIES = {"Espadas", "Machados", "Hammers", "Bows", "Crossbows", "Cajados",
                      "Espadas Lendárias", "Machados Lendários", "Martelos Lendários", "Cajados Lendários"}

def item_slot(category: str) -> str | None:
    """Retorna o slot correto para uma categoria de item, ou None se não equipável."""
    if category == "Escudos":    return "shield"
    if category in _WEAPON_CATEGORIES: return "weapon"
    if category == "Capacetes":  return "helmet"
    if category == "Armaduras":  return "armor"
    if category == "Calças":     return "legs"
    if category == "Botas":      return "boots"
    return None

def get_active_profile_level() -> int:
    """Retorna o nível atual do perfil ativo (1 se não houver perfil)."""
    if profile_mgr and profile_mgr.has_active_profile():
        ap = profile_mgr.get_active_profile()
        return ProfileManager.xp_to_level(ap.get("profile_xp", 0))[0]
    return 1

def update_mission_progress(m_type, amount, is_absolute=False):
    global save_data
    changed = False
    
    # Otimização: Throttling para missões de tempo (só processa a cada 1 segundo acumulado)
    if m_type == "time":
        if not hasattr(update_mission_progress, "_time_acc"): update_mission_progress._time_acc = 0.0
        update_mission_progress._time_acc += amount
        if update_mission_progress._time_acc < 1.0: return
        amount = update_mission_progress._time_acc
        update_mission_progress._time_acc = 0.0

    for m in save_data["daily_missions"]["active"]:
        if m["type"] == m_type and not m["completed"]:
            if is_absolute:
                m["progress"] = max(m["progress"], amount)
            else:
                m["progress"] += amount
            
            if m["progress"] >= m["goal"]:
                m["progress"] = m["goal"]
                m["completed"] = True
            changed = True
    
    # Otimização: Durante a partida, não salvamos no disco a cada pequena mudança de progresso
    # O progresso fica na memória e é salvo no final da partida ou ao sair do menu.
    # Apenas salvamos imediatamente se uma missão for COMPLETADA.
    if changed:
        any_completed = any(m["completed"] and not m.get("_notified", False) for m in save_data["daily_missions"]["active"])
        if any_completed:
            for m in save_data["daily_missions"]["active"]:
                if m["completed"]: m["_notified"] = True
            save_game()

def save_game():
    with open(_active_save_file(), "w") as f:
        json.dump(save_data, f)


def get_run_slot_path(slot_index):
    return _active_run_slot_file(slot_index)


def save_run_slot(slot_index=0):
    if player is None:
        return False

    data = {
        "char_id": getattr(player, "char_id", 0),
        "selected_difficulty": selected_difficulty,
        "selected_pact": selected_pact,
        "selected_bg": selected_bg,
        "kills": kills,
        "game_time": game_time,
        "level": level,
        "xp": xp,
        "player_hp": player.hp,
        "player_upgrades": list(player_upgrades),
        "run_gold_collected": float(globals().get("run_gold_collected", 0.0)),
    }

    try:
        with open(get_run_slot_path(slot_index), "w") as f:
            json.dump(data, f, indent=4)
        return True
    except Exception:
        return False


def load_run_slot(slot_index=0):
    global selected_difficulty, selected_pact, selected_bg
    global kills, game_time, level, xp, run_gold_collected

    path = get_run_slot_path(slot_index)
    if not os.path.exists(path):
        return False

    try:
        with open(path, "r") as f:
            data = json.load(f)
    except Exception:
        return False

    try:
        char_id = int(data.get("char_id", 0))
        selected_difficulty = data.get("selected_difficulty", "MÉDIO")
        selected_pact = data.get("selected_pact", "NENHUM")
        selected_bg = data.get("selected_bg", "dungeon")
        load_all_assets()

        prev_games = save_data["stats"].get("games_played", 0)
        reset_game(char_id)
        save_data["stats"]["games_played"] = prev_games

        for upg in data.get("player_upgrades", []):
            apply_upgrade(upg)

        kills = int(data.get("kills", 0))
        game_time = float(data.get("game_time", 0.0))
        level = max(1, int(data.get("level", 1)))
        xp = int(data.get("xp", 0))
        if player:
            player.hp = max(0.1, min(PLAYER_MAX_HP, float(data.get("player_hp", PLAYER_MAX_HP))))

        run_gold_collected = float(data.get("run_gold_collected", 0.0))
        return True
    except Exception:
        return False

load_save() 

# Árvore de Talentos Avançada
TALENT_TREE = {
    "CAOS": {
        "title": "CAMINHO DO CAOS",
        "desc": "Foco em explosões e dano crítico.",
        "skills": {
            "crit_dmg":  {"name": "GOLPE FATAL",       "desc": "+10% Dano Crítico",       "cost": [300, 600, 1200, 2400, 4800, 9600, 18000, 30000], "max": 8, "icon": "talent_chaos"},
            "exp_size":  {"name": "INSTABILIDADE",     "desc": "+10% Raio de Explosão",   "cost": [400, 800, 1600, 3200, 6400, 12000],              "max": 6, "icon": "talent_chaos"},
            "chaos_bolt":{"name": "FAÍSCA CAÓTICA",    "desc": "Tiros têm chance de explodir", "cost": [1000, 4000, 9000],                          "max": 3, "icon": "talent_chaos"},
            "crit_chance":{"name": "PRECISÃO SOMBRIA", "desc": "+5% Chance Crítica",       "cost": [500, 1000, 2000, 4000, 8000],                   "max": 5, "icon": "talent_chaos"}
        }
    },
    "GUARDIÃO": {
        "title": "CAMINHO DO GUARDIÃO",
        "desc": "Foco em defesa, regeneração e aura.",
        "skills": {
            "regen":      {"name": "VIGOR",            "desc": "Cura 0.1 HP/seg",           "cost": [400, 800, 1600, 3200, 6400, 12000, 22000, 40000], "max": 8, "icon": "talent_guardian"},
            "aura_res":   {"name": "ESCUDO ESPIRITUAL","desc": "+8% Resistência a Dano",     "cost": [400, 800, 1600, 3200, 6400, 12000],              "max": 6, "icon": "talent_guardian"},
            "thorns":     {"name": "ESPINHOS",         "desc": "Reflete 15% do dano recebido","cost": [1000, 4000, 9000],                              "max": 3, "icon": "talent_guardian"},
            "max_hp_up":  {"name": "ARMADURA ANCESTRAL","desc": "+5 HP Máximo",             "cost": [600, 1200, 2400, 4800, 9600],                   "max": 5, "icon": "talent_guardian"}
        }
    },
    "FOGO": {
        "title": "CAMINHO DO FOGO",
        "desc": "Foco em dano mágico e aura.",
        "skills": {
            "fire_dmg":  {"name": "PIROMANCIA",    "desc": "+10% Dano de Aura",       "cost": [200, 400, 800, 1600, 3200, 6400, 12000, 20000], "max": 8, "icon": "talent_fire"},
            "burn_area": {"name": "TERRA QUEIMADA","desc": "+12% Área de Aura",       "cost": [300, 600, 1200, 2400, 4800, 9600],             "max": 6, "icon": "talent_fire"},
            "inferno":   {"name": "INFERNO",       "desc": "Inimigos na aura pegam fogo", "cost": [1200, 5000, 10000],                        "max": 3, "icon": "talent_fire"},
            "eternal_flame":{"name": "FOGUEIRA INFERNAL","desc": "+3 Dano de Aura fixo",   "cost": [800, 1600, 3200, 6400, 12000],                "max": 5, "icon": "talent_fire"}
        }
    }
}

DIFFICULTIES = {
    "FÁCIL":    {"hp_mult": 1.3,  "spd_mult": 0.88, "dmg_mult": 1.0,  "gold_mult": 0.8, "color": (100, 255, 100), "desc": "Para relaxar. Inimigos fracos.", "id": "DIFF_FÁCIL"},
    "MÉDIO":    {"hp_mult": 2.0,  "spd_mult": 1.08, "dmg_mult": 1.6,  "gold_mult": 1.0, "color": (255, 255, 100), "desc": "A experiência padrão.", "id": "DIFF_MÉDIO"},
    "DIFÍCIL":  {"hp_mult": 3.2,  "spd_mult": 1.25, "dmg_mult": 2.4,  "gold_mult": 1.4, "color": (255, 150, 50), "desc": "Novos Monstros! +40% Ouro.", "id": "DIFF_DIFÍCIL"},
    "HARDCORE": {"hp_mult": 7.5,  "spd_mult": 1.70, "dmg_mult": 5.5,  "gold_mult": 2.0, "color": (255, 50, 50),   "desc": "Pesadelo. +100% Ouro.", "id": "DIFF_HARDCORE"}
}

# Atributos Modificáveis (Base)
PLAYER_SPEED = 280.0
PLAYER_MAX_HP = 100
SHOT_COOLDOWN = 0.50
HAS_FURY = False
PROJECTILE_DMG = 25
PROJECTILE_SPEED = 560.0
PICKUP_RANGE = 50.0 
AURA_DMG = 0        
AURA_RANGE = 200    
PROJ_COUNT = 1       
PROJ_PIERCE = 0
PROJ_RICOCHET = 0
EXPLOSION_RADIUS = 0 
EXPLOSION_DMG = 5    
ORB_COUNT = 0        
ORB_DMG = 6          
ORB_DISTANCE = 180   
CRIT_CHANCE = 0.05   
MUSIC_VOLUME = 0.4  
SFX_VOLUME = 0.6    
EXECUTE_THRESH = 0.0

# Configurações de Habilidades
DASH_SPEED = 900.0      
DASH_DURATION = 0.2     
DASH_COOLDOWN = 2.5
ULTIMATE_MAX_CHARGE = 25 

# Configuração de Drops e Boss
DROP_CHANCE = 0.025
BOSS_SPAWN_TIME = 90.0   # 1.5 Minutos por boss (partida de 5 min — 2 bosses em 90s e 180s)
BOSS_MAX_HP = 7500       # Bosses mais fortes para compensar a run mais curta
MINI_BOSS_SPAWN_TIME = 10.0  # Mini boss aparece logo no início
AGIS_SPAWN_TIME = 300.0  # Agis nasce no minuto 5
SHOOTER_PROJ_IMAGE = "enemy_arrow" 

# Dados dos Personagens - MENU DE ANIME FRAMES - QUANTIDADE DE IMAGENS
CHAR_DATA = {
    0: {
        "name": "GUERREIRO", "hp": 100, "speed": 280, "damage": 25, "mana": 50,
        "desc": "Ult: Fúria do Guerreiro", "size": (200, 200), "menu_size": (250, 250),
        "anim_frames": 8, "menu_anim_frames": 8,
        "dash_duration": 0.26, "dash_cooldown": 2.8,
        "id": "CHAR_0",
        # Walk: guerreiro_run.png — 512x256, 4 rows × 8 frames de 64x64
        # Row 0=baixo, 1=cima, 2=esquerda, 3=direita
        "spritesheet": "sprite/monster/guerreiro_run",
        "spritesheet_frame_w": 64,
        "spritesheet_frame_h": 64,
        "spritesheet_frame_indices": [0, 1, 2, 3, 4, 5, 6, 7],
        "anim_speed": 0.10,
        # Idle: guerreiro_idle.png — 256x256, 4 rows × 4 frames de 64x64
        "spritesheet_idle": "sprite/monster/guerreiro_idle",
        "spritesheet_idle_frame_w": 64,
        "spritesheet_idle_frame_h": 64,
        "idle_anim_frames": 4,
        "spritesheet_idle_frame_indices": [0, 1, 2, 3],
        "idle_anim_speed": 0.13,
        # Ataque: guerreiro_ataque.png — 512x256, 4 rows × 8 frames de 64x64
        "spritesheet_attack": "sprite/monster/guerreiro_ataque",
        "spritesheet_attack_frame_w": 64,
        "spritesheet_attack_frame_h": 64,
        "attack_anim_frames": 8,
        "spritesheet_attack_frame_indices": [0, 1, 2, 3, 4, 5, 6, 7],
        "attack_anim_speed": 0.07,
        # Efeito de ataque mid-range: efeito_guerreiro.png — 256x512, 4 rows × 4 frames de 64x128
        "slash_effect_spritesheet": "sprite/monster/efeito_guerreiro",
        "slash_effect_frame_w": 64,
        "slash_effect_frame_h": 128,
        "slash_effect_frames": 4,
        # Ultimate: ultimate_guerreiro.png — 256x376, 2 cols × 4 linhas = 8 frames (fw=128, fh=94)
        "ultimate_spritesheet": "sprite/ultimate_guerreiro",
        "ultimate_frame_w": 128,
        "ultimate_frame_h": 94,
        "ultimate_frames_per_row": 2,
        "ultimate_rows": 4,
    },
    1: {
        "name": "CAÇADOR", "hp": 63, "speed": 340, "damage": 38, "mana": 75,
        "desc": "Ult: Chuva de Flechas", "size": (150, 150), "menu_size": (200, 200),
        "anim_frames": 8, "menu_anim_frames": 8,
        "dash_duration": 0.18, "dash_cooldown": 2.2,
        "id": "CHAR_1",
        # caçador.png: 704×320 px, 5 rows × 11 colunas de 64×64 px.
        # Row 0=idle(5f), Row 1=attack(10f), Row 2=walk(8f)
        "spritesheet": "sprite/caçador",
        "spritesheet_frame_w": 64,
        "spritesheet_frame_h": 64,
        "spritesheet_frame_indices": [22, 23, 24, 25, 26, 27, 28, 29],
        "anim_speed": 0.10,
        "spritesheet_idle": "sprite/caçador",
        "spritesheet_idle_frame_w": 64,
        "spritesheet_idle_frame_h": 64,
        "idle_anim_frames": 5,
        "spritesheet_idle_frame_indices": [0, 1, 2, 3, 4],
        "idle_anim_speed": 0.13,
        # Attack animation: row 1, 10 frames
        "spritesheet_attack": "sprite/caçador",
        "spritesheet_attack_frame_w": 64,
        "spritesheet_attack_frame_h": 64,
        "attack_anim_frames": 10,
        "spritesheet_attack_frame_indices": [11, 12, 13, 14, 15, 16, 17, 18, 19, 20],
        "attack_anim_speed": 0.07,
        # Projétil ataque básico: arrow.png — frame único.
        "projectile_spritesheet": "sprite/arrow",
        "projectile_frame_w": 30,
        "projectile_frame_h": 5,
        "projectile_frame_count": 1,
        "projectile_display_size": (50, 8),
        # Projétil da Ultimate: flechafire.png — frame único (mesma estrutura de arrow.png)
        "ultimate_projectile_spritesheet": "sprite/flechafire",
        "ultimate_projectile_frame_w": 30,
        "ultimate_projectile_frame_h": 5,
        "ultimate_projectile_frame_count": 1,
        "ultimate_projectile_display_size": (55, 9),
    },
    2: {
        "name": "MAGO", "hp": 75, "speed": 260, "damage": 25, "mana": 200,
        "desc": "Ult: Congelamento Temporal", "size": (150, 150), "menu_size": (220, 220),
        "anim_frames": 8, "menu_anim_frames": 8,
        "dash_duration": 0.20, "dash_cooldown": 2.5,
        "id": "CHAR_2",
        # Walk: Imp3_Run_with_shadow.png — 512×256, 4 rows × 8 frames de 64×64
        # Row 0=baixo, 1=cima, 2=esquerda, 3=direita
        "spritesheet": "sprite/monster/new hero/Imp3_Run_with_shadow",
        "spritesheet_frame_w": 64,
        "spritesheet_frame_h": 64,
        "spritesheet_frame_indices": [0, 1, 2, 3, 4, 5, 6, 7],
        "anim_speed": 0.10,
        # Idle: Imp3_Idle_with_shadow.png — 256×256, 4 rows × 4 frames de 64×64
        "spritesheet_idle": "sprite/monster/new hero/Imp3_Idle_with_shadow",
        "spritesheet_idle_frame_w": 64,
        "spritesheet_idle_frame_h": 64,
        "idle_anim_frames": 4,
        "spritesheet_idle_frame_indices": [0, 1, 2, 3],
        "idle_anim_speed": 0.14,
        # Attack: Imp3_Attack_with_shadow.png — 384×256, 4 rows × 6 frames de 64×64
        "spritesheet_attack": "sprite/monster/new hero/Imp3_Attack_with_shadow",
        "spritesheet_attack_frame_w": 64,
        "spritesheet_attack_frame_h": 64,
        "attack_anim_frames": 6,
        "spritesheet_attack_frame_indices": [0, 1, 2, 3, 4, 5],
        "attack_anim_speed": 0.07,
        # Projétil básico: attackbase.png, 4 frames de 48x32 px.
        # O sprite aponta para a esquerda → flip_x=True corrige para o sistema de rotação.
        "projectile_spritesheet": "sprite/attackbase",
        "projectile_frame_w": 48,
        "projectile_frame_h": 32,
        "projectile_frame_count": 4,
        "projectile_display_size": (80, 52),
        "projectile_flip_x": True,
    },
    3: {
        "name": "VAMPIRE", "hp": 88, "speed": 300, "damage": 38, "mana": 100,
        "desc": "Ult: Tempestade Sombria", "size": (150, 150), "menu_size": (200, 200),
        "anim_frames": 8, "menu_anim_frames": 8,
        "dash_duration": 0.22, "dash_cooldown": 2.5,
        "id": "CHAR_3",
        # Walk: vampire_run.png - 512×256, 4 rows × 8 frames de 64×64
        # Row 0=baixo, Row 1=cima, Row 2=esquerda, Row 3=direita
        "spritesheet": "sprite/monster/vampire_run",
        "spritesheet_frame_w": 64,
        "spritesheet_frame_h": 64,
        "spritesheet_frame_indices": [0, 1, 2, 3, 4, 5, 6, 7],
        "anim_speed": 0.10,
        # Idle: vampire_idle.png - 256×256, 4 rows × 4 frames de 64×64
        # Row 0=baixo, Row 1=cima, Row 2=esquerda, Row 3=direita
        "spritesheet_idle": "sprite/monster/vampire_idle",
        "spritesheet_idle_frame_w": 64,
        "spritesheet_idle_frame_h": 64,
        "idle_anim_frames": 4,
        "spritesheet_idle_frame_indices": [0, 1, 2, 3],
        "idle_anim_speed": 0.13,
        # Attack: vampire_ataque.png - 768×256, 4 rows × 12 frames de 64×64
        # Row 0=baixo, Row 1=cima, Row 2=esquerda, Row 3=direita
        "spritesheet_attack": "sprite/monster/vampire_ataque",
        "spritesheet_attack_frame_w": 64,
        "spritesheet_attack_frame_h": 64,
        "attack_anim_frames": 12,
        "spritesheet_attack_frame_indices": [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11],
        "attack_anim_speed": 0.06,
        # Projétil: ataque_vampire.png - 192×32, 6 frames de 32×32
        "projectile_spritesheet": "sprite/ataque_vampire",
        "projectile_frame_w": 32,
        "projectile_frame_h": 32,
        "projectile_frame_count": 6,
        "projectile_display_size": (42, 42),
    },
    4: {
        "name": "DEMÔNIO", "hp": 75, "speed": 290, "damage": 38, "mana": 100,
        "desc": "Ult: Chama Infernal", "size": (250, 250), "menu_size": (350, 350),
        "anim_frames": 8, "menu_anim_frames": 8,
        "dash_duration": 0.20, "dash_cooldown": 2.3,
        "id": "CHAR_4",
        # Walk: demon_run.png — 1024×512, 4 rows × 8 frames de 128×128
        # Row 0=baixo, 1=cima, 2=esquerda, 3=direita
        "spritesheet": "sprite/monster/demon_run",
        "spritesheet_frame_w": 128,
        "spritesheet_frame_h": 128,
        "spritesheet_frame_indices": [0, 1, 2, 3, 4, 5, 6, 7],
        "anim_speed": 0.09,
        # Idle: demon_idle.png — 512×512, 4 rows × 4 frames de 128×128
        "spritesheet_idle": "sprite/monster/demon_idle",
        "spritesheet_idle_frame_w": 128,
        "spritesheet_idle_frame_h": 128,
        "idle_anim_frames": 4,
        "spritesheet_idle_frame_indices": [0, 1, 2, 3],
        "idle_anim_speed": 0.13,
        # Attack: demon_ataque.png — 1280×512, 4 rows × 10 frames de 128×128
        "spritesheet_attack": "sprite/monster/demon_ataque",
        "spritesheet_attack_frame_w": 128,
        "spritesheet_attack_frame_h": 128,
        "attack_anim_frames": 10,
        "spritesheet_attack_frame_indices": [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
        "attack_anim_speed": 0.06,
        # Projétil: demon_spell.png — 960×256, 5cols × 2rows = 10 frames (fw=192, fh=128)
        # Animação do feitiço: cresce de pequeno→blast escuro+vermelho→disipa
        # Frame 9 (último) está vazio; usa indices 0-8 (9 frames com conteúdo)
        "projectile_spritesheet": "sprite/monster/demon_spell",
        "projectile_frame_w": 192,
        "projectile_frame_h": 128,
        "projectile_frame_count": 9,
        "projectile_frame_indices": [0, 1, 2, 3, 4, 5, 6, 7, 8],
        "projectile_display_size": (96, 64),
        # Ultimate: ult_demon.png — 1536×128, 12 frames de 128×128 em linha única
        "ultimate_spritesheet": "sprite/monster/ult_demon",
        "ultimate_frame_w": 128,
        "ultimate_frame_h": 128,
        "ultimate_frames_per_row": 12,
        "ultimate_rows": 1,
    },
    5: {
        "name": "GOLEM", "hp": 113, "speed": 240, "damage": 50, "mana": 50,
        "desc": "Ult: Golpe da Terra", "size": (220, 220), "menu_size": (320, 320),
        "anim_frames": 8, "menu_anim_frames": 8,
        "dash_duration": 0.18, "dash_cooldown": 2.5,
        "id": "CHAR_5",
        # Walk: golem_run.png — 1024×512, 4 rows × 8 frames de 128×128
        # Row 0=baixo, 1=cima, 2=esquerda, 3=direita
        "spritesheet": "sprite/monster/new hero/golem_run",
        "spritesheet_frame_w": 128,
        "spritesheet_frame_h": 128,
        "spritesheet_frame_indices": [0, 1, 2, 3, 4, 5, 6, 7],
        "anim_speed": 0.10,
        # Idle: golem_idle.png — 512×512, 4 rows × 4 frames de 128×128
        "spritesheet_idle": "sprite/monster/new hero/golem_idle",
        "spritesheet_idle_frame_w": 128,
        "spritesheet_idle_frame_h": 128,
        "idle_anim_frames": 4,
        "spritesheet_idle_frame_indices": [0, 1, 2, 3],
        "idle_anim_speed": 0.15,
        # Efeito melee: basic_golem.png — 256×512, 2 cols × 4 rows = 8 frames de 128×128
        # Animação sequencial do impacto: lido de cima-baixo, esquerda-direita
        "projectile_spritesheet": "sprite/monster/new hero/basic_golem",
        "projectile_frame_w": 128,
        "projectile_frame_h": 128,
        "projectile_frame_count": 8,
        "projectile_frame_indices": [0, 1, 2, 3, 4, 5, 6, 7],
        "projectile_display_size": (96, 96),
    },
    6: {
        "name": "ESQUELETO", "hp": 95, "speed": 265, "damage": 44, "mana": 75,
        "desc": "Ult: Frenesi Sanguinário", "size": (200, 200), "menu_size": (280, 280),
        "anim_frames": 8, "menu_anim_frames": 8,
        "dash_duration": 0.20, "dash_cooldown": 2.3,
        "id": "CHAR_6",
        # Walk: Skeleton3_Run_with_shadow.png — 512×256, 4 rows × 8 frames de 64×64
        # Row 0=baixo, 1=cima, 2=esquerda, 3=direita
        "spritesheet": "sprite/monster/new hero/Skeleton3_Run_with_shadow",
        "spritesheet_frame_w": 64,
        "spritesheet_frame_h": 64,
        "spritesheet_frame_indices": [0, 1, 2, 3, 4, 5, 6, 7],
        "anim_speed": 0.09,
        # Idle: Skeleton3_Idle_with_shadow.png — 256×256, 4 rows × 4 frames de 64×64
        "spritesheet_idle": "sprite/monster/new hero/Skeleton3_Idle_with_shadow",
        "spritesheet_idle_frame_w": 64,
        "spritesheet_idle_frame_h": 64,
        "idle_anim_frames": 4,
        "spritesheet_idle_frame_indices": [0, 1, 2, 3],
        "idle_anim_speed": 0.14,
        # Attack: Skeleton3_Attack_with_shadow.png — 576×256, 4 rows × 9 frames de 64×64
        "spritesheet_attack": "sprite/monster/new hero/Skeleton3_Attack_with_shadow",
        "spritesheet_attack_frame_w": 64,
        "spritesheet_attack_frame_h": 64,
        "attack_anim_frames": 9,
        "spritesheet_attack_frame_indices": [0, 1, 2, 3, 4, 5, 6, 7, 8],
        "attack_anim_speed": 0.06,
        # Efeito melee (slash hitbox): reusa basic_golem.png em tamanho reduzido
        "projectile_spritesheet": "sprite/monster/new hero/basic_golem",
        "projectile_frame_w": 128,
        "projectile_frame_h": 128,
        "projectile_frame_count": 8,
        "projectile_frame_indices": [0, 1, 2, 3, 4, 5, 6, 7],
        "projectile_display_size": (80, 80),
    },
    7: {
        "name": "FURACÃO", "hp": 80, "speed": 285, "damage": 40, "mana": 85,
        "desc": "Ult: Vórtice da Tempestade", "size": (160, 160), "menu_size": (230, 230),
        "anim_frames": 6, "menu_anim_frames": 6,
        "dash_duration": 0.18, "dash_cooldown": 2.2,
        "id": "CHAR_7",
        # Walk: Lich3_Run_with_shadow.png — 384×256, 4 rows × 6 frames de 64×64
        "spritesheet": "sprite/monster/new hero/Lich3_Run_with_shadow",
        "spritesheet_frame_w": 64,
        "spritesheet_frame_h": 64,
        "spritesheet_frame_indices": [0, 1, 2, 3, 4, 5], "anim_speed": 0.10,
        # Idle: Lich3_Idle_with_shadow.png — 256×256, 4 rows × 4 frames de 64×64
        "spritesheet_idle": "sprite/monster/new hero/Lich3_Idle_with_shadow",
        "spritesheet_idle_frame_w": 64,
        "spritesheet_idle_frame_h": 64,
        "idle_anim_frames": 4, "spritesheet_idle_frame_indices": [0, 1, 2, 3], "idle_anim_speed": 0.14,
        # Attack: Lich3_Attack_with_shadow.png — 512×256, 4 rows × 8 frames de 64×64
        "spritesheet_attack": "sprite/monster/new hero/Lich3_Attack_with_shadow",
        "spritesheet_attack_frame_w": 64,
        "spritesheet_attack_frame_h": 64,
        "attack_anim_frames": 8,
        "spritesheet_attack_frame_indices": [0, 1, 2, 3, 4, 5, 6, 7], "attack_anim_speed": 0.07,
        # Projétil: frames individuais Typhoon_Frame_01..12
        "projectile_frames_list": [
            "sprite/monster/new hero/hurricane_magia/Typhoon_Frame_01",
            "sprite/monster/new hero/hurricane_magia/Typhoon_Frame_02",
            "sprite/monster/new hero/hurricane_magia/Typhoon_Frame_03",
            "sprite/monster/new hero/hurricane_magia/Typhoon_Frame_04",
            "sprite/monster/new hero/hurricane_magia/Typhoon_Frame_05",
            "sprite/monster/new hero/hurricane_magia/Typhoon_Frame_06",
            "sprite/monster/new hero/hurricane_magia/Typhoon_Frame_07",
            "sprite/monster/new hero/hurricane_magia/Typhoon_Frame_08",
            "sprite/monster/new hero/hurricane_magia/Typhoon_Frame_09",
            "sprite/monster/new hero/hurricane_magia/Typhoon_Frame_10",
            "sprite/monster/new hero/hurricane_magia/Typhoon_Frame_11",
            "sprite/monster/new hero/hurricane_magia/Typhoon_Frame_12",
        ],
        "projectile_display_size": (96, 120),
    },
}

# Constantes
WORLD_GRID = 64
BG_COLOR = (14, 14, 18)
PLAYER_IFRAMES = 1.0
GEM_XP = 20  # dobrado: menos gemas caem, cada uma vale mais
XP_TO_LEVEL_BASE = 100   
SHOT_RANGE = 600.0
SPAWN_EVERY_BASE = 0.2
MAX_UPGRADE_LEVEL = 5
GAME_VERSION = "1.1.0 (Closed Beta)"

# Pool Completa (Será filtrada pelo Unlock System)
ALL_UPGRADES_POOL = {
    "DANO ++": "Aumenta o dano dos projéteis em +2",
    "VELOCIDADE ++": "Aumenta a velocidade de movimento em 15%",
    "TIRO RÁPIDO": "Atira com mais frequência",
    "VIDA MÁXIMA": "Aumenta o HP máximo e cura +1",
    "CHAMA ARDENTE": "+2 dano e +5% chance crítica",
    "ÍMÃ DE XP": "Aumenta muito o raio de coleta",
    "TIRO MÚLTIPLO": "Atira projéteis adicionais em leque",
    "EXPLOSÃO": "Tiros explodem ao atingir o alvo",
    "PERFURAÇÃO": "O projétil atravessa +1 inimigo",
    "ORBES MÁGICOS": "Esferas giratórias protegem você",
    "SORTE": "Aumenta a Chance de Crítico em +10%",
    "CURA": "Recupera todo o HP atual",
    "RICOCHE": "Projéteis quicam em +1 inimigo próximo",
    "EXECUÇÃO": "Inimigos abaixo de 12% de vida morrem instantaneamente",
    "FÚRIA": "Quanto menor seu HP, maior dano e cadência (até +60%)",
    "CAPA INVISÍVEL": "10% de chance de inimigos não te notarem",
    "LUVA EXPULSÃO": "Aumenta muito o empurrão (Knockback)",
    "TREVO SORTE": "Aumenta a raridade dos upgrades",
    # ── 200 novas skills ─────────────────────────────────────────────────────
    # DANO E ATAQUE
    "LÂMINA SANGRADA":     "+3 dano de projétil",
    "GOLPE CERTEIRO":      "+10% chance de crítico",
    "CRÍTICO LETAL":       "+0.25x multiplicador de crítico",
    "PUNHAL SOMBRIO":      "+4 dano de projétil",
    "FLECHA EXPLOSIVA":    "+2 dano e +20 raio de explosão",
    "DESTRUIÇÃO TOTAL":    "+5 dano de projétil",
    "LÂMINA DE SOMBRA": "+4 dano e +10% espinhos",
    "SANGUE DO CAÇADOR":   "+2 dano e +8% crítico",
    "FÚRIA SELVAGEM":      "+4 dano de projétil",
    "RUNA AFIADA":         "+3 dano e +5% crítico",
    "ESCOLHA DO CARRASCO": "+8% limiar de execução",
    "TOQUE DO ABISMO":     "+5 dano de projétil",
    "FRAGMENTO DE ALMA":   "+0.20x multiplicador de crítico",
    "MARTELO DO TROVÃO":   "+6 dano de projétil",
    "FOGUEIRA INFERNAL": "+3 dano e +20 raio de explosão",
    "GOLPE CÓSMICO":       "+12% chance de crítico",
    "EXECUTAR O FRACO":    "+10% limiar de execução",
    "FLUXO DE MANA":       "+3 dano e -5% recarga de tiro",
    "SETA DO DESTINO":     "+15% chance de crítico",
    "PODER OCULTO":        "+5 dano de projétil",
    "HERANÇA SOMBRIA":     "+0.30x crítico e +2 dano",
    "INSTINTO PREDADOR":   "+8% execução e +8% crítico",
    "CRISTAL DE DANO":     "+4 dano de projétil",
    "ESPADA LENDÁRIA":     "+7 dano de projétil",
    "PEDRA DO CAOS":       "+3 dano e +10% crítico",
    "TIRO PRECISO":        "+15% crítico e +1 perfuração",
    "GOLPE DO DESTINO":    "+12% execução e +3 dano",
    "MAGIA DUPLA":         "+2 dano e +1 projétil",
    "FRIO MORTAL":         "+4 dano e +8% crítico",
    "SOPRO VENENOSO": "+4 dano e +3% vampirismo",
    # PROJÉTEIS
    "BALA FANTASMA":       "+1 perfuração de projétil",
    "TEMPESTADE DE SETAS": "+1 projétil adicional",
    "RICOCHETE DUPLO":     "+1 ricochete de projétil",
    "BALA SÔNICA":         "+80 velocidade de projétil",
    "RAJADA RÁPIDA":       "-10% recarga de tiro",
    "FLECHA TRIPLA":       "+2 projéteis adicionais",
    "PERFURAÇÃO EXTREMA":  "+2 perfurações de projétil",
    "ECO MÁGICO":          "+1 projétil e +1 ricochete",
    "VELOCIDADE DE LUZ":   "+120 velocidade de projétil",
    "CHUVA DE FLECHAS":    "+1 projétil e +1 perfuração",
    "DISPARO VELOZ":       "-12% recarga de tiro",
    "FRAGMENTAÇÃO":        "+1 projétil e +30 raio explosão",
    "SETA FANTASMA":       "+1 perfuração e +60 vel. projétil",
    "ONDA DE CHOQUE":      "+1 projétil e +1 ricochete",
    "BALA DUPLA":          "+2 projéteis adicionais",
    "RICOCHETE MÁGICO":    "+2 ricochetes de projétil",
    "DISPARO RÁPIDO":      "-15% recarga de tiro",
    "CASCATA":             "+1 projétil e +1 perfuração",
    "RAJADA SUPERSÔNICA":  "+150 velocidade de projétil",
    "FLECHA MÁGICA":       "+1 projétil e +8% crítico",
    "PERFURAÇÃO TOTAL":    "+3 perfurações de projétil",
    "TIRO VELOZ":          "-8% recarga de tiro",
    "MULTIPLICAÇÃO":       "+2 projéteis adicionais",
    "ECO BALÍSTICO":       "+100 vel. projétil e +1 pierce",
    "TEMPESTADE TOTAL":    "+2 projéteis e +2 perfurações",
    # DEFESA
    "ESCUDO DE FERRO":        "+5 HP máximo",
    "CURA RÁPIDA":            "+0.3 HP/s de regeneração",
    "ARMADURA ANTIGA":        "+8 HP máximo",
    "ESPINHOS DE AÇO":        "+12% dano de espinhos",
    "VIDA DUPLA":             "+10 HP máximo",
    "REGENERAÇÃO LENTA":      "+0.5 HP/s de regeneração",
    "MURALHA DE PEDRA":       "+12 HP máximo",
    "PELE DE DRAGÃO":         "+18% dano de espinhos",
    "RECUPERAÇÃO RÁPIDA":     "+0.8 HP/s de regeneração",
    "FORÇA VITAL":            "+15 HP máximo",
    "SANGUE VAMPIRO":         "+2% de vampirismo",
    "ESCUDO MÍSTICO":         "+5 HP máximo e +0.2 HP/s",
    "TRONCO DE CARVALHO":     "+20 HP máximo",
    "DRENO DE VIDA":          "+3% de vampirismo",
    "ARMADURA DIVINA":        "+25 HP máximo",
    "REGENERAÇÃO MÍSTICA":    "+1.0 HP/s de regeneração",
    "DRENAGEM SOMBRIA":       "+5% de vampirismo",
    "CURA ABENÇOADA":         "Restaura 30% do HP atual",
    "VIDA ETERNA":            "+30 HP máximo",
    "ESPINHOS MORTAIS":       "+22% dano de espinhos",
    "ABSORÇÃO VITAL":         "+4% de vampirismo",
    "ROCHA INQUEBRANTÁVEL":   "+35 HP máximo",
    "REGENERAÇÃO EXTREMA":    "+1.5 HP/s de regeneração",
    "BARREIRA ARCANA":        "+8 HP máximo e +0.4 HP/s",
    "VAMPIRO SOMBRIO":        "+6% de vampirismo",
    "COLETE DE AÇO":          "+5 HP máximo",
    "FONTE DE VIDA":          "+2.0 HP/s de regeneração",
    "ESSÊNCIA VITAL":         "+20 HP máximo e +0.5 HP/s",
    "RESISTÊNCIA TOTAL":      "+10 HP e +10% espinhos",
    "MANTO PROTETOR":         "+4% vampirismo e +0.3 HP/s",
    # VELOCIDADE
    "BOTAS VELOZES":         "+20 de velocidade",
    "ASAS DO VENTO":         "+30 de velocidade",
    "CORRER É VIVER":        "+15 vel. e +40 raio coleta",
    "REFLEXOS AGUÇADOS":     "+25 de velocidade",
    "MOVIMENTO FANTASMA":    "+35 de velocidade",
    "ÍMPETO DO GUERREIRO":   "+20 vel. e -8% recarga",
    "TURBILHÃO":             "+40 de velocidade",
    "PASSO DO ASSASSINO":    "+15 vel. e +5% crítico",
    "DANÇA DA MORTE":        "+50 de velocidade",
    "VENTO CORTANTE":        "+25 vel. e +50 raio coleta",
    "RELÂMPAGO":             "+60 de velocidade",
    "PASSO ESPECTRAL":       "+20 vel. e +60 raio coleta",
    "CORRIDA MÁGICA":        "+30 vel. e -5% recarga",
    "IMPULSO DIVINO":        "+45 de velocidade",
    "RASTRO DE FOGO":        "+35 vel. e +2 dano",
    "ACELERAÇÃO":            "+25 de velocidade",
    "FLUXO ETERNO":          "+80 raio coleta e +20 vel.",
    "VENTO UIVANTE":         "+50 de velocidade",
    "MARÉ VELOZ":            "+30 vel. e +5% crítico",
    "VELOZ COMO O RAIO":     "+70 de velocidade",
    # MAGIA / ORBES
    "CÍRCULO ARCANO":    "+1 orbe mágico",
    "ESCUDO RÚNICO": "+8 HP e +0.3 HP/s regeneração",
    "ORBE DESTRUIDOR":   "+3 dano de orbe",
    "MAGIA ARCANA": "+3 dano e +1 projétil",
    "DUPLO ORBE":        "+1 orbe e +2 dano de orbe",
    "AMPLIFICADOR ARCANO": "+0.20x multiplicador crítico e +5% chance",
    "VÓRTICE MÁGICO":    "+1 orbe e +50 distância orbital",
    "ONDA ÍGNEA": "+50 raio e +4 dano de explosão",
    "SEIS ORBES":        "+2 orbes mágicos",
    "DISPERSÃO MÁGICA": "+1 projétil e +80 vel. projétil",
    "ORBE FANTASMA":     "+1 orbe e +4 dano de orbe",
    "GRAÇA DIVINA": "+12 HP e +0.5 HP/s regeneração",
    "CÍRCULO DA MORTE":  "+2 orbes e +3 dano de orbe",
    "EXECUÇÃO ARCANA": "+8% execução e +8% crítico",
    "ESPIRAL DE FOGO": "+1 orbe e +3 dano de orbe",
    "ORBES EXPLOSIVOS":  "+1 orbe e +40 raio explosão",
    "CEIFA ARCANA": "+5 dano e +6% execução",
    "CONSTELAÇÃO":       "+2 orbes e +60 distância orbital",
    "VÓRTICE CÓSMICO": "+100 raio de coleta e +15% XP",
    "DANÇA DOS ORBES":   "+2 orbes e +5 dano de orbe",
    "DETONAÇÃO MÁGICA": "+60 raio e +5 dano de explosão",
    "PODER SUPREMO": "+4 dano, +1 orbe e +6% crítico",
    "PERFURAÇÃO CÓSMICA": "+6 dano e +1 perfuração",
    "NEXO ARCANO":       "+3 orbes mágicos",
    "VIDA ETERNA RÚNICA": "+1.5 HP/s e +4% vampirismo",
    # EXPLOSÃO
    "MICRO BOMBA":           "+25 raio de explosão",
    "BOMBA GRANDE":          "+40 raio de explosão",
    "FRAGMENTO EXPLOSIVO":   "+3 dano de explosão",
    "DETONAÇÃO":             "+60 raio de explosão",
    "BOMBA DE PLASMA":       "+5 dano de explosão",
    "ONDA EXPLOSIVA":        "+80 raio e +4 dano de explosão",
    "CARGA NUCLEAR":         "+100 raio de explosão",
    "FRAGMENTO INCENDIÁRIO": "+6 dano de explosão",
    "TIRO EXPLOSIVO":        "+50 raio explosão e +2 dano",
    "BOMBA GRAVITACIONAL":   "+70 raio e +5 dano explosão",
    "CADEIA EXPLOSIVA":      "+30 raio, +1 ricochet, +3 exp dmg",
    "SUPERNOVA":             "+120 raio de explosão",
    "EXPLOSÃO SOMBRIA":      "+8 dano de explosão",
    "DETONADOR EXTREMO":     "+90 raio e +6 dano explosão",
    "BOMBA FINAL":           "+150 raio e +10 dano explosão",
    # UTILIDADE
    "COLETOR DE GEMAS":          "+100 raio de coleta",
    "FORTUNA DO AVENTUREIRO":    "+20% ouro na run",
    "EXPERIÊNCIA ACELERADA":     "+15% bônus de XP",
    "IMÃ SUPREMO":               "+150 raio de coleta",
    "COFRE DO AVENTUREIRO":      "+30% ouro na run",
    "APRENDIZADO RÁPIDO":        "+20% bônus de XP",
    "CAMPOS MAGNÉTICOS":         "+200 raio de coleta",
    "OURO DO REI":               "+40% ouro na run",
    "SÁBIO DO MUNDO":            "+25% bônus de XP",
    "MAGNETISMO MÁXIMO":         "+250 raio de coleta",
    "TESOURO ANTIGO":            "+50% ouro na run",
    "INICIAÇÃO ARCANA":          "+30% bônus de XP",
    "VÓRTICE DE GEMAS":          "+180 raio de coleta",
    "GANÂNCIA ILIMITADA":        "+60% ouro na run",
    "MENTOR ESPIRITUAL":         "+35% bônus de XP",
    "SORTE DO VIAJANTE":         "+5% crítico e +10% ouro",
    "PRESENÇA MAGNÉTICA":        "+120 raio e +10% ouro",
    "TOQUE DO ALQUIMISTA":       "+15% ouro e +0.5 HP/s",
    "DÁDIVA DOS DEUSES":         "+20% XP e +0.5 HP/s",
    "SÍMBOLO DA PROSPERIDADE":   "+25% ouro e +5% crítico",
    "COLETOR MÁGICO":            "+80 raio e +10% XP",
    "ABUNDÂNCIA":                "+20% ouro e +5 HP",
    "CRESCIMENTO ESPIRITUAL":    "+15% XP e +0.3 HP/s",
    "GEMA DA FORTUNA":           "+8% crítico e +80 raio",
    "CAMINHO DO MESTRE":         "+20% XP e +5% crítico",
    "ORÁCULO":                   "+10% ouro, +10% XP e +0.2 HP/s",
    "CONHECIMENTO PROIBIDO":     "+30% XP e +2 dano",
    "HERANÇA DO REI":            "+30% ouro e +5 HP",
    "CAMINHO DO SÁBIO":          "+20% XP e +20 velocidade",
    "DÍVIDA DE SANGUE":          "+10% vampirismo e +12% espinhos",
    # ESPECIAL
    "MORTE CERTA":         "+10% execução e +10% crítico",
    "LOUCURA DE GUERRA":   "+3 dano e +20 velocidade",
    "EQUILÍBRIO PERFEITO": "+2 dano, +5 HP e +10 vel.",
    "ASCENSÃO":            "+3 dano, +0.3 HP/s e +5% crítico",
    "MESTRE DAS ARTES":    "+2 projéteis, +2 dano e +20 vel.",
    "CAMPEÃO":             "+10 HP, +2 dano e +0.3 HP/s",
    "LENDA VIVA":          "+5 dano, +5% crítico e +20 vel.",
    "PODER ILIMITADO":     "+6 dano e +30 velocidade",
    "FORMA SOMBRIA": "+3 dano, +2 orbes e +15 vel.",
    "FANTASMA DA MORTE":   "+3 dano, +1 pierce e +5% crítico",
    "REI DO CAMPO":        "+1 projétil, +1 pierce, +1 ricochet",
    "ESTRATEGISTA":        "+3 dano, +20 HP e -10% recarga",
    "GUERREIRO ETERNO":    "+5 HP, +15 vel. e +0.3 HP/s",
    "COLOSSO DE FERRO": "+20 HP, +3 dano e +10% espinhos",
    "LÂMINA SOMBRIA":      "+4 dano, +1 pierce e +1 ricochet",
    "BERSERKER FINAL":     "+6 dano, -12% recarga e +1 proj",
    "DOMINADOR":           "+4 dano, +10% crítico e +10% exec.",
    "REAPER":              "+5 dano e +15% execução",
    "TEMPESTADE MORTAL":   "+2 projéteis, +40 explosão e +3 dano",
    "FORÇA BRUTA":         "+8 dano e +10 HP",
    "AGILIDADE EXTREMA":   "+50 vel. e -12% recarga",
    "GOLPE DIVINO": "+4 dano, +1 orbe e +30 raio de explosão",
    "MESTRE DO CAOS":      "+3 projéteis, +2 dano e +5% crit",
    "TRANSCENDÊNCIA":      "+5 dano, +5 HP, +25 vel. e regen",
    "FORMA FINAL":         "+8 dano, +15% crit, +10% exec, +30 vel.",
}

UPGRADE_TAGS = {
    "DANO ++": {"dano"},
    "TIRO RÁPIDO": {"cadencia"},
    "VELOCIDADE ++": {"movimento"},
    "TIRO MÚLTIPLO": {"projeteis"},
    "PERFURAÇÃO": {"projeteis"},
    "EXPLOSÃO": {"explosao"},
    "CHAMA ARDENTE":{"dano","critico"},
    "ÍMÃ DE XP": {"magnetismo"},
    "ORBES MÁGICOS": {"orbes"},
    "SORTE": {"critico"},
    "VIDA MÁXIMA": {"tank"},
    "CURA": {"sobrevivencia"},
    "RICOCHE": {"projeteis"},
    "EXECUÇÃO": {"dano"},
    "FÚRIA": {"tank"},
    "CAPA INVISÍVEL": {"sobrevivencia"},
    "LUVA EXPULSÃO": {"defesa"},
    "TREVO SORTE": {"utilidade"},
    # novas skills
    "LÂMINA SANGRADA":{"dano"},"GOLPE CERTEIRO":{"critico"},"CRÍTICO LETAL":{"critico"},
    "PUNHAL SOMBRIO":{"dano"},"FLECHA EXPLOSIVA":{"dano","explosao"},"DESTRUIÇÃO TOTAL":{"dano"},
    "LÂMINA DE SOMBRA":{"dano","defesa"},"SANGUE DO CAÇADOR":{"dano","critico"},"FÚRIA SELVAGEM":{"dano"},
    "RUNA AFIADA":{"dano","critico"},"ESCOLHA DO CARRASCO":{"dano"},"TOQUE DO ABISMO":{"dano"},
    "FRAGMENTO DE ALMA":{"critico"},"MARTELO DO TROVÃO":{"dano"},"FOGUEIRA INFERNAL":{"dano","explosao"},
    "GOLPE CÓSMICO":{"critico"},"EXECUTAR O FRACO":{"dano"},"FLUXO DE MANA":{"dano","cadencia"},
    "SETA DO DESTINO":{"critico"},"PODER OCULTO":{"dano"},"HERANÇA SOMBRIA":{"critico","dano"},
    "INSTINTO PREDADOR":{"dano","critico"},"CRISTAL DE DANO":{"dano"},"ESPADA LENDÁRIA":{"dano"},
    "PEDRA DO CAOS":{"dano","critico"},"TIRO PRECISO":{"critico","projeteis"},"GOLPE DO DESTINO":{"dano"},
    "MAGIA DUPLA":{"dano","projeteis"},"FRIO MORTAL":{"dano","critico"},"SOPRO VENENOSO":{"dano","sobrevivencia"},
    "BALA FANTASMA":{"projeteis"},"TEMPESTADE DE SETAS":{"projeteis"},"RICOCHETE DUPLO":{"projeteis"},
    "BALA SÔNICA":{"projeteis"},"RAJADA RÁPIDA":{"cadencia"},"FLECHA TRIPLA":{"projeteis"},
    "PERFURAÇÃO EXTREMA":{"projeteis"},"ECO MÁGICO":{"projeteis"},"VELOCIDADE DE LUZ":{"projeteis"},
    "CHUVA DE FLECHAS":{"projeteis"},"DISPARO VELOZ":{"cadencia"},"FRAGMENTAÇÃO":{"projeteis","explosao"},
    "SETA FANTASMA":{"projeteis"},"ONDA DE CHOQUE":{"projeteis"},"BALA DUPLA":{"projeteis"},
    "RICOCHETE MÁGICO":{"projeteis"},"DISPARO RÁPIDO":{"cadencia"},"CASCATA":{"projeteis"},
    "RAJADA SUPERSÔNICA":{"projeteis"},"FLECHA MÁGICA":{"projeteis","critico"},"PERFURAÇÃO TOTAL":{"projeteis"},
    "TIRO VELOZ":{"cadencia"},"MULTIPLICAÇÃO":{"projeteis"},"ECO BALÍSTICO":{"projeteis"},
    "TEMPESTADE TOTAL":{"projeteis"},"ESCUDO DE FERRO":{"tank"},"CURA RÁPIDA":{"sobrevivencia"},
    "ARMADURA ANTIGA":{"tank"},"ESPINHOS DE AÇO":{"defesa"},"VIDA DUPLA":{"tank"},
    "REGENERAÇÃO LENTA":{"sobrevivencia"},"MURALHA DE PEDRA":{"tank"},"PELE DE DRAGÃO":{"defesa"},
    "RECUPERAÇÃO RÁPIDA":{"sobrevivencia"},"FORÇA VITAL":{"tank"},"SANGUE VAMPIRO":{"sobrevivencia"},
    "ESCUDO MÍSTICO":{"tank","sobrevivencia"},"TRONCO DE CARVALHO":{"tank"},"DRENO DE VIDA":{"sobrevivencia"},
    "ARMADURA DIVINA":{"tank"},"REGENERAÇÃO MÍSTICA":{"sobrevivencia"},"DRENAGEM SOMBRIA":{"sobrevivencia"},
    "CURA ABENÇOADA":{"sobrevivencia"},"VIDA ETERNA":{"tank"},"ESPINHOS MORTAIS":{"defesa"},
    "ABSORÇÃO VITAL":{"sobrevivencia"},"ROCHA INQUEBRANTÁVEL":{"tank"},"REGENERAÇÃO EXTREMA":{"sobrevivencia"},
    "BARREIRA ARCANA":{"tank","sobrevivencia"},"VAMPIRO SOMBRIO":{"sobrevivencia"},"COLETE DE AÇO":{"tank"},
    "FONTE DE VIDA":{"sobrevivencia"},"ESSÊNCIA VITAL":{"tank","sobrevivencia"},"RESISTÊNCIA TOTAL":{"tank","defesa"},
    "MANTO PROTETOR":{"sobrevivencia"},"BOTAS VELOZES":{"movimento"},"ASAS DO VENTO":{"movimento"},
    "CORRER É VIVER":{"movimento","magnetismo"},"REFLEXOS AGUÇADOS":{"movimento"},"MOVIMENTO FANTASMA":{"movimento"},
    "ÍMPETO DO GUERREIRO":{"movimento","cadencia"},"TURBILHÃO":{"movimento"},"PASSO DO ASSASSINO":{"movimento","critico"},
    "DANÇA DA MORTE":{"movimento"},"VENTO CORTANTE":{"movimento","magnetismo"},"RELÂMPAGO":{"movimento"},
    "PASSO ESPECTRAL":{"movimento","magnetismo"},"CORRIDA MÁGICA":{"movimento","cadencia"},"IMPULSO DIVINO":{"movimento"},
    "RASTRO DE FOGO":{"movimento","dano"},"ACELERAÇÃO":{"movimento"},"FLUXO ETERNO":{"magnetismo","movimento"},
    "VENTO UIVANTE":{"movimento"},"MARÉ VELOZ":{"movimento","critico"},"VELOZ COMO O RAIO":{"movimento"},
    "CÍRCULO ARCANO":{"orbes"},"ESCUDO RÚNICO":{"tank","sobrevivencia"},"ORBE DESTRUIDOR":{"orbes"},
    "MAGIA ARCANA":{"dano","projeteis"},"DUPLO ORBE":{"orbes"},"AMPLIFICADOR ARCANO":{"critico"},
    "VÓRTICE MÁGICO":{"orbes"},"ONDA ÍGNEA":{"explosao"},"SEIS ORBES":{"orbes"},
    "DISPERSÃO MÁGICA":{"projeteis"},"ORBE FANTASMA":{"orbes"},"GRAÇA DIVINA":{"tank","sobrevivencia"},
    "CÍRCULO DA MORTE":{"orbes"},"EXECUÇÃO ARCANA":{"dano","critico"},"ESPIRAL DE FOGO":{"orbes"},
    "ORBES EXPLOSIVOS":{"orbes","explosao"},"CEIFA ARCANA":{"dano"},"CONSTELAÇÃO":{"orbes"},
    "VÓRTICE CÓSMICO":{"magnetismo","utilidade"},"DANÇA DOS ORBES":{"orbes"},"DETONAÇÃO MÁGICA":{"explosao"},
    "PODER SUPREMO":{"dano","orbes","critico"},"PERFURAÇÃO CÓSMICA":{"dano","projeteis"},"NEXO ARCANO":{"orbes"},
    "VIDA ETERNA RÚNICA":{"sobrevivencia"},"MICRO BOMBA":{"explosao"},"BOMBA GRANDE":{"explosao"},
    "FRAGMENTO EXPLOSIVO":{"explosao"},"DETONAÇÃO":{"explosao"},"BOMBA DE PLASMA":{"explosao"},
    "ONDA EXPLOSIVA":{"explosao"},"CARGA NUCLEAR":{"explosao"},"FRAGMENTO INCENDIÁRIO":{"explosao"},
    "TIRO EXPLOSIVO":{"explosao","dano"},"BOMBA GRAVITACIONAL":{"explosao"},"CADEIA EXPLOSIVA":{"explosao","projeteis"},
    "SUPERNOVA":{"explosao"},"EXPLOSÃO SOMBRIA":{"explosao"},"DETONADOR EXTREMO":{"explosao"},
    "BOMBA FINAL":{"explosao"},"COLETOR DE GEMAS":{"magnetismo"},"FORTUNA DO AVENTUREIRO":{"utilidade"},
    "EXPERIÊNCIA ACELERADA":{"utilidade"},"IMÃ SUPREMO":{"magnetismo"},"COFRE DO AVENTUREIRO":{"utilidade"},
    "APRENDIZADO RÁPIDO":{"utilidade"},"CAMPOS MAGNÉTICOS":{"magnetismo"},"OURO DO REI":{"utilidade"},
    "SÁBIO DO MUNDO":{"utilidade"},"MAGNETISMO MÁXIMO":{"magnetismo"},"TESOURO ANTIGO":{"utilidade"},
    "INICIAÇÃO ARCANA":{"utilidade"},"VÓRTICE DE GEMAS":{"magnetismo"},"GANÂNCIA ILIMITADA":{"utilidade"},
    "MENTOR ESPIRITUAL":{"utilidade"},"SORTE DO VIAJANTE":{"critico","utilidade"},"PRESENÇA MAGNÉTICA":{"magnetismo","utilidade"},
    "TOQUE DO ALQUIMISTA":{"utilidade","sobrevivencia"},"DÁDIVA DOS DEUSES":{"utilidade","sobrevivencia"},
    "SÍMBOLO DA PROSPERIDADE":{"utilidade","critico"},"COLETOR MÁGICO":{"magnetismo","utilidade"},
    "ABUNDÂNCIA":{"utilidade","tank"},"CRESCIMENTO ESPIRITUAL":{"utilidade","sobrevivencia"},
    "GEMA DA FORTUNA":{"critico","magnetismo"},"CAMINHO DO MESTRE":{"utilidade","critico"},
    "ORÁCULO":{"utilidade","sobrevivencia"},"CONHECIMENTO PROIBIDO":{"utilidade","dano"},
    "HERANÇA DO REI":{"utilidade","tank"},"CAMINHO DO SÁBIO":{"utilidade","movimento"},
    "DÍVIDA DE SANGUE":{"sobrevivencia","defesa"},
    "MORTE CERTA":{"dano","critico"},"LOUCURA DE GUERRA":{"dano","movimento"},"EQUILÍBRIO PERFEITO":{"dano","tank","movimento"},
    "ASCENSÃO":{"dano","sobrevivencia","critico"},"MESTRE DAS ARTES":{"projeteis","dano","movimento"},
    "CAMPEÃO":{"tank","dano","sobrevivencia"},"LENDA VIVA":{"dano","critico","movimento"},
    "PODER ILIMITADO":{"dano","movimento"},"FORMA SOMBRIA":{"dano","orbes","movimento"},
    "FANTASMA DA MORTE":{"dano","projeteis","critico"},"REI DO CAMPO":{"projeteis"},
    "ESTRATEGISTA":{"dano","tank","cadencia"},"GUERREIRO ETERNO":{"tank","movimento","sobrevivencia"},
    "COLOSSO DE FERRO":{"tank","dano","defesa"},"LÂMINA SOMBRIA":{"dano","projeteis"},
    "BERSERKER FINAL":{"dano","cadencia","projeteis"},"DOMINADOR":{"dano","critico"},
    "REAPER":{"dano"},"TEMPESTADE MORTAL":{"projeteis","explosao","dano"},
    "FORÇA BRUTA":{"dano","tank"},"AGILIDADE EXTREMA":{"movimento","cadencia"},
    "GOLPE DIVINO":{"dano","orbes","explosao"},"MESTRE DO CAOS":{"projeteis","dano","critico"},
    "TRANSCENDÊNCIA":{"dano","tank","movimento","sobrevivencia"},"FORMA FINAL":{"dano","critico","movimento"},
}

EVOLUTIONS = {
    "BAZUCA": {"base": "TIRO MÚLTIPLO", "passive": "EXPLOSÃO", "desc": "EVOLUÇÃO: Poder de fogo extremo, com dano explosivo ampliado!"},
    "SERRAS MÁGICAS": {"base": "ORBES MÁGICOS", "passive": "VELOCIDADE ++", "desc": "EVOLUÇÃO: Orbes giram freneticamente rasgando tudo!"},
    "TESLA": {"base": "TIRO RÁPIDO", "passive": "RICOCHE", "desc": "EVOLUÇÃO: Raios em cadeia entre inimigos!"},
    "CEIFADOR": {"base": "EXECUÇÃO", "passive": "SORTE", "desc": "EVOLUÇÃO: Execução brutal + críticos insanos!"},
    "BERSERK": {"base": "FÚRIA", "passive": "VIDA MÁXIMA", "desc": "EVOLUÇÃO: Quanto mais apanha, mais destrói tudo!"},
}

UPGRADE_ICONS = {
    "DANO ++": "icon_damage",
    "VELOCIDADE ++": "icon_speed",
    "TIRO RÁPIDO": "icon_firespeed",
    "VIDA MÁXIMA": "icon_hp",
    "CHAMA ARDENTE": "icon_aura",
    "ÍMÃ DE XP": "icon_magnet",
    "TIRO MÚLTIPLO": "icon_multishot",
    "EXPLOSÃO": "icon_explosion",
    "PERFURAÇÃO": "icon_pierce",
    "ORBES MÁGICOS": "icon_orbs",
    "SORTE": "icon_luck",
    "CURA": "icon_heal",
    "BAZUCA": "icon_bazuca",
    "BURACO NEGRO": "icon_blackhole",
    "SERRAS MÁGICAS": "icon_saws",
    "RICOCHE": "icon_ricochet",
    "EXECUÇÃO": "icon_execute",
    "FÚRIA": "icon_fury",
    "CAPA INVISÍVEL": "item_capa",
    "LUVA EXPULSÃO": "item_luva",
    "TREVO SORTE": "item_trevo",
    "SYNERGY_MIDAS": "synergy_midas",
    # ícones das 200 novas skills (icons/newskills/skill N.png e skill icon N.png)
    **{k: f"icons/newskills/skill {i+1}" for i, k in enumerate([
        "LÂMINA SANGRADA","GOLPE CERTEIRO","CRÍTICO LETAL","PUNHAL SOMBRIO","FLECHA EXPLOSIVA",
        "DESTRUIÇÃO TOTAL","LÂMINA DE SOMBRA","SANGUE DO CAÇADOR","FÚRIA SELVAGEM","RUNA AFIADA",
        "ESCOLHA DO CARRASCO","TOQUE DO ABISMO","FRAGMENTO DE ALMA","MARTELO DO TROVÃO","FOGUEIRA INFERNAL",
        "GOLPE CÓSMICO","EXECUTAR O FRACO","FLUXO DE MANA","SETA DO DESTINO","PODER OCULTO",
        "HERANÇA SOMBRIA","INSTINTO PREDADOR","CRISTAL DE DANO","ESPADA LENDÁRIA","PEDRA DO CAOS",
        "TIRO PRECISO","GOLPE DO DESTINO","MAGIA DUPLA","FRIO MORTAL","SOPRO VENENOSO",
        "BALA FANTASMA","TEMPESTADE DE SETAS","RICOCHETE DUPLO","BALA SÔNICA","RAJADA RÁPIDA",
        "FLECHA TRIPLA","PERFURAÇÃO EXTREMA","ECO MÁGICO","VELOCIDADE DE LUZ","CHUVA DE FLECHAS",
        "DISPARO VELOZ","FRAGMENTAÇÃO","SETA FANTASMA","ONDA DE CHOQUE","BALA DUPLA",
        "RICOCHETE MÁGICO","DISPARO RÁPIDO","CASCATA","RAJADA SUPERSÔNICA","FLECHA MÁGICA",
        "PERFURAÇÃO TOTAL","TIRO VELOZ","MULTIPLICAÇÃO","ECO BALÍSTICO","TEMPESTADE TOTAL",
        "ESCUDO DE FERRO","CURA RÁPIDA","ARMADURA ANTIGA","ESPINHOS DE AÇO","VIDA DUPLA",
        "REGENERAÇÃO LENTA","MURALHA DE PEDRA","PELE DE DRAGÃO","RECUPERAÇÃO RÁPIDA","FORÇA VITAL",
        "SANGUE VAMPIRO","ESCUDO MÍSTICO","TRONCO DE CARVALHO","DRENO DE VIDA","ARMADURA DIVINA",
        "REGENERAÇÃO MÍSTICA","DRENAGEM SOMBRIA","CURA ABENÇOADA","VIDA ETERNA","ESPINHOS MORTAIS",
        "ABSORÇÃO VITAL","ROCHA INQUEBRANTÁVEL","REGENERAÇÃO EXTREMA","BARREIRA ARCANA","VAMPIRO SOMBRIO",
        "COLETE DE AÇO","FONTE DE VIDA","ESSÊNCIA VITAL","RESISTÊNCIA TOTAL","MANTO PROTETOR",
        "BOTAS VELOZES","ASAS DO VENTO","CORRER É VIVER","REFLEXOS AGUÇADOS","MOVIMENTO FANTASMA",
        "ÍMPETO DO GUERREIRO","TURBILHÃO","PASSO DO ASSASSINO","DANÇA DA MORTE","VENTO CORTANTE",
        "RELÂMPAGO","PASSO ESPECTRAL","CORRIDA MÁGICA","IMPULSO DIVINO","RASTRO DE FOGO",
    ])},
    **{k: f"icons/newskills/skill icon {i+1}" for i, k in enumerate([
        "ACELERAÇÃO","FLUXO ETERNO","VENTO UIVANTE","MARÉ VELOZ","VELOZ COMO O RAIO",
        "CÍRCULO ARCANO","ESCUDO RÚNICO","ORBE DESTRUIDOR","MAGIA ARCANA","DUPLO ORBE",
        "AMPLIFICADOR ARCANO","VÓRTICE MÁGICO","ONDA ÍGNEA","SEIS ORBES","DISPERSÃO MÁGICA",
        "ORBE FANTASMA","GRAÇA DIVINA","CÍRCULO DA MORTE","EXECUÇÃO ARCANA","ESPIRAL DE FOGO",
        "ORBES EXPLOSIVOS","CEIFA ARCANA","CONSTELAÇÃO","VÓRTICE CÓSMICO","DANÇA DOS ORBES",
        "DETONAÇÃO MÁGICA","PODER SUPREMO","PERFURAÇÃO CÓSMICA","NEXO ARCANO","VIDA ETERNA RÚNICA",
        "MICRO BOMBA","BOMBA GRANDE","FRAGMENTO EXPLOSIVO","DETONAÇÃO","BOMBA DE PLASMA",
        "ONDA EXPLOSIVA","CARGA NUCLEAR","FRAGMENTO INCENDIÁRIO","TIRO EXPLOSIVO","BOMBA GRAVITACIONAL",
        "CADEIA EXPLOSIVA","SUPERNOVA","EXPLOSÃO SOMBRIA","DETONADOR EXTREMO","BOMBA FINAL",
        "COLETOR DE GEMAS","FORTUNA DO AVENTUREIRO","EXPERIÊNCIA ACELERADA","IMÃ SUPREMO","COFRE DO AVENTUREIRO",
        "APRENDIZADO RÁPIDO","CAMPOS MAGNÉTICOS","OURO DO REI","SÁBIO DO MUNDO","MAGNETISMO MÁXIMO",
        "TESOURO ANTIGO","INICIAÇÃO ARCANA","VÓRTICE DE GEMAS","GANÂNCIA ILIMITADA","MENTOR ESPIRITUAL",
        "SORTE DO VIAJANTE","PRESENÇA MAGNÉTICA","TOQUE DO ALQUIMISTA","DÁDIVA DOS DEUSES","SÍMBOLO DA PROSPERIDADE",
        "COLETOR MÁGICO","ABUNDÂNCIA","CRESCIMENTO ESPIRITUAL","GEMA DA FORTUNA","CAMINHO DO MESTRE",
        "ORÁCULO","CONHECIMENTO PROIBIDO","HERANÇA DO REI","CAMINHO DO SÁBIO","DÍVIDA DE SANGUE",
        "MORTE CERTA","LOUCURA DE GUERRA","EQUILÍBRIO PERFEITO","ASCENSÃO","MESTRE DAS ARTES",
        "CAMPEÃO","LENDA VIVA","PODER ILIMITADO","FORMA SOMBRIA","FANTASMA DA MORTE",
        "REI DO CAMPO","ESTRATEGISTA","GUERREIRO ETERNO","COLOSSO DE FERRO","LÂMINA SOMBRIA",
        "BERSERKER FINAL","DOMINADOR","REAPER","TEMPESTADE MORTAL","FORÇA BRUTA",
        "AGILIDADE EXTREMA","GOLPE DIVINO","MESTRE DO CAOS","TRANSCENDÊNCIA","FORMA FINAL",
    ])},
}

# Efeitos das 200 novas skills — processados por dispatch em apply_upgrade()
# Chaves: dmg, crit, crit_mult, execute, pierce, proj, ricochet, proj_speed,
#         cooldown, hp, regen, thorns, lifesteal, speed, pickup,
#         aura_dmg, aura_range, orb, orb_dmg, orb_dist, explosion, exp_dmg,
#         gold, xp, heal
NEW_SKILL_EFFECTS = {
    "LÂMINA SANGRADA":{"dmg":3},"GOLPE CERTEIRO":{"crit":0.10},"CRÍTICO LETAL":{"crit_mult":0.25},
    "PUNHAL SOMBRIO":{"dmg":4},"FLECHA EXPLOSIVA":{"dmg":2,"explosion":20},"DESTRUIÇÃO TOTAL":{"dmg":5},
    "LÂMINA DE SOMBRA":{"dmg":4,"thorns":0.10},"SANGUE DO CAÇADOR":{"dmg":2,"crit":0.08},"FÚRIA SELVAGEM":{"dmg":4},
    "RUNA AFIADA":{"dmg":3,"crit":0.05},"ESCOLHA DO CARRASCO":{"execute":0.08},"TOQUE DO ABISMO":{"dmg":5},
    "FRAGMENTO DE ALMA":{"crit_mult":0.20},"MARTELO DO TROVÃO":{"dmg":6},"FOGUEIRA INFERNAL":{"dmg":3,"explosion":20},
    "GOLPE CÓSMICO":{"crit":0.12},"EXECUTAR O FRACO":{"execute":0.10},"FLUXO DE MANA":{"dmg":3,"cooldown":0.05},
    "SETA DO DESTINO":{"crit":0.15},"PODER OCULTO":{"dmg":5},"HERANÇA SOMBRIA":{"crit_mult":0.30,"dmg":2},
    "INSTINTO PREDADOR":{"execute":0.08,"crit":0.08},"CRISTAL DE DANO":{"dmg":4},"ESPADA LENDÁRIA":{"dmg":7},
    "PEDRA DO CAOS":{"dmg":3,"crit":0.10},"TIRO PRECISO":{"crit":0.15,"pierce":1},"GOLPE DO DESTINO":{"execute":0.12,"dmg":3},
    "MAGIA DUPLA":{"dmg":2,"proj":1},"FRIO MORTAL":{"dmg":4,"crit":0.08},"SOPRO VENENOSO":{"dmg":4,"lifesteal":0.03},
    "BALA FANTASMA":{"pierce":1},"TEMPESTADE DE SETAS":{"proj":1},"RICOCHETE DUPLO":{"ricochet":1},
    "BALA SÔNICA":{"proj_speed":80},"RAJADA RÁPIDA":{"cooldown":0.10},"FLECHA TRIPLA":{"proj":2},
    "PERFURAÇÃO EXTREMA":{"pierce":2},"ECO MÁGICO":{"proj":1,"ricochet":1},"VELOCIDADE DE LUZ":{"proj_speed":120},
    "CHUVA DE FLECHAS":{"proj":1,"pierce":1},"DISPARO VELOZ":{"cooldown":0.12},"FRAGMENTAÇÃO":{"proj":1,"explosion":30},
    "SETA FANTASMA":{"pierce":1,"proj_speed":60},"ONDA DE CHOQUE":{"proj":1,"ricochet":1},"BALA DUPLA":{"proj":2},
    "RICOCHETE MÁGICO":{"ricochet":2},"DISPARO RÁPIDO":{"cooldown":0.15},"CASCATA":{"proj":1,"pierce":1},
    "RAJADA SUPERSÔNICA":{"proj_speed":150},"FLECHA MÁGICA":{"proj":1,"crit":0.08},"PERFURAÇÃO TOTAL":{"pierce":3},
    "TIRO VELOZ":{"cooldown":0.08},"MULTIPLICAÇÃO":{"proj":2},"ECO BALÍSTICO":{"proj_speed":100,"pierce":1},
    "TEMPESTADE TOTAL":{"proj":2,"pierce":2},"ESCUDO DE FERRO":{"hp":5},"CURA RÁPIDA":{"regen":0.3},
    "ARMADURA ANTIGA":{"hp":8},"ESPINHOS DE AÇO":{"thorns":0.12},"VIDA DUPLA":{"hp":10},
    "REGENERAÇÃO LENTA":{"regen":0.5},"MURALHA DE PEDRA":{"hp":12},"PELE DE DRAGÃO":{"thorns":0.18},
    "RECUPERAÇÃO RÁPIDA":{"regen":0.8},"FORÇA VITAL":{"hp":15},"SANGUE VAMPIRO":{"lifesteal":0.02},
    "ESCUDO MÍSTICO":{"hp":5,"regen":0.2},"TRONCO DE CARVALHO":{"hp":20},"DRENO DE VIDA":{"lifesteal":0.03},
    "ARMADURA DIVINA":{"hp":25},"REGENERAÇÃO MÍSTICA":{"regen":1.0},"DRENAGEM SOMBRIA":{"lifesteal":0.05},
    "CURA ABENÇOADA":{"heal":0.30},"VIDA ETERNA":{"hp":30},"ESPINHOS MORTAIS":{"thorns":0.22},
    "ABSORÇÃO VITAL":{"lifesteal":0.04},"ROCHA INQUEBRANTÁVEL":{"hp":35},"REGENERAÇÃO EXTREMA":{"regen":1.5},
    "BARREIRA ARCANA":{"hp":8,"regen":0.4},"VAMPIRO SOMBRIO":{"lifesteal":0.06},"COLETE DE AÇO":{"hp":5},
    "FONTE DE VIDA":{"regen":2.0},"ESSÊNCIA VITAL":{"hp":20,"regen":0.5},"RESISTÊNCIA TOTAL":{"hp":10,"thorns":0.10},
    "MANTO PROTETOR":{"lifesteal":0.04,"regen":0.3},"BOTAS VELOZES":{"speed":20},"ASAS DO VENTO":{"speed":30},
    "CORRER É VIVER":{"speed":15,"pickup":40},"REFLEXOS AGUÇADOS":{"speed":25},"MOVIMENTO FANTASMA":{"speed":35},
    "ÍMPETO DO GUERREIRO":{"speed":20,"cooldown":0.08},"TURBILHÃO":{"speed":40},"PASSO DO ASSASSINO":{"speed":15,"crit":0.05},
    "DANÇA DA MORTE":{"speed":50},"VENTO CORTANTE":{"speed":25,"pickup":50},"RELÂMPAGO":{"speed":60},
    "PASSO ESPECTRAL":{"speed":20,"pickup":60},"CORRIDA MÁGICA":{"speed":30,"cooldown":0.05},"IMPULSO DIVINO":{"speed":45},
    "RASTRO DE FOGO":{"speed":35,"dmg":2},"ACELERAÇÃO":{"speed":25},"FLUXO ETERNO":{"pickup":80,"speed":20},
    "VENTO UIVANTE":{"speed":50},"MARÉ VELOZ":{"speed":30,"crit":0.05},"VELOZ COMO O RAIO":{"speed":70},
    "CÍRCULO ARCANO":{"orb":1},"ESCUDO RÚNICO":{"hp":8,"regen":0.3},"ORBE DESTRUIDOR":{"orb_dmg":3},
    "MAGIA ARCANA":{"dmg":3,"proj":1},"DUPLO ORBE":{"orb":1,"orb_dmg":2},"AMPLIFICADOR ARCANO":{"crit_mult":0.20,"crit":0.05},
    "VÓRTICE MÁGICO":{"orb":1,"orb_dist":50},"ONDA ÍGNEA":{"explosion":50,"exp_dmg":4},"SEIS ORBES":{"orb":2},
    "DISPERSÃO MÁGICA":{"proj":1,"proj_speed":80},"ORBE FANTASMA":{"orb":1,"orb_dmg":4},"GRAÇA DIVINA":{"hp":12,"regen":0.5},
    "CÍRCULO DA MORTE":{"orb":2,"orb_dmg":3},"EXECUÇÃO ARCANA":{"execute":0.08,"crit":0.08},"ESPIRAL DE FOGO":{"orb":1,"orb_dmg":3},
    "ORBES EXPLOSIVOS":{"orb":1,"explosion":40},"CEIFA ARCANA":{"dmg":5,"execute":0.06},"CONSTELAÇÃO":{"orb":2,"orb_dist":60},
    "VÓRTICE CÓSMICO":{"pickup":100,"xp":0.15},"DANÇA DOS ORBES":{"orb":2,"orb_dmg":5},"DETONAÇÃO MÁGICA":{"explosion":60,"exp_dmg":5},
    "PODER SUPREMO":{"dmg":4,"orb":1,"crit":0.06},"PERFURAÇÃO CÓSMICA":{"dmg":6,"pierce":1},"NEXO ARCANO":{"orb":3},
    "VIDA ETERNA RÚNICA":{"regen":1.5,"lifesteal":0.04},"MICRO BOMBA":{"explosion":25},"BOMBA GRANDE":{"explosion":40},
    "FRAGMENTO EXPLOSIVO":{"exp_dmg":3},"DETONAÇÃO":{"explosion":60},"BOMBA DE PLASMA":{"exp_dmg":5},
    "ONDA EXPLOSIVA":{"explosion":80,"exp_dmg":4},"CARGA NUCLEAR":{"explosion":100},"FRAGMENTO INCENDIÁRIO":{"exp_dmg":6},
    "TIRO EXPLOSIVO":{"explosion":50,"dmg":2},"BOMBA GRAVITACIONAL":{"explosion":70,"exp_dmg":5},
    "CADEIA EXPLOSIVA":{"explosion":30,"ricochet":1,"exp_dmg":3},"SUPERNOVA":{"explosion":120},
    "EXPLOSÃO SOMBRIA":{"exp_dmg":8},"DETONADOR EXTREMO":{"explosion":90,"exp_dmg":6},"BOMBA FINAL":{"explosion":150,"exp_dmg":10},
    "COLETOR DE GEMAS":{"pickup":100},"FORTUNA DO AVENTUREIRO":{"gold":0.20},"EXPERIÊNCIA ACELERADA":{"xp":0.15},
    "IMÃ SUPREMO":{"pickup":150},"COFRE DO AVENTUREIRO":{"gold":0.30},"APRENDIZADO RÁPIDO":{"xp":0.20},
    "CAMPOS MAGNÉTICOS":{"pickup":200},"OURO DO REI":{"gold":0.40},"SÁBIO DO MUNDO":{"xp":0.25},
    "MAGNETISMO MÁXIMO":{"pickup":250},"TESOURO ANTIGO":{"gold":0.50},"INICIAÇÃO ARCANA":{"xp":0.30},
    "VÓRTICE DE GEMAS":{"pickup":180},"GANÂNCIA ILIMITADA":{"gold":0.60},"MENTOR ESPIRITUAL":{"xp":0.35},
    "SORTE DO VIAJANTE":{"crit":0.05,"gold":0.10},"PRESENÇA MAGNÉTICA":{"pickup":120,"gold":0.10},
    "TOQUE DO ALQUIMISTA":{"gold":0.15,"regen":0.5},"DÁDIVA DOS DEUSES":{"xp":0.20,"regen":0.5},
    "SÍMBOLO DA PROSPERIDADE":{"gold":0.25,"crit":0.05},"COLETOR MÁGICO":{"pickup":80,"xp":0.10},
    "ABUNDÂNCIA":{"gold":0.20,"hp":5},"CRESCIMENTO ESPIRITUAL":{"xp":0.15,"regen":0.3},
    "GEMA DA FORTUNA":{"crit":0.08,"pickup":80},"CAMINHO DO MESTRE":{"xp":0.20,"crit":0.05},
    "ORÁCULO":{"gold":0.10,"xp":0.10,"regen":0.2},"CONHECIMENTO PROIBIDO":{"xp":0.30,"dmg":2},
    "HERANÇA DO REI":{"gold":0.30,"hp":5},"CAMINHO DO SÁBIO":{"xp":0.20,"speed":20},
    "DÍVIDA DE SANGUE":{"lifesteal":0.10,"thorns":0.12},"MORTE CERTA":{"execute":0.10,"crit":0.10},
    "LOUCURA DE GUERRA":{"dmg":3,"speed":20},"EQUILÍBRIO PERFEITO":{"dmg":2,"hp":5,"speed":10},
    "ASCENSÃO":{"dmg":3,"regen":0.3,"crit":0.05},"MESTRE DAS ARTES":{"proj":2,"dmg":2,"speed":20},
    "CAMPEÃO":{"hp":10,"dmg":2,"regen":0.3},"LENDA VIVA":{"dmg":5,"crit":0.05,"speed":20},
    "PODER ILIMITADO":{"dmg":6,"speed":30},"FORMA SOMBRIA":{"dmg":3,"orb":2,"speed":15},
    "FANTASMA DA MORTE":{"dmg":3,"pierce":1,"crit":0.05},"REI DO CAMPO":{"proj":1,"pierce":1,"ricochet":1},
    "ESTRATEGISTA":{"dmg":3,"hp":20,"cooldown":0.10},"GUERREIRO ETERNO":{"hp":5,"speed":15,"regen":0.3},
    "COLOSSO DE FERRO":{"hp":20,"dmg":3,"thorns":0.10},"LÂMINA SOMBRIA":{"dmg":4,"pierce":1,"ricochet":1},
    "BERSERKER FINAL":{"dmg":6,"cooldown":0.12,"proj":1},"DOMINADOR":{"dmg":4,"crit":0.10,"execute":0.10},
    "REAPER":{"dmg":5,"execute":0.15},"TEMPESTADE MORTAL":{"proj":2,"explosion":40,"dmg":3},
    "FORÇA BRUTA":{"dmg":8,"hp":10},"AGILIDADE EXTREMA":{"speed":50,"cooldown":0.12},
    "GOLPE DIVINO":{"dmg":4,"orb":1,"explosion":30},"MESTRE DO CAOS":{"proj":3,"dmg":2,"crit":0.05},
    "TRANSCENDÊNCIA":{"dmg":5,"hp":5,"speed":25,"regen":0.3},"FORMA FINAL":{"dmg":8,"crit":0.15,"execute":0.10,"speed":30},
}

RARITY = {
    # Limiares cumulativos do mais raro para o mais comum.
    # Ex.: roll < 0.02 → Lendário (2%), < 0.10 → Épico (8%), < 0.30 → Raro (20%), < 1.0 → Comum (70%)
    "LENDARIO": {"chance": 0.02, "mult": 2.50, "color": (255, 200,  50)},
    "EPICO":    {"chance": 0.10, "mult": 1.75, "color": (200,  80, 255)},
    "RARO":     {"chance": 0.30, "mult": 1.35, "color": ( 80, 170, 255)},
    "COMUM":    {"chance": 1.00, "mult": 1.00, "color": (200, 200, 200)},
}

# Alias para compatibilidade (RARITIES = RARITY)
RARITIES = RARITY

# Pool de upgrades disponíveis (filtrada pelos unlocks)
UPGRADE_POOL = {k: v for k, v in ALL_UPGRADES_POOL.items() if k in DEFAULT_UNLOCKS or True}

# Pactos disponíveis
PACTOS = {
    "NENHUM":     {"name": "SEM PACTO",       "desc": "Sem modificadores.",                     "hp": 0,  "color": (200, 200, 200)},
    "VELOCIDADE": {"name": "PACTO DA PRESSA",  "desc": "Inimigos 50% mais rápidos, +50% Ouro.",  "hp": 0,  "color": (255, 200, 0)},
    "FRÁGIL":     {"name": "PACTO FRÁGIL",     "desc": "Começa com 20% menos HP máximo, +30% XP.", "hp": 0, "hp_pct": -0.20, "xp_pct": 0.30, "color": (255, 100, 100)},
}

# Dados dos biomas / backgrounds
BG_DATA = {
    "dungeon":  {"name": "bg_dungeon",  "music": "music_dungeon",  "type": "normal"},
    "forest":   {"name": "bg_forest",   "music": "music_forest",   "type": "normal"},
    "volcano":  {"name": "bg_volcano",  "music": "music_volcano",  "type": "volcano"},
    "moon":     {"name": "bg_moon",     "music": "music_moon",     "type": "moon"},
}

# Biomas disponíveis (apenas dungeon por enquanto; demais bloqueados)
BG_LOCKED = {"forest"}

# Loja de Itens — categorias e seus assets (nome do prefixo e quantidade de arquivos)
# Estatísticas de cada item por categoria — ordem crescente de poder (estilo Diablo)
# Cada lista corresponde aos itens 1..N da categoria.
# "atk": bônus de ataque  |  "def": bônus de defesa  |  "price": custo em ouro
ITEM_SHOP_STATS: dict[str, list[dict]] = {
    "Espadas": [
        {"name": "Espada Enferrujada",    "atk":  15, "def":  0, "price":  100, "level":  1},
        {"name": "Espada de Ferro",        "atk":  22, "def":  0, "price":  150, "level":  1},
        {"name": "Espada de Aço",          "atk":  30, "def":  1, "price":  200, "level":  1},
        {"name": "Espada Curta",           "atk":  35, "def":  0, "price":  260, "level":  1},
        {"name": "Espada de Bronze",       "atk":  42, "def":  0, "price":  320, "level":  5},
        {"name": "Espada da Guarda",       "atk":  50, "def":  2, "price":  390, "level":  5},
        {"name": "Espada Afiada",          "atk":  60, "def":  0, "price":  470, "level":  5},
        {"name": "Espada de Prata",        "atk":  70, "def":  1, "price":  550, "level":  5},
        {"name": "Espada de Brilho",       "atk":  80, "def":  2, "price":  640, "level": 10},
        {"name": "Espadão",                "atk":  95, "def":  0, "price":  740, "level": 10},
        {"name": "Espada da Tempestade",   "atk": 108, "def":  3, "price":  840, "level": 10},
        {"name": "Espada do Cavaleiro",    "atk": 120, "def":  4, "price":  950, "level": 10},
        {"name": "Espada de Flama",        "atk": 133, "def":  2, "price": 1060, "level": 15},
        {"name": "Espada Negra",           "atk": 147, "def":  0, "price": 1180, "level": 15},
        {"name": "Espada de Sombra",       "atk": 160, "def":  5, "price": 1300, "level": 20},
        {"name": "Espada Encantada",       "atk": 172, "def":  6, "price": 1430, "level": 20},
        {"name": "Espada do Caos",         "atk": 185, "def":  4, "price": 1560, "level": 25},
        {"name": "Espada das Trevas",      "atk": 198, "def":  8, "price": 1700, "level": 25},
        {"name": "Espada do Inferno",      "atk": 215, "def": 10, "price": 1850, "level": 30},
        {"name": "Espada do Apocalipse",   "atk": 250, "def": 15, "price": 2100, "level": 30},
    ],
    "Machados": [
        {"name": "Machado de Pedra",       "atk":  18, "def":  0, "price":  120, "level":  1},
        {"name": "Machado de Osso",        "atk":  30, "def":  0, "price":  190, "level":  1},
        {"name": "Machado Rústico",        "atk":  45, "def":  0, "price":  270, "level":  5},
        {"name": "Machado de Ferro",       "atk":  62, "def":  0, "price":  360, "level":  5},
        {"name": "Machado Afiado",         "atk":  80, "def":  0, "price":  460, "level": 10},
        {"name": "Machado de Guerra",      "atk": 100, "def":  0, "price":  580, "level": 10},
        {"name": "Machado Rúnico",         "atk": 125, "def":  0, "price":  710, "level": 20},
        {"name": "Machado Sanguinário",    "atk": 150, "def":  0, "price":  860, "level": 20},
        {"name": "Machado do Berserker",   "atk": 180, "def":  0, "price": 1020, "level": 30},
        {"name": "Machado do Destruidor",  "atk": 220, "def":  0, "price": 1200, "level": 30},
    ],
    "Hammers": [
        {"name": "Martelo de Madeira",     "atk":  20, "def":  0, "price":  130, "level":  1},
        {"name": "Martelo Tosco",          "atk":  35, "def":  0, "price":  210, "level":  1},
        {"name": "Martelo de Ferreiro",    "atk":  52, "def":  0, "price":  300, "level":  5},
        {"name": "Martelo de Ferro",       "atk":  70, "def":  0, "price":  400, "level":  5},
        {"name": "Martelo Sólido",         "atk":  90, "def":  0, "price":  510, "level": 10},
        {"name": "Martelo de Guerra",      "atk": 115, "def":  0, "price":  640, "level": 10},
        {"name": "Martelo Rúnico",         "atk": 140, "def":  0, "price":  780, "level": 20},
        {"name": "Martelo do Ogro",        "atk": 170, "def":  0, "price":  930, "level": 20},
        {"name": "Martelo do Caos",        "atk": 200, "def":  0, "price": 1100, "level": 30},
        {"name": "Martelo do Titã",        "atk": 240, "def":  0, "price": 1300, "level": 30},
    ],
    "Escudos": [
        {"name": "Escudo de Madeira",      "atk":   0, "def":  10, "price":   90, "level":  1},
        {"name": "Escudo de Couro",        "atk":   0, "def":  18, "price":  160, "level":  1},
        {"name": "Escudo de Bronze",       "atk":   0, "def":  28, "price":  240, "level":  5},
        {"name": "Escudo de Ferro",        "atk":   0, "def":  40, "price":  330, "level":  5},
        {"name": "Escudo do Guerreiro",    "atk":   0, "def":  55, "price":  430, "level": 10},
        {"name": "Escudo de Prata",        "atk":   0, "def":  72, "price":  550, "level": 10},
        {"name": "Escudo Rúnico",          "atk":   0, "def":  90, "price":  680, "level": 20},
        {"name": "Escudo de Mithril",      "atk":   0, "def": 110, "price":  830, "level": 20},
        {"name": "Escudo Abençoado",       "atk":   0, "def": 135, "price": 1000, "level": 30},
        {"name": "Escudo do Arcanjo",      "atk":   0, "def": 165, "price": 1200, "level": 30},
    ],
    "Bows": [
        {"name": "Arco Primitivo",         "atk":  10, "def":  0, "price":   80, "level":  1},
        {"name": "Arco Simples",           "atk":  18, "def":  0, "price":  140, "level":  1},
        {"name": "Arco de Caçador",        "atk":  28, "def":  0, "price":  200, "level":  5},
        {"name": "Arco Recurvo",           "atk":  40, "def":  0, "price":  270, "level":  5},
        {"name": "Arco de Madeira Nobre",  "atk":  55, "def":  0, "price":  350, "level": 10},
        {"name": "Arco do Explorador",     "atk":  72, "def":  0, "price":  440, "level": 10},
        {"name": "Arco Élfico",            "atk":  92, "def":  0, "price":  540, "level": 20},
        {"name": "Arco da Tempestade",     "atk": 115, "def":  0, "price":  650, "level": 20},
        {"name": "Arco Sombrio",           "atk": 142, "def":  0, "price":  770, "level": 30},
        {"name": "Arco do Destino",        "atk": 175, "def":  0, "price":  910, "level": 30},
    ],
    "Crossbows": [
        {"name": "Besta Simples",          "atk":  13, "def":  0, "price":   90, "level":  1},
        {"name": "Besta de Madeira",       "atk":  22, "def":  0, "price":  155, "level":  1},
        {"name": "Besta de Ferro",         "atk":  33, "def":  0, "price":  220, "level":  5},
        {"name": "Besta Mecanizada",       "atk":  46, "def":  0, "price":  295, "level":  5},
        {"name": "Besta de Precisão",      "atk":  62, "def":  0, "price":  380, "level": 10},
        {"name": "Besta do Caçador",       "atk":  80, "def":  0, "price":  475, "level": 10},
        {"name": "Besta Rúnica",           "atk": 102, "def":  0, "price":  580, "level": 20},
        {"name": "Besta das Sombras",      "atk": 128, "def":  0, "price":  700, "level": 20},
        {"name": "Besta Infernal",         "atk": 158, "def":  0, "price":  830, "level": 30},
        {"name": "Besta do Apocalipse",    "atk": 195, "def":  0, "price":  980, "level": 30},
    ],
    "Cajados": [
        {"name": "Cajado de Aprendiz",     "atk":   8, "def":  2, "price":  100, "level":  1},
        {"name": "Cajado de Madeira",      "atk":  14, "def":  3, "price":  160, "level":  1},
        {"name": "Cajado do Viajante",     "atk":  22, "def":  4, "price":  230, "level":  5},
        {"name": "Cajado de Cristal",      "atk":  32, "def":  6, "price":  310, "level":  5},
        {"name": "Cajado de Lava",         "atk":  45, "def":  8, "price":  400, "level": 10},
        {"name": "Cajado das Trevas",      "atk":  60, "def": 10, "price":  500, "level": 10},
        {"name": "Cajado Arcano",          "atk":  78, "def": 12, "price":  610, "level": 20},
        {"name": "Cajado de Pedra Rúnica", "atk": 100, "def": 15, "price":  730, "level": 20},
        {"name": "Cajado do Abismo",       "atk": 128, "def": 18, "price":  860, "level": 30},
        {"name": "Cajado do Lich",         "atk": 160, "def": 22, "price": 1000, "level": 30},
    ],
    "Capacetes": [
        {"name": "Elmo de Madeira",       "def":  5, "price":   70, "level":  1},
        {"name": "Elmo de Couro",         "def": 10, "price":  120, "level":  1},
        {"name": "Elmo de Bronze",        "def": 16, "price":  180, "level":  1},
        {"name": "Elmo de Ferro",         "def": 23, "price":  250, "level":  5},
        {"name": "Elmo do Soldado",       "def": 30, "price":  330, "level":  5},
        {"name": "Elmo de Prata",         "def": 38, "price":  420, "level":  5},
        {"name": "Elmo Rúnico",           "def": 46, "price":  520, "level": 10},
        {"name": "Elmo de Mithril",       "def": 54, "price":  630, "level": 10},
        {"name": "Elmo do Cavaleiro",     "def": 62, "price":  760, "level": 15},
        {"name": "Elmo Abençoado",        "def": 70, "price":  900, "level": 15},
        {"name": "Elmo do Paladino",      "def": 78, "price": 1060, "level": 20},
        {"name": "Elmo do Arcanjo",       "def": 86, "price": 1240, "level": 25},
    ],
    "Armaduras": [
        {"name": "Armadura de Couro",     "def":  8, "price":  100, "level":  1},
        {"name": "Armadura Simples",      "def": 16, "price":  165, "level":  1},
        {"name": "Armadura de Bronze",    "def": 24, "price":  240, "level":  1},
        {"name": "Armadura de Ferro",     "def": 34, "price":  330, "level":  5},
        {"name": "Armadura do Soldado",   "def": 45, "price":  430, "level":  5},
        {"name": "Armadura de Aço",       "def": 57, "price":  545, "level":  5},
        {"name": "Armadura Rúnica",       "def": 70, "price":  675, "level": 10},
        {"name": "Armadura de Mithril",   "def": 84, "price":  820, "level": 10},
        {"name": "Armadura do Cavaleiro", "def": 98, "price":  980, "level": 15},
        {"name": "Armadura Abençoada",    "def":113, "price": 1160, "level": 15},
        {"name": "Armadura do Paladino",  "def":128, "price": 1360, "level": 20},
        {"name": "Armadura do Arcanjo",   "def":145, "price": 1580, "level": 25},
    ],
    "Calças": [
        {"name": "Calças de Couro",       "def":  4, "price":   60, "level":  1},
        {"name": "Calças Reforçadas",     "def":  8, "price":  110, "level":  1},
        {"name": "Calças de Bronze",      "def": 13, "price":  165, "level":  1},
        {"name": "Calças de Ferro",       "def": 19, "price":  225, "level":  5},
        {"name": "Calças do Soldado",     "def": 25, "price":  295, "level":  5},
        {"name": "Calças de Prata",       "def": 32, "price":  375, "level":  5},
        {"name": "Calças Rúnicas",        "def": 39, "price":  465, "level": 10},
        {"name": "Calças de Mithril",     "def": 46, "price":  565, "level": 10},
        {"name": "Calças do Cavaleiro",   "def": 54, "price":  675, "level": 15},
        {"name": "Calças Abençoadas",     "def": 62, "price":  800, "level": 15},
        {"name": "Calças do Paladino",    "def": 70, "price":  940, "level": 20},
        {"name": "Calças do Arcanjo",     "def": 78, "price": 1100, "level": 25},
    ],
    "Botas": [
        {"name": "Botas de Couro",        "def":  3, "spd":  5, "price":   50, "level":  1},
        {"name": "Botas Reforçadas",      "def":  6, "spd":  8, "price":   95, "level":  1},
        {"name": "Botas de Bronze",       "def": 10, "spd": 10, "price":  145, "level":  5},
        {"name": "Botas de Ferro",        "def": 15, "spd": 12, "price":  200, "level":  5},
        {"name": "Botas do Soldado",      "def": 20, "spd": 15, "price":  265, "level": 10},
        {"name": "Botas de Prata",        "def": 26, "spd": 18, "price":  340, "level": 10},
        {"name": "Botas Rúnicas",         "def": 32, "spd": 21, "price":  425, "level": 20},
        {"name": "Botas de Mithril",      "def": 38, "spd": 24, "price":  520, "level": 20},
        {"name": "Botas do Cavaleiro",    "def": 45, "spd": 27, "price":  625, "level": 30},
        {"name": "Botas do Arcanjo",      "def": 52, "spd": 30, "price":  740, "level": 30},
    ],
}

ITEM_SHOP_STATS.update(CRAFTED_WEAPON_STATS)

ITEM_SHOP_CATEGORIES = {
    "Espadas":   {"prefix": "Espadas",   "count": 20, "price": 0, "desc": ""},
    "Machados":  {"prefix": "Machados",  "count": 10, "price": 0, "desc": ""},
    "Hammers":   {"prefix": "Hammer",    "count": 10, "price": 0, "desc": ""},
    "Escudos":   {"prefix": "Escudos",   "count": 10, "price": 0, "desc": ""},
    "Bows":      {"prefix": "Bow",       "count": 10, "price": 0, "desc": ""},
    "Crossbows": {"prefix": "Crossbows", "count": 10, "price": 0, "desc": ""},
    "Cajados":   {"prefix": "Cajados",   "count": 10, "price": 0, "desc": ""},
}
ARMOR_SHOP_CATEGORIES = {
    "Capacetes": {
        "count": 12,
        "folder": os.path.join("assets", "ui", "newItens", "capacete"),
        "files":  ["h.png"] + [f"h{i}.png" for i in range(1, 12)],
        "slot":   "helmet",
    },
    "Armaduras": {
        "count": 12,
        "folder": os.path.join("assets", "ui", "newItens", "armor"),
        "files":  ["a.png"] + [f"a{i}.png" for i in range(1, 12)],
        "slot":   "armor",
    },
    "Calças": {
        "count": 12,
        "folder": os.path.join("assets", "ui", "newItens", "calças"),
        "files":  ["c.png"] + [f"c{i}.png" for i in range(1, 12)],
        "slot":   "legs",
    },
    "Botas": {
        "count": 10,
        "folder": os.path.join("assets", "ui", "newItens", "botas"),
        "files":  [f"b{i}.png" for i in range(1, 11)],
        "slot":   "boots",
    },
}
ITEM_SHOP_TABS = ["ARMAS/ESCUDOS", "ARMADURAS", "UTILITÁRIOS", "VENDER"]
_ITEM_SHOP_SELL_TAB = 3   # índice da aba de venda

def _item_img_path(category: str, idx: int):
    """Returns (filepath, cache_key) for any item category (weapons or armor)."""
    if category == "Minérios":
        if 0 <= idx < len(MINING_ORE_DEFS):
            fname = MINING_ORE_DEFS[idx]["file"]
            return os.path.join(ASSET_DIR, "Teste", "recompensa", "minérios", fname), f"ore_{idx}"
        return None, None
    if category in ARMOR_SHOP_CATEGORIES:
        _acd  = ARMOR_SHOP_CATEGORIES[category]
        _fls  = _acd["files"]
        _fn   = _fls[idx] if idx < len(_fls) else None
        if _fn is None:
            return None, None
        return os.path.join(_acd["folder"], _fn), f"a_{category}_{_fn}"
    if category in CRAFTED_CATEGORIES:
        _ccd  = CRAFTED_CATEGORIES[category]
        _fls  = _ccd["files"]
        _fn   = _fls[idx] if idx < len(_fls) else None
        if _fn is None:
            return None, None
        return (os.path.join("assets", "ui", "itens_craft", _ccd["folder"], _fn),
                f"craft_{category}_{_fn}")
    _cdat = ITEM_SHOP_CATEGORIES.get(category, {})
    _fn   = "%s (%d).png" % (_cdat.get("prefix", category), idx + 1)
    return os.path.join("assets", "ui", "itens", _fn), _fn

# Multiplicadores permanentes (serão sobrescritos em reset_game)
CRIT_DMG_MULT = 2.0
EXPLOSION_SIZE_MULT = 1.0
REGEN_RATE = 0.0
DAMAGE_RES = 0.0
THORNS_PERCENT = 0.0
LIFESTEAL_PCT  = 0.0   # % do dano devolvido como HP (run upgrade)
GOLD_RUN_MULT  = 1.0   # multiplicador de ouro por run
XP_BONUS_PCT   = 0.0   # bônus percentual de XP por run
FIRE_DMG_MULT = 1.0
BURN_AURA_MULT = 1.0
HAS_CHAOS_BOLT = False
HAS_INFERNO = False

def roll_rarity(player_upgrades=None):
    r = random.random()
    
    # Trevo da Sorte: Aumenta chance de raridades altas
    if player_upgrades and "TREVO SORTE" in player_upgrades:
        r *= 0.7 

    acc = 0
    for name, data in RARITY.items():
        acc += data["chance"]
        if r <= acc:
            return name, data
    return "COMUM", RARITY["COMUM"]

upg_images = {}

# =========================================================
# TAMANHOS PADRÃO DE BOTÃO (seguem o rótulo mais largo do jogo)
# BTN_W é largo o suficiente para "CONFIGURAÇÕES" + ícone + pontas ornamentais + margem
# =========================================================
BTN_W    = 540   # largura padrão de todos os botões primários
BTN_H    = 58    # altura padrão
BTN_SM_W = 360   # botões secundários (VOLTAR, ações)
BTN_SM_H = 58    # mesma altura para padronizar

# =========================================================
# CLASSES AUXILIARES
# =========================================================
class Button:
    def __init__(self, x_ratio, y_ratio, w, h, text, font, color=(28, 22, 18), subtext="", hover_color=(50, 38, 26), locked=False, lock_req=""):
        self.x_ratio, self.y_ratio = x_ratio, y_ratio
        self.w, self.h = w, h
        self.text, self.font, self.color = text, font, color
        self.subtext = subtext
        self.hover_color, self.is_hovered = hover_color, False
        self.was_hovered = False
        self.rect = pygame.Rect(0, 0, w, h)
        self.locked = locked
        self.lock_req = lock_req
        self.icon = ""
        self.sprite_idx = -1   # índice no menu_btn_sprites (-1 = não usa sprite)
        self.update_rect()

    def update_rect(self):
        cx, cy = int(SCREEN_W * self.x_ratio), int(SCREEN_H * self.y_ratio)
        self.rect.center = (cx, cy)

    def draw(self, screen, offset_x=0, offset_y=0):
        now_ms  = pygame.time.get_ticks()
        pulse   = 0.5 + 0.5 * math.sin(now_ms / 380.0)

        # ── cores procedurais (fallback) ───────────────────────────────────
        if self.locked:
            col        = (22, 18, 14)
            border_col = (90, 55, 40)
        elif self.is_hovered:
            col        = self.hover_color
            border_col = (
                min(255, 170 + int(40 * pulse)),
                min(255, 120 + int(30 * pulse)),
                min(255, 40  + int(15 * pulse)),
            )
        else:
            col        = self.color
            border_col = UI_THEME["iron"]

        # ── rect de desenho (hover infla ligeiramente) ──────────────────────
        scale     = 1.02 if (self.is_hovered and not self.locked) else 1.0
        draw_rect = self.rect.inflate(
            int(self.rect.width  * (scale - 1.0)),
            int(self.rect.height * (scale - 1.0))
        )
        draw_rect.center = self.rect.center
        if offset_x or offset_y:
            draw_rect.x += int(offset_x)
            draw_rect.y += int(offset_y)

        is_pressed = self.is_hovered and pygame.mouse.get_pressed(num_buttons=3)[0] and not self.locked
        if is_pressed:
            draw_rect.y += 2

        # ── sprite: barra ornamentada medieval ─────────────────────────────
        using_sprite = self.sprite_idx >= 0 and bool(menu_btn_sprites)
        if using_sprite:
            sprite_list = menu_btn_sprites
            idx = min(self.sprite_idx, len(sprite_list) - 1)
            spr = sprite_list[idx]
            if spr.get_size() != (draw_rect.width, draw_rect.height):
                spr = pygame.transform.smoothscale(spr, (draw_rect.width, draw_rect.height))
            if self.locked:
                spr = spr.copy()
                dark = pygame.Surface(spr.get_size(), pygame.SRCALPHA)
                dark.fill((0, 0, 0, 140))
                spr.blit(dark, (0, 0))

            screen.blit(spr, draw_rect.topleft)
        else:
            # ── fallback procedural ────────────────────────────────────────
            if self.is_hovered and not self.locked:
                glow = pygame.Surface((draw_rect.width + 20, draw_rect.height + 20), pygame.SRCALPHA)
                glow.fill((200, 130, 30, int(30 + 22 * pulse)))
                screen.blit(glow, (draw_rect.x - 10, draw_rect.y - 10))
            pygame.draw.rect(screen, col, draw_rect, border_radius=4)
            pygame.draw.rect(screen, border_col, draw_rect, 2, border_radius=4)
            inner = draw_rect.inflate(-6, -6)
            pygame.draw.rect(screen, (border_col[0]//2, border_col[1]//2, border_col[2]//2),
                             inner, 1, border_radius=2)
            pygame.draw.line(screen, (200, 185, 155),
                             (draw_rect.x + 5, draw_rect.y + 4),
                             (draw_rect.right - 5, draw_rect.y + 4), 1)

        # ── texto + ícone: sempre renderizados por cima ────────────────────
        alpha       = 90 if self.locked else 255
        cx, cy      = draw_rect.centerx, draw_rect.centery
        has_subtext = bool(self.subtext) or self.locked
        text_y      = cy - (9 if has_subtext else 0)

        if using_sprite:
            # Texto sobre a barra ornamentada
            if self.is_hovered and not self.locked:
                # Sombra quente deslocada → profundidade medieval
                shadow_col = (40, 20, 5)
                txt_col    = (255, 225, 120)   # ouro brilhante
            elif self.locked:
                txt_col    = (130, 100, 80)
                shadow_col = (20, 10, 5)
            else:
                txt_col    = (215, 195, 155)   # pergaminho envelhecido
                shadow_col = (25, 12, 4)

            txt = self.font.render(self.text, True, txt_col)
            txt.set_alpha(alpha)
            # Sombra 2 px abaixo-direita
            shadow = self.font.render(self.text, True, shadow_col)
            shadow.set_alpha(min(alpha, 180))

            has_icon = isinstance(self.icon, pygame.Surface)
            icon_gap  = 28 if has_icon else 0
            txt_rect  = txt.get_rect(center=(cx + icon_gap // 2, text_y))

            screen.blit(shadow, (txt_rect.x + 2, txt_rect.y + 2))
            screen.blit(txt,     txt_rect)

            # Ícone à esquerda do texto
            if has_icon:
                icon_cx = txt_rect.left - 16
                icon_surf = pygame.transform.smoothscale(self.icon, (20, 20))
                icon_surf.set_alpha(alpha)
                screen.blit(icon_surf, icon_surf.get_rect(center=(icon_cx, text_y)))

        else:
            # Texto procedural padrão
            txt_color = UI_THEME["parchment"] if (self.is_hovered and not self.locked) else (210, 200, 180)
            txt = self.font.render(self.text, True, txt_color)
            txt.set_alpha(alpha)
            has_icon_offset = bool(self.icon)
            text_center_x   = cx + (14 if has_icon_offset else 0)
            screen.blit(txt, txt.get_rect(center=(text_center_x, text_y)))

            if self.icon:
                icon_rect = pygame.Rect(draw_rect.x + 10, cy - 13, 26, 26)
                pygame.draw.rect(screen, (18, 14, 10), icon_rect, border_radius=3)
                pygame.draw.rect(screen, UI_THEME["iron"], icon_rect, 1, border_radius=3)
                if isinstance(self.icon, pygame.Surface):
                    screen.blit(self.icon, self.icon.get_rect(center=icon_rect.center))
                else:
                    icon_surf = load_title_font(17, bold=True).render(str(self.icon), True, UI_THEME["faded_gold"])
                    screen.blit(icon_surf, icon_surf.get_rect(center=icon_rect.center))

        # ── subtext / bloqueado ────────────────────────────────────────────
        if self.subtext and not self.locked:
            sub = load_body_font(14).render(self.subtext, True, (160, 140, 110))
            sub.set_alpha(200)
            screen.blit(sub, sub.get_rect(center=(cx, cy + 11)))

        if self.locked:
            lock_txt = load_title_font(15, bold=True).render("BLOQUEADO", True, (180, 90, 70))
            screen.blit(lock_txt, lock_txt.get_rect(center=(cx, cy + 11)))
            if self.is_hovered and self.lock_req:
                mx, my = pygame.mouse.get_pos()
                tt = load_body_font(15).render(self.lock_req, True, (210, 185, 165))
                tip_rect = pygame.Rect(mx + 14, my - 10, tt.get_width() + 18, tt.get_height() + 12)
                pygame.draw.rect(screen, (20, 10, 8), tip_rect, border_radius=3)
                pygame.draw.rect(screen, (110, 55, 40), tip_rect, 1, border_radius=3)
                screen.blit(tt, (tip_rect.x + 9, tip_rect.y + 6))
        elif self.subtext:
            stxt = load_body_font(15).render(self.subtext, True, UI_THEME["mist"])
            screen.blit(stxt, stxt.get_rect(center=(draw_rect.centerx, draw_rect.centery + 14)))

    def check_hover(self, m_pos, hover_sound=None):
        self.is_hovered = self.rect.collidepoint(m_pos)
        if self.is_hovered and not self.was_hovered:
            if hover_sound and not self.locked: hover_sound.play()
        self.was_hovered = self.is_hovered
        return self.is_hovered and not self.locked

class AssetLoader:
    def __init__(self):
        if not os.path.exists(ASSET_DIR):
            print(f"[ASSETS] Criando pasta: {ASSET_DIR}")
            os.makedirs(ASSET_DIR)
        else:
            print(f"[ASSETS] Pasta encontrada: {os.path.abspath(ASSET_DIR)}")
        self._cache: dict[str, str] = {}
        self._build_cache()

    def _build_cache(self):
        """Varre ASSET_DIR recursivamente e mapeia stem → caminho completo.
        Permite mover arquivos para sub-pastas sem alterar os load_image() calls."""
        self._cache = {}
        audio_exts = {".mp3", ".wav", ".ogg"}
        img_exts    = {".png", ".jpg", ".jpeg", ".gif"}
        for root, dirs, files in os.walk(ASSET_DIR):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for fname in files:
                ext = os.path.splitext(fname)[1].lower()
                if ext not in img_exts and ext not in audio_exts:
                    continue
                stem = os.path.splitext(fname)[0]
                full = os.path.join(root, fname)
                # Caminho relativo ao ASSET_DIR (para chamadas explícitas tipo "ui/loading")
                rel  = os.path.relpath(full, ASSET_DIR).replace("\\", "/")
                rel_no_ext = os.path.splitext(rel)[0]
                # Registra tanto o stem simples quanto o caminho relativo
                if stem not in self._cache:
                    self._cache[stem] = full
                if rel_no_ext not in self._cache:
                    self._cache[rel_no_ext] = full
        print(f"[ASSETS] Cache construído: {len(self._cache)} entradas")

    def _resolve(self, name: str) -> str | None:
        """Retorna o caminho completo para `name` (com ou sem extensão).
        Prioridade: caminho explícito → cache por stem/rel."""
        for ext in [".png", ".jpg", ".jpeg", ".gif", ".mp3", ".wav", ".ogg", ""]:
            p = os.path.join(ASSET_DIR, name + ext)
            if os.path.exists(p):
                return p
        # Fallback: procura no cache pelo stem ou caminho relativo
        return self._cache.get(name) or self._cache.get(name.split("/")[-1])

    def load_image(self, name, size=None, fallback_colors=((200,200,200), (100,100,100))):
        path = self._resolve(name)
        if path:
            try:
                img = pygame.image.load(path).convert_alpha()
                if size:
                    img = pygame.transform.smoothscale(img, size)
                return img
            except Exception as e:
                print(f"[ASSETS] Erro ao carregar {name}: {e}")

        print(f"[ASSETS] Não encontrado: {name} — usando fallback")
        w, h = size if size else (64, 64)
        s = pygame.Surface((w, h), pygame.SRCALPHA)
        if len(fallback_colors[0]) == 4:
            s.fill(fallback_colors[0])
        else:
            pygame.draw.rect(s, fallback_colors[0], (0, 0, w, h), border_radius=min(w,h)//4)
        pygame.draw.rect(s, fallback_colors[1], (0, 0, w, h), width=2, border_radius=min(w,h)//4)
        return s

    def load_animation(self, base_name, count, size, fallback_colors=((200,200,200), (100,100,100))):
        frames = []
        # Checa se a sequência existe (nome_0, nome_1…)
        sequence_found = bool(self._resolve(f"{base_name}_0"))
        if sequence_found:
            for i in range(count):
                frames.append(self.load_image(f"{base_name}_{i}", size, fallback_colors))
        else:
            img = self.load_image(base_name, size, fallback_colors)
            for _ in range(count):
                frames.append(img.copy())
        return frames

    def load_spritesheet(self, path_rel, frame_w, frame_h, frame_count, output_size=None, colorkey=None, frame_indices=None):
        """Carrega frames de um spritesheet único.

        - PNG com alpha nativo: usa convert_alpha(), sem colorkey.
        - PNG/JPG com fundo colorido: passa colorkey=(R,G,B) para remoção por cor exata.
        O número de colunas é detectado automaticamente pela largura ÷ frame_w.
        """
        path = self._resolve(path_rel)
        if not path:
            print(f"[ASSETS] Spritesheet não encontrado: {path_rel} - usando fallback")
            return None

        try:
            raw = pygame.image.load(path)
            # Detecta se a imagem tem canal alpha real (PNG com transparência)
            has_alpha = raw.get_bitsize() == 32 and raw.get_masks()[3] != 0
            if has_alpha:
                sheet = raw.convert_alpha()
            else:
                sheet = raw.convert()
                if colorkey is not None:
                    sheet.set_colorkey(colorkey)

            cols = max(1, sheet.get_width() // frame_w)
            indices = frame_indices if frame_indices is not None else list(range(frame_count))
            frames = []
            for i in indices:
                col = i % cols
                row = i // cols
                frame = sheet.subsurface((col * frame_w, row * frame_h, frame_w, frame_h)).copy()
                if output_size:
                    frame = pygame.transform.scale(frame, output_size)
                    if not has_alpha and colorkey is not None:
                        frame.set_colorkey(colorkey)  # scale cria nova Surface; reaplica colorkey
                frames.append(frame)
            mode = "alpha" if has_alpha else f"colorkey={colorkey}"
            print(f"[ASSETS] Spritesheet OK: {path_rel} ({frame_count} frames, {cols} col(s), {mode})")
            return frames
        except Exception as e:
            print(f"[ASSETS] Erro ao carregar spritesheet {path_rel}: {e}")
            return None

    def load_sound(self, name, volume=None):
        path = self._resolve(name)
        if path:
            try:
                snd = pygame.mixer.Sound(path)
                snd.set_volume(volume if volume is not None else SFX_VOLUME)
                return snd
            except Exception as e:
                print(f"[ASSETS] Erro som {name}: {e}")
        return None

    def play_music(self, name, loop=-1):
        path = self._resolve(name)
        if path:
            try:
                pygame.mixer.music.load(path)
                pygame.mixer.music.set_volume(MUSIC_VOLUME)
                pygame.mixer.music.play(loop)
            except Exception as e:
                print(f"[ASSETS] Erro música {name}: {e}")

# =========================================================
# ENTIDADES
# =========================================================

class Particle(pygame.sprite.Sprite):
    _pool = None  # preenchido pelo ParticlePool ao reciclar

    def __init__(self, pos, color, size, speed, life):
        super().__init__()
        self._reset(pos, color, size, speed, life)

    def _reset(self, pos, color, size, speed, life):
        self.color   = color
        self.original_size = size
        self.size    = size
        self.life    = life
        self.max_life = life
        sz = int(size)
        if not hasattr(self, "image") or self.image is None or self.image.get_size() != (sz, sz):
            self.image = pygame.Surface((sz, sz))
        self.image.fill(color)
        if not hasattr(self, "rect") or self.rect is None:
            self.rect = self.image.get_rect(center=pos)
        else:
            self.rect.center = pos
        if not hasattr(self, "pos") or self.pos is None:
            self.pos = pygame.Vector2(pos)
            self.vel = pygame.Vector2()
        else:
            self.pos.update(pos)
        angle = random.uniform(0, 6.2832)   # radianos diretamente
        speed_var = random.uniform(speed * 0.5, speed * 1.5)
        self.vel.x = math.cos(angle) * speed_var
        self.vel.y = math.sin(angle) * speed_var

    def update(self, dt, cam):
        self.pos.x += self.vel.x * dt
        self.pos.y += self.vel.y * dt
        self.vel.x *= 0.92
        self.vel.y *= 0.92
        self.life -= dt
        if self.life <= 0:
            if self._pool is not None:
                self._pool.release(self)
            else:
                self.kill()
            return
        if int(self.life * 10) != int((self.life + dt) * 10):
            ratio = self.life / self.max_life
            new_size = max(1, int(self.original_size * ratio))
            if new_size != self.size:
                self.size = new_size
                self.image = pygame.Surface((new_size, new_size))
                self.image.fill(self.color)
        self.rect.centerx = int(self.pos.x + cam.x)
        self.rect.centery = int(self.pos.y + cam.y)

class DamageText(pygame.sprite.Sprite):
    def __init__(self, pos, amount, is_crit=False, color=(255, 255, 255)):
        super().__init__()
        size = 26 if is_crit else 16
        final_color = (255, 215, 0) if is_crit else color
        if isinstance(amount, float):
            _fmt = f"{amount:.2f}".rstrip('0').rstrip('.')
        elif isinstance(amount, int):
            _fmt = str(amount)
        else:
            _fmt = str(amount)
        text_content = f"{_fmt}!" if is_crit else _fmt

        font = load_number_font(size, bold=True)
        self.image = font.render(text_content, True, final_color)

        if is_crit:
            base_surf = pygame.Surface((self.image.get_width() + 4, self.image.get_height() + 4), pygame.SRCALPHA)
            outline = font.render(text_content, True, (0, 0, 0))
            base_surf.blit(outline, (0, 0)); base_surf.blit(outline, (2, 0)); base_surf.blit(outline, (0, 2)); base_surf.blit(outline, (2, 2))
            base_surf.blit(self.image, (1, 1))
            self.image = base_surf

        self.rect = self.image.get_rect()
        offset_x = random.randint(-20, 20)
        offset_y = random.randint(-20, 20)
        self.world_pos = pygame.Vector2(pos.x + offset_x, pos.y + offset_y)
        self.vel_y = -150 if is_crit else -80
        self.max_timer = 0.8 if is_crit else 0.6
        self.timer = self.max_timer
        self.alpha = 255

    def update(self, dt, cam):
        self.world_pos.y += self.vel_y * dt
        self.timer -= dt
        if self.timer <= 0:
            self.kill()
        else:
            self.alpha = int((self.timer / self.max_timer) * 255)
        self.rect.center = self.world_pos + cam

class Puddle(pygame.sprite.Sprite):
    def __init__(self, pos, loader):
        super().__init__()
        self.image = loader.load_image("puddle_black", (80, 80), ((20, 0, 20), (0, 0, 0)))
        self.rect = self.image.get_rect(center=pos)
        self.pos = pygame.Vector2(pos)
        self.timer = 4.0 
        self.tick_timer = 0.0
        self.hitbox = self.rect.inflate(-20, -20)

    def update(self, dt, cam):
        self.timer -= dt
        if self.timer <= 0:
            self.kill()
        self.rect.center = self.pos + cam
        self.hitbox.center = self.pos

class BloodRainDrop(pygame.sprite.Sprite):
    """Gota de sangue que cai do céu — ataque em área do Esqueleto.

    Fases: queda visual (gota elongada desce), impacto (hitbox ativa + anel),
    splash (anel se expande e some). Cada gota tem _fall_t aleatório para criar
    dispersão temporal natural, imitando chuva real.
    """

    _COLORS = [(200, 0, 0), (180, 10, 10), (220, 20, 20), (150, 0, 0), (255, 30, 30)]

    def __init__(self, world_pos, dmg):
        super().__init__()
        self.pos      = pygame.Vector2(world_pos)
        self.dmg      = dmg
        self.is_melee = True
        self.hit_enemies = set()

        self._color   = random.choice(self._COLORS)
        self._w       = random.randint(4, 9)
        self._h_max   = random.randint(22, 42)

        # _fall_t varia → chegada dispersa no tempo (efeito de chuva)
        self._fall_t   = random.uniform(0.10, 0.55)
        self._impact_t = 0.16
        self._splash_t = 0.30

        self._timer = 0.0
        self._phase = 0   # 0=queda  1=impacto  2=splash

        # Superfície pré-renderizada da gota (gradiente vermelho brilhante→escuro)
        self._drop_surf = self._bake_drop()

        # Cor do anel de impacto (um tom mais brilhante)
        self._ring_col  = (min(255, self._color[0] + 50), 25, 25)

        self.image  = pygame.Surface((self._w, 1), pygame.SRCALPHA)
        self.rect   = self.image.get_rect()
        self.hitbox = pygame.Rect(0, 0, 0, 0)

    def _bake_drop(self):
        """Gota elongada com gradiente: topo brilhante, base escura."""
        w, h = self._w, self._h_max
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        r0 = min(255, self._color[0] + 50);  g0, b0 = 25, 25
        r1 = max(80,  self._color[0] - 60);  g1, b1 = 0,  0
        for y in range(h):
            t = y / h
            col = (int(r0 + (r1-r0)*t), int(g0 + (g1-g0)*t), int(b0 + (b1-b0)*t), 255)
            pygame.draw.line(surf, col, (0, y), (w-1, y))
        return surf

    def _make_ring(self, radius, alpha):
        """Anel de sangue para as fases de impacto e splash."""
        r    = max(1, radius)
        size = r * 2 + 4
        surf = pygame.Surface((size, size), pygame.SRCALPHA)
        thickness = max(1, r // 4)
        pygame.draw.circle(surf, (*self._ring_col, alpha), (r + 2, r + 2), r, thickness)
        return surf

    def update(self, dt, cam):
        self._timer += dt
        cx = int(self.pos.x + cam.x)
        cy = int(self.pos.y + cam.y)

        if self._phase == 0:   # ── queda ─────────────────────────────────────
            ratio   = min(1.0, self._timer / self._fall_t)
            cur_h   = max(1, int(self._h_max * ratio))
            # Deslocamento Y visual: começa acima e desce até o ponto de impacto
            y_off   = int(-self._h_max * (1.0 - ratio) * 0.9)
            # Recorta a parte superior da gota pré-renderizada
            self.image = self._drop_surf.subsurface(pygame.Rect(0, 0, self._w, cur_h))
            self.rect  = self.image.get_rect(center=(cx, cy + y_off))
            self.hitbox = pygame.Rect(0, 0, 0, 0)
            if self._timer >= self._fall_t:
                self._phase = 1
                self._timer = 0.0

        elif self._phase == 1:  # ── impacto (hitbox ativa) ───────────────────
            r = self._w + 5
            self.image  = self._make_ring(r, 230)
            self.rect   = self.image.get_rect(center=(cx, cy))
            # Hitbox em screen-space (consistente com enemy.rect)
            self.hitbox = pygame.Rect(cx - r, cy - r, r * 2, r * 2)
            if self._timer >= self._impact_t:
                self._phase = 2
                self._timer = 0.0
                self.hitbox = pygame.Rect(0, 0, 0, 0)

        elif self._phase == 2:  # ── splash visual (sem dano) ──────────────────
            ratio  = min(1.0, self._timer / self._splash_t)
            r      = int((self._w + 5) * (1 + ratio * 4.5))
            alpha  = int(220 * (1.0 - ratio))
            self.image  = self._make_ring(r, alpha)
            self.rect   = self.image.get_rect(center=(cx, cy))
            self.hitbox = pygame.Rect(0, 0, 0, 0)
            if self._timer >= self._splash_t:
                self.kill()


def build_character_dependencies():
    """Cria o pacote de dependências enviado ao módulo characters.

    A função existe para deixar a integração explícita e didática: tudo o que o
    sistema de personagens usa vem daqui, de forma centralizada.
    """

    def _create_projectile(pos, vel, dmg, frames):
        """Cria projétil usando pool se disponível, senão cria direto"""
        if projectile_pool is not None:
            return projectile_pool.spawn(
                pos, vel, dmg, frames,
                pierce=PROJ_PIERCE,
                ricochet=PROJ_RICOCHET,
                screen_size_getter=lambda: (SCREEN_W, SCREEN_H),
            )
        else:
            return CoreProjectile(
                pos, vel, dmg, frames,
                pierce=PROJ_PIERCE,
                ricochet=PROJ_RICOCHET,
                screen_size_getter=lambda: (SCREEN_W, SCREEN_H),
            )

    def _create_melee_slash(player, target_dir, dmg, frames):
        """Cria golpe melee usando pool se disponível, senão cria direto"""
        if melee_slash_pool is not None:
            return melee_slash_pool.spawn(player, target_dir, dmg, frames)
        else:
            return CoreMeleeSlash(player, target_dir, dmg, frames)

    return CharacterDependencies(
        char_data_map=CHAR_DATA,
        control_reader=is_control_pressed,
        particle_cls=Particle,
        damage_text_cls=DamageText,
        projectile_cls=_create_projectile,
        melee_slash_cls=_create_melee_slash,
        gem_cls=Gem,
        dash_speed=DASH_SPEED,
        dash_duration=DASH_DURATION,
        dash_cooldown=DASH_COOLDOWN,
        ultimate_max_charge=ULTIMATE_MAX_CHARGE,
        screen_size_getter=lambda: (SCREEN_W, SCREEN_H),
    )


def build_character_combat_context(dmg_mult_fury=1.0):
    """Monta o contexto dinâmico usado pelas skills durante a run.

    Diferente das dependências estáticas, este contexto reflete o estado atual
    da partida: grupos de sprites, dano modificado por upgrades, assets ativos
    e efeitos especiais como a bazuca.
    """

    return CharacterCombatContext(
        enemies=enemies,
        projectiles=projectiles,
        particles=particles,
        damage_texts=damage_texts,
        gems=gems,
        projectile_frames_raw=projectile_frames_raw,
        slash_frames_raw=slash_frames_raw,
        loader=loader,
        projectile_speed=PROJECTILE_SPEED,
        projectile_damage=PROJECTILE_DMG,
        projectile_count=PROJ_COUNT,
        fury_multiplier=dmg_mult_fury,
        bazooka_active=has_bazuca,
        blood_rain_cls=BloodRainDrop,
    )


def create_enemy(kind, pos, diff_mults, time_scale=1.0, boss_tier=1, is_elite=False):
    """Fábrica de inimigos que usa a implementação modularizada de enemies.py."""
    return ModularEnemy(
        kind=kind,
        pos=pos,
        loader=loader,
        diff_mults=diff_mults,
        screen_size_getter=lambda: (SCREEN_W, SCREEN_H),
        time_scale=time_scale,
        boss_tier=boss_tier,
        is_elite=is_elite,
        boss_max_hp=BOSS_MAX_HP,
    )


def create_drop(pos, kind):
    """Fábrica de drops para centralizar o uso do módulo drops.py."""
    return ModularDrop(pos, kind, loader)

class Obstacle(pygame.sprite.Sprite):
    def __init__(self, pos, loader, kind):
        super().__init__()
        sizes = [(90, 90), (70, 90), (100, 100), (100, 90)]
        self.image = loader.load_image(f"obstacle_{kind}", sizes[kind], ((80,80,80),(40,40,40)))
        self.rect, self.pos = self.image.get_rect(), pos
        self.hitbox = pygame.Rect(0, 0, sizes[kind][0]-20, sizes[kind][1]-20)
    def update(self, dt, cam):
        self.rect.center = self.pos + cam
        self.hitbox.center = self.pos

class DoomSeal(pygame.sprite.Sprite):
    """Selo de invocação do Agis — doom_agis.png.
    Aparece perto do herói, anima até o fim e sinaliza o spawn do boss."""

    FRAME_W = 512
    FRAME_H = 512
    FRAME_COUNT = 36          # 18432 / 512 = 36
    FRAME_SPEED = 0.075       # segundos por frame (~2.7 s de animação total)
    DISPLAY_SIZE = (280, 280)

    def __init__(self, pos, loader):
        super().__init__()
        frames_raw = loader.load_spritesheet(
            "sprite/monster/boss/doom_agis",
            self.FRAME_W, self.FRAME_H,
            self.FRAME_COUNT,
            self.DISPLAY_SIZE,
        )
        if frames_raw:
            self.frames = frames_raw
        else:
            # Fallback: quadrado roxo pulsante
            s = pygame.Surface(self.DISPLAY_SIZE, pygame.SRCALPHA)
            pygame.draw.ellipse(s, (120, 0, 180, 180), s.get_rect())
            self.frames = [s]

        self.frame_idx  = 0
        self.timer      = 0.0
        self.done       = False  # True quando a animação termina → spawna Agis
        self.pos        = pygame.Vector2(pos)
        self.image      = self.frames[0]
        self.rect       = self.image.get_rect()

    def update(self, dt, cam):
        if self.done:
            return
        self.timer += dt
        if self.timer >= self.FRAME_SPEED:
            self.timer = 0.0
            self.frame_idx += 1
            if self.frame_idx >= len(self.frames):
                self.frame_idx = len(self.frames) - 1
                self.done = True
            self.image = self.frames[self.frame_idx]
        self.rect.center = self.pos + cam


class AgisProjectile(pygame.sprite.Sprite):
    """Projétil de longa distância do boss Agis — agis_att.png (3 frames, 64×32)."""

    FRAME_W    = 64
    FRAME_H    = 32
    FRAME_COUNT = 3
    FRAME_SPEED = 0.09          # s/frame — animação da orbe
    DISPLAY_SIZE = (100, 50)    # tamanho de exibição do projétil
    SPEED      = 230.0          # px/s

    def __init__(self, pos, direction, dmg, loader):
        super().__init__()
        frames_raw = loader.load_spritesheet(
            "sprite/monster/boss/agis_att",
            self.FRAME_W, self.FRAME_H,
            self.FRAME_COUNT,
            self.DISPLAY_SIZE,
        )
        if frames_raw:
            self.frames = frames_raw
        else:
            s = pygame.Surface(self.DISPLAY_SIZE, pygame.SRCALPHA)
            pygame.draw.ellipse(s, (180, 0, 255, 220), s.get_rect())
            self.frames = [s]

        # Rotaciona frames na direção de disparo
        angle = -math.degrees(math.atan2(direction.y, direction.x))
        self.frames = [pygame.transform.rotate(f, angle) for f in self.frames]

        self.frame_idx = 0
        self.timer     = 0.0
        self.pos       = pygame.Vector2(pos)
        self.vel       = direction * self.SPEED
        self.dmg       = dmg
        self.image     = self.frames[0]
        self.rect      = self.image.get_rect()

    def update(self, dt, cam, screen_w, screen_h):
        self.pos += self.vel * dt
        self.timer += dt
        if self.timer >= self.FRAME_SPEED:
            self.timer = 0.0
            self.frame_idx = (self.frame_idx + 1) % len(self.frames)
            self.image = self.frames[self.frame_idx]
        self.rect.center = self.pos + cam
        # Remove quando sair de tela com margem
        if not pygame.Rect(-800, -800, screen_w + 1600, screen_h + 1600).collidepoint(self.rect.center):
            self.kill()


class Gem(pygame.sprite.Sprite):
    def __init__(self, pos, loader):
        super().__init__()
        self.image = loader.load_image("gem", (24, 24), ((0,255,255), (255,255,255)))
        self.rect, self.pos = self.image.get_rect(), pos
        self.fpos = pygame.Vector2(pos)
        self.magnetic = False

    def update(self, dt, cam, player_pos=None):
        if self.magnetic and player_pos:
            d = player_pos - self.fpos
            if d.length_squared() > 0:
                move = d.normalize() * 900 * dt
                self.fpos += move
        
        self.rect.center = self.fpos + cam

# =========================================================
# FUNÇÕES AUXILIARES DO JOGO
# =========================================================

# Referências globais que serão preenchidas em main()
ecs_world = None
player = None
enemies = None
projectiles = None
enemy_projectiles = None
gems = None
drops = None
particles = None
obstacles = None
puddles = None
damage_texts = None
doom_seals = None
death_anims = None
loader = None
SFX = {}
snd_hover = None
snd_click = None
upg_images = {}
menu_char_anims = []
menu_idle_anims = []
screen = None
obstacle_grid_index = None
enemy_batch_index = None
last_obstacle_count = -1

# Variáveis de estado de jogo (inicializadas em reset_game)
kills = 0
game_time = 0.0
level = 1
xp = 0
shot_t = 0.0
aura_t = 0.0
aura_anim_timer = 0.0
aura_frame_idx = 0
orb_rot_angle = 0.0
spawn_t = 0.0
bosses_spawned = 0
session_boss_kills = 0
session_max_level = 1
triggered_hordes = set()
# Fila de spawn da horda (anti-spike de CPU)
pending_horde_queue: list = []
# Obstáculos graduais
obstacle_spawn_t        = 0.0
obstacle_spawn_interval = 18.0
obstacle_total_placed   = 0
OBSTACLE_MAX_GRADUAL    = 28
player_upgrades = []
has_bazuca = False
has_buraco_negro = False
has_serras = False
has_tesla = False
has_ceifador = False
has_berserk = False
chest_loot = []
chest_ui_timer = 0.0
new_unlocks_this_session = []
selected_difficulty = "MÉDIO"
current_hardcore_stage = 1
show_stage_victory = False
show_reward_dialog   = False   # diálogo "Entrar na Sala de Recompensas?" após Agis
reward_room_player_pos = None  # posição do jogador na sala de recompensa (screen coords)
reward_room_anim_t   = 0.0
reward_room_anim_idx = 0
_reward_room_bg      = None    # cache da imagem de fundo da sala de recompensa
_mining_system: "MiningSystem | None" = None   # sistema de mineração da sala
_spawn_diff = None  # set by reset_game() before use
selected_pact = "NENHUM"
selected_bg = "dungeon"
current_bg_name = "bg_dungeon"
up_options = []
up_keys = []
up_rarities = []
active_explosions = []
menu_particles = []
UI_TRANSITION_DURATION = 0.18
MENU_ENTER_DURATION = 0.45
MENU_EXIT_DURATION = 0.28

# Assets de jogo (preenchidos em load_all_assets)
ground_img = None
menu_bg_img = None
cursor_img = None       # cursor personalizado (seta.png)
forest_deco_manager = None
dungeon_deco_manager = None
volcano_deco_manager = None
moon_deco_manager = None
menu_btn_sprites = []        # frames normais do spritesheet menu.png
menu_btn_sprites_hover = []  # frames com brilho para hover
skill_card_sprites = []      # 3 cartas de seleção de skill (skills.png)
skill_card_sprites_hover = []
config_title_spr  = None     # barra grande de config.png (título)
config_tag_spr    = None     # barra pequena de config.png (subtítulo/seção)
menu_logo_img = None         # logo do jogo (logouwh.png)
char_panel_imgs = {}         # painéis da tela de seleção: {char_id: Surface}
char_select_panel_img  = None  # selecionarpersonagem.png já escalada
char_select_panel_meta = {}    # {panel_w, panel_h, panel_ox, panel_oy, panel_scale}
char_select_title_frame = None # faixa ornamental do topo do painelguerreiro.png
select_title_img = None      # imagem do título "Selecionar Herói"
diff_screen_imgs = {}        # sprites da tela de seleção de dificuldade
aura_frames = []
explosion_frames_raw = []
projectile_frames_raw = []
slash_frames_raw = []
orb_img = None
tornado_img = None
_steam_btn_surf = None
_site_btn_surf  = None

# ── Constantes de vetor reutilizáveis (evita alloc em hot-paths) ─────────────
_VEC2_RIGHT = pygame.Vector2(1, 0)

# ── Cache de rotações pré-renderizadas do tornado (72 frames × 5°) ────────────
_TORNADO_STEPS     = 72
_tornado_rot_cache: list = []          # preenchido em _build_tornado_cache()

# ── Vetores pré-alocados para posições dos orbs (max 8 orbs) ─────────────────
_orb_vecs = [pygame.Vector2(0, 0) for _ in range(8)]

# ── Pool de partículas ────────────────────────────────────────────────────────
_particle_pool = ParticlePool(max_free=800)


def _build_tornado_cache():
    """Pré-renderiza 72 rotações do tornado_img (chamado após load)."""
    global _tornado_rot_cache
    if tornado_img is None:
        _tornado_rot_cache = []
        return
    step = 360.0 / _TORNADO_STEPS
    _tornado_rot_cache = [
        pygame.transform.rotate(tornado_img, i * step)
        for i in range(_TORNADO_STEPS)
    ]


class ExplosionAnimation:
    # Cache de frames escalados para evitar smoothscale repetido por frame
    _frame_cache: dict = {}

    def __init__(self, pos, radius, raw_frames, frame_duration_ms=70):
        self.pos = pygame.Vector2(pos)
        self.radius = int(radius)
        self.frame_duration_ms = frame_duration_ms
        self.start_ms = pygame.time.get_ticks()
        self.frame_idx = 0

        # O raio lógico (hitbox) pode ser grande, mas o visual é limitado para
        # não sobrecarregar a GPU e manter a legibilidade da tela.
        VISUAL_CAP = 220          # px — máximo do raio visual
        visual_r   = min(self.radius, VISUAL_CAP)
        size       = (visual_r * 2, visual_r * 2)

        cache_key = (id(raw_frames), size)
        if cache_key not in ExplosionAnimation._frame_cache:
            ExplosionAnimation._frame_cache[cache_key] = [
                pygame.transform.smoothscale(f, size) for f in raw_frames
            ]
        self.frames = ExplosionAnimation._frame_cache[cache_key]
        self.image  = self.frames[0]
        self.rect   = self.image.get_rect(center=self.pos)

    def update(self, now_ms):
        elapsed = max(0, now_ms - self.start_ms)
        self.frame_idx = elapsed // self.frame_duration_ms
        if self.frame_idx >= len(self.frames):
            return False
        self.image = self.frames[self.frame_idx]
        self.rect = self.image.get_rect(center=self.pos)
        return True

    def draw(self, screen, cam):
        draw_rect = self.image.get_rect(center=self.pos + cam)
        screen.blit(self.image, draw_rect, special_flags=pygame.BLEND_RGBA_ADD)


def load_explosion_frames(loader, size=(128, 128)):
    # Tenta carregar do spritesheet primeiro (sprite/explosion.png, 9 frames 32x32)
    sheet_frames = loader.load_spritesheet("sprite/explosion", 32, 32, 9, size)
    if sheet_frames:
        return sheet_frames

    # Fallback: sequência explosion_0.png … explosion_5.png
    frames = []
    for i in range(6):
        img_name = f"explosion_{i}"
        img_path = os.path.join(ASSET_DIR, f"{img_name}.png")
        if os.path.exists(img_path):
            frames.append(loader.load_image(img_name, size, ((255, 150, 0, 200), (255, 50, 0, 150))))
    if len(frames) == 6:
        return frames

    return loader.load_animation("explosion", 6, size, fallback_colors=((255, 150, 0, 200), (255, 50, 0, 150)))


def projectile_enemy_collision(projectile, enemy):
    return core_projectile_enemy_collision(projectile, enemy)


def play_sfx(name):
    """Reproduz um efeito sonoro pelo nome, se disponível."""
    global SFX, settings
    if settings and settings["audio"].get("mute") == "On":
        return
    snd = SFX.get(name)
    if snd:
        vol = settings["audio"].get("sfx", 100) / 100.0 if settings else 1.0
        snd.set_volume(vol)
        snd.play()


def pick_upgrades_with_synergy(pool, current_upgrades, k=3):
    """Seleciona upgrades com lógica de sinergia e evoluções."""
    return pick_upgrades_with_synergy_mod(
        pool=pool,
        current_upgrades=current_upgrades,
        unlocks=save_data["unlocks"],
        default_unlocks=DEFAULT_UNLOCKS,
        evolutions=EVOLUTIONS,
        upgrade_tags=UPGRADE_TAGS,
        max_upgrade_level=MAX_UPGRADE_LEVEL,
        k=k,
    )


def get_upgrade_description(key):
    """Retorna a descrição de um upgrade comum ou evolução sem lançar KeyError."""
    return get_upgrade_description_mod(key, EVOLUTIONS, ALL_UPGRADES_POOL, UPGRADE_POOL)


# Feed lateral de skills ativadas durante a run.
#
# Ele existe para mostrar rapidamente o que o jogador acabou de usar em termos
# de ação: dash, ultimate e eventos importantes do herói atual.
skill_feed = []

# Avisos especiais de upgrade/evolução.
#
# Diferente do skill_feed, esta lista é voltada a progresso. Cada entrada usa
# fade-out por alpha para dar feedback visual elegante sem poluir a tela por
# tempo demais.
upgrade_notifications = []

# Estado visual interpolado da HUD.
#
# As barras não pulam direto para o valor real. Em vez disso, o valor visual se
# aproxima do alvo aos poucos, criando uma leitura mais suave quando o jogador
# toma dano ou gasta recurso.
ui_visual_state = {"char_id": None, "hp": None, "mana": None}


def push_skill_feed(text, color=(220, 220, 220), duration=4.0):
    """Adiciona um evento ao feed de skills usadas recentemente."""
    dark_hud.push_skill_feed(text, color=color, duration=duration)


def push_upgrade_notification(text, color=None, duration=4.5):
    """Adiciona um aviso de upgrade com desaparecimento progressivo.

    A cor padrão usa o dourado fosco da interface, reforçando a fantasia sombria
    sem recorrer a um amarelo saturado demais.
    """
    dark_hud.push_upgrade_notification(text, color=color, duration=duration)


def smooth_ui_value(current_value, target_value, dt, speed=8.0):
    """Interpola suavemente um valor visual em direção ao valor real.

    Funcionamento:

    - `target_value` é o valor verdadeiro do gameplay.
    - `current_value` é o valor que a HUD está exibindo no momento.
    - A função aproxima um valor do outro usando um fator por segundo, evitando
      cortes secos na barra.

    Na prática, isso faz a barra “deslizar” até o valor correto, deixando o HUD
    mais legível e mais elegante visualmente.
    """
    if current_value is None:
        return target_value
    blend = min(1.0, speed * dt)
    return current_value + (target_value - current_value) * blend


def update_skill_feed(dt):
    """Atualiza o tempo de vida de logs e avisos visuais da HUD."""
    dark_hud.update_feedback(dt)


def draw_dark_panel(screen, rect, alpha=180, border_color=None):
    """Desenha um painel translúcido no estilo ferro/pergaminho escuro."""
    dark_hud.draw_dark_panel(screen, rect, alpha=alpha, border_color=border_color)


def draw_screen_title(screen, font, text, center_x, center_y, text_color=None, pill_alpha=195):
    """Desenha título medieval com moldura de pedra gravada."""
    if text_color is None:
        text_color = UI_THEME["old_gold"]
    surf = font.render(text, True, text_color)
    rect = surf.get_rect(center=(center_x, center_y))
    # Stone plaque background
    plaque = rect.inflate(52, 20)
    plaque_s = pygame.Surface((plaque.w, plaque.h), pygame.SRCALPHA)
    plaque_s.fill((12, 9, 6, pill_alpha))
    # Outer border: aged iron, sharp corners
    pygame.draw.rect(plaque_s, UI_THEME["iron"], plaque_s.get_rect(), 2, border_radius=3)
    # Inner engraving
    inner = plaque_s.get_rect().inflate(-6, -6)
    pygame.draw.rect(plaque_s, (55, 45, 32), inner, 1, border_radius=1)
    screen.blit(plaque_s, plaque.topleft)
    screen.blit(surf, rect)


def draw_metallic_bar(screen, rect, display_value, max_value, fill_color, label, font_s, font_m, current_value=None):
    """Desenha uma barra com moldura metálica e preenchimento suave.

    O parâmetro `display_value` já deve vir interpolado. Isso desacopla a lógica
    de animação da lógica de desenho: primeiro suavizamos, depois renderizamos.
    """
    safe_max_value = max(1.0, max_value)
    display_ratio = max(0.0, min(1.0, display_value / safe_max_value))
    current_ratio = max(0.0, min(1.0, (current_value if current_value is not None else display_value) / safe_max_value))

    outer_rect = pygame.Rect(rect)
    draw_dark_panel(screen, outer_rect, alpha=185, border_color=UI_THEME["old_gold"])

    fill_area = outer_rect.inflate(-10, -12)
    pygame.draw.rect(screen, UI_THEME["void_black"], fill_area, border_radius=8)
    pygame.draw.rect(screen, (55, 20, 20) if fill_color == UI_THEME["blood_red"] else (20, 28, 45), fill_area, 1, border_radius=8)

    current_rect = fill_area.copy()
    current_rect.width = int(fill_area.width * current_ratio)
    pygame.draw.rect(screen, tuple(min(255, channel + 30) for channel in fill_color), current_rect, border_radius=8)

    display_rect = fill_area.copy()
    display_rect.width = int(fill_area.width * display_ratio)
    pygame.draw.rect(screen, fill_color, display_rect, border_radius=8)

    if display_rect.width > 8:
        highlight = pygame.Surface((display_rect.width, display_rect.height), pygame.SRCALPHA)
        highlight.fill((255, 255, 255, 24))
        screen.blit(highlight, display_rect.topleft)

    title_text = font_s.render(label, True, UI_THEME["parchment"])
    value_text = font_m.render(f"{int(max(0, current_value if current_value is not None else display_value))}", True, UI_THEME["mist"])
    screen.blit(title_text, (outer_rect.x + 14, outer_rect.y - 4))
    screen.blit(value_text, (outer_rect.right - value_text.get_width() - 14, outer_rect.y + 6))


def draw_skill_feed_panel(screen, player, font_s, font_m, hud_scale, high_contrast):
    """Desenha a lista vertical de magias/skills ativas no estilo dark fantasy."""
    dark_hud.draw_skill_feed_panel(screen, player, font_s, hud_scale, high_contrast, SCREEN_W)


def draw_upgrade_notifications(screen, font_s):
    """Desenha os avisos dourados de upgrades com fade-out por alpha."""
    dark_hud.draw_upgrade_notifications(screen, font_s, screen_w=SCREEN_W)


def draw_ui(screen, player, state, font_s, font_m, font_l, hud_scale, high_contrast, level, xp, current_xp_to_level, game_time, kills, dt):
    """Desenha a HUD por último, acima de todos os sprites e partículas."""
    if player and hasattr(player, "dash_cooldown_timer") and player.dash_cooldown > 0:
        dash_ratio = 1.0 - min(1.0, player.dash_cooldown_timer / player.dash_cooldown)
    else:
        dash_ratio = 1.0

    dark_hud.draw_ui(
        screen=screen,
        player=player,
        state=state,
        font_s=font_s,
        font_m=font_m,
        font_l=font_l,
        hud_scale=hud_scale,
        high_contrast=high_contrast,
        level=level,
        xp=xp,
        current_xp_to_level=current_xp_to_level,
        game_time=game_time,
        kills=kills,
        dt=dt,
        screen_w=SCREEN_W,
        screen_h=SCREEN_H,
        player_max_hp=PLAYER_MAX_HP,
        game_version=GAME_VERSION,
        build_type=BUILD_TYPE,
        player_upgrades=player_upgrades,
        dash_ratio=dash_ratio,
    )


def apply_upgrade(key, mult=1.0):
    """Aplica um upgrade ao jogador, modificando as variáveis globais."""
    global PLAYER_MAX_HP, PROJECTILE_DMG, SHOT_COOLDOWN, PLAYER_SPEED
    global PROJECTILE_SPEED, PICKUP_RANGE, AURA_DMG, AURA_RANGE
    global PROJ_COUNT, PROJ_PIERCE, EXPLOSION_RADIUS, ORB_COUNT, EXPLOSION_DMG
    global CRIT_CHANCE, EXECUTE_THRESH, HAS_FURY, player, player_upgrades
    global has_bazuca, has_buraco_negro, has_serras, has_tesla, has_ceifador, has_berserk
    global PROJ_RICOCHET, CRIT_DMG_MULT, REGEN_RATE, THORNS_PERCENT
    global LIFESTEAL_PCT, GOLD_RUN_MULT, XP_BONUS_PCT, ORB_DMG, ORB_DISTANCE

    feed_color = UI_THEME["old_gold"] if key in EVOLUTIONS else UI_THEME["faded_gold"]
    feed_prefix = "Evolução" if key in EVOLUTIONS else "Upgrade"
    
    player_upgrades.append(key)
    
    # Evoluções
    if key == "BAZUCA":
        has_bazuca = True
        push_upgrade_notification(f"{feed_prefix}: {key}", feed_color)
        return
    elif key == "SERRAS MÁGICAS":
        has_serras = True
        push_upgrade_notification(f"{feed_prefix}: {key}", feed_color)
        return
    elif key == "TESLA":
        has_tesla = True
        push_upgrade_notification(f"{feed_prefix}: {key}", feed_color)
        return
    elif key == "CEIFADOR":
        has_ceifador = True
        push_upgrade_notification(f"{feed_prefix}: {key}", feed_color)
        return
    elif key == "BERSERK":
        has_berserk = True
        push_upgrade_notification(f"{feed_prefix}: {key}", feed_color)
        return
    
    if key == "DANO ++":         PROJECTILE_DMG += int(2 * mult)
    elif key == "VELOCIDADE ++": PLAYER_SPEED = min(600, PLAYER_SPEED * (1 + 0.15 * mult))
    elif key == "TIRO RÁPIDO":   SHOT_COOLDOWN = max(0.05, SHOT_COOLDOWN * (1 - 0.15 * mult))
    elif key == "VIDA MÁXIMA":
        PLAYER_MAX_HP += int(2 * mult)
        if player: player.hp = min(player.hp + int(2 * mult), PLAYER_MAX_HP)
    elif key == "ÍMÃ DE XP":      PICKUP_RANGE = min(600, PICKUP_RANGE + 80 * mult)
    elif key == "TIRO MÚLTIPLO": PROJ_COUNT = min(8, PROJ_COUNT + 1)
    elif key == "EXPLOSÃO":      EXPLOSION_RADIUS = max(EXPLOSION_RADIUS, 50); EXPLOSION_RADIUS += int(25 * mult)
    elif key == "PERFURAÇÃO":    PROJ_PIERCE += 1
    elif key == "ORBES MÁGICOS": ORB_COUNT = min(6, ORB_COUNT + 1)
    elif key == "SORTE":         CRIT_CHANCE = min(0.95, CRIT_CHANCE + 0.10 * mult)
    elif key == "CURA":
        if player: player.hp = min(PLAYER_MAX_HP, player.hp + PLAYER_MAX_HP)
    elif key == "RICOCHE":       PROJ_RICOCHET += 1
    elif key == "EXECUÇÃO":      EXECUTE_THRESH = min(0.30, EXECUTE_THRESH + 0.12 * mult)
    elif key == "FÚRIA":         HAS_FURY = True
    elif key == "CAPA INVISÍVEL": pass  # Efeito passivo tratado no Enemy.update
    elif key == "LUVA EXPULSÃO": pass  # Efeito passivo tratado no knockback
    elif key == "TREVO SORTE":   pass  # Efeito passivo em roll_rarity
    elif key in NEW_SKILL_EFFECTS:
        eff = NEW_SKILL_EFFECTS[key]
        if "dmg"       in eff: PROJECTILE_DMG += int(eff["dmg"] * mult)
        if "crit"      in eff: CRIT_CHANCE = min(0.95, CRIT_CHANCE + eff["crit"] * mult)
        if "crit_mult" in eff: CRIT_DMG_MULT += eff["crit_mult"] * mult
        if "execute"   in eff: EXECUTE_THRESH = min(0.50, EXECUTE_THRESH + eff["execute"] * mult)
        if "pierce"    in eff: PROJ_PIERCE += int(eff["pierce"])
        if "proj"      in eff: PROJ_COUNT = min(10, PROJ_COUNT + int(eff["proj"]))
        if "ricochet"  in eff: PROJ_RICOCHET += int(eff["ricochet"])
        if "proj_speed"in eff: PROJECTILE_SPEED = min(1500, PROJECTILE_SPEED + eff["proj_speed"] * mult)
        if "cooldown"  in eff: SHOT_COOLDOWN = max(0.05, SHOT_COOLDOWN * (1 - eff["cooldown"] * mult))
        if "hp"        in eff:
            PLAYER_MAX_HP += int(eff["hp"] * mult)
            if player: player.hp = min(player.hp + int(eff["hp"] * mult), PLAYER_MAX_HP)
        if "regen"     in eff: REGEN_RATE += eff["regen"] * mult
        if "thorns"    in eff: THORNS_PERCENT = min(0.80, THORNS_PERCENT + eff["thorns"] * mult)
        if "lifesteal" in eff: LIFESTEAL_PCT = min(0.50, LIFESTEAL_PCT + eff["lifesteal"] * mult)
        if "speed"     in eff: PLAYER_SPEED = min(700, PLAYER_SPEED + eff["speed"] * mult)
        if "pickup"    in eff: PICKUP_RANGE = min(800, PICKUP_RANGE + eff["pickup"] * mult)
        if "aura_dmg"  in eff: AURA_DMG = max(AURA_DMG, 1); AURA_DMG += int(eff["aura_dmg"] * mult)
        if "aura_range"in eff: AURA_RANGE = min(600, AURA_RANGE + int(eff["aura_range"] * mult))
        if "orb"       in eff: ORB_COUNT = min(8, ORB_COUNT + int(eff["orb"]))
        if "orb_dmg"   in eff: ORB_DMG += int(eff["orb_dmg"] * mult)
        if "orb_dist"  in eff: ORB_DISTANCE = min(400, ORB_DISTANCE + int(eff["orb_dist"] * mult))
        if "explosion" in eff: EXPLOSION_RADIUS = max(EXPLOSION_RADIUS, 50); EXPLOSION_RADIUS += int(eff["explosion"] * mult)
        if "exp_dmg"   in eff: EXPLOSION_DMG += int(eff["exp_dmg"] * mult)
        if "gold"      in eff: GOLD_RUN_MULT += eff["gold"] * mult
        if "xp"        in eff: XP_BONUS_PCT += eff["xp"] * mult
        if "heal"      in eff:
            if player: player.hp = min(PLAYER_MAX_HP, player.hp + int(PLAYER_MAX_HP * eff["heal"]))

    push_upgrade_notification(f"{feed_prefix}: {key}", feed_color)


def check_achievements(stats_override=None, save_when_unlocked=False):
    """Verifica e desbloqueia conquistas com base nas estatísticas."""
    global new_unlocks_this_session
    stats = stats_override if stats_override is not None else save_data["stats"]
    unlocked_any = False
    for ach_id, ach_data in ACHIEVEMENTS.items():
        if ach_id not in save_data["unlocks"]:
            try:
                if ach_data["req"](stats):
                    save_data["unlocks"].append(ach_id)
                    new_unlocks_this_session.append(ach_data["name"])
                    if SFX.get("unlock"): SFX["unlock"].play()
                    unlocked_any = True
            except Exception:
                pass

    if unlocked_any and save_when_unlocked:
        save_game()
    return unlocked_any


def trim_sprite_to_content(surf):
    """Remove bordas transparentes de um Surface e retorna o conteúdo re-centralizado
    num novo Surface do mesmo tamanho. Garante que o conteúdo fique centrado no frame."""
    w, h = surf.get_size()
    min_x, min_y, max_x, max_y = w, h, 0, 0
    for y in range(h):
        for x in range(w):
            if surf.get_at((x, y))[3] > 10:
                min_x = min(min_x, x)
                min_y = min(min_y, y)
                max_x = max(max_x, x)
                max_y = max(max_y, y)
    if max_x <= min_x or max_y <= min_y:
        return surf  # frame vazio — devolver original
    content = surf.subsurface(pygame.Rect(min_x, min_y, max_x - min_x + 1, max_y - min_y + 1))
    result = pygame.Surface((w, h), pygame.SRCALPHA)
    result.blit(content, content.get_rect(center=(w // 2, h // 2)))
    return result


def load_menu_btn_sprites(btn_w, btn_h):
    """Carrega as 7 barras ornamentadas medievais de assets/ui/buttons/.
    A imagem tem fundo transparente (Photoroom). O texto é renderizado
    por cima em Button.draw(), portanto os frames ficam limpos."""
    sheet_path = os.path.join(ASSET_DIR, "ui", "buttons",
                              "Barras de interface medieval ornamentada-Photoroom.png")
    if not os.path.exists(sheet_path):
        return [], []
    sheet = pygame.image.load(sheet_path).convert_alpha()

    # 7 barras medidas por varredura de alpha (imagem 1536x1024, fundo transparente)
    BAR_ROWS = [
        (19,  141),   # 0 – Jogar
        (159, 281),   # 1 – Missões
        (298, 419),   # 2 – Talentos
        (437, 559),   # 3 – Saves
        (576, 696),   # 4 – Bioma
        (715, 836),   # 5 – Configurações
        (854, 975),   # 6 – Sair
    ]
    sw = sheet.get_width()

    normals = []
    hovers  = []
    for y1, y2 in BAR_ROWS:
        bar = sheet.subsurface(pygame.Rect(0, y1, sw, y2 - y1))
        scaled = pygame.transform.smoothscale(bar, (btn_w, btn_h))

        # Versão hover: leve brilho dourado-âmbar sobre a barra
        h_surf = scaled.copy()
        glow = pygame.Surface((btn_w, btn_h), pygame.SRCALPHA)
        glow.fill((220, 160, 40, 18))   # âmbar suave
        h_surf.blit(glow, (0, 0))

        normals.append(scaled)
        hovers.append(h_surf)
    return normals, hovers


def load_skill_card_sprites(card_w, card_h):
    """Carrega as 3 cartas medievais de skills.png para a tela de level-up."""
    sheet_path = os.path.join(ASSET_DIR, "ui", "buttons", "skills.png")
    if not os.path.exists(sheet_path):
        return [], []
    sheet = pygame.image.load(sheet_path).convert_alpha()

    # 3 barras medidas por varredura de alpha (imagem 1492×1054, fundo transparente)
    # x: 71–1423 (largura 1352), y: bar0=60-331, bar1=379-664, bar2=712-997
    BAR_RECTS = [
        (71, 60,  1352, 271),  # x, y, w, h
        (71, 379, 1352, 285),
        (71, 712, 1352, 285),
    ]

    normals = []
    hovers  = []
    for x, y, w, h in BAR_RECTS:
        bar = sheet.subsurface(pygame.Rect(x, y, w, h))
        scaled = pygame.transform.smoothscale(bar, (card_w, card_h))

        h_surf = scaled.copy()
        glow = pygame.Surface((card_w, card_h), pygame.SRCALPHA)
        glow.fill((220, 160, 40, 55))
        h_surf.blit(glow, (0, 0))

        normals.append(scaled)
        hovers.append(h_surf)
    return normals, hovers


def load_config_sprites(title_w, title_h, tag_w, tag_h):
    """Carrega as 2 barras de config.png: barra grande (título) e barra pequena (seção)."""
    path = os.path.join(ASSET_DIR, "ui", "buttons", "config.png")
    if not os.path.exists(path):
        return None, None
    sheet = pygame.image.load(path).convert_alpha()
    sw = sheet.get_width()
    # Barras medidas por varredura de alpha (imagem 2168×725, fundo transparente)
    title_bar = sheet.subsurface(pygame.Rect(0, 34,  sw, 408))   # barra grande
    tag_bar   = sheet.subsurface(pygame.Rect(0, 484, sw, 180))   # barra pequena
    return (pygame.transform.smoothscale(title_bar, (title_w, title_h)),
            pygame.transform.smoothscale(tag_bar,   (tag_w,   tag_h)))


def _reload_biome_assets():
    """Recarrega apenas ground + decos + música do bioma selecionado (sem bloquear o jogo)."""
    global ground_img, current_bg_name
    global forest_deco_manager, dungeon_deco_manager, volcano_deco_manager, moon_deco_manager

    bg_name = BG_DATA.get(selected_bg, BG_DATA["dungeon"])["name"]
    current_bg_name = bg_name

    if selected_bg == "forest":
        ground_img = build_forest_ground(loader)
        if forest_deco_manager is None:
            forest_deco_manager = ForestDecoManager(ASSET_DIR)
        forest_deco_manager.load_frames()
    elif selected_bg == "volcano":
        ground_img = build_volcano_ground(loader)
        if volcano_deco_manager is None:
            volcano_deco_manager = VolcanoDecoManager(ASSET_DIR)
        volcano_deco_manager.load_frames()
    elif selected_bg == "moon":
        ground_img = build_moon_ground(loader)
        if moon_deco_manager is None:
            moon_deco_manager = MoonDecoManager(ASSET_DIR)
        moon_deco_manager.load_frames()
    else:
        ground_img = loader.load_image(bg_name, (256, 256), ((20, 20, 30), (10, 10, 20)))
        if dungeon_deco_manager is None:
            dungeon_deco_manager = DungeonDecoManager(ASSET_DIR)
        dungeon_deco_manager.load_frames()

    music_name = BG_DATA.get(selected_bg, BG_DATA["dungeon"])["music"]
    loader.play_music(music_name)


def load_all_assets():
    """Carrega (ou recarrega) todos os assets gráficos e de áudio do jogo."""
    global ground_img, menu_bg_img, aura_frames, explosion_frames_raw
    global projectile_frames_raw, slash_frames_raw, orb_img, tornado_img
    global upg_images, menu_char_anims, menu_idle_anims, loader, current_bg_name
    global menu_btn_sprites, menu_btn_sprites_hover, menu_logo_img, char_panel_imgs, select_title_img, diff_screen_imgs
    global char_select_panel_img, char_select_panel_meta, char_select_title_frame
    global skill_card_sprites, skill_card_sprites_hover
    global config_title_spr, config_tag_spr
    global forest_deco_manager, dungeon_deco_manager, volcano_deco_manager, moon_deco_manager
    global cursor_img, _steam_btn_surf, _site_btn_surf

    bg_name = BG_DATA.get(selected_bg, BG_DATA["dungeon"])["name"]
    current_bg_name = bg_name

    dark_hud.init_stat_sprites(ASSET_DIR)

    # Bioma Forest: usa tilemap composto em vez de imagem estática
    if selected_bg == "forest":
        ground_img = build_forest_ground(loader)
        if forest_deco_manager is None:
            forest_deco_manager = ForestDecoManager(ASSET_DIR)
        forest_deco_manager.load_frames()
    elif selected_bg == "volcano":
        ground_img = build_volcano_ground(loader)
    elif selected_bg == "moon":
        ground_img = build_moon_ground(loader)
    else:
        ground_img = loader.load_image(bg_name, (256, 256), ((20, 20, 30), (10, 10, 20)))

    # Bioma Dungeon: decorações de chão (pentagrama, BDS, dinossauro)
    if selected_bg == "dungeon":
        if dungeon_deco_manager is None:
            dungeon_deco_manager = DungeonDecoManager(ASSET_DIR)
        dungeon_deco_manager.load_frames()

    # Bioma Volcano: decorações procedurais (poças de lava, rochas, geiseres)
    if selected_bg == "volcano":
        if volcano_deco_manager is None:
            volcano_deco_manager = VolcanoDecoManager(ASSET_DIR)
        volcano_deco_manager.load_frames()

    # Bioma Moon: decorações procedurais (óleo, rachaduras, rochas)
    if selected_bg == "moon":
        if moon_deco_manager is None:
            moon_deco_manager = MoonDecoManager(ASSET_DIR)
        moon_deco_manager.load_frames()
    menu_bg_img = loader.load_image("menu_bg", (SCREEN_W, SCREEN_H), ((10, 5, 20), (5, 0, 10)))
    menu_btn_sprites, menu_btn_sprites_hover = load_menu_btn_sprites(350, 46)
    skill_card_sprites, skill_card_sprites_hover = load_skill_card_sprites(560, 108)
    config_title_spr, config_tag_spr = load_config_sprites(420, 58, 280, 36)

    # Logo do jogo
    logo_path = os.path.join(ASSET_DIR, "ui", "logouwh.png")
    if os.path.exists(logo_path):
        raw_logo = pygame.image.load(logo_path).convert_alpha()
        logo_w = 420
        logo_h = int(logo_w * raw_logo.get_height() / raw_logo.get_width())
        menu_logo_img = pygame.transform.smoothscale(raw_logo, (logo_w, logo_h))

    # Painel grade estilo Vampire Survivors (selecionarpersonagem.png)
    char_panel_imgs = {}   # mantido por compatibilidade, não mais usado no draw
    _sp_path = os.path.join(ASSET_DIR, "ui", "panels", "selecionarpersonagem.png")
    char_select_panel_img  = None
    char_select_panel_meta = {}
    if os.path.exists(_sp_path):
        _sp_raw = pygame.image.load(_sp_path).convert_alpha()
        # Margem superior para o título (50 px) + margem inferior (15 px)
        _SP_TOP    = 50
        _SP_BOT    = 15
        _sp_target_h = SCREEN_H - _SP_TOP - _SP_BOT
        _sp_scale    = _sp_target_h / _sp_raw.get_height()
        _sp_w        = int(_sp_raw.get_width()  * _sp_scale)
        _sp_h        = _sp_target_h
        char_select_panel_img  = pygame.transform.smoothscale(_sp_raw, (_sp_w, _sp_h))
        char_select_panel_meta = {
            "w": _sp_w, "h": _sp_h,
            "ox": (SCREEN_W - _sp_w) // 2,
            "oy": _SP_TOP,
            "scale": _sp_scale,
            # Grade confirmada (imagem original 1510×1041, células 122×122 px, pitch 179 px)
            # Centros das colunas e linhas no original:
            "col_cx": [215, 394, 574, 754, 934, 1113, 1293],
            "row_cy": [215, 394, 574, 752],
            "cell_half": 61,
        }

    # Frame ornamental para o título da seleção — topo do painelguerreiro.png
    # O painel mede 1024×1536; os ~110 px superiores contêm a borda dourada.
    char_select_title_frame = None
    _pnl_path = os.path.join(ASSET_DIR, "ui", "panels", "painelguerreiro.png")
    if os.path.exists(_pnl_path):
        _pnl_raw = pygame.image.load(_pnl_path).convert_alpha()
        _pnl_crop_h = int(_pnl_raw.get_height() * 0.085)   # ~130 px dos 1536 px
        _pnl_strip  = _pnl_raw.subsurface(
            pygame.Rect(0, 0, _pnl_raw.get_width(), _pnl_crop_h))
        _frame_w    = 480
        _frame_h    = int(_frame_w * _pnl_crop_h / _pnl_raw.get_width())
        char_select_title_frame = pygame.transform.smoothscale(
            _pnl_strip, (_frame_w, _frame_h))

    # Título da tela de seleção de herói
    sel_path = os.path.join(ASSET_DIR, "ui", "select.png")
    if os.path.exists(sel_path):
        raw_sel = pygame.image.load(sel_path).convert_alpha()
        sel_w = int(SCREEN_W * 0.38)
        sel_h = int(sel_w * raw_sel.get_height() / raw_sel.get_width())
        select_title_img = pygame.transform.smoothscale(raw_sel, (sel_w, sel_h))

    # Tela de seleção de dificuldade — spritesheet completo
    diff_path = os.path.join(ASSET_DIR, "ui", "selecionar_dificuldade.png")
    if os.path.exists(diff_path):
        dsheet = pygame.image.load(diff_path).convert_alpha()
        SW = dsheet.get_width()  # 1024
        # Cortes medidos via alpha (y_start, y_end_exclusive)
        _diff_cuts = {
            "title":    (77,  282),
            "FÁCIL":    (387, 511),
            "MÉDIO":    (586, 707),
            "DIFÍCIL":  (799, 917),
            "HARDCORE": (994, 1112),
            "VOLTAR":   (1318, 1407),
        }
        # Larguras alvo: botões de dificuldade = 500px, título = 580px, voltar = 380px
        _diff_target_w = {"title": 580, "VOLTAR": 380}
        diff_screen_imgs = {}
        for key, (ys, ye) in _diff_cuts.items():
            frame = dsheet.subsurface(pygame.Rect(0, ys, SW, ye - ys))
            tw = _diff_target_w.get(key, 500)
            th = int(tw * (ye - ys) / SW)
            diff_screen_imgs[key] = pygame.transform.smoothscale(frame, (tw, th))

        # Versão desbloqueada do HARDCORE
        hard_path = os.path.join(ASSET_DIR, "ui", "hard_desbloqueado.png")
        if os.path.exists(hard_path):
            raw_hd = pygame.image.load(hard_path).convert_alpha()
            hd_tw = 500
            hd_th = int(hd_tw * raw_hd.get_height() / raw_hd.get_width())
            diff_screen_imgs["HARDCORE_UNLOCK"] = pygame.transform.smoothscale(raw_hd, (hd_tw, hd_th))

    aura_frames = []  # aura removida
    ExplosionAnimation._frame_cache.clear()   # invalida cache ao recarregar assets
    explosion_frames_raw = load_explosion_frames(loader, (128, 128))
    projectile_frames_raw = loader.load_animation("projectile", 4, (40, 20), fallback_colors=((255, 255, 100), (200, 200, 0)))
    slash_frames_raw = loader.load_animation("slash", 6, (120, 120), fallback_colors=((255, 255, 200, 180), (200, 200, 150, 120)))
    orb_img = loader.load_image("orb", (50, 50), ((0, 200, 255), (0, 100, 200)))
    tornado_img = loader.load_image("tornado", (300, 300), ((200, 200, 255, 150), (150, 150, 200, 100)))
    _build_tornado_cache()
    cursor_img = loader.load_image("seta", (76, 76))

    _ext_w = max(200, int(SCREEN_W * 0.13))
    _ext_h = _ext_w * 2 // 3

    _sb_path = os.path.join(ASSET_DIR, "ui", "steambotton.png")
    if os.path.exists(_sb_path):
        _steam_btn_surf = pygame.transform.smoothscale(
            pygame.image.load(_sb_path).convert_alpha(), (_ext_w, _ext_h))

    _site_path = os.path.join(ASSET_DIR, "ui", "sitebotton.png")
    if os.path.exists(_site_path):
        _site_btn_surf = pygame.transform.smoothscale(
            pygame.image.load(_site_path).convert_alpha(), (_ext_w, _ext_h))

    # Ícones de upgrades
    for upg_key, icon_name in UPGRADE_ICONS.items():
        upg_images[upg_key] = loader.load_image(icon_name, (64, 64))
    
    # assets de personagens
    # Animações dos personagens para o menu
    menu_char_anims = []
    for char_id, char_data in CHAR_DATA.items():
        menu_size = char_data.get("menu_size", (200, 200))
        menu_anim_frames = char_data.get("menu_anim_frames", 10)
        spritesheet_path = char_data.get("spritesheet")
        frames = None
        if spritesheet_path:
            frames = loader.load_spritesheet(
                spritesheet_path,
                char_data.get("spritesheet_frame_w", 64),
                char_data.get("spritesheet_frame_h", 64),
                menu_anim_frames,
                menu_size,
                frame_indices=char_data.get("spritesheet_frame_indices"),
            )
        if not frames:
            frames = loader.load_animation(f"char{char_id}", menu_anim_frames, menu_size)
        frames = [trim_sprite_to_content(f) for f in frames]
        menu_char_anims.append(frames)

    # Animações IDLE para a tela de seleção (mesmo sprite usado no jogo parado)
    # Tamanhos maiores para Guerreiro e Mago na seleção
    _IDLE_SIZES = {0: (280, 280), 1: (220, 220), 2: (560, 560), 3: (220, 220), 4: (360, 360), 5: (340, 340)}
    menu_idle_anims = []
    for char_id, char_data in CHAR_DATA.items():
        idle_sheet = char_data.get("spritesheet_idle")
        idle_size  = _IDLE_SIZES.get(char_id, char_data.get("menu_size", (220, 220)))
        idle_frames_n = char_data.get("idle_anim_frames", 7)
        idle_indices  = char_data.get("spritesheet_idle_frame_indices")
        iframes = None
        if idle_sheet:
            iframes = loader.load_spritesheet(
                idle_sheet,
                char_data.get("spritesheet_idle_frame_w", 96),
                char_data.get("spritesheet_idle_frame_h", 84),
                idle_frames_n,
                idle_size,
                frame_indices=idle_indices,
            )
        if not iframes:
            iframes = menu_char_anims[char_id]   # fallback para walk
        iframes = [trim_sprite_to_content(f) for f in iframes]
        menu_idle_anims.append(iframes)
    
    # Música do bioma
    music_name = BG_DATA.get(selected_bg, BG_DATA["dungeon"])["music"]
    loader.play_music(music_name)


def reset_game(char_id=0):
    """Reinicia todas as variáveis de estado para uma nova partida."""
    global player, enemies, projectiles, enemy_projectiles, gems, drops
    global particles, obstacles, puddles, damage_texts, active_explosions
    global kills, game_time, level, xp, shot_t, aura_t, aura_anim_timer
    global aura_frame_idx, orb_rot_angle, spawn_t, bosses_spawned
    global session_boss_kills, session_max_level, triggered_hordes
    global player_upgrades, has_bazuca, has_buraco_negro, has_serras
    global has_tesla, has_ceifador, has_berserk, chest_loot, chest_ui_timer
    global new_unlocks_this_session, up_options, up_keys, up_rarities
    global PLAYER_MAX_HP, PROJECTILE_DMG, SHOT_COOLDOWN, PLAYER_SPEED
    global PROJECTILE_SPEED, PICKUP_RANGE, AURA_DMG, PROJ_COUNT, PROJ_PIERCE
    global EXPLOSION_RADIUS, ORB_COUNT, CRIT_CHANCE, EXECUTE_THRESH, HAS_FURY
    global CRIT_DMG_MULT, EXPLOSION_SIZE_MULT, REGEN_RATE, DAMAGE_RES
    global THORNS_PERCENT, FIRE_DMG_MULT, BURN_AURA_MULT, HAS_CHAOS_BOLT, HAS_INFERNO
    global PROJ_RICOCHET, ORB_DMG, ORB_DISTANCE, EXPLOSION_DMG
    global LIFESTEAL_PCT, GOLD_RUN_MULT, XP_BONUS_PCT
    global obstacle_grid_index, enemy_batch_index, last_obstacle_count
    global pending_horde_queue, obstacle_spawn_t, obstacle_spawn_interval
    global obstacle_total_placed
    global doom_seals
    global _spawn_diff, current_hardcore_stage, show_stage_victory, show_reward_dialog
    global death_anims
    global ecs_world

    save_data["stats"]["games_played"] += 1
    
    # Resetar stats base
    char_data = CHAR_DATA.get(char_id, CHAR_DATA[0])
    PLAYER_MAX_HP = char_data["hp"]
    PLAYER_SPEED = char_data["speed"]
    PROJECTILE_DMG = char_data.get("damage", 2)
    SHOT_COOLDOWN = 0.50

    # Aplicar bônus de equipamento (arma e escudo da loja de itens)
    _eq        = get_char_equipped(char_id)
    _eq_weapon = _eq.get("weapon")
    _eq_shield = _eq.get("shield")
    if _eq_weapon:
        _wcat   = _eq_weapon.get("category", "")
        _widx   = _eq_weapon.get("idx", 0)
        _wstats = ITEM_SHOP_STATS.get(_wcat, [])
        if _widx < len(_wstats):
            PROJECTILE_DMG += _wstats[_widx].get("atk", 0)
    PROJECTILE_SPEED = 560.0
    PICKUP_RANGE = 50.0
    AURA_DMG = 0
    PROJ_COUNT = 1
    PROJ_PIERCE = 0
    PROJ_RICOCHET = 0
    EXPLOSION_RADIUS = 0
    ORB_COUNT = 0
    CRIT_CHANCE = 0.05
    EXECUTE_THRESH = 0.0
    HAS_FURY = False
    
    # Aplicar upgrades permanentes da árvore de talentos
    pu = save_data["perm_upgrades"]
    CRIT_DMG_MULT = 2.0 + pu.get("crit_dmg", 0) * 0.10
    EXPLOSION_SIZE_MULT = 1.0 + pu.get("exp_size", 0) * 0.10
    HAS_CHAOS_BOLT = pu.get("chaos_bolt", 0) >= 1
    CRIT_CHANCE = min(0.95, CRIT_CHANCE + pu.get("crit_chance", 0) * 0.05)
    REGEN_RATE = pu.get("regen", 0) * 0.1
    DAMAGE_RES = pu.get("aura_res", 0) * 0.08
    if _eq_shield:
        _scat   = _eq_shield.get("category", "Escudos")
        _sidx   = _eq_shield.get("idx", 0)
        _sstats = ITEM_SHOP_STATS.get(_scat, [])
        if _sidx < len(_sstats):
            DAMAGE_RES = min(0.55, DAMAGE_RES + _sstats[_sidx].get("def", 0) / 600.0)
    for _armor_slot in ("helmet", "armor", "legs", "boots"):
        _armor_item = _eq.get(_armor_slot)
        if _armor_item:
            _acat   = _armor_item.get("category", "")
            _aidx   = _armor_item.get("idx", 0)
            _astats = ITEM_SHOP_STATS.get(_acat, [])
            if _aidx < len(_astats):
                DAMAGE_RES = min(0.55, DAMAGE_RES + _astats[_aidx].get("def", 0) / 600.0)
                if _armor_slot == "boots":
                    PLAYER_SPEED += _astats[_aidx].get("spd", 0)
    THORNS_PERCENT = pu.get("thorns", 0) * 0.15
    LIFESTEAL_PCT  = 0.0
    GOLD_RUN_MULT  = 1.0
    XP_BONUS_PCT   = 0.0
    ORB_DMG        = 6
    ORB_DISTANCE   = 180
    EXPLOSION_DMG  = 5
    PLAYER_MAX_HP += pu.get("max_hp_up", 0) * 5
    FIRE_DMG_MULT = 1.0 + pu.get("fire_dmg", 0) * 0.10
    BURN_AURA_MULT = 1.0 + pu.get("burn_area", 0) * 0.12
    HAS_INFERNO = pu.get("inferno", 0) >= 1
    AURA_DMG += pu.get("eternal_flame", 0) * 3
    
    # Resetar grupos de sprites
    enemies = pygame.sprite.Group()
    projectiles = pygame.sprite.Group()
    enemy_projectiles = pygame.sprite.Group()
    gems = pygame.sprite.Group()
    drops = pygame.sprite.Group()
    particles = pygame.sprite.Group()
    obstacles = pygame.sprite.Group()
    puddles = pygame.sprite.Group()
    damage_texts = pygame.sprite.Group()
    doom_seals = pygame.sprite.Group()
    death_anims = pygame.sprite.Group()
    obstacle_grid_index = ObstacleGridIndex(cell_size=WORLD_GRID)
    enemy_batch_index = EnemyBatchIndex()
    last_obstacle_count = 0

    # Inicializar pools de objetos para otimização
    try:
        init_projectile_pools()
        projectile_pool.set_projectile_class(CoreProjectile)
        melee_slash_pool.set_melee_class(CoreMeleeSlash)
        projectile_pool.set_group(projectiles)
        melee_slash_pool.set_group(projectiles)
    except Exception as e:
        print(f"[Projectile Pool] Aviso: Falha ao inicializar pools: {e}")

    # Inicializar mundo ECS
    ecs_world = ECSWorld()
    ecs_world.add_system(EnemyAISystem())
    ecs_world.add_system(EnemyCombatSystem())
    ecs_world.add_system(EnemyAnimationSystem())
    ecs_world.add_system(EnemyRenderSystem())
    ModularEnemy._ecs_world = ecs_world

    # Resetar variáveis de estado
    kills = 0
    game_time = 0.0
    level = 1
    xp = 0
    shot_t = 0.0
    aura_t = 0.0
    aura_anim_timer = 0.0
    aura_frame_idx = 0
    orb_rot_angle = 0.0
    spawn_t = 0.0
    bosses_spawned = 0
    session_boss_kills = 0
    session_max_level = 1
    triggered_hordes = set()
    player_upgrades = []
    has_bazuca = False
    has_buraco_negro = False
    has_serras = False
    has_tesla = False
    has_ceifador = False
    has_berserk = False
    chest_loot = []
    chest_ui_timer = 0.0
    new_unlocks_this_session = []
    active_explosions = []
    # Fila de horda: evita spike de CPU ao spawnar todos de uma vez
    pending_horde_queue = []
    # Obstáculos graduais: espalhados pelo mapa desde o início
    obstacle_spawn_t        = 0.0
    obstacle_spawn_interval = 18.0
    obstacle_total_placed   = 0
    up_options = []
    up_keys = []
    up_rarities = []
    # Computar dificuldade efetiva com multiplicador de fase Hardcore
    _spawn_diff = dict(DIFFICULTIES.get(selected_difficulty, DIFFICULTIES["MÉDIO"]))
    if selected_difficulty == "HARDCORE" and current_hardcore_stage > 1:
        _stage_mult = 1.0 + (current_hardcore_stage - 1) * 0.22
        _spawn_diff = dict(_spawn_diff)
        _spawn_diff["hp_mult"]  = _spawn_diff["hp_mult"]  * _stage_mult
        _spawn_diff["dmg_mult"] = _spawn_diff["dmg_mult"] * _stage_mult
        _spawn_diff["spd_mult"] = _spawn_diff["spd_mult"] * _stage_mult
    show_stage_victory = False
    show_reward_dialog = False

    dark_hud.reset_feedback()

    # Criar jogador
    player = create_player(loader, char_id, build_character_dependencies())
    push_skill_feed(f"Herói ativo: {CHAR_DATA[player.char_id]['name']}", (255, 220, 120), 5.0)


def clear_current_run_state():
    """Limpa estado transitório da run atual e retorna ao menu sem contar nova partida."""
    global player, enemies, projectiles, enemy_projectiles, gems, drops
    global particles, obstacles, puddles, damage_texts, active_explosions
    global kills, game_time, level, xp, shot_t, aura_t, aura_anim_timer
    global aura_frame_idx, orb_rot_angle, spawn_t, bosses_spawned
    global session_boss_kills, session_max_level, triggered_hordes
    global player_upgrades, chest_loot, chest_ui_timer, up_options, up_keys, up_rarities
    global obstacle_grid_index, enemy_batch_index, last_obstacle_count
    global doom_seals, death_anims
    global ecs_world

    player = None
    enemies = pygame.sprite.Group()
    projectiles = pygame.sprite.Group()
    enemy_projectiles = pygame.sprite.Group()
    gems = pygame.sprite.Group()
    drops = pygame.sprite.Group()
    particles = pygame.sprite.Group()
    obstacles = pygame.sprite.Group()
    puddles = pygame.sprite.Group()
    damage_texts = pygame.sprite.Group()
    doom_seals = pygame.sprite.Group()
    death_anims = pygame.sprite.Group()
    obstacle_grid_index = ObstacleGridIndex(cell_size=WORLD_GRID)
    enemy_batch_index = EnemyBatchIndex()
    last_obstacle_count = 0

    # Inicializar mundo ECS
    ecs_world = ECSWorld()
    ecs_world.add_system(EnemyAISystem())
    ecs_world.add_system(EnemyCombatSystem())
    ecs_world.add_system(EnemyAnimationSystem())
    ecs_world.add_system(EnemyRenderSystem())
    ModularEnemy._ecs_world = ecs_world

    kills = 0
    game_time = 0.0
    level = 1
    xp = 0
    shot_t = 0.0
    aura_t = 0.0
    aura_anim_timer = 0.0
    aura_frame_idx = 0
    orb_rot_angle = 0.0
    spawn_t = 0.0
    bosses_spawned = 0
    session_boss_kills = 0
    session_max_level = 1
    triggered_hordes = set()
    player_upgrades = []
    chest_loot = []
    chest_ui_timer = 0.0
    active_explosions = []
    up_options = []
    up_keys = []
    up_rarities = []
    dark_hud.reset_feedback()


# =========================================================
# LÓGICA PRINCIPAL
# =========================================================

def _draw_debug_overlay(screen, font_s, clock):
    """Painel de debug (F3) com métricas de performance em tempo real."""
    cython_label = "Cython ON" if _CYTHON_ACTIVE else "NumPy fallback"
    lines = [
        f"[F3] DEBUG OVERLAY",
        f"FPS: {int(clock.get_fps())}  |  Frame médio: {PERF.avg_frame_ms:.2f} ms",
        f"Consultas espaciais/frame: {PERF.spatial_queries}",
        f"Chamadas A*/frame: {PERF.astar_calls}  |  Cache hit: {PERF.astar_hit_rate * 100:.0f}%",
        f"Kernels: {cython_label}",
    ]

    padding = 8
    line_h = font_s.get_linesize()
    panel_w = 460
    panel_h = len(lines) * line_h + padding * 2

    panel = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
    panel.fill((0, 0, 0, 175))
    screen.blit(panel, (padding, padding))

    for i, text in enumerate(lines):
        color = (255, 220, 60) if i == 0 else (200, 255, 200)
        surf = font_s.render(text, True, color)
        screen.blit(surf, (padding * 2, padding + i * line_h))


def init_menu_particles(count=60):
    """Embers: small rising orange-red sparks that drift sideways."""
    global menu_particles
    menu_particles = []
    for _ in range(count):
        menu_particles.append({
            "x": random.uniform(0, SCREEN_W),
            "y": random.uniform(0, SCREEN_H),
            "speed": random.uniform(18.0, 55.0),   # upward speed
            "size": random.uniform(0.8, 2.8),
            "phase": random.uniform(0.0, math.tau),
            "drift": random.uniform(10.0, 28.0),
            "alpha": random.randint(40, 100),
            "flicker": random.uniform(0.0, math.tau),  # per-particle flicker offset
        })


def draw_menu_background(screen, mouse_pos, dt, overlay_alpha=0):
    if menu_bg_img is None:
        screen.fill((8, 8, 12))
        return

    ox = int(((mouse_pos[0] / max(1, SCREEN_W)) - 0.5) * -20)
    oy = int(((mouse_pos[1] / max(1, SCREEN_H)) - 0.5) * -12)
    screen.blit(menu_bg_img, (ox, oy))
    screen.blit(menu_bg_img, (ox - SCREEN_W, oy))
    screen.blit(menu_bg_img, (ox + SCREEN_W, oy))
    screen.blit(menu_bg_img, (ox, oy - SCREEN_H))
    screen.blit(menu_bg_img, (ox, oy + SCREEN_H))

    t = pygame.time.get_ticks() / 1000.0
    for p in menu_particles:
        # Embers rise upward
        p["y"] -= p["speed"] * dt
        p["x"] += math.sin(t + p["phase"]) * p["drift"] * dt
        if p["y"] < -6:
            p["y"] = SCREEN_H + 4
            p["x"] = random.uniform(0, SCREEN_W)
        if p["x"] < -5:
            p["x"] = SCREEN_W + 5
        elif p["x"] > SCREEN_W + 5:
            p["x"] = -5

        # Flicker: randomly shift alpha and hue per frame toward orange-red
        flicker = 0.5 + 0.5 * math.sin(t * 6.0 + p["flicker"])
        a = int(p["alpha"] * (0.7 + 0.3 * flicker))
        # Color: hot core white→amber→orange-red based on size
        heat = min(1.0, p["size"] / 2.8)
        r = int(255)
        g = int(80 + 90 * heat * flicker)
        b = int(10 * (1.0 - heat))
        sz = max(1, round(p["size"]))
        pygame.draw.circle(screen, (r, g, b, a), (int(p["x"]), int(p["y"])), sz)

    if overlay_alpha > 0:
        overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, overlay_alpha))
        screen.blit(overlay, (0, 0))


def draw_state_transition_overlay(screen, timer):
    if timer <= 0:
        return
    alpha = int(190 * min(1.0, timer / UI_TRANSITION_DURATION))
    surf = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
    surf.fill((8, 8, 12, alpha))
    screen.blit(surf, (0, 0))


def build_menu_icon(kind, tint=(210, 240, 245)):
    surf = pygame.Surface((20, 20), pygame.SRCALPHA)
    if kind == "play":
        pygame.draw.polygon(surf, tint, [(5, 3), (17, 10), (5, 17)])
    elif kind == "missions":
        pygame.draw.rect(surf, tint, (4, 3, 12, 14), 2, border_radius=3)
        pygame.draw.line(surf, tint, (7, 8), (13, 8), 2)
        pygame.draw.line(surf, tint, (7, 12), (13, 12), 2)
    elif kind == "talents":
        pygame.draw.circle(surf, tint, (10, 10), 6, 2)
        pygame.draw.line(surf, tint, (10, 2), (10, 18), 2)
        pygame.draw.line(surf, tint, (2, 10), (18, 10), 2)
    elif kind == "saves":
        pygame.draw.rect(surf, tint, (3, 3, 14, 14), 2)
        pygame.draw.rect(surf, tint, (6, 5, 8, 4))
        pygame.draw.rect(surf, (18, 18, 26), (7, 11, 6, 5))
    elif kind == "biome":
        pygame.draw.circle(surf, tint, (10, 10), 7, 2)
        pygame.draw.line(surf, tint, (3, 10), (17, 10), 2)
        pygame.draw.line(surf, tint, (10, 3), (10, 17), 2)
    elif kind == "settings":
        pygame.draw.circle(surf, tint, (10, 10), 3)
        for i in range(8):
            ang = i * (math.tau / 8.0)
            x1 = 10 + int(math.cos(ang) * 5)
            y1 = 10 + int(math.sin(ang) * 5)
            x2 = 10 + int(math.cos(ang) * 8)
            y2 = 10 + int(math.sin(ang) * 8)
            pygame.draw.line(surf, tint, (x1, y1), (x2, y2), 2)
    elif kind == "exit":
        pygame.draw.line(surf, tint, (4, 4), (16, 16), 3)
        pygame.draw.line(surf, tint, (16, 4), (4, 16), 3)
    return surf


def load_menu_icon_surface(loader, kind, size=(20, 20)):
    icon_rel = f"ui/menu_icons/{kind}"
    icon_abs = os.path.join(ASSET_DIR, "ui", "menu_icons", f"{kind}.png")
    if os.path.exists(icon_abs):
        return loader.load_image(icon_rel, size)

    icon_tint = (255, 220, 220) if kind == "exit" else (210, 240, 245)
    return build_menu_icon(kind, icon_tint)


# =========================================================
# SPLASH SCREEN (aviso1.png → intro.mp4)
# =========================================================

def show_splash_screen(screen):
    """Exibe aviso1.png, save.png (com fade), depois reproduz intro.mp4."""
    sw, sh = screen.get_size()
    clock  = pygame.time.Clock()
    splash_dir = os.path.join(BASE_DIR, "assets", "ui", "splashscreen")

    def _fade_to_black(duration=0.6):
        fade = pygame.Surface((sw, sh))
        fade.fill((0, 0, 0))
        t = 0.0
        while t < duration:
            dt = clock.tick(60) / 1000.0
            t += dt
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    pygame.quit(); raise SystemExit
            fade.set_alpha(int(255 * min(1.0, t / duration)))
            screen.blit(fade, (0, 0))
            pygame.display.flip()

    # ── Fase 1: aviso1.png ────────────────────────────────────────────────
    aviso_path = os.path.join(splash_dir, "aviso1.png")
    if os.path.exists(aviso_path):
        try:
            raw_aviso = pygame.image.load(aviso_path).convert()
            aviso_surf = pygame.transform.smoothscale(raw_aviso, (sw, sh))
        except Exception:
            aviso_surf = None

        if aviso_surf:
            HOLD   = 3.0   # segundos visível
            FADE_I = 0.6   # fade in
            FADE_O = 0.8   # fade out
            timer  = 0.0
            total  = FADE_I + HOLD + FADE_O
            skip   = False

            fade_surf = pygame.Surface((sw, sh))
            fade_surf.fill((0, 0, 0))

            while timer < total and not skip:
                dt = clock.tick(60) / 1000.0
                timer += dt
                for ev in pygame.event.get():
                    if ev.type == pygame.QUIT:
                        pygame.quit(); raise SystemExit
                    if ev.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN):
                        skip = True

                screen.blit(aviso_surf, (0, 0))

                # fade in
                if timer < FADE_I:
                    alpha = int(255 * (1.0 - timer / FADE_I))
                    fade_surf.set_alpha(alpha)
                    screen.blit(fade_surf, (0, 0))
                # hold: nada
                # fade out
                elif timer > FADE_I + HOLD:
                    alpha = int(255 * min(1.0, (timer - FADE_I - HOLD) / FADE_O))
                    fade_surf.set_alpha(alpha)
                    screen.blit(fade_surf, (0, 0))

                pygame.display.flip()

    # ── Fase 2: save.png ──────────────────────────────────────────────────
    save_path = os.path.join(splash_dir, "save.png")
    if os.path.exists(save_path):
        try:
            raw_save = pygame.image.load(save_path).convert()
            save_surf = pygame.transform.smoothscale(raw_save, (sw, sh))
        except Exception:
            save_surf = None

        if save_surf:
            HOLD   = 3.0
            FADE_I = 0.6
            FADE_O = 0.8
            timer  = 0.0
            total  = FADE_I + HOLD + FADE_O
            skip   = False

            fade_surf2 = pygame.Surface((sw, sh))
            fade_surf2.fill((0, 0, 0))

            while timer < total and not skip:
                dt = clock.tick(60) / 1000.0
                timer += dt
                for ev in pygame.event.get():
                    if ev.type == pygame.QUIT:
                        pygame.quit(); raise SystemExit
                    if ev.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN):
                        skip = True

                screen.blit(save_surf, (0, 0))

                if timer < FADE_I:
                    alpha = int(255 * (1.0 - timer / FADE_I))
                    fade_surf2.set_alpha(alpha)
                    screen.blit(fade_surf2, (0, 0))
                elif timer > FADE_I + HOLD:
                    alpha = int(255 * min(1.0, (timer - FADE_I - HOLD) / FADE_O))
                    fade_surf2.set_alpha(alpha)
                    screen.blit(fade_surf2, (0, 0))

                pygame.display.flip()

    # ── Fase 3: intro.mp4 ─────────────────────────────────────────────────
    video_path = os.path.join(splash_dir, "intro.mp4")
    if os.path.exists(video_path):
        try:
            from pyvidplayer2 import Video
            vid = Video(video_path, no_audio=False)
            vid.resize((sw, sh))
            screen.fill((0, 0, 0))
            skip = False
            while vid.active and not skip:
                for ev in pygame.event.get():
                    if ev.type == pygame.QUIT:
                        vid.close(); pygame.quit(); raise SystemExit
                    if ev.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN):
                        skip = True
                vid.draw(screen, (0, 0), force_draw=True)
                pygame.display.flip()
                clock.tick(60)
            vid.close()
        except Exception:
            pass  # falha silenciosa: segue para o loading

    # Fade final para preto antes do loading
    _fade_to_black(0.5)


# =========================================================
# TELA DE CARREGAMENTO
# =========================================================

def show_loading_screen(screen, load_fn):
    """Exibe tela de carregamento com efeito de sangue escorrendo."""
    sw, sh = screen.get_size()

    # --- Background ---
    loading_bg_path = os.path.join(BASE_DIR, "assets", "ui", "loading.png")
    if os.path.exists(loading_bg_path):
        raw_bg = pygame.image.load(loading_bg_path).convert()
        bg_surf = pygame.transform.smoothscale(raw_bg, (sw, sh))
    else:
        bg_surf = pygame.Surface((sw, sh))
        bg_surf.fill((8, 3, 3))

    overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 150))

    # --- Fontes ---
    font_title = dark_hud.load_title_font(52, bold=True, asset_dir=ASSET_DIR)
    font_bar   = dark_hud.load_number_font(22, bold=True, asset_dir=ASSET_DIR)  # texto dentro da barra
    font_label = dark_hud.load_number_font(28, bold=True, asset_dir=ASSET_DIR)
    font_tip   = dark_hud.load_body_font(20, asset_dir=ASSET_DIR)

    # --- Dimensões da barra ---
    bar_w  = int(sw * 0.50)
    bar_h  = 36                # altura aumentada para caber o texto "Carregando"
    bar_x  = (sw - bar_w) // 2
    bar_y  = int(sh * 0.84)   # abaixo da palavra HERO no loading.png
    corner = 4

    # --- Thread ---
    _done  = [False]
    _error = [None]

    def _worker():
        try:
            load_fn()
        except Exception as e:
            _error[0] = e
        finally:
            _done[0] = True

    t = threading.Thread(target=_worker, daemon=True)
    t.start()

    # --- Pré-computa gradiente de sangue (dark → bright → dark) ---
    _blood_pre = pygame.Surface((bar_w, bar_h - 4))
    for _i in range(bar_w):
        _t = _i / max(1, bar_w - 1)
        if _t < 0.55:
            _r = int(75 + (195 - 75) * (_t / 0.55))
        else:
            _r = int(195 - (195 - 110) * ((_t - 0.55) / 0.45))
        _g = int(4 + _t * 7)
        pygame.draw.line(_blood_pre, (min(255, _r), _g, 4), (_i, 0), (_i, bar_h - 5))

    # --- Splatters estáticos pré-computados (surfaces com alpha) ---
    _rng = random.Random(7)
    _splatters = []
    for _ in range(28):
        _sx = bar_x + int(_rng.random() * bar_w)
        _sy = bar_y + bar_h + int(_rng.random() * 55 + 6)
        _sr = _rng.randint(1, 3)
        _sa = _rng.randint(120, 200)
        _ss = pygame.Surface((_sr * 2 + 2, _sr * 2 + 2), pygame.SRCALPHA)
        pygame.draw.circle(_ss, (80, 5, 5, _sa), (_sr + 1, _sr + 1), _sr)
        _splatters.append((_sx - _sr - 1, _sy - _sr - 1, _ss, _sx - bar_x))

    # --- Gotas de sangue animadas ---
    # Cada gota: [x, top_y, bottom_y, speed, width, phase, land_y, age]
    # phase: 0=crescendo, 1=caindo, 2=pousada
    _drips = []
    _puddles = []   # (cx, cy, rx, ry) para ellipses de poça

    # --- Textos ---
    title_surf = font_bar.render("Carregando", True, (255, 210, 0))
    title_rect = title_surf.get_rect(center=(sw // 2, bar_y + bar_h // 2))

    tip_texts = [
        "Explore o mundo e enfrente hordas de inimigos.",
        "Colete gemas para evoluir seu personagem.",
        "Combine upgrades para criar sinergias poderosas.",
        "Cada run é única — adapte sua estratégia.",
    ]
    tip_surf = font_tip.render(random.choice(tip_texts), True, (150, 90, 90))
    tip_rect = tip_surf.get_rect(center=(sw // 2, bar_y + bar_h + 90))

    clock     = pygame.time.Clock()
    elapsed   = 0.0
    fake_prog = 0.0
    dot_timer = 0.0
    dot_count = 0

    while not (_done[0] and fake_prog >= 0.995 and elapsed >= 5.0):
        dt = clock.tick(60) / 1000.0
        elapsed   += dt
        dot_timer += dt
        if dot_timer >= 0.45:
            dot_timer = 0.0
            dot_count = (dot_count + 1) % 4

        target = 0.85 if not _done[0] else 1.0
        fake_prog += (target - fake_prog) * min(1.0, dt * 2.2)

        fill_w = max(corner * 2, int(bar_w * fake_prog))

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                raise SystemExit

        # ── Spawn de novas gotas ────────────────────────────────────────────
        active_count = sum(1 for d in _drips if d[6] < 2)
        if fill_w > corner * 3 and active_count < 20:
            rate = 0.05 + 0.08 * (fill_w / bar_w)
            if random.random() < rate * dt * 60:
                _gx  = bar_x + random.randint(corner, fill_w - corner)
                _spd = random.uniform(22, 95)
                _gw  = random.randint(1, 4)
                _mlen = random.uniform(12, 55)
                _land = bar_y + bar_h + _mlen + random.uniform(30, 110)
                _drips.append([_gx, float(bar_y + bar_h), float(bar_y + bar_h),
                                _spd, _gw, _mlen, 0, 0.0])

        # ── Atualiza gotas ──────────────────────────────────────────────────
        for _d in _drips:
            _gx2, _gtop, _gbot, _spd2, _gw2, _mlen2, _phase, _age = _d
            if _phase == 0:
                _gbot += _spd2 * dt
                _d[2]  = _gbot
                if (_gbot - _gtop) >= _mlen2:
                    _d[6] = 1
            elif _phase == 1:
                _gtop += _spd2 * dt * 0.35
                _gbot += _spd2 * dt * 1.15
                _d[1], _d[2] = _gtop, _gbot
                if _gbot >= bar_y + bar_h + _mlen2 + 80:
                    _d[6] = 2
                    _pw = random.randint(3, 7)
                    _puddles.append((int(_gx2), int(_gbot), _pw, random.randint(1, 2)))
                    if len(_puddles) > 30:
                        _puddles.pop(0)
            elif _phase == 2:
                _d[7] += dt

        _drips[:] = [_d for _d in _drips if not (_d[6] == 2 and _d[7] > 4.0)]

        # ═══════════════════ DESENHO ═══════════════════════════════════════
        screen.blit(bg_surf, (0, 0))
        screen.blit(overlay, (0, 0))

        # Splatters de sangue seco (aparecem gradualmente com o progresso)
        for _sbx, _sby, _ss2, _srel in _splatters:
            if _srel <= fill_w * 1.15:
                screen.blit(_ss2, (_sbx, _sby))

        # Poças de sangue (gotas pousadas)
        for _pcx, _pcy, _prx, _pry in _puddles:
            pygame.draw.ellipse(screen, (70, 4, 4), (_pcx - _prx, _pcy - _pry, _prx * 2, _pry * 2))

        # Trilho da barra (sangue ressecado/escuro)
        pygame.draw.rect(screen, (12, 4, 4), (bar_x - 3, bar_y - 3, bar_w + 6, bar_h + 6), border_radius=corner + 2)
        pygame.draw.rect(screen, (22, 7, 7), (bar_x, bar_y, bar_w, bar_h), border_radius=corner)

        # Preenchimento de sangue (gradiente pré-computado, 1 blit)
        if fill_w > 0:
            screen.blit(_blood_pre, (bar_x, bar_y + 2), (0, 0, fill_w, bar_h - 4))

            # Veia de textura: linhas horizontais escuras internas
            for _vy in (bar_y + 7, bar_y + 14, bar_y + 20):
                if _vy < bar_y + bar_h - 3:
                    _va = 30 + int(20 * math.sin(elapsed * 2.8 + _vy))
                    _vsurf = pygame.Surface((fill_w, 1), pygame.SRCALPHA)
                    _vsurf.fill((0, 0, 0, _va))
                    screen.blit(_vsurf, (bar_x, _vy))

        # Borda pulsante da barra (batimento cardíaco)
        _heart = abs(math.sin(elapsed * 3.8)) * 0.6 + 0.4
        _br    = int(45 + _heart * 50)
        pygame.draw.rect(screen, (_br, 5, 5), (bar_x, bar_y, bar_w, bar_h), width=1, border_radius=corner)

        # Gotas ativas
        for _d in _drips:
            if _d[6] == 2:
                continue
            _dx2, _dtop, _dbot = int(_d[0]), int(_d[1]), int(_d[2])
            _dw2  = _d[4]
            _dlen = _dbot - _dtop
            if _dlen >= 2:
                pygame.draw.line(screen, (168, 10, 8), (_dx2, _dtop), (_dx2, _dbot), _dw2)
            # Bolha na ponta (teardrop)
            pygame.draw.circle(screen, (195, 15, 10), (_dx2, _dbot), _dw2 + 1)
            # Brilho especular na bolha
            if _dw2 >= 2:
                pygame.draw.circle(screen, (230, 60, 50), (_dx2 - 1, _dbot - 1), max(1, _dw2 - 1))

        # ── Título "Carregando" (pulsação de batimento cardíaco) ────────────
        _hbeat = 0.75 + 0.25 * abs(math.sin(elapsed * 3.8))
        title_surf.set_alpha(int(255 * _hbeat))
        screen.blit(title_surf, title_rect)

        # Pontos animados — dentro da barra, à direita de "Carregando"
        _dots_surf = font_bar.render("." * dot_count, True, (220, 180, 0))
        _dots_rect = _dots_surf.get_rect(midleft=(title_rect.right + 2, title_rect.centery))
        _dots_surf.set_alpha(int(255 * _hbeat))
        screen.blit(_dots_surf, _dots_rect)

        # Dica
        screen.blit(tip_surf, tip_rect)

        pygame.display.flip()

    if _error[0]:
        raise _error[0]

    # Fade out (escurece para preto)
    fade = pygame.Surface((sw, sh))
    fade.fill((0, 0, 0))
    for _fa in range(0, 256, 8):
        screen.blit(bg_surf, (0, 0))
        screen.blit(overlay, (0, 0))
        fade.set_alpha(_fa)
        screen.blit(fade, (0, 0))
        pygame.display.flip()
        clock.tick(60)


# ═══════════════════════════════════════════════════════════════════════════
# FUNÇÕES DE INTERFACE — PERFIS / CONQUISTAS
# ═══════════════════════════════════════════════════════════════════════════

_CHAR_NAMES = ["Guerreiro", "Caçador", "Mago", "Vampire", "Demônio", "Golem"]
_NUM_CHARS = 48


_CHAR_COLORS = [
    (120, 40, 30),   # Guerreiro — vermelho-ferrugem
    (30, 80, 45),    # Caçador  — verde floresta
    (35, 55, 120),   # Mago     — azul arcano
    (70, 20, 80),    # Vampire  — roxo noturno
    (110, 35, 20),   # Demônio  — vermelho-fogo
    (55, 60, 65),    # Golem    — cinza pedra
]


def _prof_btn(screen, rect, label, font, active=True, hovered=False, color_base=(55, 45, 32)):
    """Botão com estilo pergaminho medieval."""
    if not active:
        col = (30, 27, 22)
        pygame.draw.rect(screen, col, rect, border_radius=5)
        pygame.draw.rect(screen, UI_THEME["iron"], rect, 1, border_radius=5)
        t = font.render(label, True, (80, 75, 65))
    else:
        col = tuple(min(255, c + 22) for c in color_base) if hovered else color_base
        pygame.draw.rect(screen, col, rect, border_radius=5)
        pygame.draw.rect(screen, UI_THEME["old_gold"], rect, 2, border_radius=5)
        inner = rect.inflate(-6, -4)
        pygame.draw.rect(screen, (255, 255, 255, 18) if hovered else (0, 0, 0, 0), inner, border_radius=3)
        t = font.render(label, True, UI_THEME["parchment"])
    screen.blit(t, t.get_rect(center=rect.center))


def _draw_profile_widget(screen, font_s, font_m, m_pos, align_right=True):
    """Minicard de perfil no canto superior usando o asset perfilnovo.png."""
    global _perfilnovo_img_cache
    if not (profile_mgr and profile_mgr.has_active_profile()):
        return None
    p = profile_mgr.get_active_profile()
    sw, sh = screen.get_size()

    # Card com proporção natural do asset (1536×792 após crop): ~1.96:1
    # CARD_W=275 garante área de texto ≥155px para nomes de até 16 chars (font 14)
    CARD_H = 140
    CARD_W = 275

    card_x = sw - CARD_W - 12 if align_right else 12
    card_y = 12
    card_rect = pygame.Rect(card_x, card_y, CARD_W, CARD_H)

    # Carrega e escala o asset (crop y=128–920 remove padding transparente topo/base)
    if (_perfilnovo_img_cache is None
            or _perfilnovo_img_cache.get_size() != (CARD_W, CARD_H)):
        _img_path = os.path.join(BASE_DIR, "assets", "ui", "perfilnovo.png")
        try:
            _raw = pygame.image.load(_img_path).convert_alpha()
            _cropped = _raw.subsurface((0, 128, 1536, 792))
            _perfilnovo_img_cache = pygame.transform.smoothscale(_cropped, (CARD_W, CARD_H))
        except Exception:
            _perfilnovo_img_cache = None

    if _perfilnovo_img_cache:
        screen.blit(_perfilnovo_img_cache, card_rect.topleft)
        # Brilho sutil ao hover
        if card_rect.collidepoint(m_pos):
            _glow = pygame.Surface((CARD_W, CARD_H), pygame.SRCALPHA)
            _glow.fill((255, 220, 100, 22))
            screen.blit(_glow, card_rect.topleft)
    else:
        draw_dark_panel(screen, card_rect, alpha=210, border_color=UI_THEME["old_gold"])

    # Áreas internas mapeadas das frações do asset recortado (1536×792):
    #   Quadrado esquerdo: x=92–508  → 6.0%–33.1%
    #   Retângulo direito: x=512–1388 → 33.3%–90.4%
    #   Vertical (ambos):  y=192–612  → 24.2%–77.3%
    _sq_x1 = card_x + int(0.060 * CARD_W)
    _sq_x2 = card_x + int(0.331 * CARD_W)
    _sq_y1 = card_y + int(0.242 * CARD_H)
    _sq_y2 = card_y + int(0.773 * CARD_H)
    _sq_w  = _sq_x2 - _sq_x1   # ≈75px
    _sq_h  = _sq_y2 - _sq_y1   # ≈75px

    _rx1 = card_x + int(0.333 * CARD_W)   # ≈91
    _rx2 = card_x + int(0.904 * CARD_W)   # ≈248
    _rw  = _rx2 - _rx1                    # ≈157px

    # Avatar perfeitamente enquadrado no quadrado esquerdo
    av_size = min(_sq_w, _sq_h)
    av_x = _sq_x1 + (_sq_w - av_size) // 2
    av_y = _sq_y1 + (_sq_h - av_size) // 2
    avatar_idx = p.get("avatar_idx", p.get("avatar_char", 0)) % 48
    icon = _load_avatar_icon(avatar_idx, av_size)
    if icon:
        screen.blit(icon, (av_x, av_y))
    else:
        clr = _CHAR_COLORS[avatar_idx % len(_CHAR_COLORS)]
        pygame.draw.rect(screen, clr, pygame.Rect(av_x, av_y, av_size, av_size), border_radius=4)

    # Informações no retângulo direito (fonte dedicada menor para o minicard)
    _font_name = load_title_font(14, bold=True)
    tx = _rx1 + 6
    cy = _sq_y1 + _sq_h // 2

    name         = p.get("nickname", "?")[:16]
    country_code = p.get("country", "BR")
    country_name = COUNTRY_BY_CODE.get(country_code, country_code)
    prof_level   = ProfileManager.xp_to_level(p.get("profile_xp", 0))[0]

    name_s    = _font_name.render(name,        True, UI_THEME["parchment"])
    country_s = font_s.render(country_name,    True, (140, 170, 200))
    level_s   = font_s.render(f"Lv.{prof_level}", True, (200, 170, 60))

    screen.blit(name_s,    name_s.get_rect(left=tx,    centery=cy - 22))
    screen.blit(country_s, country_s.get_rect(left=tx, centery=cy - 1))
    screen.blit(level_s,   level_s.get_rect(left=tx,   centery=cy + 18))

    hovered = card_rect.collidepoint(m_pos)
    if hovered:
        hint = font_s.render("clique para trocar", True, (130, 120, 90))
        screen.blit(hint, hint.get_rect(right=card_rect.right - 6, bottom=card_rect.bottom - 3))

    return card_rect


def _draw_profile_select(screen, font_s, font_m, font_l, m_pos,
                         mode, sel_idx, new_name, new_ci, new_char, name_focus, del_confirm):
    """Renderiza o diálogo de seleção / criação de perfil sobre o fundo do menu."""
    global _select_perfil_img
    sw, sh = screen.get_size()

    GOLD   = UI_THEME["old_gold"]
    PARCH  = UI_THEME["parchment"]
    IRON   = UI_THEME["iron"]
    DIM    = (90, 82, 68)

    # ── Painel com imagem de fundo ───────────────────────────────────────
    pan_w = int(min(sw * 0.78, 1200))
    pan_h = int(min(sh * 0.85, 860))
    pan_x = (sw - pan_w) // 2
    pan_y = (sh - pan_h) // 2

    if not isinstance(_select_perfil_img, pygame.Surface) or _select_perfil_img.get_size() != (pan_w, pan_h):
        _img_path = os.path.join(BASE_DIR, "assets", "ui", "panels", "select_perfil.png")
        try:
            _raw = pygame.image.load(_img_path).convert_alpha()
            _select_perfil_img = pygame.transform.smoothscale(_raw, (pan_w, pan_h))
        except Exception:
            _select_perfil_img = None

    if isinstance(_select_perfil_img, pygame.Surface):
        screen.blit(_select_perfil_img, (pan_x, pan_y))
    else:
        draw_dark_panel(screen, pygame.Rect(pan_x, pan_y, pan_w, pan_h), alpha=215, border_color=GOLD)

    # Referências de layout baseadas nos elementos da imagem:
    # cabeçalho ocupa ~top 8% do painel, área de botões ~bottom 14%
    _hdr_cy  = pan_y + int(pan_h * 0.068)   # centro vertical do header
    _tbar_y  = pan_y + int(pan_h * 0.130)   # início da área de conteúdo
    _btn_top = pan_y + int(pan_h * 0.878)   # topo da faixa de botões na base

    # Título no cabeçalho
    if mode == "create":   title_txt = "CRIAR NOVO PERFIL"
    elif mode == "edit":   title_txt = "EDITAR PERFIL"
    else:                  title_txt = "SELECIONAR HERÓI"
    _title_s = font_l.render(title_txt, True, GOLD)
    screen.blit(_title_s, _title_s.get_rect(centerx=sw // 2, centery=_hdr_cy))

    # Margem lateral interna (respeita as bordas douradas da imagem ~4%)
    INNER_X = pan_x + int(pan_w * 0.04)
    INNER_W = pan_w - int(pan_w * 0.08)

    if mode in ("create", "edit"):
        # ── FORMULÁRIO DE CRIAÇÃO ────────────────────────────────────────
        body_y = _tbar_y + 22
        row_h  = int(pan_h * 0.145)

        def _section_label(text, y):
            tag = font_s.render(text, True, GOLD)
            screen.blit(tag, (INNER_X, y))
            pygame.draw.line(screen, (*GOLD, 90), (INNER_X + tag.get_width() + 8, y + tag.get_height() // 2),
                             (INNER_X + INNER_W, y + tag.get_height() // 2), 1)
            return y + tag.get_height() + 6

        # — Nome —
        row_y = _section_label("  NOME DO JOGADOR", body_y)
        inp_rect = pygame.Rect(INNER_X, row_y, INNER_W, 40)
        inp_bg_col = (28, 22, 16)
        pygame.draw.rect(screen, inp_bg_col, inp_rect, border_radius=4)
        brd = GOLD if name_focus else IRON
        pygame.draw.rect(screen, brd, inp_rect, 2, border_radius=4)
        # entalhe interno
        inner_inp = inp_rect.inflate(-6, -6)
        pygame.draw.rect(screen, (18, 14, 10), inner_inp, 1, border_radius=2)
        cursor = "|" if (pygame.time.get_ticks() // 530) % 2 == 0 and name_focus else ""
        n_surf = font_m.render(new_name + cursor, True, PARCH)
        screen.blit(n_surf, (inp_rect.x + 10, inp_rect.y + 6))
        hint_max = font_s.render(f"{len(new_name)}/16", True, DIM)
        screen.blit(hint_max, hint_max.get_rect(right=inp_rect.right - 8, bottom=inp_rect.bottom - 4))

        # — País —
        row_y += row_h
        row_y = _section_label("  PAÍS DE ORIGEM", row_y)
        arr_w = 34
        country_name = COUNTRIES[new_ci][1]
        arr_l = pygame.Rect(INNER_X, row_y + 2, arr_w, 34)
        arr_r = pygame.Rect(INNER_X + arr_w + 220, row_y + 2, arr_w, 34)
        for _ar, _ch in ((arr_l, "◄"), (arr_r, "►")):
            _hov = _ar.collidepoint(m_pos)
            draw_dark_panel(screen, _ar, alpha=200, border_color=GOLD if _hov else IRON)
            _cs = font_s.render(_ch, True, GOLD if _hov else PARCH)
            screen.blit(_cs, _cs.get_rect(center=_ar.center))
        c_surf = font_m.render(country_name, True, PARCH)
        screen.blit(c_surf, c_surf.get_rect(left=arr_l.right + 12, centery=arr_l.centery))
        _draw_profile_select._arr_country_l = arr_l
        _draw_profile_select._arr_country_r = arr_r

        # — Avatar —
        row_y += row_h
        row_y = _section_label("  PERSONAGEM FAVORITO", row_y)
        av_l = pygame.Rect(INNER_X, row_y + 2, arr_w, 34)
        av_r = pygame.Rect(INNER_X + arr_w + 220, row_y + 2, arr_w, 34)
        char_idx = new_char % _NUM_CHARS
        char_col = _CHAR_COLORS[char_idx % len(_CHAR_COLORS)]
        for _ar, _ch in ((av_l, "◄"), (av_r, "►")):
            _hov = _ar.collidepoint(m_pos)
            draw_dark_panel(screen, _ar, alpha=200, border_color=GOLD if _hov else IRON)
            _cs = font_s.render(_ch, True, GOLD if _hov else PARCH)
            screen.blit(_cs, _cs.get_rect(center=_ar.center))
        # Preview do avatar: ícone real ou badge colorida como fallback
        AVATAR_PREVIEW_SIZE = 48
        badge_r = pygame.Rect(av_l.right + 12, av_l.top - 7, AVATAR_PREVIEW_SIZE, AVATAR_PREVIEW_SIZE)
        _av_icon = _load_avatar_icon(new_char % 48, AVATAR_PREVIEW_SIZE)
        if _av_icon:
            screen.blit(_av_icon, badge_r)
            pygame.draw.rect(screen, GOLD, badge_r, 1, border_radius=4)
        else:
            draw_dark_panel(screen, badge_r, alpha=220, border_color=GOLD)
            badge_fill = pygame.Surface((badge_r.w - 4, badge_r.h - 4), pygame.SRCALPHA)
            badge_fill.fill((*char_col, 100))
            screen.blit(badge_fill, (badge_r.x + 2, badge_r.y + 2))
            av_surf = font_m.render(_CHAR_NAMES[char_idx % len(_CHAR_NAMES)], True, PARCH)
            screen.blit(av_surf, av_surf.get_rect(center=badge_r.center))
        _draw_profile_select._arr_avatar_l = av_l
        _draw_profile_select._arr_avatar_r = av_r

        # — Botões: "Criar Perfil" alinhado ao 1º box, "Voltar" ao último box —
        _box_margin = int(pan_w * 0.088)
        _box_gap = int(pan_w * 0.005)
        _4box_w = (pan_w - 2 * _box_margin - 3 * _box_gap) // 4
        btn_h_px = int(pan_h * 0.108)
        btn_criar  = pygame.Rect(pan_x + _box_margin, _btn_top, _4box_w, btn_h_px)
        btn_voltar = pygame.Rect(pan_x + pan_w - _box_margin - _4box_w, _btn_top, _4box_w, btn_h_px)

        can_create = bool(new_name.strip())
        _btn_label = "SALVAR ALTERAÇÕES" if mode == "edit" else "CRIAR PERFIL"
        # O asset já tem as caixas desenhadas — apenas o texto
        _criar_hov = can_create and btn_criar.collidepoint(m_pos)
        _tc1 = GOLD if _criar_hov else (PARCH if can_create else (80, 75, 65))
        _t1 = font_m.render(_btn_label, True, _tc1)
        screen.blit(_t1, _t1.get_rect(center=btn_criar.center))
        _voltar_hov = btn_voltar.collidepoint(m_pos)
        _tc2 = GOLD if _voltar_hov else PARCH
        _t2 = font_m.render("VOLTAR", True, _tc2)
        screen.blit(_t2, _t2.get_rect(center=btn_voltar.center))
        _draw_profile_select._btn_criar = btn_criar
        _draw_profile_select._btn_voltar_create = btn_voltar
        _draw_profile_select._edit_mode = (mode == "edit")

        _hint_txt = "Enter para salvar   •   ESC para voltar" if mode == "edit" else "Enter para criar   •   ESC para voltar"
        hint = font_s.render(_hint_txt, True, DIM)
        screen.blit(hint, hint.get_rect(centerx=sw // 2, bottom=_btn_top - 6))

    else:
        # ── LISTA DE PERFIS ───────────────────────────────────────────────
        profiles = profile_mgr.get_all_profiles() if profile_mgr else []
        n = max(1, len(profiles))

        # Cards — largura dinâmica, max 5 perfis visíveis por vez
        CARD_GAP = 18
        MAX_VISIBLE = 5
        vis = min(max(1, len(profiles)), MAX_VISIBLE)
        _avail_w = pan_w - int(pan_w * 0.08)
        CARD_W = max(160, min(220, (_avail_w - CARD_GAP * (vis - 1)) // vis))
        CARD_H = int(pan_h * 0.58)  # cards fill the central area without overflowing header
        cards_total_w = len(profiles) * CARD_W + (len(profiles) - 1) * CARD_GAP
        cards_x = pan_x + (pan_w - min(cards_total_w, _avail_w)) // 2
        cards_y = _tbar_y + 14

        _draw_profile_select._card_rects = []

        for ci, p in enumerate(profiles):
            cx = cards_x + ci * (CARD_W + CARD_GAP)
            if cx + CARD_W > pan_x + pan_w - 14:
                break
            is_sel = (ci == sel_idx)
            char_idx = p.get("avatar_idx", p.get("avatar_char", 0)) % _NUM_CHARS
            char_col = _CHAR_COLORS[char_idx % len(_CHAR_COLORS)]
            card_r = pygame.Rect(cx, cards_y, CARD_W, CARD_H)
            _draw_profile_select._card_rects.append((ci, card_r))

            # Sombra sutil do card selecionado
            if is_sel:
                sh_r = card_r.inflate(8, 8)
                sh_s = pygame.Surface((sh_r.w, sh_r.h), pygame.SRCALPHA)
                sh_s.fill((*GOLD, 40))
                screen.blit(sh_s, sh_r.topleft)

            draw_dark_panel(screen, card_r, alpha=220,
                            border_color=GOLD if is_sel else (70, 62, 48))

            # Faixa colorida do personagem no topo do card
            stripe = pygame.Rect(card_r.x + 2, card_r.y + 2, card_r.w - 4, int(card_r.h * 0.28))
            stripe_surf = pygame.Surface((stripe.w, stripe.h), pygame.SRCALPHA)
            stripe_surf.fill((*char_col, 180))
            screen.blit(stripe_surf, stripe.topleft)
            pygame.draw.rect(screen, GOLD if is_sel else IRON, stripe, 1)

            # Ícone do personagem: avatar real ou inicial como fallback
            small_size = min(stripe.h - 4, stripe.w - 4, 90)
            _card_av_icon = _load_avatar_icon(char_idx % 48, small_size)
            if _card_av_icon:
                screen.blit(_card_av_icon, _card_av_icon.get_rect(center=(card_r.centerx, stripe.centery)))
            else:
                char_initial = _CHAR_NAMES[char_idx % len(_CHAR_NAMES)][0]
                ci_font = font_l
                ci_s = ci_font.render(char_initial, True, PARCH if is_sel else (140, 130, 110))
                screen.blit(ci_s, ci_s.get_rect(center=(card_r.centerx, stripe.centery)))

            # Nickname
            nk_y = stripe.bottom + 8
            nk = font_m.render(p.get("nickname", "?")[:12], True, GOLD if is_sel else PARCH)
            nk_s = pygame.transform.smoothscale(nk, (min(nk.get_width(), card_r.w - 10),
                                                      nk.get_height())) if nk.get_width() > card_r.w - 10 else nk
            screen.blit(nk_s, nk_s.get_rect(centerx=card_r.centerx, top=nk_y))

            # País
            country_code = p.get("country", "BR")
            country_name = COUNTRY_BY_CODE.get(country_code, country_code)
            ct = font_s.render(country_name, True, (140, 170, 200))
            screen.blit(ct, ct.get_rect(centerx=card_r.centerx, top=nk_y + 26))

            # Nível do perfil
            _card_lv = ProfileManager.xp_to_level(p.get("profile_xp", 0))[0]
            lv_s = font_s.render(f"Nível {_card_lv}", True, (200, 170, 60))
            screen.blit(lv_s, lv_s.get_rect(centerx=card_r.centerx, top=nk_y + 44))

            # Divider
            dv_y = nk_y + 66
            pygame.draw.line(screen, (*IRON, 160), (card_r.x + 10, dv_y), (card_r.right - 10, dv_y), 1)

            # Tempo de jogo
            playtime = ProfileManager.format_playtime(p.get("total_playtime", 0.0))
            pt = font_s.render(playtime, True, (120, 170, 110))
            screen.blit(pt, pt.get_rect(centerx=card_r.centerx, top=dv_y + 6))

            # Conquistas (só para o selecionado, para compactar)
            if is_sel:
                total_ach = len(_ach.ACHIEVEMENT_DEFS)
                unlocked_c = len(achievements_data.get("unlocked", [])) if achievements_data else 0
                ach_s = font_s.render(f"★ {unlocked_c}/{total_ach}", True, (200, 160, 60))
                screen.blit(ach_s, ach_s.get_rect(centerx=card_r.centerx, top=dv_y + 26))

            # Overlay de confirmação de exclusão
            if del_confirm == p["id"]:
                del_ov = pygame.Surface((card_r.w, card_r.h), pygame.SRCALPHA)
                del_ov.fill((80, 5, 5, 210))
                screen.blit(del_ov, card_r.topleft)
                pygame.draw.rect(screen, (180, 40, 40), card_r, 2, border_radius=4)
                dl1 = font_s.render("Excluir?", True, (255, 120, 120))
                screen.blit(dl1, dl1.get_rect(centerx=card_r.centerx, centery=card_r.centery - 14))
                dl2 = font_s.render("Clique EXCLUIR", True, (200, 140, 140))
                screen.blit(dl2, dl2.get_rect(centerx=card_r.centerx, centery=card_r.centery + 10))
                dl3 = font_s.render("para confirmar", True, (200, 140, 140))
                screen.blit(dl3, dl3.get_rect(centerx=card_r.centerx, centery=card_r.centery + 28))

        # Botões de ação
        BTN_H = 42
        BTN_GAP = 12
        if profiles:
            btns_def = [
                ("JOGAR",       (34, 68, 34)),
                ("EDITAR",      (30, 55, 80)),
                ("EXCLUIR",     (72, 24, 18)),
                ("NOVO PERFIL", (38, 36, 22)),
            ]
        else:
            btns_def = [("CRIAR PERFIL", (34, 68, 34))]

        # Botões alinhados com os 4 retângulos na base da imagem
        # A imagem tem 4 caixas que cobrem ~3%–97% da largura, topo em ~86% da altura
        _nb = len(btns_def)
        _box_margin_l = int(pan_w * 0.088)
        _box_margin_r = int(pan_w * 0.096)
        _box_total_w = pan_w - _box_margin_l - _box_margin_r
        _box_gap = int(pan_w * 0.005)
        _box_w = (_box_total_w - (_nb - 1) * _box_gap) // _nb
        BTN_H = int(pan_h * 0.108)
        bx = pan_x + _box_margin_l
        by = _btn_top

        btns = []
        for _txt, _base_col in btns_def:
            br = pygame.Rect(bx, by, _box_w, BTN_H)
            btns.append((br, _txt, _base_col))
            # O asset já tem as caixas desenhadas — apenas o texto
            _hov = br.collidepoint(m_pos)
            _tcol = GOLD if _hov else PARCH
            _t = font_m.render(_txt, True, _tcol)
            screen.blit(_t, _t.get_rect(center=br.center))
            bx += _box_w + _box_gap

        _draw_profile_select._btns_list = btns

        # Dica de navegação
        nav_s = font_s.render("Clique no perfil para selecionar   •   ← → navega   •   Enter para jogar", True, DIM)
        screen.blit(nav_s, nav_s.get_rect(centerx=sw // 2, bottom=_btn_top - 6))


def _handle_profile_select_click(click_pos, mode, sel_idx, new_name, new_ci, new_char, name_focus, del_confirm):
    """Processa cliques na tela de perfil. Retorna tupla atualizada ou None."""
    profiles = profile_mgr.get_all_profiles() if profile_mgr else []

    if mode in ("create", "edit"):
        if hasattr(_draw_profile_select, "_arr_country_l") and _draw_profile_select._arr_country_l.collidepoint(click_pos):
            return (mode, sel_idx, new_name, (new_ci - 1) % len(COUNTRIES), new_char, name_focus, del_confirm)
        if hasattr(_draw_profile_select, "_arr_country_r") and _draw_profile_select._arr_country_r.collidepoint(click_pos):
            return (mode, sel_idx, new_name, (new_ci + 1) % len(COUNTRIES), new_char, name_focus, del_confirm)
        if hasattr(_draw_profile_select, "_arr_avatar_l") and _draw_profile_select._arr_avatar_l.collidepoint(click_pos):
            return (mode, sel_idx, new_name, new_ci, (new_char - 1) % _NUM_CHARS, name_focus, del_confirm)
        if hasattr(_draw_profile_select, "_arr_avatar_r") and _draw_profile_select._arr_avatar_r.collidepoint(click_pos):
            return (mode, sel_idx, new_name, new_ci, (new_char + 1) % _NUM_CHARS, name_focus, del_confirm)
        if hasattr(_draw_profile_select, "_btn_criar") and _draw_profile_select._btn_criar.collidepoint(click_pos):
            if new_name.strip() and profile_mgr:
                if mode == "edit" and profiles and sel_idx < len(profiles):
                    pid = profiles[sel_idx]["id"]
                    profile_mgr.update_nickname(pid, new_name.strip())
                    profile_mgr.update_country(pid, COUNTRIES[new_ci][0])
                    profile_mgr.update_avatar(pid, new_char)
                    _avatar_icon_cache.clear()
                    return ("list", sel_idx, new_name, new_ci, new_char, name_focus, None)
                else:
                    profile_mgr.create_profile(new_name.strip(), COUNTRIES[new_ci][0], new_char)
                    return ("SELECTED", 0, "", 0, 0, True, None)
        if hasattr(_draw_profile_select, "_btn_voltar_create") and _draw_profile_select._btn_voltar_create.collidepoint(click_pos):
            return ("list", sel_idx, new_name, new_ci, new_char, name_focus, None)

    elif mode == "list":
        # Botões de ação
        if hasattr(_draw_profile_select, "_btns_list"):
            for _br, _txt, _col in _draw_profile_select._btns_list:
                if _br.collidepoint(click_pos):
                    if "JOGAR" in _txt or "CRIAR PERFIL" in _txt:
                        if "CRIAR" in _txt:
                            return ("create", sel_idx, "", new_ci, new_char, True, None)
                        if profiles and sel_idx < len(profiles):
                            profile_mgr.select_profile(profiles[sel_idx]["id"])
                            return ("SELECTED", sel_idx, new_name, new_ci, new_char, name_focus, None)
                    elif "EDITAR" in _txt:
                        if profiles and sel_idx < len(profiles):
                            p = profiles[sel_idx]
                            pre_name = p.get("nickname", "")
                            pre_cc   = p.get("country", "BR")
                            pre_ci   = next((i for i, (c, _) in enumerate(COUNTRIES) if c == pre_cc), 0)
                            pre_char = p.get("avatar_idx", p.get("avatar_char", 0)) % _NUM_CHARS
                            return ("edit", sel_idx, pre_name, pre_ci, pre_char, True, None)
                    elif "EXCLUIR" in _txt or "DELETAR" in _txt:
                        if profiles and sel_idx < len(profiles):
                            pid = profiles[sel_idx]["id"]
                            if del_confirm == pid:
                                profile_mgr.delete_profile(pid)
                                remaining = profile_mgr.get_all_profiles()
                                new_idx = max(0, min(sel_idx, len(remaining) - 1))
                                new_mode = "list" if remaining else "create"
                                return (new_mode, new_idx, new_name, new_ci, new_char, name_focus, None)
                            return (mode, sel_idx, new_name, new_ci, new_char, name_focus, pid)
                    elif "NOVO" in _txt:
                        return ("create", sel_idx, "", new_ci, new_char, True, None)

        # Clique em cartão de perfil
        if hasattr(_draw_profile_select, "_card_rects"):
            for ci, card_r in _draw_profile_select._card_rects:
                if card_r.collidepoint(click_pos):
                    return (mode, ci, new_name, new_ci, new_char, name_focus, del_confirm)

    return None


def _load_ach_icon(icon_filename: str, size: int = 48) -> "pygame.Surface | None":
    """Carrega e cacheia ícone de conquista."""
    key = (icon_filename, size)
    if key in _ach_icon_cache:
        return _ach_icon_cache[key]
    path = os.path.join(BASE_DIR, "assets", "conquistas", icon_filename)
    surf = None
    if os.path.exists(path):
        try:
            raw = pygame.image.load(path).convert_alpha()
            surf = pygame.transform.smoothscale(raw, (size, size))
        except Exception:
            surf = None
    _ach_icon_cache[key] = surf
    return surf


def _load_avatar_icon(idx: int, size: int = 48):
    """Carrega e cacheia ícone de avatar pelo índice (0-47)."""
    key = (idx, size)
    if key in _avatar_icon_cache:
        return _avatar_icon_cache[key]
    path = os.path.join(BASE_DIR, "assets", "avatares", f"Icon{idx + 1}.png")
    try:
        img = pygame.image.load(path).convert_alpha()
        img = pygame.transform.smoothscale(img, (size, size))
    except Exception:
        img = None
    _avatar_icon_cache[key] = img
    return img


def _draw_profile_viewer(screen, font_s, font_m, font_l, m_pos, show_change_btn=False):
    """Overlay de Perfil e Conquistas (tecla L no Hub ou clique no widget do Menu)."""
    if not (profile_mgr and profile_mgr.has_active_profile()):
        return
    sw, sh = screen.get_size()

    # Fundo
    ov = pygame.Surface((sw, sh), pygame.SRCALPHA)
    ov.fill((6, 4, 12, 230))
    screen.blit(ov, (0, 0))

    GOLD   = (220, 190, 80)
    SILVER = (180, 175, 160)
    DIM    = (90, 85, 80)

    profile = profile_mgr.get_active_profile()
    nickname = profile.get("nickname", "?")
    country_code = profile.get("country", "BR")
    country_name = COUNTRY_BY_CODE.get(country_code, country_code)
    playtime = ProfileManager.format_playtime(profile.get("total_playtime", 0.0))
    created = profile.get("created_at", "")[:10]

    # ── Painel esquerdo (informações) ─────────────────────────────────────
    lp_w, lp_h = int(sw * 0.28), int(sh * 0.78)
    lp_x, lp_y = int(sw * 0.04), int(sh * 0.11)
    lp_surf = pygame.Surface((lp_w, lp_h), pygame.SRCALPHA)
    lp_surf.fill((14, 10, 24, 220))
    screen.blit(lp_surf, (lp_x, lp_y))
    pygame.draw.rect(screen, GOLD, pygame.Rect(lp_x, lp_y, lp_w, lp_h), 2, border_radius=10)

    _lcy = lp_y + 16
    title_s = font_l.render("PERFIL", True, GOLD)
    screen.blit(title_s, title_s.get_rect(centerx=lp_x + lp_w // 2, top=_lcy))
    _lcy += title_s.get_height() + 10
    pygame.draw.line(screen, GOLD, (lp_x + 12, _lcy), (lp_x + lp_w - 12, _lcy))
    _lcy += 12

    # ── Avatar editável ───────────────────────────────────────────────
    AV_SIZE = min(72, lp_w - 80)
    av_idx  = profile.get("avatar_idx", profile.get("avatar_char", 0)) % 48
    av_icon = _load_avatar_icon(av_idx, AV_SIZE)
    av_rect = pygame.Rect(lp_x + lp_w // 2 - AV_SIZE // 2, _lcy, AV_SIZE, AV_SIZE)
    av_hov  = av_rect.collidepoint(m_pos)
    if av_icon:
        screen.blit(av_icon, av_rect)
    else:
        pygame.draw.rect(screen, _CHAR_COLORS[av_idx % len(_CHAR_COLORS)], av_rect, border_radius=6)
    pygame.draw.rect(screen, GOLD if av_hov else (140, 110, 40), av_rect, 2, border_radius=6)
    if av_hov:
        _cam_s = font_s.render("clique para trocar", True, GOLD)
        screen.blit(_cam_s, _cam_s.get_rect(centerx=av_rect.centerx, top=av_rect.bottom + 2))
    _draw_profile_viewer._av_main_rect  = av_rect
    _draw_profile_viewer._av_profile_id = profile["id"]
    _draw_profile_viewer._av_idx        = av_idx
    if not hasattr(_draw_profile_viewer, "_av_picker_open"):
        _draw_profile_viewer._av_picker_open = False
    _lcy = av_rect.bottom + (22 if av_hov else 8)
    pygame.draw.line(screen, (60, 55, 80), (lp_x + 12, _lcy), (lp_x + lp_w - 12, _lcy))
    _lcy += 10

    # Level / XP bar
    _prof_xp = profile.get("profile_xp", 0)
    _prof_lv, _xp_in_lv, _xp_for_next = ProfileManager.xp_to_level(_prof_xp)
    _lv_s = font_m.render(f"Nível {_prof_lv}", True, (220, 190, 60))
    screen.blit(_lv_s, _lv_s.get_rect(centerx=lp_x + lp_w // 2, top=_lcy))
    _lcy += _lv_s.get_height() + 4
    _bar_x, _bar_w, _bar_h = lp_x + 14, lp_w - 28, 10
    pygame.draw.rect(screen, (40, 35, 20), pygame.Rect(_bar_x, _lcy, _bar_w, _bar_h), border_radius=4)
    _fill_w = int(_bar_w * min(1.0, _xp_in_lv / max(1, _xp_for_next)))
    if _fill_w > 0:
        pygame.draw.rect(screen, (200, 160, 40), pygame.Rect(_bar_x, _lcy, _fill_w, _bar_h), border_radius=4)
    pygame.draw.rect(screen, (120, 100, 40), pygame.Rect(_bar_x, _lcy, _bar_w, _bar_h), 1, border_radius=4)
    _xp_txt = font_s.render(f"{int(_xp_in_lv)} / {int(_xp_for_next)} XP", True, (150, 130, 60))
    screen.blit(_xp_txt, _xp_txt.get_rect(centerx=lp_x + lp_w // 2, top=_lcy + _bar_h + 2))
    _lcy += _bar_h + _xp_txt.get_height() + 10
    pygame.draw.line(screen, (60, 55, 80), (lp_x + 12, _lcy), (lp_x + lp_w - 12, _lcy))
    _lcy += 8

    for label, value, col in [
        ("Jogador:",     nickname,     (240, 220, 140)),
        ("País:",        country_name, (160, 190, 220)),
        ("Tempo Total:", playtime,     (140, 200, 140)),
        ("Criado em:",   created,      (140, 150, 160)),
    ]:
        ls = font_s.render(label, True, DIM)
        vs = font_m.render(value, True, col)
        screen.blit(ls, (lp_x + 14, _lcy))
        _lcy += ls.get_height() + 2
        screen.blit(vs, (lp_x + 20, _lcy))
        _lcy += vs.get_height() + 8

    _lcy += 4
    pygame.draw.line(screen, (60, 55, 80), (lp_x + 12, _lcy), (lp_x + lp_w - 12, _lcy))
    _lcy += 12

    stat_title = font_s.render("ESTATÍSTICAS:", True, GOLD)
    screen.blit(stat_title, (lp_x + 14, _lcy)); _lcy += stat_title.get_height() + 6

    st = save_data.get("stats", {})
    stats_pairs = [
        ("Abates Totais",  f'{st.get("total_kills",0):,}'.replace(",",".")),
        ("Chefões",        str(st.get("boss_kills", 0))),
        ("Mortes",         str(st.get("deaths", 0))),
        ("Partidas",       str(st.get("games_played", 0))),
        ("Nível Máximo",   str(st.get("max_level_reached", 0))),
    ]
    for lbl, val in stats_pairs:
        sl = font_s.render(f"{lbl}:", True, SILVER)
        sv = font_s.render(val, True, (200, 210, 180))
        screen.blit(sl, (lp_x + 14, _lcy))
        screen.blit(sv, sv.get_rect(right=lp_x + lp_w - 14, centery=_lcy + sl.get_height() // 2))
        _lcy += sl.get_height() + 5

    # ── Painel direito (conquistas) ───────────────────────────────────────
    rp_x = lp_x + lp_w + int(sw * 0.03)
    rp_w = sw - rp_x - int(sw * 0.04)
    rp_y = lp_y
    rp_h = lp_h
    rp_surf = pygame.Surface((rp_w, rp_h), pygame.SRCALPHA)
    rp_surf.fill((14, 10, 24, 220))
    screen.blit(rp_surf, (rp_x, rp_y))
    pygame.draw.rect(screen, GOLD, pygame.Rect(rp_x, rp_y, rp_w, rp_h), 2, border_radius=10)

    _rcy = rp_y + 16
    ach_title = font_l.render("CONQUISTAS", True, GOLD)
    screen.blit(ach_title, ach_title.get_rect(centerx=rp_x + rp_w // 2, top=_rcy))
    _rcy += ach_title.get_height() + 6

    counts = _ach.count_by_series(achievements_data)
    total_unlocked = sum(c[0] for c in counts.values())
    total_all = sum(c[1] for c in counts.values())
    count_surf = font_s.render(f"Desbloqueadas: {total_unlocked} / {total_all}", True, SILVER)
    screen.blit(count_surf, count_surf.get_rect(centerx=rp_x + rp_w // 2, top=_rcy))
    _rcy += count_surf.get_height() + 8
    pygame.draw.line(screen, GOLD, (rp_x + 12, _rcy), (rp_x + rp_w - 12, _rcy))
    _rcy += 14

    unlocked_ids = _ach.get_unlocked_set(achievements_data)
    ICON_SIZE = min(46, int(rp_w * 0.065))
    ICON_GAP  = max(4, int(ICON_SIZE * 0.12))
    SERIES_LABELS = {"gold": "OURO", "forte": "FORTE / BATALHA", "hardcore": "HARDCORE"}

    _pending_tt = None
    for series in _ach.SERIES_ORDER:
        defs = [a for a in _ach.ACHIEVEMENT_DEFS if a["series"] == series]
        un, tot = counts[series]
        lbl_s = font_s.render(f"{SERIES_LABELS.get(series, series.upper())}  ({un}/{tot})", True, GOLD)
        screen.blit(lbl_s, (rp_x + 14, _rcy))
        _rcy += lbl_s.get_height() + 6

        # Fileira de ícones
        row_x = rp_x + 14
        for a in defs:
            is_unlocked = a["id"] in unlocked_ids
            icon = _load_ach_icon(a["icon"], ICON_SIZE)
            icon_rect = pygame.Rect(row_x, _rcy, ICON_SIZE, ICON_SIZE)
            if icon:
                if not is_unlocked:
                    dim = pygame.Surface((ICON_SIZE, ICON_SIZE), pygame.SRCALPHA)
                    dim.fill((0, 0, 0, 160))
                    screen.blit(icon, icon_rect)
                    screen.blit(dim, icon_rect)
                else:
                    screen.blit(icon, icon_rect)
                    pygame.draw.rect(screen, GOLD, icon_rect, 1, border_radius=4)
            else:
                col_box = (60, 45, 15) if is_unlocked else (30, 25, 20)
                pygame.draw.rect(screen, col_box, icon_rect, border_radius=4)
                if is_unlocked:
                    pygame.draw.rect(screen, GOLD, icon_rect, 1, border_radius=4)

            # Tooltip ao hover
            if icon_rect.collidepoint(m_pos):
                _pending_tt = (icon_rect, a["name"], a["desc"], is_unlocked)

            row_x += ICON_SIZE + ICON_GAP
        _rcy += ICON_SIZE + 14

    if _pending_tt:
        _tt_rect, _tt_name, _tt_desc, _tt_unlocked = _pending_tt
        tt_lines = [_tt_name, _tt_desc]
        if not _tt_unlocked:
            tt_lines.append("[ Bloqueada ]")
        tt_w = max(font_s.size(l)[0] for l in tt_lines) + 16
        tt_h = len(tt_lines) * 20 + 10
        tt_x = min(_tt_rect.right + 6, sw - tt_w - 4)
        tt_y = max(4, _tt_rect.top - tt_h // 2)
        tt_s = pygame.Surface((tt_w, tt_h), pygame.SRCALPHA)
        tt_s.fill((20, 15, 30, 230))
        screen.blit(tt_s, (tt_x, tt_y))
        pygame.draw.rect(screen, GOLD, pygame.Rect(tt_x, tt_y, tt_w, tt_h), 1, border_radius=4)
        for li, line in enumerate(tt_lines):
            lc = GOLD if li == 0 else ((180, 170, 150) if li == 1 else (140, 100, 100))
            ls = font_s.render(line, True, lc)
            screen.blit(ls, (tt_x + 8, tt_y + 5 + li * 20))

    # ── Botão "Alterar Perfil" (só quando aberto pelo menu) ──────────────
    if show_change_btn:
        _alt_w, _alt_h = 200, 38
        _alt_r = pygame.Rect(lp_x + (lp_w - _alt_w) // 2, lp_y + lp_h - _alt_h - 12, _alt_w, _alt_h)
        _alt_hov = _alt_r.collidepoint(m_pos)
        _alt_bg = pygame.Surface((_alt_w, _alt_h), pygame.SRCALPHA)
        _alt_bg.fill((35, 28, 55, 220) if not _alt_hov else (52, 42, 80, 235))
        screen.blit(_alt_bg, _alt_r.topleft)
        pygame.draw.rect(screen, GOLD if _alt_hov else (120, 95, 45), _alt_r, 2, border_radius=6)
        _alt_s = font_s.render("ALTERAR PERFIL", True, GOLD if _alt_hov else (180, 150, 70))
        screen.blit(_alt_s, _alt_s.get_rect(center=_alt_r.center))
        _draw_profile_viewer._btn_alterar = _alt_r
    else:
        if hasattr(_draw_profile_viewer, "_btn_alterar"):
            del _draw_profile_viewer._btn_alterar

    # ── Avatar picker (grade flutuante de 48 ícones) ──────────────────
    if getattr(_draw_profile_viewer, "_av_picker_open", False):
        _pk_cols, _pk_icon = 8, 52
        _pk_pad = 6
        _pk_rows = 6  # 8×6 = 48
        _pk_w = _pk_cols * (_pk_icon + _pk_pad) + _pk_pad
        _pk_h = _pk_rows * (_pk_icon + _pk_pad) + _pk_pad + 32
        _pk_x = lp_x + lp_w + 12
        _pk_y = max(10, min(lp_y, sh - _pk_h - 10))
        if _pk_x + _pk_w > sw - 10:
            _pk_x = lp_x - _pk_w - 12
        _pk_bg = pygame.Surface((_pk_w, _pk_h), pygame.SRCALPHA)
        _pk_bg.fill((14, 10, 22, 240))
        screen.blit(_pk_bg, (_pk_x, _pk_y))
        pygame.draw.rect(screen, GOLD, pygame.Rect(_pk_x, _pk_y, _pk_w, _pk_h), 2, border_radius=8)
        _unlocked_count = ProfileManager.level_unlocked_avatars(_prof_lv)
        _pk_title = font_s.render(f"Escolha um avatar  ({_unlocked_count}/48 desbloqueados)", True, GOLD)
        screen.blit(_pk_title, _pk_title.get_rect(centerx=_pk_x + _pk_w // 2, top=_pk_y + 6))
        _draw_profile_viewer._av_picker_rects = []
        for _pi in range(48):
            _pc = _pi % _pk_cols; _pr = _pi // _pk_cols
            _pr_x = _pk_x + _pk_pad + _pc * (_pk_icon + _pk_pad)
            _pr_y = _pk_y + 30 + _pk_pad + _pr * (_pk_icon + _pk_pad)
            _pir = pygame.Rect(_pr_x, _pr_y, _pk_icon, _pk_icon)
            _pimg = _load_avatar_icon(_pi, _pk_icon)
            _psel = (_pi == av_idx)
            _phov = _pir.collidepoint(m_pos)
            _plocked = _pi >= _unlocked_count
            if not _plocked:
                _draw_profile_viewer._av_picker_rects.append((_pi, _pir))
            _pbg_col = (50, 40, 18, 200) if (_psel or _phov) and not _plocked else (25, 20, 12, 160)
            _pbgs = pygame.Surface((_pk_icon, _pk_icon), pygame.SRCALPHA)
            _pbgs.fill(_pbg_col)
            screen.blit(_pbgs, _pir.topleft)
            if _plocked:
                if _pimg:
                    _dim_img = _pimg.copy()
                    _dim_img.set_alpha(50)
                    screen.blit(_dim_img, _pir)
                _lock_s = font_s.render("🔒", True, (80, 70, 60))
                screen.blit(_lock_s, _lock_s.get_rect(center=_pir.center))
                pygame.draw.rect(screen, (50, 45, 35), _pir, 1, border_radius=4)
            else:
                if _pimg:
                    screen.blit(_pimg, _pir)
                else:
                    pygame.draw.rect(screen, _CHAR_COLORS[_pi % len(_CHAR_COLORS)], _pir, border_radius=4)
                _pborder = GOLD if _psel else ((180, 150, 60) if _phov else (60, 50, 30))
                pygame.draw.rect(screen, _pborder, _pir, 2 if (_psel or _phov) else 1, border_radius=4)

    # Dica fechar
    close_hint = "[ESC] para fechar" if show_change_btn else "[L] ou [ESC] para fechar"
    close_s = font_s.render(close_hint, True, DIM)
    screen.blit(close_s, close_s.get_rect(centerx=sw // 2, bottom=sh - 10))


def _draw_achievement_toast(screen, ach_def: dict, font_s, font_m):
    """Exibe toast de conquista desbloqueada no canto inferior-direito."""
    sw, sh = screen.get_size()
    if not _achievement_notifs:
        return
    remaining = _achievement_notifs[0][1]
    DURATION = 5.0
    alpha = 255
    if remaining < 0.8:
        alpha = int(255 * remaining / 0.8)
    elif remaining > DURATION - 0.5:
        alpha = int(255 * (DURATION - remaining) / 0.5)

    ICON_SIZE = 52
    PADDING = 12
    toast_w = int(sw * 0.28)
    toast_h = ICON_SIZE + PADDING * 2

    icon = _load_ach_icon(ach_def.get("icon", ""), ICON_SIZE)
    title_s = font_s.render("CONQUISTA DESBLOQUEADA!", True, (220, 190, 60))
    name_s  = font_m.render(ach_def.get("name", ""), True, (240, 230, 200))
    desc_s  = font_s.render(ach_def.get("desc", ""), True, (160, 150, 130))

    toast_h = max(toast_h, PADDING + title_s.get_height() + name_s.get_height() + desc_s.get_height() + PADDING)

    toast_surf = pygame.Surface((toast_w, toast_h), pygame.SRCALPHA)
    toast_surf.fill((20, 15, 30))
    pygame.draw.rect(toast_surf, (180, 150, 50), pygame.Rect(0, 0, toast_w, toast_h), 2, border_radius=10)

    ix = PADDING
    iy = (toast_h - ICON_SIZE) // 2
    if icon:
        toast_surf.blit(icon, (ix, iy))
    else:
        pygame.draw.rect(toast_surf, (80, 60, 20), pygame.Rect(ix, iy, ICON_SIZE, ICON_SIZE), border_radius=6)

    tx = ix + ICON_SIZE + 10
    ty = PADDING
    toast_surf.blit(title_s, (tx, ty))
    ty += title_s.get_height() + 2
    toast_surf.blit(name_s, (tx, ty))
    ty += name_s.get_height() + 2
    toast_surf.blit(desc_s, (tx, ty))

    toast_surf.set_alpha(alpha)
    tx_pos = sw - toast_w - 16
    ty_pos = sh - toast_h - 16
    screen.blit(toast_surf, (tx_pos, ty_pos))


def main():
    # Inicialização do Pygame e Mixer (Deve vir antes de apply_settings para o mixer funcionar)
    pygame.init()
    pygame.mixer.init()
    pygame.joystick.init()
    pygame.mouse.set_visible(False)   # esconde cursor do sistema; usamos cursor_img
    if pygame.joystick.get_count() > 0:
        _gamepad_connect(0)
    settings_category = "video"  # ou "audio" ou "controls"

    global settings
    settings = load_settings()
    apply_settings(settings)

    # Globais que serão modificados
    global screen, loader, snd_hover, snd_click, SFX, upg_images, menu_char_anims
    global PLAYER_MAX_HP, PROJECTILE_DMG, SHOT_COOLDOWN, PLAYER_SPEED, PROJECTILE_SPEED, PICKUP_RANGE, AURA_DMG, PROJ_COUNT, PROJ_PIERCE, EXPLOSION_RADIUS, ORB_COUNT, CRIT_CHANCE, EXECUTE_THRESH, HAS_FURY
    global CRIT_DMG_MULT, EXPLOSION_SIZE_MULT, REGEN_RATE, DAMAGE_RES, THORNS_PERCENT, FIRE_DMG_MULT, BURN_AURA_MULT, HAS_CHAOS_BOLT, HAS_INFERNO
    global selected_difficulty, selected_pact, selected_bg, current_bg_name, bg_choices
    global current_hardcore_stage, show_stage_victory, show_reward_dialog, _spawn_diff
    global reward_room_player_pos, reward_room_anim_t, reward_room_anim_idx, _reward_room_bg
    global player, enemies, projectiles, enemy_projectiles, gems, drops, particles, obstacles, puddles, damage_texts
    global kills, game_time, level, xp, shot_t, aura_t, aura_anim_timer, aura_frame_idx, orb_rot_angle
    global spawn_t, bosses_spawned, session_boss_kills, session_max_level, triggered_hordes
    global player_upgrades, has_bazuca, has_buraco_negro, has_serras, has_tesla, has_ceifador, has_berserk
    global chest_loot, chest_ui_timer, new_unlocks_this_session, up_options, up_keys, up_rarities, active_explosions
    global ground_img, menu_bg_img, aura_frames, explosion_frames_raw, projectile_frames_raw, slash_frames_raw, orb_img, tornado_img
    global PROJ_RICOCHET, temp_settings, settings_control_waiting, settings_dragging_slider
    global LIFESTEAL_PCT, GOLD_RUN_MULT, XP_BONUS_PCT, ORB_DMG, ORB_DISTANCE, EXPLOSION_DMG
    global obstacle_grid_index, enemy_batch_index, last_obstacle_count

    # Configuração da tela (Já feita no apply_settings, mas garantindo o caption)
    pygame.display.set_caption("UnderWorld Hero")
    clock = pygame.time.Clock()

    # Inicializar sistema de UI Scaler para responsividade (opcional, usar quando necessário)
    try:
        init_ui_scaler(base_res=(1920, 1080), current_res=(SCREEN_W, SCREEN_H))
    except Exception as e:
        print(f"[UI Scaler] Aviso: Falha ao inicializar UI Scaler: {e}")

    # Carregador de assets e sons
    loader = AssetLoader()
    snd_hover, snd_click = loader.load_sound("hover", 0.3), loader.load_sound("click", 0.6)
    SFX = {
        "shoot": loader.load_sound("sfx_shoot"),
        "slash": loader.load_sound("sfx_slash"),
        "hit": loader.load_sound("sfx_hit", 0.4),
        "hurt": loader.load_sound("sfx_hurt"),
        "dash": loader.load_sound("sfx_dash"),
        "gem": loader.load_sound("sfx_gem", 0.3),
        "drop": loader.load_sound("sfx_drop"),
        "levelup": loader.load_sound("sfx_levelup"),
        "explosion": loader.load_sound("sfx_explosion"),
        "ult": loader.load_sound("sfx_ult"),
        "win": loader.load_sound("sfx_win"),
        "lose": loader.load_sound("sfx_lose"),
        "unlock": loader.load_sound("sfx_levelup")
    }

    # Fontes — font_l usa Runewood (títulos puros), font_m/font_s usam Catholicon (texto+números)
    font_s = load_number_font(18, bold=True)
    font_m = load_number_font(28, bold=True)
    font_l = load_title_font(46, bold=True)

    obstacle_grid_index = ObstacleGridIndex(cell_size=WORLD_GRID)
    enemy_batch_index = EnemyBatchIndex()
    last_obstacle_count = 0

    # Inicializar botões de configurações (precisam das fontes)
    init_settings_buttons(font_m)

    # Carregar todos os assets gráficos com tela de carregamento
    def _load_everything():
        load_all_assets()
        init_menu_particles()

    show_splash_screen(screen)
    show_loading_screen(screen, _load_everything)

    # Criar todos os botões da interface
    # Menu reposicionado para o canto inferior esquerdo conforme imagem
    menu_btns = [
        Button(0.15, 0.53, BTN_W, BTN_H, "JOGAR",          font_m, color=(32, 86, 52), hover_color=(48, 120, 70)),
        Button(0.15, 0.59, BTN_W, BTN_H, "MISSÕES",        font_m),
        Button(0.15, 0.65, BTN_W, BTN_H, "TALENTOS",       font_m),
        Button(0.15, 0.71, BTN_W, BTN_H, "CONFIGURAÇÕES",  font_m),
        Button(0.15, 0.77, BTN_W, BTN_H, "SAIR",           font_m, color=(80, 30, 30), hover_color=(120, 42, 42)),
    ]
    menu_icons = ["play", "missions", "talents", "settings", "exit"]
    for idx, (btn, icon) in enumerate(zip(menu_btns, menu_icons)):
        btn.icon = load_menu_icon_surface(loader, icon, size=(20, 20))
        btn.sprite_idx = idx % 7

    menu_preview_map = {
        "JOGAR": ("Iniciar Jornada", "Selecione heroi, dificuldade e pacto para começar uma nova run de sobrevivencia."),
        "MISSÕES": ("Rotina Diaria", "Acompanhe objetivos diarios, resgate recompensas e acelere sua progressao."),
        "TALENTOS": ("Arvore de Talentos", "Invista ouro em melhorias permanentes e desbloqueie builds mais fortes."),
        "CONFIGURAÇÕES": ("Ajustes do Jogo", "Video, audio, controles e acessibilidade com aplicacao imediata."),
        "SAIR": ("Encerrar", "Salva progresso atual e fecha o jogo com seguranca."),
    }
    _menu_site_url = "https://underworld-hero-landing.vercel.app/"
    _ext_btn_w = max(200, int(SCREEN_W * 0.13))
    _ext_btn_h = _ext_btn_w * 2 // 3
    _ext_gap = max(20, int(SCREEN_W * 0.02))
    _ext_btn_y = SCREEN_H - _ext_btn_h - 10
    menu_site_rect = pygame.Rect(SCREEN_W // 2 - _ext_btn_w - _ext_gap // 2, _ext_btn_y, _ext_btn_w, _ext_btn_h)
    menu_steam_rect = pygame.Rect(SCREEN_W // 2 + _ext_gap // 2, _ext_btn_y, _ext_btn_w, _ext_btn_h)

    saves_slot_btns = [
        Button(0.5, 0.35, BTN_W, BTN_H, "SLOT 1", font_m),
        Button(0.5, 0.47, BTN_W, BTN_H, "SLOT 2", font_m),
        Button(0.5, 0.59, BTN_W, BTN_H, "SLOT 3", font_m),
    ]
    for i, btn in enumerate(saves_slot_btns):
        btn.sprite_idx = i

    saves_back_btn = Button(0.5, 0.90, BTN_SM_W, BTN_SM_H, "VOLTAR", font_m, color=(80, 30, 30))
    saves_back_btn.sprite_idx = 6

    mission_btns = [Button(0.5, 0.90, BTN_SM_W, BTN_SM_H, "VOLTAR", font_m, color=(80, 30, 30))]
    mission_btns[0].sprite_idx = 6
    mission_claim_btns = [
        Button(0.75, 0.25 + i * 0.10, BTN_SM_W, BTN_H, "COLETAR", font_m, color=(40, 100, 40))
        for i in range(6)
    ]
    for btn in mission_claim_btns:
        btn.sprite_idx = 3

    # Layout compartilhado da tela de talentos para manter painel, textos e botões sincronizados.
    SHOP_PATH_TOP_RATIO = 0.18
    SHOP_PATH_GAP_RATIO = 0.26
    SHOP_SKILL_TOP_OFFSET = 78
    SHOP_SKILL_GAP = 42
    SHOP_ROW_PANEL_HEIGHT = 250
    SHOP_BTN_X_RATIO = 0.80
    SHOP_BTN_Y_OFFSET = 11

    shop_back_btn = Button(0.5, 0.93, BTN_SM_W, BTN_SM_H, "VOLTAR", font_m, color=(80, 30, 30))
    shop_back_btn.sprite_idx = 6

    # Loja de Itens
    item_shop_back_btn = Button(0.5, 0.93, BTN_SM_W, BTN_SM_H, "VOLTAR", font_m, color=(80, 30, 30))
    item_shop_back_btn.sprite_idx = 6
    item_shop_tab_btns = []
    _tab_w = max(180, SCREEN_W // (len(ITEM_SHOP_TABS) + 1))
    for _ti, _tlabel in enumerate(ITEM_SHOP_TABS):
        _tx = int(SCREEN_W * 0.15) + _ti * (_tab_w + 10)
        _btn = Button(0, 0, _tab_w, 42, _tlabel, font_s,
                      color=(40, 35, 30), hover_color=(70, 60, 40))
        _btn.rect.topleft = (_tx, int(SCREEN_H * 0.13))
        _btn.sprite_idx = _ti % 7
        item_shop_tab_btns.append(_btn)
    item_shop_active_tab    = 0
    item_shop_scroll_y      = 0       # posição de scroll em pixels
    item_shop_sell_selected = None    # item selecionado para vender: {"item":{cat,idx},"source","cid"}
    item_shop_sell_confirm  = None    # item aguardando confirmação de venda: {"entry":{...},"price":int,"st":{...}}
    item_shop_confirm       = None    # item aguardando confirmação de compra: {category,idx,price,name,st}
    _item_shop_img_cache    = {}      # cache de imagens da loja
    shop_talent_btns = []
    shop_talent_btn_map = {}
    path_names = list(TALENT_TREE.keys())
    for p_idx, p_name in enumerate(path_names):
        path = TALENT_TREE[p_name]
        skill_keys = list(path["skills"].keys())
        for s_idx, s_key in enumerate(skill_keys):
            bx = SHOP_BTN_X_RATIO
            by = SHOP_PATH_TOP_RATIO + p_idx * SHOP_PATH_GAP_RATIO + 0.09 + s_idx * 0.045
            btn = Button(bx, by, 150, 38, "COMPRAR", font_s, color=(40, 80, 40))
            shop_talent_btns.append((p_name, s_key, btn))
            shop_talent_btn_map[(p_name, s_key)] = btn

    def update_shop_talent_button_layout():
        for p_idx, p_name in enumerate(path_names):
            py = int(SCREEN_H * (SHOP_PATH_TOP_RATIO + p_idx * SHOP_PATH_GAP_RATIO))
            skill_keys = list(TALENT_TREE[p_name]["skills"].keys())
            for s_idx, s_key in enumerate(skill_keys):
                sy = py + SHOP_SKILL_TOP_OFFSET + s_idx * SHOP_SKILL_GAP
                shop_talent_btn_map[(p_name, s_key)].rect.center = (
                    int(SCREEN_W * SHOP_BTN_X_RATIO),
                    sy + SHOP_BTN_Y_OFFSET,
                )

    update_shop_talent_button_layout()

    char_btns = []
    char_back_btn = Button(0.5, 0.92, BTN_SM_W, BTN_SM_H, "VOLTAR", font_m, color=(80, 30, 30))
    char_back_btn.sprite_idx = 6
    for i, (char_id, char_data) in enumerate(CHAR_DATA.items()):
        x_ratio = 0.25 + i * 0.25
        locked = char_data["id"] not in save_data["unlocks"]
        lock_req = ACHIEVEMENTS.get(char_data["id"], {}).get("desc", "") if locked else ""
        btn = Button(x_ratio, 0.78, BTN_W, BTN_H, char_data["name"], font_m,
                     locked=locked, lock_req=lock_req)
        btn.sprite_idx = i % 7
        btn.x_ratio = x_ratio
        char_btns.append(btn)

    diff_btns = []
    diff_back_btn = Button(0.5, 0.92, BTN_SM_W, BTN_SM_H, "VOLTAR", font_m, color=(80, 30, 30))
    diff_back_btn.sprite_idx = 6
    diff_order = ["FÁCIL", "MÉDIO", "DIFÍCIL", "HARDCORE"]
    for i, diff_name in enumerate(diff_order):
        diff_data = DIFFICULTIES[diff_name]
        locked = diff_data["id"] not in save_data["unlocks"]
        lock_req = ACHIEVEMENTS.get(diff_data["id"], {}).get("desc", "") if locked else ""
        diff_btns.append(Button(0.5, 0.30 + i * 0.13, BTN_W, BTN_H,
                                diff_name, font_m,
                                color=(30, 60, 30),
                                subtext=diff_data["desc"],
                                locked=locked, lock_req=lock_req))
    # Sincronizar hit-box com sprites de dificuldade (têm design próprio)
    for i, (btn, key) in enumerate(zip(diff_btns, diff_order)):
        btn.sprite_idx = i
        spr_key = "HARDCORE_UNLOCK" if key == "HARDCORE" and diff_screen_imgs.get("HARDCORE_UNLOCK") else key
        spr = diff_screen_imgs.get(spr_key) or diff_screen_imgs.get(key)
        if spr:
            btn.w, btn.h = spr.get_size()
            btn.rect = pygame.Rect(0, 0, btn.w, btn.h)
            btn.update_rect()
    _vs = diff_screen_imgs.get("VOLTAR")
    if _vs:
        diff_back_btn.w, diff_back_btn.h = _vs.get_size()
        diff_back_btn.rect = pygame.Rect(0, 0, diff_back_btn.w, diff_back_btn.h)
        diff_back_btn.update_rect()

    pact_btns = []
    pact_back_btn = Button(0.5, 0.92, BTN_SM_W, BTN_SM_H, "VOLTAR", font_m, color=(80, 30, 30))
    pact_back_btn.sprite_idx = 6
    for i, (pact_name, pact_data) in enumerate(PACTOS.items()):
        btn = Button(0.5, 0.27 + i * 0.16, BTN_W, BTN_H,
                     pact_data["name"], font_m,
                     color=(40, 20, 60))
        btn.sprite_idx = i % 7
        pact_btns.append(btn)

    bg_btns = []
    bg_back_btn = Button(0.5, 0.92, BTN_SM_W, BTN_SM_H, "VOLTAR", font_m, color=(80, 30, 30))
    bg_back_btn.sprite_idx = 6
    bg_choices = list(BG_DATA.keys())
    for i, bg_key in enumerate(bg_choices):
        is_locked = bg_key in BG_LOCKED
        label = bg_key.upper() + (" 🔒 EM BREVE" if is_locked else "")
        btn = Button(0.5, 0.28 + i * 0.14, BTN_W, BTN_H, label, font_m,
                     locked=is_locked, lock_req="Em breve!" if is_locked else "")
        btn.sprite_idx = i % 7
        bg_btns.append(btn)

    pause_btns = [
        Button(0.5, 0.50, BTN_W, BTN_H, "CONTINUAR",        font_m, color=(30, 80, 30)),
        Button(0.5, 0.62, BTN_W, BTN_H, "VOLTAR PARA ROOM", font_m, color=(30, 50, 90)),
        Button(0.5, 0.74, BTN_W, BTN_H, "MENU PRINCIPAL",   font_m, color=(80, 30, 30)),
    ]
    pause_btns[0].sprite_idx = 0
    pause_btns[1].sprite_idx = 2
    pause_btns[2].sprite_idx = 6
    pause_save_btns = [
        Button(0.70, 0.54, BTN_SM_W, BTN_H, "SALVAR SLOT 1", font_s, color=(35, 80, 35)),
        Button(0.70, 0.61, BTN_SM_W, BTN_H, "SALVAR SLOT 2", font_s, color=(35, 80, 35)),
        Button(0.70, 0.68, BTN_SM_W, BTN_H, "SALVAR SLOT 3", font_s, color=(35, 80, 35)),
    ]
    for i, btn in enumerate(pause_save_btns):
        btn.sprite_idx = i + 1
    game_over_btn = Button(0.5, 0.78, BTN_W, BTN_H, "SAIR", font_m, color=(80, 30, 30))
    game_over_btn.sprite_idx = 6

    # ── Sistema de Perfis ─────────────────────────────────────────────────
    global profile_mgr, achievements_data, _achievement_notifs, _ach_icon_cache, _avatar_icon_cache
    profile_mgr = ProfileManager()
    _achievement_notifs = []
    _ach_icon_cache = {}
    _avatar_icon_cache = {}

    # Estado da tela de seleção/criação de perfil
    _prof_mode       = "create" if not profile_mgr.has_profiles() else "list"
    _prof_sel_idx    = 0
    _prof_new_name   = ""
    _prof_new_ci     = 0   # índice do país em COUNTRIES
    _prof_new_char   = 0   # personagem do avatar
    _prof_name_focus = True
    _prof_del_confirm = None  # id do perfil aguardando confirmação de delete

    # Variáveis de estado do jogo
    state = "PROFILE_SELECT"
    running = True
    m_pos = (0, 0)
    hitstop_timer = 0.0
    shake_timer = 0.0
    shake_strength = 0
    shake_offset = pygame.Vector2(0, 0)
    up_options = []
    run_gold_collected = 0.0
    autosave_timer = 0.0
    autosave_feedback_timer = 0.0
    pause_save_feedback_timer = 0.0
    current_xp_to_level = XP_TO_LEVEL_BASE
    
    # Inicializa temp_settings para evitar UnboundLocalError
    temp_settings = json.loads(json.dumps(settings))

    # Loop principal refatorado
    last_res = (SCREEN_W, SCREEN_H)
    debug_overlay_on = False
    transition_timer = 0.0
    prev_state = state
    menu_intro_timer = MENU_ENTER_DURATION
    menu_exit_timer = 0.0
    menu_pending_action = None
    _menu_profile_widget_rect = None
    _hub_profile_widget_rect = None

    # Hub Room state
    hub_scene: HubScene | None = None
    hub_countdown_active = False
    hub_countdown_timer  = 0.0
    hub_last_char_id     = 0   # char_id da última partida iniciada pelo HUB
    hub_pronto_btn = Button(0.920, 0.562, 200, BTN_H, "PRONTO", font_m, color=(30, 80, 30))
    hub_return         = False   # True when SHOP/ITEM_SHOP was opened from HUB
    market_return      = False   # True when ITEM_SHOP was opened from MARKET via Ferreiro
    market_shop_open   = False   # Overlay flutuante de Talentos no Mercado
    market_missions_open = False # Overlay flutuante de Missões no Mercado
    hub_chest_open     = False   # Janela do Baú (F key — abre baú + inventário)
    _chest_tab         = "itens" # Aba ativa do baú: "itens" | "minerios"
    hub_equip_open     = False   # Janela de Equipamento (I key — layout Diablo)
    hub_status_open    = False   # Janela de Status (C key)
    hub_profile_open   = False   # Janela de Perfil/Conquistas (L key)
    market_scene: MarketScene | None = None   # Cena do Mercado (carregada na primeira visita)
    menu_profile_open  = False   # Overlay de Perfil/Conquistas no MENU
    # Mensagem de erro de equipamento (nível insuficiente)
    _equip_err_msg       = ""
    _equip_err_msg_start = 0
    # Crafting (FERREIRO)
    craft_open        = False          # Janela de Crafting do Ferreiro
    _craft_slots: list= [None, None, None]  # 3 slots de ingredientes
    _craft_selected: tuple = ("Espadas Lendárias", 0)  # (categoria, idx) da receita selecionada
    _craft_img_cache: dict = {}
    _craft_scroll_y: int = 0          # scroll da lista de receitas
    # Drag-and-drop: item sendo arrastado com o mouse
    _drag_item: dict | None = None   # {"item":{...}, "from":"chest"|"inventory"|"equip"|"craft_slot", "_idx":int, "_slot":str|None}
    _drag_active: bool = False       # True enquanto o botão do mouse está pressionado
    _drag_offset: tuple = (0, 0)     # offset do centro do item até o cursor no início do drag
    _discard_confirm: dict | None = None  # item aguardando confirmação de descarte
    # Cache da imagem do painel de inventário escalada
    _inv_panel_cache: dict = {}      # {scale_key: scaled_surface}
    _sala_heroi_cache: dict = {}     # {(w,h): scaled_surface}
    _status_panel_cache: dict = {}   # {(w,h): scaled_surface}

    # Fila de horda e obstáculos graduais (inicializados aqui para o caso
    # de o loop começar antes de reset_game ser chamado)
    pending_horde_queue    = []
    obstacle_spawn_t       = 0.0
    obstacle_spawn_interval = 18.0
    obstacle_total_placed  = 0
    OBSTACLE_MAX_GRADUAL   = 28
    _dt_history = [1/60.0] * 6  # média móvel para suavizar micro-stutters
    _dt_idx = 0
    _bg_cache = None        # surface pré-renderizada do chão (invalida ao trocar bioma)
    _bg_cache_src = None    # referência ao ground_img que gerou o cache
    _sep_frame = 0          # throttle: separação de inimigos roda em frames alternados
    SEP_DIST  = 52
    SEP_FORCE = 18.0

    # Console in-game (temporário) para comandos de criador.
    _dev_console_open = False
    _dev_console_input = ""
    _dev_console_msg = ""
    _dev_console_msg_timer = 0.0

    def _is_creator_cheat_enabled() -> bool:
        # Libera no ambiente local do criador (username do SO) e também por nickname do perfil.
        _os_user = os.environ.get("USERNAME", "").strip().lower()
        if _os_user in {"athed"}:
            return True
        if profile_mgr is not None and profile_mgr.has_active_profile():
            _p = profile_mgr.get_active_profile() or {}
            _nick = str(_p.get("nickname", "")).strip().lower()
            if "xinoqs" in _nick:
                return True
        return False

    while running:
        # 1. Delta Time (dt) com clamp e smoothing por média móvel (6 frames)
        PERF.begin_frame()
        dt_raw = clock.tick(FPS) / 1000.0
        dt_clamped = min(dt_raw, 1/30.0)  # evita bugs de física com lag severo
        _dt_history[_dt_idx] = dt_clamped
        _dt_idx = (_dt_idx + 1) % 6
        dt = sum(_dt_history) / 6

        if _dev_console_msg_timer > 0.0:
            _dev_console_msg_timer = max(0.0, _dev_console_msg_timer - dt_raw)

        if pause_save_feedback_timer > 0:
            pause_save_feedback_timer = max(0.0, pause_save_feedback_timer - dt_raw)
        if autosave_feedback_timer > 0:
            autosave_feedback_timer = max(0.0, autosave_feedback_timer - dt_raw)
        
        # Atualiza posição do mouse
        m_pos = pygame.mouse.get_pos()

        # Controle de cursor pelo analógico esquerdo / D-Pad (menus)
        if _joy is not None and state not in ("PLAYING", "PAUSED", "UPGRADE"):
            _cx = _joy_axis(0); _cy = _joy_axis(1)
            _hx, _hy = _joy_hat()
            if _cx == 0.0: _cx = _hx * 0.5
            if _cy == 0.0: _cy = -_hy * 0.5
            if _cx or _cy:
                _nx = max(0, min(SCREEN_W - 1, int(m_pos[0] + _cx * 600 * dt_raw)))
                _ny = max(0, min(SCREEN_H - 1, int(m_pos[1] + _cy * 600 * dt_raw)))
                pygame.mouse.set_pos(_nx, _ny)
                m_pos = (_nx, _ny)

        if state == "SHOP":
            update_shop_talent_button_layout()

        # Se a resolução mudou, atualiza a posição de todos os botões
        if (SCREEN_W, SCREEN_H) != last_res:
            last_res = (SCREEN_W, SCREEN_H)
            init_menu_particles()
            for b in menu_btns: b.update_rect()
            for b in saves_slot_btns: b.update_rect()
            saves_back_btn.update_rect()
            for b in mission_btns: b.update_rect()
            for b in mission_claim_btns: b.update_rect()
            shop_back_btn.update_rect()
            for _, _, b in shop_talent_btns: b.update_rect()
            for b in char_btns: b.update_rect()
            char_back_btn.update_rect()
            for b in diff_btns: b.update_rect()
            diff_back_btn.update_rect()
            for b in pact_btns: b.update_rect()
            pact_back_btn.update_rect()
            for b in bg_btns: b.update_rect()
            bg_back_btn.update_rect()
            hub_pronto_btn.update_rect()
            for b in pause_btns: b.update_rect()
            for b in pause_save_btns: b.update_rect()
            game_over_btn.update_rect()
            for b in settings_main_btns: b.update_rect()
            for b in settings_action_btns.values(): b.update_rect()

        # Lógica de Hit-Stop
        if hitstop_timer > 0:
            hitstop_timer -= dt_raw
            dt = 0 # Pausa a lógica do jogo, mas continua desenhando

        # 2. Manipulação de Eventos
        for event in pygame.event.get():
            if event.type == pygame.QUIT: 
                save_run_slot(0)
                save_game()
                running = False
            
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_F3:
                    debug_overlay_on = not debug_overlay_on

                # Toggle do console com a tecla ' (apóstrofo).
                if event.key == pygame.K_QUOTE or (event.unicode in ("'", '"')):
                    _dev_console_open = not _dev_console_open
                    if _dev_console_open:
                        _dev_console_input = ""
                        _dev_console_msg = ""
                    if snd_click:
                        snd_click.play()
                    continue

                # Quando console está aberto, ele consome o teclado.
                if _dev_console_open:
                    if event.key == pygame.K_ESCAPE:
                        _dev_console_open = False
                        continue

                    if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                        _cmd = _dev_console_input.strip().lower()
                        _dev_console_input = ""

                        if _cmd == "":
                            _dev_console_msg = "Digite um comando."
                        elif _cmd == "recompensa":
                            if not _is_creator_cheat_enabled():
                                _dev_console_msg = "Sem permissao para este comando."
                            elif state != "PLAYING" or player is None:
                                _dev_console_msg = "Use durante a run (estado PLAYING)."
                            else:
                                show_reward_dialog = False
                                _reward_room_bg = None
                                try:
                                    _rr_path = os.path.join(ASSET_DIR, "Teste", "recompensa", "sala_recompença.png")
                                    _raw_rr = pygame.image.load(_rr_path).convert_alpha()
                                    _reward_room_bg = pygame.transform.smoothscale(_raw_rr, (SCREEN_W, SCREEN_H))
                                except Exception:
                                    pass
                                reward_room_player_pos = pygame.Vector2(SCREEN_W // 2, int(SCREEN_H * 0.65))
                                reward_room_anim_t = 0.0
                                reward_room_anim_idx = 0
                                hub_equip_open = False
                                hub_status_open = False
                                _mining_system = MiningSystem(SCREEN_W, SCREEN_H,
                                                              selected_difficulty, current_hardcore_stage)
                                _mining_system.spawn_ores()
                                save_game()
                                state = "REWARD_ROOM"
                                push_skill_feed("CONSOLE: Sala de recompensa", (255, 215, 80))
                                _dev_console_msg = "Teleportado para sala de recompensa."
                                _dev_console_open = False
                                if snd_click:
                                    snd_click.play()
                        else:
                            _dev_console_msg = f"Comando desconhecido: {_cmd}"

                        _dev_console_msg_timer = 2.5
                        continue

                    if event.key == pygame.K_BACKSPACE:
                        _dev_console_input = _dev_console_input[:-1]
                        continue

                    _ch = event.unicode or ""
                    if _ch.isprintable() and _ch not in ("\r", "\n"):
                        _dev_console_input += _ch
                        _dev_console_input = _dev_console_input[:48]
                    continue

                if state == "SETTINGS" and settings_category == "controls" and settings_control_waiting:
                    if event.key == pygame.K_ESCAPE:
                        settings_control_waiting = None
                    else:
                        if "controls" not in temp_settings or not isinstance(temp_settings["controls"], dict):
                            temp_settings["controls"] = _deepcopy_settings(load_settings(force_default=True))["controls"]
                        if settings_control_waiting in temp_settings["controls"]:
                            temp_settings["controls"][settings_control_waiting] = pygame.key.name(event.key)
                            settings = _deepcopy_settings(temp_settings)
                            save_settings(settings)
                        settings_control_waiting = None
                        if snd_click: snd_click.play()
                    continue

                if state == "UPGRADE":
                    selected_idx = None
                    if event.key in [pygame.K_1, pygame.K_KP1]:
                        selected_idx = 0
                    elif event.key in [pygame.K_2, pygame.K_KP2]:
                        selected_idx = 1
                    elif event.key in [pygame.K_3, pygame.K_KP3]:
                        selected_idx = 2
                    elif event.key in [pygame.K_4, pygame.K_KP4]:
                        selected_idx = 3
                    elif event.key in [pygame.K_5, pygame.K_KP5]:
                        selected_idx = 4
                    elif event.key in [pygame.K_RETURN, pygame.K_KP_ENTER] and len(up_keys) > 0:
                        selected_idx = 0

                    if selected_idx is not None and selected_idx < len(up_keys):
                        if snd_click: snd_click.play()
                        apply_upgrade(up_keys[selected_idx])
                        up_options = []
                        up_keys = []
                        up_rarities = []
                        state = "PLAYING"
                        continue

                if state == "HUB" and event.key == pygame.K_f:
                    if hub_chest_open:
                        hub_chest_open = False
                        _drag_item = None; _drag_active = False
                        if snd_click: snd_click.play()
                    elif hub_scene is not None and hub_scene.player_near_chest:
                        hub_chest_open = True
                        _chest_tab = "itens"
                        _drag_item = None; _drag_active = False
                        if snd_click: snd_click.play()

                if state == "MARKET" and event.key == pygame.K_f:
                    if (market_scene is not None and market_scene.player_near_ferreiro
                            and not hub_status_open and not hub_profile_open):
                        craft_open = not craft_open
                        if craft_open:
                            hub_equip_open = True
                            _craft_slots   = [None, None, None]
                            _craft_scroll_y = 0
                        else:
                            hub_equip_open = False
                            _craft_slots   = [None, None, None]
                        _drag_item = None; _drag_active = False
                        if snd_click: snd_click.play()
                    elif (market_scene is not None and market_scene.player_near_loja
                            and not hub_status_open and not hub_profile_open
                            and not craft_open):
                        state = "ITEM_SHOP"
                        market_return = True
                        hub_equip_open = False
                        _drag_item = None; _drag_active = False
                        if snd_click: snd_click.play()

                if (state == "REWARD_ROOM" and event.key == pygame.K_f
                        and _mining_system is not None
                        and not hub_equip_open and not hub_status_open
                        and reward_room_player_pos is not None):
                    _mining_system.try_start_mining(reward_room_player_pos)

                if state in ("HUB", "MARKET", "REWARD_ROOM") and event.key == pygame.K_i:
                    hub_equip_open = not hub_equip_open
                    _drag_item = None; _drag_active = False
                    if state == "REWARD_ROOM" and _mining_system is not None:
                        _mining_system.cancel_mining()
                    if snd_click: snd_click.play()

                if state in ("HUB", "MARKET", "REWARD_ROOM") and event.key == pygame.K_c:
                    hub_status_open = not hub_status_open
                    if state == "REWARD_ROOM" and _mining_system is not None:
                        _mining_system.cancel_mining()
                    if snd_click: snd_click.play()

                if state in ("HUB", "MARKET") and event.key == pygame.K_l:
                    hub_profile_open = not hub_profile_open
                    if snd_click: snd_click.play()

                # ── Teclado na tela de Seleção de Perfil ─────────────────
                if state == "PROFILE_SELECT":
                    if _prof_mode == "create":
                        if event.key == pygame.K_RETURN or event.key == pygame.K_KP_ENTER:
                            if _prof_new_name.strip():
                                _country_code = COUNTRIES[_prof_new_ci][0]
                                profile_mgr.create_profile(_prof_new_name.strip(), _country_code, _prof_new_char)
                                # Reseta save_data para defaults e recarrega do perfil novo
                                save_data.update({
                                    "gold": 0, "perm_upgrades": {k: 0 for k in save_data["perm_upgrades"]},
                                    "stats": {"total_kills": 0, "total_time": 0, "boss_kills": 0,
                                              "deaths": 0, "games_played": 0, "max_level_reached": 0},
                                    "unlocks": list(DEFAULT_UNLOCKS), "daily_missions": {"last_reset": "", "active": []},
                                    "purchased_items": [], "chest_items": [], "char_inventories": {},
                                    "char_equipped": {}, "hardcore_stages": {"unlocked": 1},
                                    "beaten_difficulties": [],
                                })
                                load_save()
                                _reload_achievements()
                                for _bi2, _bk2 in enumerate(diff_order):
                                    diff_btns[_bi2].locked = DIFFICULTIES[_bk2]["id"] not in save_data["unlocks"]
                                _prof_mode = "list"; _prof_sel_idx = len(profile_mgr.get_all_profiles()) - 1
                                state = "MENU"
                                menu_intro_timer = MENU_ENTER_DURATION
                        elif event.key == pygame.K_ESCAPE:
                            if profile_mgr.has_profiles():
                                _prof_mode = "list"
                        elif event.key == pygame.K_BACKSPACE:
                            _prof_new_name = _prof_new_name[:-1]
                        elif event.key == pygame.K_TAB:
                            pass  # foco já está no nome
                        elif event.unicode and event.unicode.isprintable() and _prof_name_focus:
                            if len(_prof_new_name) < 16:
                                _prof_new_name += event.unicode
                    elif _prof_mode == "list":
                        profiles_list = profile_mgr.get_all_profiles()
                        if event.key == pygame.K_RETURN or event.key == pygame.K_KP_ENTER:
                            if profiles_list:
                                pid = profiles_list[_prof_sel_idx]["id"]
                                profile_mgr.select_profile(pid)
                                save_data.update({
                                    "gold": 0, "perm_upgrades": {k: 0 for k in save_data["perm_upgrades"]},
                                    "stats": {"total_kills": 0, "total_time": 0, "boss_kills": 0,
                                              "deaths": 0, "games_played": 0, "max_level_reached": 0},
                                    "unlocks": list(DEFAULT_UNLOCKS), "daily_missions": {"last_reset": "", "active": []},
                                    "purchased_items": [], "chest_items": [], "char_inventories": {},
                                    "char_equipped": {}, "hardcore_stages": {"unlocked": 1},
                                    "beaten_difficulties": [],
                                })
                                load_save()
                                _reload_achievements()
                                for _bi2, _bk2 in enumerate(diff_order):
                                    diff_btns[_bi2].locked = DIFFICULTIES[_bk2]["id"] not in save_data["unlocks"]
                                state = "MENU"
                                menu_intro_timer = MENU_ENTER_DURATION
                        elif event.key == pygame.K_LEFT:
                            if profiles_list:
                                _prof_sel_idx = (_prof_sel_idx - 1) % len(profiles_list)
                        elif event.key == pygame.K_RIGHT:
                            if profiles_list:
                                _prof_sel_idx = (_prof_sel_idx + 1) % len(profiles_list)
                        elif event.key == pygame.K_ESCAPE:
                            if profile_mgr.has_profiles():
                                state = "MENU"
                                menu_intro_timer = MENU_ENTER_DURATION
                    elif _prof_mode == "edit":
                        if event.key == pygame.K_RETURN or event.key == pygame.K_KP_ENTER:
                            if _prof_new_name.strip():
                                all_ps = profile_mgr.get_all_profiles()
                                if _prof_sel_idx < len(all_ps):
                                    pid = all_ps[_prof_sel_idx]["id"]
                                    profile_mgr.update_nickname(pid, _prof_new_name.strip())
                                    profile_mgr.update_country(pid, COUNTRIES[_prof_new_ci][0])
                                    profile_mgr.update_avatar(pid, _prof_new_char)
                                    _avatar_icon_cache.clear()
                                    _prof_mode = "list"
                        elif event.key == pygame.K_ESCAPE:
                            _prof_mode = "list"
                        elif event.key == pygame.K_BACKSPACE:
                            _prof_new_name = _prof_new_name[:-1]
                        elif event.unicode and event.unicode.isprintable() and _prof_name_focus:
                            if len(_prof_new_name) < 16:
                                _prof_new_name += event.unicode

                if event.key == pygame.K_ESCAPE:
                    if state == "MENU" and menu_profile_open:
                        if getattr(_draw_profile_viewer, "_av_picker_open", False):
                            _draw_profile_viewer._av_picker_open = False
                        else:
                            menu_profile_open = False
                    elif state == "MARKET":
                        if market_shop_open:
                            market_shop_open = False
                            save_game()
                        elif market_missions_open:
                            market_missions_open = False
                        elif craft_open:
                            craft_open     = False
                            hub_equip_open = False
                            _craft_slots   = [None, None, None]
                            _drag_item = None; _drag_active = False
                        elif hub_chest_open or hub_equip_open or hub_status_open or hub_profile_open:
                            hub_chest_open   = False
                            hub_equip_open   = False
                            hub_status_open  = False
                            hub_profile_open = False
                            craft_open       = False
                            _craft_slots     = [None, None, None]
                            _drag_item       = None
                            _drag_active     = False
                        else:
                            craft_open   = False
                            _craft_slots = [None, None, None]
                            state = "HUB"
                    elif state == "HUB":
                        if hub_chest_open or hub_equip_open or hub_status_open or hub_profile_open:
                            hub_chest_open   = False
                            hub_equip_open   = False
                            hub_status_open  = False
                            hub_profile_open = False
                            _drag_item       = None
                            _drag_active     = False
                        else:
                            hub_countdown_active = False
                            hub_countdown_timer  = 0.0
                            state = "PACT_SELECT"
                    elif state == "REWARD_ROOM":
                        if _mining_system is not None:
                            _mining_system.cancel_mining()
                        if hub_equip_open or hub_status_open:
                            hub_equip_open  = False
                            hub_status_open = False
                            _drag_item = None; _drag_active = False
                        else:
                            hub_equip_open  = False
                            hub_status_open = False
                            _drag_item = None; _drag_active = False
                            save_game()
                            state = "HUB"
                    elif state == "PLAYING": state = "PAUSED"
                    elif state == "PAUSED": state = "PLAYING"
                    elif state == "SETTINGS":
                        if settings_category == "main":
                            state = "MENU"
                        else:
                            settings_category = "main"
                            temp_settings = json.loads(json.dumps(settings))
                    elif state in ["CHAR_SELECT", "MISSIONS", "BG_SELECT", "SAVES"]:
                        state = "MENU"
                    elif state in ["SHOP", "ITEM_SHOP"]:
                        if item_shop_sell_confirm is not None:
                            item_shop_sell_confirm  = None
                            item_shop_sell_selected = None
                        elif item_shop_confirm is not None:
                            item_shop_confirm = None
                        elif market_return and market_scene is not None:
                            market_return = False
                            state = "MARKET"
                        elif hub_return and hub_scene is not None:
                            hub_return = False
                            state = "HUB"
                        else:
                            state = "MENU"
                    elif state == "DIFF_SELECT":
                        state = "CHAR_SELECT"
                    elif state == "PACT_SELECT":
                        state = "DIFF_SELECT"
                
                if event.key == get_control_key_code("pause"):
                    if state == "PLAYING": state = "PAUSED"
                    elif state == "PAUSED": state = "PLAYING"
                
                if event.key == get_control_key_code("dash"):
                    if state == "PLAYING" and player:
                        dash_feedback = player.start_dash(particles)
                        if dash_feedback.activated:
                            play_sfx(dash_feedback.sound_name)
                            push_skill_feed(dash_feedback.log_text, dash_feedback.log_color)
                
                if event.key == get_control_key_code("ultimate"):
                    if state == "PLAYING" and player:
                        ultimate_feedback = player.use_ultimate(build_character_combat_context())
                        if ultimate_feedback.activated:
                            damage_texts.add(DamageText(player.pos, "ULTIMATE!", True, (255, 0, 255)))
                            shake_timer = 1.0
                            shake_strength = 15
                            play_sfx("ult")
                            push_skill_feed(ultimate_feedback.log_text, ultimate_feedback.log_color)
            
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    click_pos = event.pos

                    # ── Tela de Seleção de Perfil ─────────────────────────
                    if state == "PROFILE_SELECT":
                        _res = _handle_profile_select_click(
                            click_pos, _prof_mode, _prof_sel_idx, _prof_new_name,
                            _prof_new_ci, _prof_new_char, _prof_name_focus, _prof_del_confirm)
                        if _res:
                            (_prof_mode, _prof_sel_idx, _prof_new_name,
                             _prof_new_ci, _prof_new_char, _prof_name_focus, _prof_del_confirm) = _res
                            if _prof_mode == "SELECTED":
                                # Perfil foi selecionado — carregar save e ir ao menu
                                save_data.update({
                                    "gold": 0, "perm_upgrades": {k: 0 for k in save_data["perm_upgrades"]},
                                    "stats": {"total_kills": 0, "total_time": 0, "boss_kills": 0,
                                              "deaths": 0, "games_played": 0, "max_level_reached": 0},
                                    "unlocks": list(DEFAULT_UNLOCKS), "daily_missions": {"last_reset": "", "active": []},
                                    "purchased_items": [], "chest_items": [], "char_inventories": {},
                                    "char_equipped": {}, "hardcore_stages": {"unlocked": 1},
                                    "beaten_difficulties": [],
                                })
                                load_save()
                                _reload_achievements()
                                for _bi2, _bk2 in enumerate(diff_order):
                                    diff_btns[_bi2].locked = DIFFICULTIES[_bk2]["id"] not in save_data["unlocks"]
                                _prof_mode = "list"
                                state = "MENU"
                                menu_intro_timer = MENU_ENTER_DURATION
                        continue

                    # Overlay de vitória de fase Hardcore (prioridade máxima)
                    if show_stage_victory and hasattr(main, "_sv_btns_rects"):
                        for _svr, _svact in main._sv_btns_rects:
                            if _svr.collidepoint(click_pos):
                                if snd_click: snd_click.play()
                                if _svact == "continue":
                                    show_stage_victory = False
                                elif _svact == "next":
                                    if current_hardcore_stage < 10:
                                        _next = current_hardcore_stage + 1
                                        if _next > save_data["hardcore_stages"].get("unlocked", 1):
                                            save_data["hardcore_stages"]["unlocked"] = _next
                                        current_hardcore_stage = _next
                                        achievements_data["hardcore_stages_unlocked"] = max(
                                            achievements_data.get("hardcore_stages_unlocked", 1),
                                            save_data["hardcore_stages"]["unlocked"],
                                        )
                                        _check_achievements()
                                        save_game()
                                    show_stage_victory = False
                                    state = "HUB"
                                elif _svact == "hub":
                                    show_stage_victory = False
                                    state = "HUB"
                                break

                    # Diálogo "Entrar na Sala de Recompensas?" (após morte do Agis)
                    if show_reward_dialog:
                        _rrd_w = 460; _rrd_h = 210
                        _rrd_x = (SCREEN_W - _rrd_w) // 2; _rrd_y = (SCREEN_H - _rrd_h) // 2
                        _rrd_sim = pygame.Rect(_rrd_x + 40,  _rrd_y + 140, 160, 48)
                        _rrd_nao = pygame.Rect(_rrd_x + 260, _rrd_y + 140, 160, 48)
                        if _rrd_sim.collidepoint(click_pos):
                            show_reward_dialog = False
                            _reward_room_bg = None
                            try:
                                _rr_path = os.path.join(ASSET_DIR, "Teste", "recompensa", "sala_recompença.png")
                                _raw_rr = pygame.image.load(_rr_path).convert_alpha()
                                _reward_room_bg = pygame.transform.smoothscale(_raw_rr, (SCREEN_W, SCREEN_H))
                            except Exception:
                                pass
                            reward_room_player_pos = pygame.Vector2(SCREEN_W // 2, int(SCREEN_H * 0.65))
                            reward_room_anim_t = 0.0; reward_room_anim_idx = 0
                            hub_equip_open = False; hub_status_open = False
                            _mining_system = MiningSystem(SCREEN_W, SCREEN_H,
                                                          selected_difficulty, current_hardcore_stage)
                            _mining_system.spawn_ores()
                            save_game()
                            autosave_feedback_timer = 2.5
                            state = "REWARD_ROOM"
                            if snd_click: snd_click.play()
                        elif _rrd_nao.collidepoint(click_pos):
                            show_reward_dialog = False
                            hub_equip_open = False; hub_status_open = False
                            save_game()
                            state = "HUB"
                            if snd_click: snd_click.play()
                        continue

                    # ── Diálogo de confirmação de descarte (prioridade alta) ──
                    if _discard_confirm is not None:
                        _dc_w, _dc_h = 420, 210
                        _dc_x = (SCREEN_W - _dc_w) // 2
                        _dc_y = (SCREEN_H - _dc_h) // 2
                        _dc_sim_r = pygame.Rect(_dc_x + 40,  _dc_y + 138, 148, 50)
                        _dc_nao_r = pygame.Rect(_dc_x + 232, _dc_y + 138, 148, 50)
                        if _dc_sim_r.collidepoint(click_pos):
                            _dc_cid = player.char_id if player else 0
                            _dc_inv = get_char_inventory(_dc_cid)
                            _dc_eq  = get_char_equipped(_dc_cid)
                            _dc_src = _discard_confirm["from"]
                            _dc_it  = _discard_confirm["item"]
                            if _dc_src == "inventory":
                                _dc_ri = _discard_confirm["_idx"]
                                if 0 <= _dc_ri < len(_dc_inv) and _dc_inv[_dc_ri] is _dc_it:
                                    _dc_inv.pop(_dc_ri)
                                elif _dc_it in _dc_inv:
                                    _dc_inv.remove(_dc_it)
                            elif _dc_src == "equip":
                                _dc_sl = _discard_confirm.get("_slot")
                                if _dc_sl and _dc_eq.get(_dc_sl) is _dc_it:
                                    _dc_eq[_dc_sl] = None
                            save_game()
                            _discard_confirm = None
                            if snd_click: snd_click.play()
                        elif _dc_nao_r.collidepoint(click_pos):
                            _discard_confirm = None
                            if snd_click: snd_click.play()
                        continue

                    # Diálogo de confirmação de venda (prioridade máxima)
                    if item_shop_sell_confirm is not None and state == "ITEM_SHOP":
                        _scfd_w = 420; _scfd_h = 200
                        _scfd_x = (SCREEN_W - _scfd_w) // 2; _scfd_y = (SCREEN_H - _scfd_h) // 2
                        _scfd_sim = pygame.Rect(_scfd_x + 40,  _scfd_y + 130, 140, 44)
                        _scfd_nao = pygame.Rect(_scfd_x + 240, _scfd_y + 130, 140, 44)
                        if _scfd_sim.collidepoint(click_pos):
                            _scf = item_shop_sell_confirm
                            _scf_entry = _scf["entry"]
                            _scf_it    = _scf_entry["item"]
                            _scf_cat   = _scf_it.get("category", ""); _scf_idx = _scf_it.get("idx", 0)
                            if _scf_entry["source"] == "chest":
                                try: save_data["chest_items"].remove(_scf_it)
                                except ValueError: pass
                            else:
                                _cid_scf = _scf_entry.get("cid", "0")
                                _inv_scf = save_data["char_inventories"].get(_cid_scf, [])
                                try: _inv_scf.remove(_scf_it)
                                except ValueError: pass
                            _scf_key = {"category": _scf_cat, "idx": _scf_idx}
                            try: save_data["purchased_items"].remove(_scf_key)
                            except ValueError: pass
                            save_data["gold"] += _scf["price"]
                            achievements_data["total_gold_accumulated"] = achievements_data.get("total_gold_accumulated", 0.0) + _scf["price"]
                            item_shop_sell_selected = None
                            item_shop_sell_confirm  = None
                            save_game()
                            push_skill_feed(f"+{_scf['price']} ouro", (220, 200, 80))
                            if snd_click: snd_click.play()
                        elif _scfd_nao.collidepoint(click_pos):
                            item_shop_sell_confirm  = None
                            item_shop_sell_selected = None
                            if snd_click: snd_click.play()
                        continue

                    # Diálogo de confirmação de compra (prioridade máxima)
                    if item_shop_confirm is not None and state == "ITEM_SHOP":
                        _cfd_w = 420; _cfd_h = 220
                        _cfd_x = (SCREEN_W - _cfd_w) // 2; _cfd_y = (SCREEN_H - _cfd_h) // 2
                        _cfd_sim = pygame.Rect(_cfd_x + 40,  _cfd_y + 150, 140, 44)
                        _cfd_nao = pygame.Rect(_cfd_x + 240, _cfd_y + 150, 140, 44)
                        if _cfd_sim.collidepoint(click_pos):
                            _cf = item_shop_confirm
                            save_data["gold"] -= _cf["price"]
                            save_data["purchased_items"].append({"category": _cf["category"], "idx": _cf["idx"]})
                            _buy_cid = player.char_id if player else hub_last_char_id
                            get_char_inventory(_buy_cid).append({"category": _cf["category"], "idx": _cf["idx"]})
                            item_shop_confirm = None
                            save_game()
                            if snd_click: snd_click.play()
                        elif _cfd_nao.collidepoint(click_pos):
                            item_shop_confirm = None
                            if snd_click: snd_click.play()
                        # Bloqueia qualquer outro clique enquanto o diálogo está aberto
                        continue

                    if state == "SETTINGS":
                        start_settings_drag(click_pos)

                    if state == "MENU":
                        # Clique no overlay de perfil (quando aberto)
                        if menu_profile_open:
                            if hasattr(_draw_profile_viewer, "_btn_alterar") and _draw_profile_viewer._btn_alterar.collidepoint(click_pos):
                                menu_profile_open = False
                                _prof_mode = "list"
                                _active_prof = profile_mgr.get_active_profile()
                                _all_profs   = profile_mgr.get_all_profiles()
                                _prof_sel_idx = next((i for i, p in enumerate(_all_profs) if _active_prof and p["id"] == _active_prof["id"]), 0)
                                state = "PROFILE_SELECT"
                                if snd_click: snd_click.play()
                            elif hasattr(_draw_profile_viewer, "_av_picker_rects") and getattr(_draw_profile_viewer, "_av_picker_open", False):
                                for _pck_idx, _pck_r in _draw_profile_viewer._av_picker_rects:
                                    if _pck_r.collidepoint(click_pos):
                                        profile_mgr.update_avatar(_draw_profile_viewer._av_profile_id, _pck_idx)
                                        _avatar_icon_cache.clear()
                                        _draw_profile_viewer._av_picker_open = False
                                        if snd_click: snd_click.play()
                                        break
                            elif hasattr(_draw_profile_viewer, "_av_main_rect") and _draw_profile_viewer._av_main_rect.collidepoint(click_pos):
                                _draw_profile_viewer._av_picker_open = not getattr(_draw_profile_viewer, "_av_picker_open", False)
                                if snd_click: snd_click.play()
                        elif _menu_profile_widget_rect and _menu_profile_widget_rect.collidepoint(click_pos):
                            menu_profile_open = True
                            if snd_click: snd_click.play()
                        if not menu_profile_open and menu_pending_action is None and menu_exit_timer <= 0.0:
                            if menu_btns[0].rect.collidepoint(click_pos):
                                menu_pending_action = "CHAR_SELECT"
                            elif menu_btns[1].rect.collidepoint(click_pos):
                                menu_pending_action = "MISSIONS"
                            elif menu_btns[2].rect.collidepoint(click_pos):
                                menu_pending_action = "SHOP"
                            elif menu_btns[3].rect.collidepoint(click_pos):
                                menu_pending_action = "SETTINGS"
                            elif menu_btns[4].rect.collidepoint(click_pos):
                                menu_pending_action = "QUIT"
                            elif menu_site_rect.collidepoint(click_pos):
                                webbrowser.open(_menu_site_url)
                                if snd_click: snd_click.play()

                            if menu_pending_action is not None:
                                if snd_click:
                                    snd_click.play()
                                menu_exit_timer = MENU_EXIT_DURATION

                    elif state == "HUB":
                        # ── Cliques no overlay de perfil (hub) ─────────────────────
                        if hub_profile_open:
                            if hasattr(_draw_profile_viewer, "_av_picker_rects") and getattr(_draw_profile_viewer, "_av_picker_open", False):
                                for _pck_idx, _pck_r in _draw_profile_viewer._av_picker_rects:
                                    if _pck_r.collidepoint(click_pos):
                                        profile_mgr.update_avatar(_draw_profile_viewer._av_profile_id, _pck_idx)
                                        _avatar_icon_cache.clear()
                                        _draw_profile_viewer._av_picker_open = False
                                        if snd_click: snd_click.play()
                                        break
                            elif hasattr(_draw_profile_viewer, "_av_main_rect") and _draw_profile_viewer._av_main_rect.collidepoint(click_pos):
                                _draw_profile_viewer._av_picker_open = not getattr(_draw_profile_viewer, "_av_picker_open", False)
                                if snd_click: snd_click.play()
                        # Perfil no canto esquerdo: use a tecla L para abrir (não clicável)
                        # ── Inicio de Drag-and-Drop nas janelas de Inventário / Baú ──
                        elif hub_equip_open and not _drag_active:
                            _dd_cid  = player.char_id if player else 0
                            _dd_inv  = get_char_inventory(_dd_cid)
                            _dd_eq   = get_char_equipped(_dd_cid)
                            # Calcular posição/escala do painel (mesma lógica do draw)
                            _dd_sc   = min(SCREEN_W * 0.42 / 1128, SCREEN_H * 0.80 / 1254)
                            _dd_PW   = int(1128 * _dd_sc); _dd_PH = int(1254 * _dd_sc)
                            _dd_PX   = (SCREEN_W - _dd_PW) // 2
                            _dd_PY   = (SCREEN_H - _dd_PH) // 2
                            # Slots de equipamento (posições relativas à imagem 1128×1254)
                            _dd_eqslots = {
                                "helmet": (295,143,110,104), "weapon": (141,266,106,105),
                                "shield": (457,266,106,105),
                                "armor":  (295,381,110,104),
                                "legs":   (295,509,110,104), "boots":  (295,637,110,100),
                            }
                            # Testar clique em slots de equipamento
                            _dd_hit_eq = None
                            for _sk_dd, (ex,ey,ew,eh) in _dd_eqslots.items():
                                _sr_dd = pygame.Rect(
                                    _dd_PX + int(ex*_dd_sc), _dd_PY + int(ey*_dd_sc),
                                    int(ew*_dd_sc), int(eh*_dd_sc))
                                if _sr_dd.collidepoint(click_pos) and _dd_eq.get(_sk_dd):
                                    _dd_hit_eq = _sk_dd; break
                            # Testar clique em slots do inventário (grade 8×5)
                            _dd_COLS = 8
                            _dd_gx0   = _dd_PX + int(53*_dd_sc)
                            _dd_gy0   = _dd_PY + int(807*_dd_sc)
                            _dd_sw    = int(93*_dd_sc)
                            _dd_sh    = int(85*_dd_sc)
                            _dd_stepx = int(95*_dd_sc)
                            _dd_stepy = int(88*_dd_sc)
                            _dd_hit_inv = -1
                            for _di_dd in range(len(_dd_inv)):
                                _col_dd = _di_dd % _dd_COLS
                                _row_dd = _di_dd // _dd_COLS
                                _ir_dd = pygame.Rect(_dd_gx0 + _col_dd*_dd_stepx,
                                                     _dd_gy0 + _row_dd*_dd_stepy,
                                                     _dd_sw, _dd_sh)
                                if _ir_dd.collidepoint(click_pos):
                                    _dd_hit_inv = _di_dd; break
                            if _dd_hit_eq is not None:
                                _itm_dd = _dd_eq[_dd_hit_eq]
                                _drag_item   = {"item": _itm_dd, "from": "equip", "_idx": -1, "_slot": _dd_hit_eq}
                                _drag_active = True
                                _drag_offset = (click_pos[0] - int((_dd_eqslots[_dd_hit_eq][0]+_dd_eqslots[_dd_hit_eq][2]//2)*_dd_sc+_dd_PX),
                                               click_pos[1] - int((_dd_eqslots[_dd_hit_eq][1]+_dd_eqslots[_dd_hit_eq][3]//2)*_dd_sc+_dd_PY))
                                if snd_click: snd_click.play()
                            elif _dd_hit_inv >= 0:
                                _itm_dd = _dd_inv[_dd_hit_inv]
                                _col_dd = _dd_hit_inv % _dd_COLS; _row_dd = _dd_hit_inv // _dd_COLS
                                _cx_dd = _dd_gx0 + _col_dd*_dd_stepx + _dd_sw//2
                                _cy_dd = _dd_gy0 + _row_dd*_dd_stepy + _dd_sh//2
                                _drag_item   = {"item": _itm_dd, "from": "inventory", "_idx": _dd_hit_inv, "_slot": None}
                                _drag_active = True
                                _drag_offset = (click_pos[0]-_cx_dd, click_pos[1]-_cy_dd)
                                if snd_click: snd_click.play()

                        elif hub_chest_open and not _drag_active:
                            _dd_cid2   = player.char_id if player else 0
                            _dd_inv2   = get_char_inventory(_dd_cid2)
                            _dd_chest2 = save_data["chest_items"]
                            # Constantes iguais ao render do baú
                            _SL2=68; _PD2=8; _CLS2=4
                            _PW2 = _CLS2*(_SL2+_PD2)-_PD2+20
                            _ww2 = min(int(SCREEN_W*0.98), _PW2*2+60)
                            _wh2 = int(SCREEN_H*0.95)
                            _wx2 = (SCREEN_W-_ww2)//2; _wy2=(SCREEN_H-_wh2)//2
                            _cox2 = _wx2+(_ww2//2-_PW2)//2
                            _iox2 = _wx2+_ww2//2+(_ww2//2-_PW2)//2
                            _iy02 = _wy2+108
                            # Clique nas abas
                            _tab2_i_r = pygame.Rect(_wx2+_ww2//2-116, _wy2+50, 108, 26)
                            _tab2_m_r = pygame.Rect(_wx2+_ww2//2+8,   _wy2+50, 108, 26)
                            if _tab2_i_r.collidepoint(click_pos):
                                _chest_tab = "itens"
                            elif _tab2_m_r.collidepoint(click_pos):
                                _chest_tab = "minerios"
                            else:
                                # Filtrar itens pela aba
                                if _chest_tab == "minerios":
                                    _vis_c2 = [(i,it) for i,it in enumerate(_dd_chest2) if it.get("category")=="Minérios"]
                                    _vis_i2 = [(i,it) for i,it in enumerate(_dd_inv2)   if it.get("category")=="Minérios"]
                                else:
                                    _vis_c2 = [(i,it) for i,it in enumerate(_dd_chest2) if it.get("category")!="Minérios"]
                                    _vis_i2 = [(i,it) for i,it in enumerate(_dd_inv2)   if it.get("category")!="Minérios"]
                                def _ghit_drag(vis_items, ox, oy):
                                    for _vi2 in range(len(vis_items)):
                                        _rx = ox+(_vi2%_CLS2)*(_SL2+_PD2)
                                        _ry = oy+(_vi2//_CLS2)*(_SL2+_PD2)
                                        if pygame.Rect(_rx,_ry,_SL2,_SL2).collidepoint(click_pos):
                                            return _vi2, vis_items[_vi2][0]
                                    return -1, -1
                                _hc2_vi, _hc2_oi = _ghit_drag(_vis_c2, _cox2, _iy02)
                                _hi2_vi, _hi2_oi = _ghit_drag(_vis_i2, _iox2, _iy02)
                                if _hc2_vi >= 0:
                                    _itm_c = _vis_c2[_hc2_vi][1]
                                    _cx_c = _cox2+(_hc2_vi%_CLS2)*(_SL2+_PD2)+_SL2//2
                                    _cy_c = _iy02+(_hc2_vi//_CLS2)*(_SL2+_PD2)+_SL2//2
                                    _drag_item = {"item":_itm_c,"from":"chest","_idx":_hc2_oi,"_slot":None}
                                    _drag_active = True
                                    _drag_offset = (click_pos[0]-_cx_c, click_pos[1]-_cy_c)
                                    if snd_click: snd_click.play()
                                elif _hi2_vi >= 0:
                                    _itm_i = _vis_i2[_hi2_vi][1]
                                    _cx_i = _iox2+(_hi2_vi%_CLS2)*(_SL2+_PD2)+_SL2//2
                                    _cy_i = _iy02+(_hi2_vi//_CLS2)*(_SL2+_PD2)+_SL2//2
                                    _drag_item = {"item":_itm_i,"from":"inventory","_idx":_hi2_oi,"_slot":None}
                                    _drag_active = True
                                    _drag_offset = (click_pos[0]-_cx_i, click_pos[1]-_cy_i)
                                    if snd_click: snd_click.play()

                        # Setas do seletor de bioma
                        _avail_bgs_click = [k for k in bg_choices if k not in BG_LOCKED]
                        if hasattr(main, "_biome_larr") and main._biome_larr.collidepoint(click_pos) and not hub_countdown_active:
                            _ci = _avail_bgs_click.index(selected_bg) if selected_bg in _avail_bgs_click else 0
                            selected_bg = _avail_bgs_click[(_ci - 1) % len(_avail_bgs_click)]
                            _reload_biome_assets()
                            if snd_click: snd_click.play()
                        elif hasattr(main, "_biome_rarr") and main._biome_rarr.collidepoint(click_pos) and not hub_countdown_active:
                            _ci = _avail_bgs_click.index(selected_bg) if selected_bg in _avail_bgs_click else 0
                            selected_bg = _avail_bgs_click[(_ci + 1) % len(_avail_bgs_click)]
                            _reload_biome_assets()
                            if snd_click: snd_click.play()
                        # Botões do painel lateral direito
                        if hub_pronto_btn.rect.collidepoint(click_pos) and not hub_countdown_active:
                            hub_countdown_active = True
                            hub_countdown_timer  = 5.0
                            if snd_click: snd_click.play()
                        # Botões de atalho: Mercado e Talentos
                        _hub_panel_x = int(SCREEN_W * 0.84)
                        _hub_panel_w = SCREEN_W - _hub_panel_x
                        _hub_rb_rw = _hub_panel_w - int(_hub_panel_w * 0.20)
                        _hub_rb_rx = _hub_panel_x + int(_hub_panel_w * 0.10)
                        _hub_rb_h  = 50
                        _hub_market_rect = pygame.Rect(_hub_rb_rx, int(SCREEN_H * 0.373) - _hub_rb_h//2, _hub_rb_rw, _hub_rb_h)
                        _hub_talent_rect = pygame.Rect(_hub_rb_rx, int(SCREEN_H * 0.453) - _hub_rb_h//2, _hub_rb_rw, _hub_rb_h)
                        if _hub_market_rect.collidepoint(click_pos):
                            if market_scene is None:
                                _ferreiro_dir = os.path.join(BASE_DIR, "assets", "Teste", "ferreiro")
                                market_scene = MarketScene(_ferreiro_dir)
                                market_scene.load_all()
                                market_scene.load_surfaces_and_bake()
                                market_scene.setup_player()
                            if player is not None:
                                _cid_m  = player.char_id
                                _cdat_m = CHAR_DATA.get(_cid_m, {})
                                market_scene.apply_char_frames(
                                    dir_walk      = dict(player._dir_walk_frames),
                                    dir_idle      = dict(player._dir_idle_frames),
                                    walk_fallback = list(player.anim_frames),
                                    idle_fallback = list(player.idle_frames),
                                    anim_spd      = _cdat_m.get("anim_speed", 0.10),
                                    idle_anim_spd = _cdat_m.get("idle_anim_speed", 0.13),
                                )
                            state = "MARKET"
                            if snd_click: snd_click.play()
                        elif _hub_talent_rect.collidepoint(click_pos):
                            hub_return = True
                            state = "SHOP"
                        # Setas de fase Hardcore
                        if selected_difficulty == "HARDCORE" and hasattr(main, "_hc_larr"):
                            _hc_max_unl = save_data.get("hardcore_stages", {}).get("unlocked", 1)
                            if main._hc_larr.collidepoint(click_pos) and current_hardcore_stage > 1:
                                current_hardcore_stage -= 1
                                if snd_click: snd_click.play()
                            elif main._hc_rarr.collidepoint(click_pos) and current_hardcore_stage < _hc_max_unl:
                                current_hardcore_stage += 1
                                if snd_click: snd_click.play()

                    elif state == "MARKET":
                        if hub_profile_open:
                            if hasattr(_draw_profile_viewer, "_av_picker_rects") and getattr(_draw_profile_viewer, "_av_picker_open", False):
                                for _pck_idx, _pck_r in _draw_profile_viewer._av_picker_rects:
                                    if _pck_r.collidepoint(click_pos):
                                        profile_mgr.update_avatar(_draw_profile_viewer._av_profile_id, _pck_idx)
                                        _avatar_icon_cache.clear()
                                        _draw_profile_viewer._av_picker_open = False
                                        if snd_click: snd_click.play()
                                        break
                            elif hasattr(_draw_profile_viewer, "_av_main_rect") and _draw_profile_viewer._av_main_rect.collidepoint(click_pos):
                                _draw_profile_viewer._av_picker_open = not getattr(_draw_profile_viewer, "_av_picker_open", False)
                                if snd_click: snd_click.play()
                        elif hub_equip_open and not _drag_active:
                            _dd_cid  = player.char_id if player else 0
                            _dd_inv  = get_char_inventory(_dd_cid)
                            _dd_eq   = get_char_equipped(_dd_cid)
                            if craft_open:
                                _dd_sc = min(SCREEN_W * 0.44 / 1128, SCREEN_H * 0.80 / 1254)
                            else:
                                _dd_sc = min(SCREEN_W * 0.42 / 1128, SCREEN_H * 0.80 / 1254)
                            _dd_PW   = int(1128 * _dd_sc); _dd_PH = int(1254 * _dd_sc)
                            _dd_PX   = (SCREEN_W - _dd_PW - 8) if craft_open else (SCREEN_W - _dd_PW) // 2
                            _dd_PY   = (SCREEN_H - _dd_PH) // 2
                            # ── Crafting panel click detection ─────────────────
                            if craft_open:
                                _cf_ev_PX  = 8
                                _cf_ev_PW  = _dd_PX - 16
                                _cf_ev_PY  = _dd_PY
                                _cf_ev_PH  = _dd_PH
                                _cf_ev_lw  = _cf_ev_PW // 2 - 8
                                _cf_ev_rx  = _cf_ev_PX + _cf_ev_lw + 12
                                _cf_ev_rw  = _cf_ev_PW - _cf_ev_lw - 20
                                # Recipe list click (approximate — just check if inside list area)
                                _cf_ev_list_rect = pygame.Rect(_cf_ev_PX + 4, _cf_ev_PY + 46,
                                                                _cf_ev_lw, _cf_ev_PH - 50)
                                if _cf_ev_list_rect.collidepoint(click_pos):
                                    _cf_ev_rects = getattr(main, "_cf_ui_rects", {})
                                    for (_rcat, _ridx), _rrect in _cf_ev_rects.get("recipe_rects", {}).items():
                                        if _rrect.collidepoint(click_pos):
                                            _craft_selected = (_rcat, _ridx)
                                            _craft_slots    = [None, None, None]
                                            if snd_click: snd_click.play()
                                            break
                                # Craft slot click (pick up item from slot)
                                _cf_ev_rects2 = getattr(main, "_cf_ui_rects", {})
                                for _cf_sn, _cf_sr_ev in enumerate(_cf_ev_rects2.get("slot_rects", [])):
                                    if _cf_sr_ev.collidepoint(click_pos) and _craft_slots[_cf_sn] is not None:
                                        _drag_item   = {"item": _craft_slots[_cf_sn], "from": "craft_slot",
                                                        "_idx": -1, "_slot": None, "_slot_n": _cf_sn}
                                        _drag_active = True
                                        _drag_offset = (click_pos[0] - _cf_sr_ev.centerx,
                                                        click_pos[1] - _cf_sr_ev.centery)
                                        _craft_slots[_cf_sn] = None
                                        if snd_click: snd_click.play()
                                        break
                                # FORJAR button click
                                _cf_ev_btn = _cf_ev_rects2.get("btn_forge")
                                if _cf_ev_btn and _cf_ev_btn.collidepoint(click_pos):
                                    _cf_sel_c, _cf_sel_i = _craft_selected
                                    _cf_cid_forge = player.char_id if player else 0
                                    _cf_inv_forge  = get_char_inventory(_cf_cid_forge)
                                    # Consume ingredients from slots
                                    for _cf_sl in _craft_slots:
                                        if _cf_sl is not None:
                                            _cf_sl_qty = _cf_sl.get("qty", 1)
                                            if _cf_sl_qty > 1:
                                                _cf_sl["qty"] = _cf_sl_qty - 1
                                            elif _cf_sl in _cf_inv_forge:
                                                _cf_inv_forge.remove(_cf_sl)
                                    # Add crafted item (soulbound)
                                    _cf_new_item = {
                                        "category": _cf_sel_c,
                                        "idx":      _cf_sel_i,
                                        "soulbound": True,
                                        "cid":      _cf_cid_forge,
                                        "crafted":  True,
                                    }
                                    _cf_inv_forge.append(_cf_new_item)
                                    _craft_slots = [None, None, None]
                                    save_game()
                                    if snd_click: snd_click.play()
                            _dd_eqslots = {
                                "helmet": (295,143,110,104), "weapon": (141,266,106,105),
                                "shield": (457,266,106,105),
                                "armor":  (295,381,110,104),
                                "legs":   (295,509,110,104), "boots":  (295,637,110,100),
                            }
                            _dd_hit_eq = None
                            for _sk_dd, (ex,ey,ew,eh) in _dd_eqslots.items():
                                _sr_dd = pygame.Rect(
                                    _dd_PX + int(ex*_dd_sc), _dd_PY + int(ey*_dd_sc),
                                    int(ew*_dd_sc), int(eh*_dd_sc))
                                if _sr_dd.collidepoint(click_pos) and _dd_eq.get(_sk_dd):
                                    _dd_hit_eq = _sk_dd; break
                            _dd_COLS = 8
                            _dd_gx0   = _dd_PX + int(53*_dd_sc)
                            _dd_gy0   = _dd_PY + int(807*_dd_sc)
                            _dd_sw    = int(93*_dd_sc)
                            _dd_sh    = int(85*_dd_sc)
                            _dd_stepx = int(95*_dd_sc)
                            _dd_stepy = int(88*_dd_sc)
                            _dd_hit_inv = -1
                            for _di_dd in range(len(_dd_inv)):
                                _col_dd = _di_dd % _dd_COLS
                                _row_dd = _di_dd // _dd_COLS
                                _ir_dd = pygame.Rect(_dd_gx0 + _col_dd*_dd_stepx,
                                                     _dd_gy0 + _row_dd*_dd_stepy,
                                                     _dd_sw, _dd_sh)
                                if _ir_dd.collidepoint(click_pos):
                                    _dd_hit_inv = _di_dd; break
                            if _dd_hit_eq is not None:
                                _itm_dd = _dd_eq[_dd_hit_eq]
                                _drag_item   = {"item": _itm_dd, "from": "equip", "_idx": -1, "_slot": _dd_hit_eq}
                                _drag_active = True
                                _drag_offset = (click_pos[0] - int((_dd_eqslots[_dd_hit_eq][0]+_dd_eqslots[_dd_hit_eq][2]//2)*_dd_sc+_dd_PX),
                                               click_pos[1] - int((_dd_eqslots[_dd_hit_eq][1]+_dd_eqslots[_dd_hit_eq][3]//2)*_dd_sc+_dd_PY))
                                if snd_click: snd_click.play()
                            elif _dd_hit_inv >= 0:
                                _itm_dd = _dd_inv[_dd_hit_inv]
                                _col_dd = _dd_hit_inv % _dd_COLS; _row_dd = _dd_hit_inv // _dd_COLS
                                _cx_dd = _dd_gx0 + _col_dd*_dd_stepx + _dd_sw//2
                                _cy_dd = _dd_gy0 + _row_dd*_dd_stepy + _dd_sh//2
                                _drag_item   = {"item": _itm_dd, "from": "inventory", "_idx": _dd_hit_inv, "_slot": None}
                                _drag_active = True
                                _drag_offset = (click_pos[0]-_cx_dd, click_pos[1]-_cy_dd)
                                if snd_click: snd_click.play()
                        elif market_shop_open:
                            if shop_back_btn.rect.collidepoint(click_pos):
                                market_shop_open = False
                                save_game()
                                if snd_click: snd_click.play()
                            else:
                                for p_name, s_key, btn in shop_talent_btns:
                                    if btn.rect.collidepoint(click_pos):
                                        skill = TALENT_TREE[p_name]["skills"][s_key]
                                        lvl = save_data["perm_upgrades"].get(s_key, 0)
                                        if lvl < skill["max"]:
                                            price = skill["cost"][lvl]
                                            if save_data["gold"] >= price:
                                                save_data["gold"] -= price
                                                save_data["perm_upgrades"][s_key] = lvl + 1
                                                if snd_click: snd_click.play()
                        elif market_missions_open:
                            if mission_btns[0].rect.collidepoint(click_pos):
                                market_missions_open = False
                                if snd_click: snd_click.play()
                            else:
                                for i, m in enumerate(save_data["daily_missions"]["active"]):
                                    if m["completed"] and not m["claimed"]:
                                        if mission_claim_btns[i].rect.collidepoint(click_pos):
                                            m["claimed"] = True
                                            save_data["gold"] += m["reward"]
                                            achievements_data["total_gold_accumulated"] = achievements_data.get("total_gold_accumulated", 0.0) + m["reward"]
                                            play_sfx("win")
                                            save_game()
                        else:
                            # Painel direito só recebe cliques quando visível
                            _mk_panel_visible = (not craft_open) or (click_pos[0] >= SCREEN_W - 60)
                            if _mk_panel_visible:
                                _mk_panel_x = int(SCREEN_W * 0.84)
                                _mk_panel_w = SCREEN_W - _mk_panel_x
                                _mk_rb_rw = _mk_panel_w - int(_mk_panel_w * 0.20)
                                _mk_rb_rx = _mk_panel_x + int(_mk_panel_w * 0.10)
                                _mk_rb_h  = 50
                                _mk_missions_rect = pygame.Rect(_mk_rb_rx, int(SCREEN_H * 0.373) - _mk_rb_h//2, _mk_rb_rw, _mk_rb_h)
                                _mk_talent_rect   = pygame.Rect(_mk_rb_rx, int(SCREEN_H * 0.453) - _mk_rb_h//2, _mk_rb_rw, _mk_rb_h)
                                _mk_voltar_rect   = pygame.Rect(_mk_rb_rx, int(SCREEN_H * 0.562) - _mk_rb_h//2, _mk_rb_rw, _mk_rb_h)
                                if _mk_missions_rect.collidepoint(click_pos):
                                    market_missions_open = True
                                    if snd_click: snd_click.play()
                                elif _mk_talent_rect.collidepoint(click_pos):
                                    market_shop_open = True
                                    update_shop_talent_button_layout()
                                    if snd_click: snd_click.play()
                                elif _mk_voltar_rect.collidepoint(click_pos):
                                    state = "HUB"
                                    if snd_click: snd_click.play()

                    elif state == "REWARD_ROOM":
                        if hub_equip_open and not _drag_active:
                            _dd_cid  = player.char_id if player else 0
                            _dd_inv  = get_char_inventory(_dd_cid)
                            _dd_eq   = get_char_equipped(_dd_cid)
                            _dd_sc   = min(SCREEN_W * 0.42 / 1128, SCREEN_H * 0.80 / 1254)
                            _dd_PW   = int(1128 * _dd_sc); _dd_PH = int(1254 * _dd_sc)
                            _dd_PX   = (SCREEN_W - _dd_PW) // 2
                            _dd_PY   = (SCREEN_H - _dd_PH) // 2
                            _dd_eqslots = {
                                "helmet": (295,143,110,104), "weapon": (141,266,106,105),
                                "shield": (457,266,106,105),
                                "armor":  (295,381,110,104),
                                "legs":   (295,509,110,104), "boots":  (295,637,110,100),
                            }
                            _dd_hit_eq = None
                            for _sk_dd, (ex,ey,ew,eh) in _dd_eqslots.items():
                                _sr_dd = pygame.Rect(_dd_PX+int(ex*_dd_sc), _dd_PY+int(ey*_dd_sc),
                                                     int(ew*_dd_sc), int(eh*_dd_sc))
                                if _sr_dd.collidepoint(click_pos) and _dd_eq.get(_sk_dd):
                                    _dd_hit_eq = _sk_dd; break
                            _dd_COLS = 8
                            _dd_gx0   = _dd_PX + int(53*_dd_sc)
                            _dd_gy0   = _dd_PY + int(807*_dd_sc)
                            _dd_sw    = int(93*_dd_sc); _dd_sh = int(85*_dd_sc)
                            _dd_stepx = int(95*_dd_sc); _dd_stepy = int(88*_dd_sc)
                            _dd_hit_inv = -1
                            for _di_dd in range(len(_dd_inv)):
                                _ir_dd = pygame.Rect(_dd_gx0+(_di_dd%_dd_COLS)*_dd_stepx,
                                                     _dd_gy0+(_di_dd//_dd_COLS)*_dd_stepy,
                                                     _dd_sw, _dd_sh)
                                if _ir_dd.collidepoint(click_pos): _dd_hit_inv = _di_dd; break
                            if _dd_hit_eq is not None:
                                _itm_dd = _dd_eq[_dd_hit_eq]
                                _drag_item   = {"item": _itm_dd, "from": "equip", "_idx": -1, "_slot": _dd_hit_eq}
                                _drag_active = True
                                _drag_offset = (click_pos[0]-int((_dd_eqslots[_dd_hit_eq][0]+_dd_eqslots[_dd_hit_eq][2]//2)*_dd_sc+_dd_PX),
                                               click_pos[1]-int((_dd_eqslots[_dd_hit_eq][1]+_dd_eqslots[_dd_hit_eq][3]//2)*_dd_sc+_dd_PY))
                                if snd_click: snd_click.play()
                            elif _dd_hit_inv >= 0:
                                _itm_dd = _dd_inv[_dd_hit_inv]
                                _cx_dd  = _dd_gx0+(_dd_hit_inv%_dd_COLS)*_dd_stepx+_dd_sw//2
                                _cy_dd  = _dd_gy0+(_dd_hit_inv//_dd_COLS)*_dd_stepy+_dd_sh//2
                                _drag_item   = {"item": _itm_dd, "from": "inventory", "_idx": _dd_hit_inv, "_slot": None}
                                _drag_active = True
                                _drag_offset = (click_pos[0]-_cx_dd, click_pos[1]-_cy_dd)
                                if snd_click: snd_click.play()
                        elif not hub_equip_open and not hub_status_open:
                            _rr_sair_rect = pygame.Rect(SCREEN_W // 2 - 110, SCREEN_H - 78, 220, 54)
                            if _rr_sair_rect.collidepoint(click_pos):
                                hub_equip_open = False; hub_status_open = False
                                _drag_item = None; _drag_active = False
                                save_game()
                                state = "HUB"
                                if snd_click: snd_click.play()

                    elif state == "SAVES":
                        if saves_back_btn.rect.collidepoint(click_pos):
                            state = "MENU"
                        else:
                            for idx, btn in enumerate(saves_slot_btns):
                                if btn.rect.collidepoint(click_pos):
                                    if load_run_slot(idx):
                                        if snd_click: snd_click.play()
                                        autosave_timer = 0.0
                                        state = "PLAYING"
                                    break

                    elif state == "MISSIONS":
                        if mission_btns[0].rect.collidepoint(click_pos): 
                            state = "MENU"
                        for i, m in enumerate(save_data["daily_missions"]["active"]):
                            if m["completed"] and not m["claimed"]:
                                if mission_claim_btns[i].rect.collidepoint(click_pos):
                                    m["claimed"] = True
                                    save_data["gold"] += m["reward"]
                                    achievements_data["total_gold_accumulated"] = achievements_data.get("total_gold_accumulated", 0.0) + m["reward"]
                                    play_sfx("win")
                                    save_game()

                    elif state == "SHOP":
                        if shop_back_btn.rect.collidepoint(click_pos):
                            save_game()
                            if hub_return and hub_scene is not None:
                                hub_return = False
                                state = "HUB"
                            else:
                                state = "MENU"
                        else:
                            for p_name, s_key, btn in shop_talent_btns:
                                if btn.rect.collidepoint(click_pos):
                                    skill = TALENT_TREE[p_name]["skills"][s_key]
                                    lvl = save_data["perm_upgrades"].get(s_key, 0)
                                    if lvl < skill["max"]:
                                        price = skill["cost"][lvl]
                                        if save_data["gold"] >= price:
                                            save_data["gold"] -= price
                                            save_data["perm_upgrades"][s_key] = lvl + 1
                                            if snd_click: snd_click.play()

                    elif state == "ITEM_SHOP":
                        if item_shop_back_btn.rect.collidepoint(click_pos):
                            if market_return and market_scene is not None:
                                market_return = False
                                state = "MARKET"
                            elif hub_return and hub_scene is not None:
                                hub_return = False
                                state = "HUB"
                            else:
                                state = "MENU"
                        else:
                            for _ti, _tbtn in enumerate(item_shop_tab_btns):
                                if _tbtn.rect.collidepoint(click_pos):
                                    if _ti in (0, 1, _ITEM_SHOP_SELL_TAB):
                                        item_shop_active_tab    = _ti
                                        item_shop_scroll_y      = 0
                                        item_shop_sell_selected = None
                                        item_shop_sell_confirm  = None
                                        if snd_click: snd_click.play()
                                    else:
                                        push_skill_feed("Em breve!", (180, 180, 180))
                            # Compra de item ao clicar num slot
                            if item_shop_active_tab == 0:
                                _SLOT = 72; _PAD = 8
                                _itens_dir = os.path.join("assets", "ui", "itens")
                                _cx0 = int(SCREEN_W * 0.05); _cy0 = int(SCREEN_H * 0.21)
                                _cw  = int(SCREEN_W * 0.90); _SB_W = 14
                                _grid_w = _cw - _SB_W - 8
                                _COLS = max(1, (_grid_w - 16) // (_SLOT + _PAD))
                                _draw_x = _cx0 + 12; _draw_y = _cy0 + 12 - item_shop_scroll_y
                                _clip_rect = pygame.Rect(_cx0 + 4, _cy0 + 4, _grid_w, int(SCREEN_H * 0.67) - 8)
                                for _cname, _cdat in ITEM_SHOP_CATEGORIES.items():
                                    _draw_y += 30; _col = 0; _draw_x = _cx0 + 12
                                    _stats_list = ITEM_SHOP_STATS.get(_cname, [])
                                    for _n in range(1, _cdat["count"] + 1):
                                        _sr = pygame.Rect(_draw_x, _draw_y, _SLOT, _SLOT)
                                        if _sr.collidepoint(click_pos) and _clip_rect.collidepoint(click_pos):
                                            _idx = _n - 1
                                            _st  = _stats_list[_idx] if _idx < len(_stats_list) else {}
                                            _price = _st.get("price", 0)
                                            _key   = {"category": _cname, "idx": _idx}
                                            _owned = _key in save_data["purchased_items"]
                                            if _price > 0 and save_data["gold"] >= _price:
                                                item_shop_confirm = {
                                                    "category": _cname, "idx": _idx,
                                                    "price": _price, "st": _st,
                                                }
                                                if snd_click: snd_click.play()
                                            elif _owned:
                                                push_skill_feed("Item já comprado!", (180, 180, 80))
                                            else:
                                                push_skill_feed("Ouro insuficiente!", (200, 60, 60))
                                        _col += 1
                                        if _col >= _COLS: _col = 0; _draw_x = _cx0 + 12; _draw_y += _SLOT + _PAD
                                        else: _draw_x += _SLOT + _PAD
                                    if _col > 0: _draw_x = _cx0 + 12; _draw_y += _SLOT + _PAD
                                    _draw_y += 10

                            if item_shop_active_tab == 1:
                                _SLOT = 72; _PAD = 8
                                _cx0 = int(SCREEN_W * 0.05); _cy0 = int(SCREEN_H * 0.21)
                                _cw  = int(SCREEN_W * 0.90); _SB_W = 14
                                _grid_w = _cw - _SB_W - 8
                                _COLS = max(1, (_grid_w - 16) // (_SLOT + _PAD))
                                _draw_x = _cx0 + 12; _draw_y = _cy0 + 12 - item_shop_scroll_y
                                _clip_rect = pygame.Rect(_cx0 + 4, _cy0 + 4, _grid_w, int(SCREEN_H * 0.67) - 8)
                                for _acname, _acdat in ARMOR_SHOP_CATEGORIES.items():
                                    _draw_y += 30; _col = 0; _draw_x = _cx0 + 12
                                    _stats_list = ITEM_SHOP_STATS.get(_acname, [])
                                    for _n, _afname in enumerate(_acdat["files"]):
                                        _sr = pygame.Rect(_draw_x, _draw_y, _SLOT, _SLOT)
                                        if _sr.collidepoint(click_pos) and _clip_rect.collidepoint(click_pos):
                                            _idx = _n
                                            _st  = _stats_list[_idx] if _idx < len(_stats_list) else {}
                                            _price = _st.get("price", 0)
                                            _key   = {"category": _acname, "idx": _idx}
                                            _owned = _key in save_data["purchased_items"]
                                            if _price > 0 and save_data["gold"] >= _price:
                                                item_shop_confirm = {
                                                    "category": _acname, "idx": _idx,
                                                    "price": _price, "st": _st,
                                                }
                                                if snd_click: snd_click.play()
                                            elif _owned:
                                                push_skill_feed("Item já comprado!", (180, 180, 80))
                                            else:
                                                push_skill_feed("Ouro insuficiente!", (200, 60, 60))
                                        _col += 1
                                        if _col >= _COLS: _col = 0; _draw_x = _cx0 + 12; _draw_y += _SLOT + _PAD
                                        else: _draw_x += _SLOT + _PAD
                                    if _col > 0: _draw_x = _cx0 + 12; _draw_y += _SLOT + _PAD
                                    _draw_y += 10

                            # ── Aba VENDER: clique para selecionar/confirmar venda ──
                            if item_shop_active_tab == _ITEM_SHOP_SELL_TAB:
                                _sv_SLOT = 72; _sv_PAD = 8
                                _sv_cx0 = int(SCREEN_W * 0.05); _sv_cy0 = int(SCREEN_H * 0.21)
                                _sv_cw  = int(SCREEN_W * 0.90); _sv_SB_W = 14
                                _sv_gw  = _sv_cw - _sv_SB_W - 8
                                _sv_COLS = max(1, (_sv_gw - 16) // (_sv_SLOT + _sv_PAD))
                                _sv_clip = pygame.Rect(_sv_cx0+4, _sv_cy0+4, _sv_gw, int(SCREEN_H*0.67)-8)

                                # Monta lista de itens vendáveis
                                _sv_items = []
                                for _svi in save_data["chest_items"]:
                                    _sv_items.append({"item": _svi, "source": "chest", "cid": None})
                                for _svcid, _svinv in save_data["char_inventories"].items():
                                    for _svi in _svinv:
                                        _sv_items.append({"item": _svi, "source": "inventory", "cid": _svcid})

                                _sv_dx = _sv_cx0 + 12; _sv_dy = _sv_cy0 + 12 - item_shop_scroll_y
                                for _svi2, _sventry in enumerate(_sv_items):
                                    _svr = pygame.Rect(_sv_dx, _sv_dy, _sv_SLOT, _sv_SLOT)
                                    if _svr.collidepoint(click_pos) and _sv_clip.collidepoint(click_pos):
                                        _is_sel = (item_shop_sell_selected is not None and
                                                   item_shop_sell_selected.get("item") == _sventry["item"] and
                                                   item_shop_sell_selected.get("source") == _sventry["source"] and
                                                   item_shop_sell_selected.get("cid") == _sventry["cid"])
                                        if _is_sel:
                                            # Segunda clique → abrir confirmação de venda
                                            _sv_it2  = _sventry["item"]
                                            _sv_cat2 = _sv_it2.get("category", ""); _sv_idx2 = _sv_it2.get("idx", 0)
                                            _sv_st2b = ITEM_SHOP_STATS.get(_sv_cat2, [{}])
                                            _sv_st2b = _sv_st2b[_sv_idx2] if _sv_idx2 < len(_sv_st2b) else {}
                                            _sv_price2 = max(1, _sv_st2b.get("price", 0) // 2)
                                            item_shop_sell_confirm = {"entry": dict(_sventry), "price": _sv_price2, "st": _sv_st2b}
                                            if snd_click: snd_click.play()
                                        else:
                                            # Primeiro clique → selecionar
                                            item_shop_sell_selected = dict(_sventry)
                                            if snd_click: snd_click.play()
                                        break
                                    _sv_c = (_svi2 + 1) % _sv_COLS
                                    if _sv_c == 0: _sv_dx = _sv_cx0+12; _sv_dy += _sv_SLOT + _sv_PAD
                                    else: _sv_dx += _sv_SLOT + _sv_PAD

                    elif state == "CHAR_SELECT":
                        if char_back_btn.rect.collidepoint(click_pos):
                            state = "MENU"
                        for i, btn in enumerate(char_btns):
                            if btn.rect.collidepoint(click_pos):
                                if snd_click: snd_click.play()
                                reset_game(i)
                                state = "DIFF_SELECT"

                    elif state == "DIFF_SELECT":
                        if diff_back_btn.rect.collidepoint(click_pos):
                            state = "CHAR_SELECT"
                        diff_order = ["FÁCIL", "MÉDIO", "DIFÍCIL", "HARDCORE"]
                        for i, btn in enumerate(diff_btns):
                            if btn.rect.collidepoint(click_pos) and not btn.locked:
                                selected_difficulty = diff_order[i]
                                if snd_click: snd_click.play()
                                state = "PACT_SELECT"

                    elif state == "PACT_SELECT":
                        if pact_back_btn.rect.collidepoint(click_pos):
                            state = "DIFF_SELECT"
                        pact_names = list(PACTOS.keys())
                        for i, btn in enumerate(pact_btns):
                            if btn.rect.collidepoint(click_pos):
                                selected_pact = pact_names[i]
                                if snd_click: snd_click.play()
                                p_data = PACTOS[selected_pact]
                                _init_cid = player.char_id if player else 0
                                reset_game(_init_cid)
                                hub_last_char_id = _init_cid
                                run_gold_collected = 0.0
                                autosave_timer = 0.0
                                if p_data["hp"] > 0:
                                    player.hp = p_data["hp"]
                                _hp_pct = p_data.get("hp_pct", 0)
                                if _hp_pct != 0:
                                    PLAYER_MAX_HP = max(1, int(PLAYER_MAX_HP * (1.0 + _hp_pct)))
                                    player.hp = min(player.hp, PLAYER_MAX_HP)
                                    player.base_hp = PLAYER_MAX_HP
                                _xp_pct = p_data.get("xp_pct", 0)
                                if _xp_pct != 0:
                                    XP_BONUS_PCT += _xp_pct
                                # Carrega o Hub Room multi-mapa antes de começar a partida
                                _tmx_dir = os.path.join(BASE_DIR, "assets", "Teste", "Tiled_files")
                                if os.path.isdir(_tmx_dir):
                                    hub_scene = HubScene(_tmx_dir)
                                    hub_scene.load_all()
                                    hub_scene.load_surfaces_and_bake()
                                    hub_scene.setup_player("interior_1_default")
                                    if player is not None:
                                        _cid   = player.char_id
                                        _cdata = CHAR_DATA.get(_cid, {})
                                        hub_scene.apply_char_frames(
                                            dir_walk      = dict(player._dir_walk_frames),
                                            dir_idle      = dict(player._dir_idle_frames),
                                            walk_fallback = list(player.anim_frames),
                                            idle_fallback = list(player.idle_frames),
                                            anim_spd      = _cdata.get("anim_speed", 0.10),
                                            idle_anim_spd = _cdata.get("idle_anim_speed", 0.13),
                                        )
                                    hub_countdown_active = False
                                    hub_countdown_timer  = 0.0
                                    state = "HUB"
                                else:
                                    state = "PLAYING"

                    elif state == "BG_SELECT":
                        if bg_back_btn.rect.collidepoint(click_pos):
                            state = "MENU"
                        else:
                            for i, btn in enumerate(bg_btns):
                                if btn.rect.collidepoint(click_pos):
                                    if btn.locked:
                                        push_skill_feed("Em breve!", (180, 180, 180))
                                    else:
                                        selected_bg = bg_choices[i]
                                        load_all_assets()
                                        if snd_click: snd_click.play()
                                    break

                    elif state == "SETTINGS":
                        # categorias (sempre clicáveis para facilitar navegação)
                        for btn in settings_main_btns:
                            if btn.rect.collidepoint(click_pos):
                                if snd_click: snd_click.play()
                                label = btn.text.strip().lower()
                                if "vídeo" in label or "video" in label:
                                    settings_category = "video"
                                elif "áudio" in label or "audio" in label:
                                    settings_category = "audio"
                                elif "controles" in label:
                                    settings_category = "controls"
                                elif "gameplay" in label:
                                    settings_category = "gameplay"
                                elif "acessibilidade" in label:
                                    settings_category = "accessibility"
                                if settings_category != "main":
                                    temp_settings = json.loads(json.dumps(settings))
                                break

                        # ações
                        for key, btn in settings_action_btns.items():
                            if btn.rect.collidepoint(click_pos):
                                if snd_click: snd_click.play()

                                if key == "apply":
                                    settings = json.loads(json.dumps(temp_settings))
                                    apply_settings(settings)
                                    load_all_assets()
                                    save_settings(settings)

                                elif key == "default":
                                    default_settings = load_settings(force_default=True)
                                    temp_settings = json.loads(json.dumps(default_settings))
                                    settings = json.loads(json.dumps(default_settings))
                                    apply_settings(settings)
                                    load_all_assets()
                                    save_settings(settings)

                                elif key == "back":
                                    if settings_category != "main":
                                        settings_category = "main"
                                    else:
                                        state = "MENU"
                                break

                        # opções internas da aba ativa
                        if settings_category == "video":
                            handle_video_settings_clicks(click_pos)
                        elif settings_category == "audio":
                            handle_audio_settings_clicks(click_pos)
                        elif settings_category == "controls":
                            handle_controls_settings_clicks(click_pos)
                        elif settings_category == "gameplay":
                            handle_gameplay_settings_clicks(click_pos)
                        elif settings_category == "accessibility":
                            handle_accessibility_settings_clicks(click_pos)

                    elif state == "GAME_OVER":
                        if game_over_btn.rect.collidepoint(click_pos):
                            if snd_click: snd_click.play()
                            save_data["gold"] = save_data.get("gold", 0) + int(run_gold_collected)
                            run_gold_collected = 0.0
                            if profile_mgr and profile_mgr.has_active_profile():
                                _xp_rate = PROFILE_XP_RATES.get(selected_difficulty, 10)
                                _xp_earned = int(game_time / 60 * _xp_rate)
                                if _xp_earned > 0:
                                    _ap = profile_mgr.get_active_profile()
                                    profile_mgr.update_xp(_ap["id"], _xp_earned)
                            _saved_cid = player.char_id if player else hub_last_char_id
                            clear_current_run_state()
                            hub_last_char_id = _saved_cid
                            reset_game(_saved_cid)
                            if player is not None and hub_scene is not None:
                                _cdata_go = CHAR_DATA.get(_saved_cid, {})
                                hub_scene.apply_char_frames(
                                    dir_walk      = dict(player._dir_walk_frames),
                                    dir_idle      = dict(player._dir_idle_frames),
                                    walk_fallback = list(player.anim_frames),
                                    idle_fallback = list(player.idle_frames),
                                    anim_spd      = _cdata_go.get("anim_speed", 0.10),
                                    idle_anim_spd = _cdata_go.get("idle_anim_speed", 0.13),
                                )
                            save_game()
                            state = "HUB"

                    elif state == "UPGRADE":
                        for i, rect in enumerate(up_options):
                            if i < len(up_keys) and rect.collidepoint(click_pos):
                                if snd_click: snd_click.play()
                                apply_upgrade(up_keys[i])
                                up_options = []
                                up_keys = []
                                up_rarities = []
                                state = "PLAYING"
                                break

                    elif state == "CHEST_UI":
                        auto_apply = settings["gameplay"].get("auto_apply_chest_reward", "On") == "On"
                        if not auto_apply:
                            box_w, box_h = 700, 100 + len(chest_loot) * 80
                            box_rect = pygame.Rect(SCREEN_W/2 - box_w/2, SCREEN_H/2 - box_h/2, box_w, box_h)
                            for i, loot in enumerate(chest_loot):
                                line_rect = pygame.Rect(box_rect.left + 20, box_rect.y + 25 + i * 80, box_w - 40, 70)
                                if line_rect.collidepoint(click_pos):
                                    apply_upgrade(loot)
                                    chest_loot = []
                                    chest_ui_timer = 0.0
                                    state = "PLAYING"
                                    if snd_click: snd_click.play()
                                    break

                    elif state == "PAUSED":
                        if pause_btns[0].rect.collidepoint(click_pos):
                            if snd_click: snd_click.play()
                            state = "PLAYING"
                        elif pause_btns[1].rect.collidepoint(click_pos):  # VOLTAR PARA ROOM
                            if snd_click: snd_click.play()
                            save_data["gold"] = save_data.get("gold", 0) + int(run_gold_collected)
                            run_gold_collected = 0.0
                            # XP de perfil antes de clear (game_time ainda válido)
                            if profile_mgr and profile_mgr.has_active_profile():
                                _xp_rate = PROFILE_XP_RATES.get(selected_difficulty, 10)
                                _xp_earned = int(game_time / 60 * _xp_rate)
                                if _xp_earned > 0:
                                    _ap = profile_mgr.get_active_profile()
                                    profile_mgr.update_xp(_ap["id"], _xp_earned)
                            _saved_cid = player.char_id if player else hub_last_char_id
                            clear_current_run_state()
                            hub_last_char_id = _saved_cid
                            reset_game(_saved_cid)
                            if player is not None and hub_scene is not None:
                                _cdata_ret = CHAR_DATA.get(_saved_cid, {})
                                hub_scene.apply_char_frames(
                                    dir_walk      = dict(player._dir_walk_frames),
                                    dir_idle      = dict(player._dir_idle_frames),
                                    walk_fallback = list(player.anim_frames),
                                    idle_fallback = list(player.idle_frames),
                                    anim_spd      = _cdata_ret.get("anim_speed", 0.10),
                                    idle_anim_spd = _cdata_ret.get("idle_anim_speed", 0.13),
                                )
                            save_game()
                            state = "HUB"
                        elif pause_btns[2].rect.collidepoint(click_pos):  # MENU PRINCIPAL
                            if snd_click: snd_click.play()
                            save_run_slot(0)
                            clear_current_run_state()
                            run_gold_collected = 0.0
                            state = "MENU"
                        else:
                            for i, s_btn in enumerate(pause_save_btns):
                                if s_btn.rect.collidepoint(click_pos):
                                    if snd_click: snd_click.play()
                                    if save_run_slot(i):
                                        pause_save_feedback_timer = 2.0
                                    break

            # Scroll na tela de perfil (navegar perfis / seletor de país)
            if event.type == pygame.MOUSEWHEEL and state == "PROFILE_SELECT":
                if _prof_mode == "list":
                    profiles_list = profile_mgr.get_all_profiles() if profile_mgr else []
                    if profiles_list:
                        _prof_sel_idx = (_prof_sel_idx - event.y) % len(profiles_list)
                elif _prof_mode == "create":
                    _prof_new_ci = (_prof_new_ci - event.y) % len(COUNTRIES)

            # Scroll da Loja de Itens (roda do mouse)
            if event.type == pygame.MOUSEWHEEL and state == "ITEM_SHOP":
                item_shop_scroll_y -= event.y * 40
                item_shop_scroll_y  = max(0, item_shop_scroll_y)

            # Scroll da lista de receitas do FERREIRO
            if event.type == pygame.MOUSEWHEEL and state == "MARKET" and craft_open:
                _craft_scroll_y -= event.y * 30
                _craft_scroll_y  = max(0, _craft_scroll_y)

            if event.type == pygame.MOUSEMOTION and state == "SETTINGS":
                update_settings_drag(event.pos)

            if event.type == pygame.MOUSEBUTTONUP and state == "SETTINGS":
                stop_settings_drag()

            # ── Drop do Drag-and-Drop de Inventário/Baú/Equipamento ──────────
            if event.type == pygame.MOUSEBUTTONUP and event.button == 1 and state in ("HUB", "MARKET", "REWARD_ROOM") and _drag_active:
                _drop_pos = event.pos
                _dd_cid_u = player.char_id if player else 0
                _dd_inv_u = get_char_inventory(_dd_cid_u)
                _dd_eq_u  = get_char_equipped(_dd_cid_u)
                _dd_chest_u = save_data["chest_items"]
                _dropped = False

                if hub_equip_open:
                    # --- Painel de Inventário (tecla I) ---
                    if craft_open:
                        _dd_sc_u = min(SCREEN_W * 0.44 / 1128, SCREEN_H * 0.80 / 1254)
                    else:
                        _dd_sc_u = min(SCREEN_W * 0.42 / 1128, SCREEN_H * 0.80 / 1254)
                    _dd_PW_u   = int(1128 * _dd_sc_u); _dd_PH_u = int(1254 * _dd_sc_u)
                    _dd_PX_u   = (SCREEN_W - _dd_PW_u - 8) if craft_open else (SCREEN_W - _dd_PW_u) // 2
                    _dd_PY_u   = (SCREEN_H - _dd_PH_u) // 2
                    # ── Drop em slot de crafting ───────────────────────────
                    if craft_open and _drag_item is not None:
                        _cf_drop_rects = getattr(main, "_cf_ui_rects", {}).get("slot_rects", [])
                        for _cf_sn2, _cf_sr_drop in enumerate(_cf_drop_rects):
                            if _cf_sr_drop.collidepoint(_drop_pos):
                                _di = _drag_item["item"]
                                if _drag_item["from"] == "inventory":
                                    _src_inv_i = _drag_item["_idx"]
                                    if _src_inv_i < len(_dd_inv_u):
                                        _moved_cf = _dd_inv_u.pop(_src_inv_i)
                                        _craft_slots[_cf_sn2] = _moved_cf
                                        save_game(); _dropped = True
                                        if snd_click: snd_click.play()
                                elif _drag_item["from"] == "craft_slot":
                                    _craft_slots[_cf_sn2] = _di
                                    _dropped = True
                                    if snd_click: snd_click.play()
                                break
                        # Drop craft_slot item back to inventory
                        if not _dropped and _drag_item.get("from") == "craft_slot":
                            _dd_inv_u.append(_drag_item["item"])
                            save_game(); _dropped = True
                    _dd_eqslots_u = {
                        "helmet": (295,143,110,104), "weapon": (141,266,106,105),
                        "shield": (457,266,106,105),
                        "armor":  (295,381,110,104),
                        "legs":   (295,509,110,104), "boots":  (295,637,110,100),
                    }
                    # Inventário grid
                    _dd_COLS_u  = 8
                    _dd_gx0_u   = _dd_PX_u + int(53*_dd_sc_u)
                    _dd_gy0_u   = _dd_PY_u + int(807*_dd_sc_u)
                    _dd_sw_u    = int(93*_dd_sc_u)
                    _dd_sh_u    = int(85*_dd_sc_u)
                    _dd_stepx_u = int(95*_dd_sc_u)
                    _dd_stepy_u = int(88*_dd_sc_u)

                    # Testar drop em slot de equipamento
                    for _sk_du, (ex,ey,ew,eh) in _dd_eqslots_u.items():
                        _sr_du = pygame.Rect(_dd_PX_u+int(ex*_dd_sc_u), _dd_PY_u+int(ey*_dd_sc_u),
                                             int(ew*_dd_sc_u), int(eh*_dd_sc_u))
                        if _sr_du.collidepoint(_drop_pos):
                            _di_item = _drag_item["item"]
                            _di_slot = item_slot(_di_item.get("category",""))
                            if _di_slot == _sk_du:
                                _eq_cat_c = _di_item.get("category","")
                                _eq_idx_c = _di_item.get("idx", 0)
                                _eq_st_l  = ITEM_SHOP_STATS.get(_eq_cat_c, [])
                                _eq_st_c  = _eq_st_l[_eq_idx_c] if 0 <= _eq_idx_c < len(_eq_st_l) else {}
                                _req_lv_c = _eq_st_c.get("level", 1)
                                _cur_lv_c = get_active_profile_level()
                                if _cur_lv_c < _req_lv_c:
                                    _equip_err_msg       = f"Nível {_req_lv_c} necessário para equipar!"
                                    _equip_err_msg_start = pygame.time.get_ticks()
                                    _dropped = True
                                else:
                                    _old_eq_u = _dd_eq_u.get(_sk_du)
                                    _dd_eq_u[_sk_du] = {"category":_di_item["category"],"idx":_di_item["idx"]}
                                    if _drag_item["from"] == "inventory": _dd_inv_u.pop(_drag_item["_idx"])
                                    elif _drag_item["from"] == "equip": _dd_eq_u[_drag_item["_slot"]] = None
                                    if _old_eq_u: _dd_inv_u.append(_old_eq_u)
                                    save_game(); _dropped = True
                                    if snd_click: snd_click.play()
                            break

                    if not _dropped:
                        # Testar drop em slot de inventário
                        _max_slots_u = 8 * 5  # 40 slots
                        _target_idx_u = -1
                        for _di_u in range(_max_slots_u):
                            _col_u = _di_u % _dd_COLS_u; _row_u = _di_u // _dd_COLS_u
                            _ir_u = pygame.Rect(_dd_gx0_u+_col_u*_dd_stepx_u, _dd_gy0_u+_row_u*_dd_stepy_u,
                                                _dd_sw_u, _dd_sh_u)
                            if _ir_u.collidepoint(_drop_pos):
                                _target_idx_u = _di_u; break
                        if _target_idx_u >= 0:
                            _di_item = _drag_item["item"]
                            if _drag_item["from"] == "equip":
                                _dd_eq_u[_drag_item["_slot"]] = None
                                if _target_idx_u < len(_dd_inv_u):
                                    _dd_inv_u.insert(_target_idx_u, _di_item)
                                else:
                                    _dd_inv_u.append(_di_item)
                                save_game(); _dropped = True
                                if snd_click: snd_click.play()
                            elif _drag_item["from"] == "inventory":
                                _src_u = _drag_item["_idx"]
                                _dd_inv_u.pop(_src_u)
                                _real_target = min(_target_idx_u, len(_dd_inv_u))
                                _dd_inv_u.insert(_real_target, _di_item)
                                save_game(); _dropped = True
                                if snd_click: snd_click.play()
                            elif _drag_item["from"] == "chest":
                                _dd_chest_u.pop(_drag_item["_idx"])
                                if _target_idx_u < len(_dd_inv_u):
                                    _dd_inv_u.insert(_target_idx_u, _di_item)
                                else:
                                    _dd_inv_u.append(_di_item)
                                save_game(); _dropped = True
                                if snd_click: snd_click.play()

                elif hub_chest_open:
                    # --- Painel de Baú (tecla F) ---
                    # Dimensões devem bater com o render do baú
                    _SL_u=68; _PD_u=8; _CLS_u=4
                    _PW_u = _CLS_u*(_SL_u+_PD_u)-_PD_u+20
                    _ww_u = min(int(SCREEN_W*0.98), _PW_u*2+60)
                    _wh_u = int(SCREEN_H*0.95)
                    _wx_u = (SCREEN_W-_ww_u)//2; _wy_u=(SCREEN_H-_wh_u)//2
                    _cox_u= _wx_u+(_ww_u//2-_PW_u)//2
                    _iox_u= _wx_u+_ww_u//2+(_ww_u//2-_PW_u)//2
                    _iy0_u= _wy_u+108
                    # Filtrar por aba
                    if _chest_tab == "minerios":
                        _vis_c_u = [(i,it) for i,it in enumerate(_dd_chest_u) if it.get("category")=="Minérios"]
                        _vis_i_u = [(i,it) for i,it in enumerate(_dd_inv_u)   if it.get("category")=="Minérios"]
                    else:
                        _vis_c_u = [(i,it) for i,it in enumerate(_dd_chest_u) if it.get("category")!="Minérios"]
                        _vis_i_u = [(i,it) for i,it in enumerate(_dd_inv_u)   if it.get("category")!="Minérios"]
                    def _ghit_up(vis_items, ox, oy):
                        for _vu in range(len(vis_items)):
                            _rx = ox + (_vu % _CLS_u)*(_SL_u+_PD_u)
                            _ry = oy + (_vu // _CLS_u)*(_SL_u+_PD_u)
                            if pygame.Rect(_rx,_ry,_SL_u,_SL_u).collidepoint(_drop_pos):
                                return _vu, vis_items[_vu][0]
                        return -1, -1
                    _hc_u_vi, _hc_u_oi = _ghit_up(_vis_c_u, _cox_u, _iy0_u)
                    _hi_u_vi, _hi_u_oi = _ghit_up(_vis_i_u, _iox_u, _iy0_u)
                    _di_item = _drag_item["item"]
                    _src_oi  = _drag_item["_idx"]

                    def _try_stack_u(src_list, src_idx, tgt_list, tgt_idx):
                        """Stack same minerals. Returns True if any quantity was transferred."""
                        if tgt_idx >= len(tgt_list): return False
                        _su = src_list[src_idx]; _tu = tgt_list[tgt_idx]
                        if (_su.get("category") != "Minérios" or _tu.get("category") != "Minérios"
                                or _su.get("idx") != _tu.get("idx") or _tu.get("qty",1) >= 20):
                            return False
                        _give_u = min(_su.get("qty",1), 20 - _tu.get("qty",1))
                        _tu["qty"] = _tu.get("qty",1) + _give_u
                        _su["qty"] = _su.get("qty",1) - _give_u
                        if _su["qty"] <= 0:
                            src_list.pop(src_idx)
                        return True

                    if _hc_u_vi >= 0:
                        _chst_tgt = _dd_chest_u[_hc_u_oi] if _hc_u_oi < len(_dd_chest_u) else None
                        if _drag_item["from"] == "inventory":
                            if _chst_tgt and _try_stack_u(_dd_inv_u, _src_oi, _dd_chest_u, _hc_u_oi):
                                save_game(); _dropped = True
                            else:
                                _moved = _dd_inv_u.pop(_src_oi)
                                _tgt = min(_hc_u_oi, len(_dd_chest_u))
                                _dd_chest_u.insert(_tgt, _moved); save_game(); _dropped = True
                        elif _drag_item["from"] == "chest" and _src_oi != _hc_u_oi:
                            if _chst_tgt and _try_stack_u(_dd_chest_u, _src_oi, _dd_chest_u, _hc_u_oi):
                                save_game(); _dropped = True
                            else:
                                _moved = _dd_chest_u.pop(_src_oi)
                                _tgt = min(_hc_u_oi, len(_dd_chest_u))
                                _dd_chest_u.insert(_tgt, _moved); save_game(); _dropped = True
                        if _dropped and snd_click: snd_click.play()
                    elif _hi_u_vi >= 0:
                        _inv_tgt = _dd_inv_u[_hi_u_oi] if _hi_u_oi < len(_dd_inv_u) else None
                        if _drag_item["from"] == "chest":
                            if _inv_tgt and _try_stack_u(_dd_chest_u, _src_oi, _dd_inv_u, _hi_u_oi):
                                save_game(); _dropped = True
                            else:
                                _moved = _dd_chest_u.pop(_src_oi)
                                _tgt = min(_hi_u_oi, len(_dd_inv_u))
                                _dd_inv_u.insert(_tgt, _moved); save_game(); _dropped = True
                        elif _drag_item["from"] == "inventory" and _src_oi != _hi_u_oi:
                            if _inv_tgt and _try_stack_u(_dd_inv_u, _src_oi, _dd_inv_u, _hi_u_oi):
                                save_game(); _dropped = True
                            else:
                                _moved = _dd_inv_u.pop(_src_oi)
                                _tgt = min(_hi_u_oi, len(_dd_inv_u))
                                _dd_inv_u.insert(_tgt, _moved); save_game(); _dropped = True
                        if _dropped and snd_click: snd_click.play()
                    else:
                        _inv_area_u   = pygame.Rect(_iox_u, _wy_u+80, _PW_u, _wh_u-90)
                        _chest_area_u = pygame.Rect(_cox_u, _wy_u+80, _PW_u, _wh_u-90)
                        if _drag_item["from"] == "chest" and _inv_area_u.collidepoint(_drop_pos):
                            _moved = _dd_chest_u.pop(_src_oi)
                            _dd_inv_u.append(_moved); save_game(); _dropped = True
                        elif _drag_item["from"] == "inventory" and _chest_area_u.collidepoint(_drop_pos):
                            _moved = _dd_inv_u[_src_oi]
                            if _moved.get("soulbound"):
                                _equip_err_msg = "Item vinculado — não pode ir ao baú!"
                                _equip_err_msg_start = pygame.time.get_ticks()
                                _dropped = True
                            else:
                                _dd_inv_u.pop(_src_oi)
                                _dd_chest_u.append(_moved); save_game(); _dropped = True
                        if _dropped and snd_click: snd_click.play()

                # Craft slot item dropped outside → return to inventory
                if not _dropped and _drag_item is not None and _drag_item.get("from") == "craft_slot":
                    _dd_cid_u2 = player.char_id if player else 0
                    get_char_inventory(_dd_cid_u2).append(_drag_item["item"])
                    save_game(); _dropped = True
                # Se não caiu em slot válido e veio do inventário/equip → oferecer descarte
                if not _dropped and hub_equip_open and _drag_item is not None:
                    if _drag_item["from"] in ("inventory", "equip"):
                        if craft_open:
                            _dc_sc2 = min(SCREEN_W * 0.44 / 1128, SCREEN_H * 0.80 / 1254)
                        else:
                            _dc_sc2 = min(SCREEN_W * 0.42 / 1128, SCREEN_H * 0.80 / 1254)
                        _dc_PW2 = int(1128 * _dc_sc2); _dc_PH2 = int(1254 * _dc_sc2)
                        _dc_PX2 = (SCREEN_W - _dc_PW2 - 8) if craft_open else (SCREEN_W - _dc_PW2) // 2
                        _dc_PY2 = (SCREEN_H - _dc_PH2) // 2
                        _panel_r2 = pygame.Rect(_dc_PX2, _dc_PY2, _dc_PW2, _dc_PH2)
                        if not _panel_r2.collidepoint(_drop_pos):
                            _discard_confirm = dict(_drag_item)

                _drag_item = None; _drag_active = False

            # ── Gamepad: conexão/desconexão ──────────────────────────────────
            if event.type == pygame.JOYDEVICEADDED:
                _gamepad_connect(event.device_index)

            if event.type == pygame.JOYDEVICEREMOVED:
                _gamepad_disconnect()

            # ── Gamepad: botões ──────────────────────────────────────────────
            if event.type == pygame.JOYBUTTONDOWN:
                btn = event.button

                # Start (7) → pausar/continuar
                if btn == 7:
                    if state == "PLAYING": state = "PAUSED"
                    elif state == "PAUSED": state = "PLAYING"

                # B (1) → voltar nos menus
                elif btn == 1:
                    if state == "PAUSED": state = "PLAYING"
                    elif state == "SETTINGS":
                        if settings_category == "main":
                            state = "MENU"
                        else:
                            settings_category = "main"
                            temp_settings = json.loads(json.dumps(settings))
                    elif state in ["CHAR_SELECT", "MISSIONS", "BG_SELECT", "SAVES"]:
                        state = "MENU"
                    elif state in ["SHOP", "ITEM_SHOP"]:
                        if item_shop_confirm is not None:
                            item_shop_confirm = None
                        elif market_return and market_scene is not None:
                            market_return = False
                            state = "MARKET"
                        elif hub_return and hub_scene is not None:
                            hub_return = False
                            state = "HUB"
                        else:
                            state = "MENU"
                    elif state == "DIFF_SELECT": state = "CHAR_SELECT"
                    elif state == "PACT_SELECT": state = "DIFF_SELECT"

                # A (0) → opção 1 de upgrade / clique nos menus
                elif btn == 0:
                    if state == "UPGRADE" and len(up_keys) > 0:
                        if snd_click: snd_click.play()
                        apply_upgrade(up_keys[0])
                        up_options = []; up_keys = []; up_rarities = []
                        state = "PLAYING"
                    elif state not in ("PLAYING",):
                        mx, my = pygame.mouse.get_pos()
                        pygame.event.post(pygame.event.Event(
                            pygame.MOUSEBUTTONDOWN, pos=(mx, my), button=1, touch=False))

                # X (2) → opção 2 de upgrade
                elif btn == 2:
                    if state == "UPGRADE" and len(up_keys) > 1:
                        if snd_click: snd_click.play()
                        apply_upgrade(up_keys[1])
                        up_options = []; up_keys = []; up_rarities = []
                        state = "PLAYING"

                # Y (3) → opção 3 de upgrade
                elif btn == 3:
                    if state == "UPGRADE" and len(up_keys) > 2:
                        if snd_click: snd_click.play()
                        apply_upgrade(up_keys[2])
                        up_options = []; up_keys = []; up_rarities = []
                        state = "PLAYING"

                # RB (5) → dash
                elif btn == 5:
                    if state == "PLAYING" and player:
                        dash_feedback = player.start_dash(particles)
                        if dash_feedback.activated:
                            play_sfx(dash_feedback.sound_name)
                            push_skill_feed(dash_feedback.log_text, dash_feedback.log_color)

                # LB (4) → ultimate
                elif btn == 4:
                    if state == "PLAYING" and player:
                        ultimate_feedback = player.use_ultimate(build_character_combat_context())
                        if ultimate_feedback.activated:
                            damage_texts.add(DamageText(player.pos, "ULTIMATE!", True, (255, 0, 255)))
                            shake_timer = 1.0; shake_strength = 15
                            play_sfx("ult")
                            push_skill_feed(ultimate_feedback.log_text, ultimate_feedback.log_color)

        if state != prev_state:
            if state == "MENU":
                menu_intro_timer = MENU_ENTER_DURATION
                menu_exit_timer = 0.0
                menu_pending_action = None
            prev_state = state
            transition_timer = UI_TRANSITION_DURATION
        transition_timer = max(0.0, transition_timer - dt_raw)
        if state == "MENU":
            menu_intro_timer = max(0.0, menu_intro_timer - dt_raw)
            if menu_pending_action is not None:
                menu_exit_timer = max(0.0, menu_exit_timer - dt_raw)
                if menu_exit_timer <= 0.0:
                    if menu_pending_action == "SETTINGS":
                        global _resolution_cache
                        _resolution_cache = None  # Limpa cache para recarregar resoluções
                        state = "SETTINGS"
                        settings_category = "main"
                        temp_settings = json.loads(json.dumps(settings))
                        for b in settings_main_btns:
                            b.update_rect()
                        for b in settings_action_btns.values():
                            b.update_rect()
                    elif menu_pending_action == "QUIT":
                        save_run_slot(0)
                        save_game()
                        running = False
                    else:
                        state = menu_pending_action
                    menu_pending_action = None

        # 3a. Lógica do Hub Room
        if state == "HUB" and hub_scene is not None:
            keys = pygame.key.get_pressed()
            hub_scene.update(dt, keys, SCREEN_W, SCREEN_H,
                             suppress_transitions=hub_chest_open or hub_equip_open or hub_status_open)
            if hub_countdown_active:
                hub_countdown_timer -= dt
                if hub_countdown_timer <= 0.0:
                    hub_countdown_active = False
                    if player is None:
                        reset_game(hub_last_char_id)
                        run_gold_collected = 0.0
                        autosave_timer = 0.0
                        if player is not None and hub_scene is not None:
                            _cid2   = player.char_id
                            _cdata2 = CHAR_DATA.get(_cid2, {})
                            hub_scene.apply_char_frames(
                                dir_walk      = dict(player._dir_walk_frames),
                                dir_idle      = dict(player._dir_idle_frames),
                                walk_fallback = list(player.anim_frames),
                                idle_fallback = list(player.idle_frames),
                                anim_spd      = _cdata2.get("anim_speed", 0.10),
                                idle_anim_spd = _cdata2.get("idle_anim_speed", 0.13),
                            )
                    state = "PLAYING"

        # 3b. Lógica do Mercado
        if state == "MARKET" and market_scene is not None:
            keys = pygame.key.get_pressed()
            market_scene.update(dt, keys, SCREEN_W, SCREEN_H)

        # 3c. Lógica da Sala de Recompensa
        if state == "REWARD_ROOM" and player is not None:
            if reward_room_player_pos is None:
                reward_room_player_pos = pygame.Vector2(SCREEN_W // 2, int(SCREEN_H * 0.65))
            keys = pygame.key.get_pressed()
            _rr_mv = pygame.Vector2(0, 0)
            if not hub_equip_open and not hub_status_open:
                if keys[pygame.K_w] or keys[pygame.K_UP]:    _rr_mv.y -= 1
                if keys[pygame.K_s] or keys[pygame.K_DOWN]:  _rr_mv.y += 1
                if keys[pygame.K_a] or keys[pygame.K_LEFT]:  _rr_mv.x -= 1
                if keys[pygame.K_d] or keys[pygame.K_RIGHT]: _rr_mv.x += 1
            _rr_is_moving = _rr_mv.length_squared() > 0
            if _rr_is_moving:
                _rr_mv = _rr_mv.normalize() * player.base_speed * dt
                reward_room_player_pos += _rr_mv
                _rr_bounds = pygame.Rect(int(SCREEN_W * 0.12), int(SCREEN_H * 0.28),
                                         int(SCREEN_W * 0.76), int(SCREEN_H * 0.55))
                reward_room_player_pos.x = max(_rr_bounds.left, min(_rr_bounds.right,  reward_room_player_pos.x))
                reward_room_player_pos.y = max(_rr_bounds.top,  min(_rr_bounds.bottom, reward_room_player_pos.y))
                # Atualiza direção de encaramento (igual ao player.update)
                if _rr_mv.x > 0:
                    player.facing_right = True;  player._facing_dir = "right"
                elif _rr_mv.x < 0:
                    player.facing_right = False; player._facing_dir = "left"
                elif _rr_mv.y > 0:
                    player._facing_dir = "down"
                elif _rr_mv.y < 0:
                    player._facing_dir = "up"
                # Animação de caminhada
                player.anim_timer += dt
                if player.anim_timer >= player.anim_speed:
                    player.anim_timer = 0.0
                    player.frame_idx = (player.frame_idx + 1) % len(player.anim_frames)
                player.idle_frame_idx = 0; player.idle_anim_timer = 0.0
            else:
                # Animação idle
                player.frame_idx = 0
                player.idle_anim_timer += dt
                if player.idle_anim_timer >= player.idle_anim_speed:
                    player.idle_anim_timer = 0.0
                    player.idle_frame_idx = (player.idle_frame_idx + 1) % len(player.idle_frames)
            # Atualiza player.image com a direção e frame corretos
            if _rr_is_moving:
                if player._dir_walk_frames:
                    _rr_dir_f = player._dir_walk_frames.get(player._facing_dir) or next(iter(player._dir_walk_frames.values()))
                    player.image = _rr_dir_f[player.frame_idx % len(_rr_dir_f)]
                else:
                    _rr_fset = player.anim_frames if player.facing_right else player.flipped_frames
                    player.image = _rr_fset[player.frame_idx % len(_rr_fset)]
            else:
                if player._dir_idle_frames:
                    _rr_dir_f = player._dir_idle_frames.get(player._facing_dir) or next(iter(player._dir_idle_frames.values()))
                    player.image = _rr_dir_f[player.idle_frame_idx % len(_rr_dir_f)]
                else:
                    _rr_fset = player.idle_frames if player.facing_right else player.idle_flipped_frames
                    player.image = _rr_fset[player.idle_frame_idx % len(_rr_fset)]

            # Atualiza mineração e coleta ores concluídos para o inventário
            if _mining_system is not None and not hub_equip_open and not hub_status_open:
                if reward_room_player_pos is not None:
                    _mining_system.update(dt, reward_room_player_pos)
                if player is not None:
                    _mining_system.collect_mined_ores(get_char_inventory(player.char_id))

        # 3. Atualização da Lógica do Jogo
        if state == "PLAYING" and player and player.hp > 0 and not show_stage_victory and not show_reward_dialog:

            current_xp_to_level = _bal.xp_to_level(level)

            keys = pygame.key.get_pressed()
            
            shake_multiplier = max(0.0, min(1.0, settings["accessibility"].get("screen_shake", 100) / 100.0))
            if shake_timer > 0:
                shake_timer -= dt
                shake_offset.x = random.uniform(-shake_strength, shake_strength) * shake_multiplier
                shake_offset.y = random.uniform(-shake_strength, shake_strength) * shake_multiplier
            else:
                shake_offset.x = 0
                shake_offset.y = 0
            
            game_time += dt
            autosave_timer += dt
            if autosave_timer >= 15.0:
                save_run_slot(0)
                autosave_timer = 0.0
                autosave_feedback_timer = 2.5
                # Atualiza tempo de jogo no perfil ativo a cada 15s
                if profile_mgr and profile_mgr.has_active_profile():
                    profile_mgr.update_playtime(15.0)
            update_mission_progress("time", dt)
            
            if REGEN_RATE > 0:
                player.hp = min(PLAYER_MAX_HP, player.hp + REGEN_RATE * dt)

            update_skill_feed(dt)

            time_scale = _bal.enemy_scale(game_time)

            current_spawn_rate = _bal.spawn_interval(game_time)
            
            biome_type = BG_DATA[selected_bg]["type"]
            player.base_speed = PLAYER_SPEED
            player.update(
                dt,
                keys,
                obstacles,
                particles_group=particles,
                biome_type=biome_type,
                combat_context=build_character_combat_context(),
            )
            
            if biome_type == "volcano" and player.iframes <= 0:
                if int(game_time * 2) % 5 == 0 and int((game_time - dt) * 2) % 5 != 0:
                    player.hp -= 0.05
                    damage_texts.add(DamageText(player.pos, "🔥", False, (255, 69, 0)))

            cam = pygame.Vector2(SCREEN_W/2, SCREEN_H/2) - player.pos + shake_offset

            combat_context = build_character_combat_context()
            ult_feedback = player.update_ultimate_effects(combat_context)
            kills += ult_feedback.kills_gained

            shot_t += dt

            dynamic_cooldown = SHOT_COOLDOWN
            dmg_mult_fury = 1.0

            if HAS_FURY:
                hp_ratio = max(player.hp / PLAYER_MAX_HP, 0.0)
                fury = (1.0 - hp_ratio)  
                dmg_mult_fury = 1.0 + 0.60 * fury
                dynamic_cooldown = SHOT_COOLDOWN * (1.0 - 0.45 * fury)

            if shot_t >= dynamic_cooldown:
                shot_t = 0
                target = None
                best_d = SHOT_RANGE**2
                p_pos = player.pos
                for e in enemies:
                    if abs(e.pos.x - p_pos.x) > SHOT_RANGE or abs(e.pos.y - p_pos.y) > SHOT_RANGE:
                        continue
                    d2 = (e.pos - p_pos).length_squared()
                    if d2 < best_d: best_d = d2; target = e
                if target:
                    attack_feedback = player.atacar(target, build_character_combat_context(dmg_mult_fury))
                    if attack_feedback.activated and attack_feedback.sound_name:
                        play_sfx(attack_feedback.sound_name)

            if ORB_COUNT > 0:
                rot_speed = 450 if has_serras else 150
                orb_rot_angle += rot_speed * dt
                current_orb_dmg = (ORB_DMG * 3) if has_serras else ORB_DMG
                _px = player.pos.x
                _py = player.pos.y
                _orb_step = 360.0 / ORB_COUNT
                for i in range(ORB_COUNT):
                    _rad = math.radians(orb_rot_angle + i * _orb_step)
                    _ov = _orb_vecs[i]
                    _ov.x = _px + math.cos(_rad) * ORB_DISTANCE
                    _ov.y = _py + math.sin(_rad) * ORB_DISTANCE
                    for e in enemy_batch_index.enemies_in_radius(_ov, 50):
                        tick_dmg = current_orb_dmg * dt * 10
                        if random.random() < CRIT_CHANCE: tick_dmg *= 2
                        e.hp -= tick_dmg
                        if e.hp <= 0:
                            if player.ult_charge < player.ult_max: player.ult_charge += 1
                            if random.random() < 0.50: gems.add(Gem(e.pos, loader))
                            if e.kind == "agis":
                                if selected_difficulty == "HARDCORE":
                                    show_stage_victory = True
                                else:
                                    show_reward_dialog = True
                                session_boss_kills += 1
                                save_data["stats"]["boss_kills"] += 1
                                update_mission_progress("boss", 1)
                            elif e.kind in ("boss", "mini_boss"):
                                session_boss_kills += 1
                                save_data["stats"]["boss_kills"] += 1
                                update_mission_progress("boss", 1)
                            e.kill(); kills += 1

            spawn_t += dt

            # ── OBSTÁCULOS GRADUAIS ──────────────────────────────────────────────
            # Espalhados pelo mundo desde o início, sem explosão ao nascer.
            # Usamos posições fixas de mundo (não relativas ao player) para que
            # o jogador vá encontrando-os à medida que explora/corre.
            obstacle_spawn_t += dt
            if (obstacle_spawn_t >= obstacle_spawn_interval
                    and obstacle_total_placed < OBSTACLE_MAX_GRADUAL):
                obstacle_spawn_t -= obstacle_spawn_interval
                _MIN_OBS_DIST = 130
                _MAX_TRIES    = 12
                for _try in range(_MAX_TRIES):
                    angle_rand = random.uniform(0, 2 * math.pi)
                    dist_rand  = random.uniform(600, 1800)
                    obs_pos    = player.pos + pygame.Vector2(
                        math.cos(angle_rand) * dist_rand,
                        math.sin(angle_rand) * dist_rand,
                    )
                    if all(obs_pos.distance_to(o.pos) >= _MIN_OBS_DIST for o in obstacles):
                        obstacles.add(Obstacle(obs_pos, loader, random.randint(0, 3)))
                        obstacle_total_placed += 1
                        break
                obstacle_spawn_interval = max(8.0, 18.0 - game_time / 40.0)

            # ── FILA DE HORDA (processada aos poucos por frame) ─────────────────
            # Limite de inimigos instanciados por frame para evitar spike de CPU
            HORDE_PER_FRAME = 6
            if pending_horde_queue:
                batch = pending_horde_queue[:HORDE_PER_FRAME]
                del pending_horde_queue[:HORDE_PER_FRAME]
                for _hkind, _hpos in batch:
                    enemies.add(create_enemy(
                        _hkind, _hpos,
                        _spawn_diff,
                        time_scale=time_scale,
                    ))

            current_int_time = int(game_time)
            if current_int_time % 60 == 0 and current_int_time > 0 and current_int_time not in triggered_hordes:
                triggered_hordes.add(current_int_time)
                damage_texts.add(DamageText(player.pos, "⚠️ HORDA! ⚠️", True, (255, 50, 50)))
                shake_timer = 1.0; shake_strength = 20
                play_sfx("ult")
                enemy_count = 40 + int(game_time // 120) * 10
                radius = 900
                horde_kind = "tank" if current_int_time % 120 == 0 else "runner"
                # Apenas enfileira — não cria tudo em um frame
                for i in range(enemy_count):
                    angle = math.radians(i * (360 / enemy_count))
                    hpos  = pygame.Vector2(
                        player.pos.x + math.cos(angle) * radius,
                        player.pos.y + math.sin(angle) * radius,
                    )
                    pending_horde_queue.append((horde_kind, hpos))

            if game_time >= BOSS_SPAWN_TIME * (bosses_spawned + 1):
                bosses_spawned += 1
                boss_pos = player.pos + pygame.Vector2(1200, 0)
                enemies.add(create_enemy("boss", boss_pos, _spawn_diff, time_scale=time_scale, boss_tier=bosses_spawned))
                warn_txt = font_l.render("⚠️ ALERTA DE CHEFÃO ⚠️", True, (255, 0, 0))
                screen.blit(warn_txt, warn_txt.get_rect(center=(SCREEN_W//2, SCREEN_H//2 - 200)))
                play_sfx("ult")

            # --- Mini Boss ---
            if game_time >= MINI_BOSS_SPAWN_TIME and "mini_boss_test" not in triggered_hordes:
                triggered_hordes.add("mini_boss_test")
                mb_pos = player.pos + pygame.Vector2(1000, 0)
                enemies.add(create_enemy("mini_boss", mb_pos, _spawn_diff, time_scale=time_scale))
                warn_txt = font_l.render("⚠️ MINI BOSS SURGIU! ⚠️", True, (255, 120, 0))
                screen.blit(warn_txt, warn_txt.get_rect(center=(SCREEN_W//2, SCREEN_H//2 - 200)))
                play_sfx("ult")

            # --- Agis — selo de invocação aparece no minuto 2 ---
            if game_time >= AGIS_SPAWN_TIME and "agis_seal" not in triggered_hordes:
                triggered_hordes.add("agis_seal")
                seal_offset = pygame.Vector2(random.choice([-1, 1]) * random.randint(180, 300),
                                             random.choice([-1, 1]) * random.randint(100, 220))
                doom_seals.add(DoomSeal(player.pos + seal_offset, loader))
                warn_txt = font_l.render("⚠️ AGIS ESTÁ CHEGANDO! ⚠️", True, (180, 0, 255))
                screen.blit(warn_txt, warn_txt.get_rect(center=(SCREEN_W//2, SCREEN_H//2 - 200)))
                play_sfx("ult")

            # --- Verifica se o selo do Agis terminou a animação ---
            for seal in list(doom_seals):
                if seal.done:
                    agis_pos = seal.pos.copy()
                    seal.kill()
                    enemies.add(create_enemy("agis", agis_pos, _spawn_diff,
                                             time_scale=time_scale, boss_tier=1))
                    warn_txt = font_l.render("⚠️ AGIS SURGIU! ⚠️", True, (220, 0, 255))
                    screen.blit(warn_txt, warn_txt.get_rect(center=(SCREEN_W//2, SCREEN_H//2 - 200)))
                    play_sfx("ult")

            if int(game_time) > 0 and int(game_time) % 120 == 0 and int(game_time) not in triggered_hordes:
                event_type = random.choice(["METEORO", "OURO", "SLIME", "DARKNESS"])
                triggered_hordes.add(int(game_time))
                if event_type == "METEORO":
                    damage_texts.add(DamageText(player.pos, "⚠️ CHUVA DE METEOROS! ⚠️", True, (255, 69, 0)))
                    for _ in range(15):
                        m_pos = player.pos + pygame.Vector2(random.randint(-800, 800), random.randint(-800, 800))
                        active_explosions.append(ExplosionAnimation(m_pos, 250, explosion_frames_raw))
                elif event_type == "OURO":
                    damage_texts.add(DamageText(player.pos, "💰 CHUVA DE OURO! 💰", True, (255, 215, 0)))
                    for _ in range(20):
                        drops.add(create_drop(player.pos + pygame.Vector2(random.randint(-500, 500), random.randint(-500, 500)), "coin"))
                elif event_type == "SLIME":
                    damage_texts.add(DamageText(player.pos, "🟢 INVASÃO DE SLIMES! 🟢", True, (0, 255, 0)))
                    # Slimes também enfileirados para não travar
                    for _ in range(30):
                        slime_pos = player.pos + pygame.Vector2(random.randint(-900, 900), random.randint(-900, 900))
                        pending_horde_queue.append(("slime", slime_pos))
                elif event_type == "DARKNESS":
                    damage_texts.add(DamageText(player.pos, "🌑 ESCURIDÃO TOTAL! 🌑", True, (100, 100, 255)))
                    darkness_timer = 30.0

            # ARENA_EVENT: obstáculos em anel — mantidos mas sem duplicar com os graduais
            if int(game_time) == 240 and "ARENA_EVENT" not in triggered_hordes:
                triggered_hordes.add("ARENA_EVENT")
                damage_texts.add(DamageText(player.pos, "🏟️ ARENA DE PAREDES! 🏟️", True, (255, 255, 0)))
                _ARENA_MIN_DIST = 130
                for i in range(16):   # reduzido de 24→16 para ser menos agressivo
                    angle    = math.radians(i * (360 / 16))
                    wall_pos = player.pos + pygame.Vector2(math.cos(angle), math.sin(angle)) * 700
                    if all(wall_pos.distance_to(o.pos) >= _ARENA_MIN_DIST for o in obstacles):
                        obstacles.add(Obstacle(wall_pos, loader, random.randint(0, 3)))
                
            if spawn_t >= current_spawn_rate:
                spawn_t = 0
                sp = player.pos + pygame.Vector2(random.choice([-1,1])*1100, random.randint(-600,600))

                if game_time < 30:
                    # Fase inicial: bat e runner
                    kind_early = random.choices(["bat", "runner"], weights=[60, 40], k=1)[0]
                    enemies.add(create_enemy(kind_early, sp, _spawn_diff, time_scale=time_scale))
                else:
                    # Pool base
                    spawn_list    = ["runner", "bat", "tank", "shooter"]
                    spawn_weights = [35,       25,    25,     15]

                    # Goblin entra no pool a partir de 60 segundos — rápido e ágil
                    if game_time >= 60:
                        spawn_list.append("goblin")
                        spawn_weights.append(22)

                    # Beholder entra no pool a partir de 90 segundos — todas as dificuldades
                    if game_time >= 90:
                        spawn_list.append("beholder")
                        spawn_weights.append(18)

                    # Orc entra no pool a partir do minuto 3 (180 s)
                    if game_time >= 180:
                        spawn_list.append("orc")
                        spawn_weights.append(20)

                    # Monstros exclusivos do vulcão — a partir de 2 min
                    if selected_bg == "volcano" and game_time >= 120:
                        spawn_list.extend(["slime_fire", "slime_red", "slime_yellow"])
                        spawn_weights.extend([18, 14, 14])

                    # Ghost — Moon e Volcano a partir de 2 min
                    if selected_bg in ("moon", "volcano") and game_time >= 120:
                        spawn_list.append("ghost")
                        spawn_weights.append(16)

                    if selected_difficulty in ["DIFÍCIL", "HARDCORE"]:
                        spawn_list.extend(["slime", "minotauro"])
                        spawn_weights.extend([15, 15])
                        # Rat com peso extra em dificuldades harder
                        if game_time >= 120:
                            spawn_list.append("rat")
                            spawn_weights.append(20)
                            # Monstros do vulcão com peso extra em hard/hardcore
                            if selected_bg == "volcano":
                                for _vk in ["slime_fire", "slime_red", "slime_yellow"]:
                                    _vi = spawn_list.index(_vk) if _vk in spawn_list else -1
                                    if _vi >= 0:
                                        spawn_weights[_vi] += 8
                            # Ghost com peso extra em hard/hardcore
                            if selected_bg in ("moon", "volcano"):
                                _gi = spawn_list.index("ghost") if "ghost" in spawn_list else -1
                                if _gi >= 0:
                                    spawn_weights[_gi] += 6

                    chosen_enemy = random.choices(spawn_list, weights=spawn_weights, k=1)[0]
                    elite_chance = min(0.15, 0.03 + (game_time / AGIS_SPAWN_TIME) * 0.12)
                    is_elite     = random.random() < elite_chance

                    enemies.add(create_enemy(chosen_enemy, sp, _spawn_diff, time_scale=time_scale, is_elite=is_elite))

            # ECS batch update — substitui o loop LOD por inimigo
            _lod_dist_sq = 1_440_000  # 1200**2
            ecs_world.context.update(
                p_pos=player.pos,
                cam=cam,
                obstacles=obstacles,
                enemy_projectiles=enemy_projectiles,
                puddles=puddles,
                loader=loader,
                selected_pact=selected_pact,
                enemy_projectile_cls=ModularEnemyProjectile,
                puddle_cls=Puddle,
                shooter_proj_image=SHOOTER_PROJ_IMAGE,
                obstacle_grid_index=obstacle_grid_index,
                lod_dist_sq=_lod_dist_sq,
                sep_frame=_sep_frame,
            )
            ecs_world.process(dt)
            for _da in list(death_anims):
                _da.update(dt, cam)
            # --- Colisão física: empurra inimigos para fora do raio do player ---
            _PUSH_R    = (player.rect.width + 8) // 2
            _PUSH_R_SQ = _PUSH_R * _PUSH_R
            for _pe in enemy_batch_index.enemies_in_radius(player.pos, _PUSH_R + 20):
                _dv    = _pe.pos - player.pos
                _dl_sq = _dv.length_squared()
                if 0 < _dl_sq < _PUSH_R_SQ:
                    _dl = _dl_sq ** 0.5
                    _pe.pos += _dv * ((_PUSH_R - _dl) / _dl)

            puddles.update(dt, cam)
            doom_seals.update(dt, cam)

            # --- Projéteis do Agis ---
            for e in enemies:
                if e.kind != "agis":
                    continue
                agis_dmg = 1.5 * _spawn_diff.get("dmg_mult", 1.0)

                # Ataque básico — 1 projétil direto ao jogador
                if getattr(e, "pending_agis_shot", False):
                    e.pending_agis_shot = False
                    enemy_projectiles.add(
                        AgisProjectile(e.pos, e.agis_shot_dir, agis_dmg, loader))

                # Magia em área — 8 orbes em todas as direções
                if getattr(e, "pending_agis_area", False):
                    e.pending_agis_area = False
                    num_orbs = 8
                    for i in range(num_orbs):
                        angle_rad = math.radians(i * (360 / num_orbs))
                        area_dir  = pygame.Vector2(math.cos(angle_rad), math.sin(angle_rad))
                        enemy_projectiles.add(
                            AgisProjectile(e.pos, area_dir, agis_dmg * 0.8, loader))
                    damage_texts.add(DamageText(e.pos, "MAGIA!", True, (180, 0, 255)))
                    shake_timer    = 0.2
                    shake_strength = 8

            projectiles.update(dt, cam)
            enemy_projectiles.update(dt, cam, SCREEN_W, SCREEN_H)
            gems.update(dt, cam, player.pos)
            drops.update(dt, cam)
            obstacles.update(dt, cam)
            damage_texts.update(dt, cam)
            particles.update(dt, cam)

            # --- Dano melee do mini_boss ---
            for e in enemies:
                if getattr(e, "pending_melee_hit", False):
                    e.pending_melee_hit = False
                    if player.iframes <= 0:
                        raw_dmg = getattr(e, "melee_dmg", 1.5)
                        player.hp     -= raw_dmg * (1.0 - DAMAGE_RES)
                        player.iframes = 0.6
                        shake_timer    = 0.25
                        shake_strength = 10
                        play_sfx("hurt")
                        damage_texts.add(DamageText(player.pos, raw_dmg, False, (255, 80, 80)))
                        if THORNS_PERCENT > 0:
                            e.hp -= raw_dmg * THORNS_PERCENT

            # --- Separação de inimigos via Numba/NumPy kernel (frames alternados) ---
            _sep_frame = (_sep_frame + 1) % 2
            if _sep_frame == 0:
                _sep_enemies = [_e for _e in enemies if _e.kind not in ("boss", "agis")]
                if len(_sep_enemies) > 1:
                    _sep_pos = np.empty((len(_sep_enemies), 2), dtype=np.float32)
                    for _i, _e in enumerate(_sep_enemies):
                        _sep_pos[_i, 0] = _e.pos.x
                        _sep_pos[_i, 1] = _e.pos.y
                    _sep_deltas = enemy_separation(_sep_pos, SEP_DIST, SEP_FORCE * dt * 2)
                    for _i, _e in enumerate(_sep_enemies):
                        _e.pos.x += float(_sep_deltas[_i, 0])
                        _e.pos.y += float(_sep_deltas[_i, 1])

            # Decorações animadas da floresta
            if selected_bg == "forest" and forest_deco_manager is not None:
                forest_deco_manager.update(dt, cam, SCREEN_W, SCREEN_H, player.pos)

            # Decorações do dungeon + colisão BDS
            if selected_bg == "dungeon" and dungeon_deco_manager is not None:
                dungeon_deco_manager.update(dt, cam, SCREEN_W, SCREEN_H, player.pos)
                dungeon_deco_manager.push_player(player)

            # Decorações do volcano + colisão rochas/geiseres
            if selected_bg == "volcano" and volcano_deco_manager is not None:
                volcano_deco_manager.update(dt, cam, SCREEN_W, SCREEN_H, player.pos)
                volcano_deco_manager.push_player(player)

            # Decorações do moon + colisão rochas
            if selected_bg == "moon" and moon_deco_manager is not None:
                moon_deco_manager.update(dt, cam, SCREEN_W, SCREEN_H, player.pos)
                moon_deco_manager.push_player(player)

            current_obstacle_count = len(obstacles)
            if current_obstacle_count != last_obstacle_count:
                obstacle_grid_index.rebuild(obstacles)
                last_obstacle_count = current_obstacle_count

            enemy_batch_index.rebuild(enemies)

            now_ms = pygame.time.get_ticks()
            active_explosions = [exp for exp in active_explosions if exp.update(now_ms)]

            for p in list(projectiles):
                is_melee = getattr(p, "is_melee", False)
                if not is_melee:
                    if obstacle_grid_index.point_collides(p.pos):
                        p.kill()
                        continue

                _p_hitbox = getattr(p, "hitbox", p.rect)
                # +80 garante que sprites grandes (boss/tank) na borda do hitbox sejam incluídos
                _p_radius = max(_p_hitbox.width, _p_hitbox.height) + 80
                _nearby   = enemy_batch_index.enemies_in_radius(p.pos, _p_radius)
                hits = [_e for _e in _nearby if _p_hitbox.colliderect(_e.rect)]
                for hit in hits:
                    if hit not in p.hit_enemies:
                        dmg_dealt = p.dmg
                        is_crit = random.random() < CRIT_CHANCE
                        if is_crit:
                            dmg_dealt *= CRIT_DMG_MULT
                            hitstop_timer = 0.03
                        
                        hit.hp -= dmg_dealt
                        if LIFESTEAL_PCT > 0 and player:
                            player.hp = min(PLAYER_MAX_HP, player.hp + dmg_dealt * LIFESTEAL_PCT * 0.50)
                        p.hit_enemies.add(hit)
                        play_sfx("hit") 

                        if EXECUTE_THRESH > 0 and hit.kind != "boss":
                            if hit.hp > 0 and (hit.hp / hit.max_hp) <= EXECUTE_THRESH:
                                hit.hp = 0
                        
                        hit.flash_timer = 0.1 
                        
                        if is_melee:
                            knock_dir = (hit.pos - player.pos).normalize()
                            knock_force = 15.0 
                        else:
                            _vsq = p.vel.length_squared()
                            knock_dir = (p.vel * (1.0 / _vsq**0.5)) if _vsq > 0 else _VEC2_RIGHT
                            knock_force = 3.0 
                        
                        if HAS_CHAOS_BOLT and random.random() < 0.15:
                            active_explosions.append(ExplosionAnimation(hit.pos, 150, explosion_frames_raw))
                            hit.hp -= PROJECTILE_DMG * 2

                        if hit.kind == "boss": knock_force *= 0.1
                        elif hit.kind == "agis": knock_force *= 0.15
                        elif hit.kind == "mini_boss": knock_force *= 0.2
                        hit.knockback += knock_dir * knock_force
                        
                        d_color = (255, 200, 0) if is_melee else (255, 255, 255)
                        damage_texts.add(DamageText(hit.pos, dmg_dealt, is_crit, d_color))
                        
                        has_explosion = EXPLOSION_RADIUS > 0 or has_bazuca
                        if has_explosion:
                            current_exp_rad = EXPLOSION_RADIUS
                            current_exp_rad *= EXPLOSION_SIZE_MULT
                            current_exp_dmg = EXPLOSION_DMG * 3 if has_bazuca else EXPLOSION_DMG
                            
                            exp_pos = p.pos
                            active_explosions.append(ExplosionAnimation(exp_pos, current_exp_rad, explosion_frames_raw))
                            play_sfx("explosion")
                            for e in enemy_batch_index.enemies_in_radius(exp_pos, current_exp_rad):
                                exp_dmg_dealt = current_exp_dmg
                                exp_is_crit = random.random() < CRIT_CHANCE
                                if exp_is_crit:
                                    exp_dmg_dealt *= 2
                                    hitstop_timer = 0.03
                                e.hp -= exp_dmg_dealt
                                e.flash_timer = 0.1
                                exp_dir = (e.pos - exp_pos).normalize() if (e.pos - exp_pos).length() > 0 else pygame.Vector2(1,0)
                                e.knockback += exp_dir * 8.0
                                damage_texts.add(DamageText(e.pos, exp_dmg_dealt, exp_is_crit, (255, 100, 0)))
                        
                        if hit.hp <= 0:
                            if player.ult_charge < player.ult_max: player.ult_charge += 1
                            # Burst de partículas na morte do inimigo para game feel.
                            if hit.kind == "agis":
                                kill_color  = (200, 0, 255)
                            elif hit.kind in ("boss", "mini_boss"):
                                kill_color  = (255, 200, 0)
                            else:
                                kill_color  = (255, 80, 40)
                            if hit.kind == "boss":
                                burst_count = 20
                            elif hit.kind == "agis":
                                burst_count = 22
                            elif hit.kind == "mini_boss":
                                burst_count = 16
                            elif hit.kind in ("tank", "elite", "orc"):
                                burst_count = 12
                            elif hit.kind == "goblin":
                                burst_count = 6
                            elif hit.kind == "beholder":
                                burst_count = 10
                            elif hit.kind == "rat":
                                burst_count = 10
                            else:
                                burst_count = 8
                            _ri, _ru = random.randint, random.uniform
                            for _ in range(burst_count):
                                _particle_pool.spawn(particles, hit.pos, kill_color, _ri(4, 8), _ri(120, 240), _ru(0.25, 0.55))
                            if hit.kind == "boss":
                                shake_timer = 0.6; shake_strength = 18
                            elif hit.kind == "agis":
                                shake_timer = 0.7; shake_strength = 22
                            elif hit.kind == "mini_boss":
                                shake_timer = 0.4; shake_strength = 12
                            # Animação de morte para inimigos com morte_sheet (ex: ghost)
                            _morte_frames = hit.get_morte_frames() if hasattr(hit, "get_morte_frames") else None
                            if _morte_frames:
                                death_anims.add(EnemyDeathAnim(hit.pos, _morte_frames))
                            if random.random() < 0.50: gems.add(Gem(hit.pos, loader))
                            hit.kill(); kills += 1
                            save_data["stats"]["total_kills"] += 1
                            update_mission_progress("kills", 1)
                            # Verifica conquistas forte a cada 100 abates
                            if save_data["stats"]["total_kills"] % 100 == 0:
                                _check_achievements()
                            if hit.kind == "boss":
                                session_boss_kills += 1
                                save_data["stats"]["boss_kills"] += 1
                                update_mission_progress("boss", 1)
                                drops.add(create_drop(hit.pos, "chest"))
                                if selected_difficulty != "HARDCORE" and selected_difficulty not in save_data.get("beaten_difficulties", []):
                                    save_data.setdefault("beaten_difficulties", []).append(selected_difficulty)
                            elif hit.kind == "agis":
                                # Agis dropa baú + várias moedas
                                session_boss_kills += 1
                                save_data["stats"]["boss_kills"] += 1
                                update_mission_progress("boss", 1)
                                if selected_difficulty != "HARDCORE" and selected_difficulty not in save_data.get("beaten_difficulties", []):
                                    save_data.setdefault("beaten_difficulties", []).append(selected_difficulty)
                                drops.add(create_drop(hit.pos, "chest"))
                                gold_count = getattr(hit, "gold_drops", 15)
                                for gi in range(gold_count):
                                    offset = pygame.Vector2(random.randint(-80, 80), random.randint(-80, 80))
                                    drops.add(create_drop(hit.pos + offset, "coin"))
                                if selected_difficulty == "HARDCORE":
                                    show_stage_victory = True
                                else:
                                    show_reward_dialog = True
                                _check_achievements()
                            elif hit.kind == "mini_boss":
                                # Mini boss conta como kill de boss e dropa várias moedas
                                session_boss_kills += 1
                                save_data["stats"]["boss_kills"] += 1
                                update_mission_progress("boss", 1)
                                gold_count = getattr(hit, "gold_drops", 5)
                                for gi in range(gold_count):
                                    offset = pygame.Vector2(random.randint(-60, 60), random.randint(-60, 60))
                                    drops.add(create_drop(hit.pos + offset, "coin"))
                            elif random.random() < DROP_CHANCE:
                                drops.add(create_drop(hit.pos, "coin"))

                            # Salva imediatamente ao desbloquear metas de personagem (Caçador/Mago).
                            check_achievements(save_when_unlocked=True)
                        
                        # Lógica de Ricochete e Perfuração (Apenas para Projéteis)
                        if not is_melee:
                            if p.ricochet > 0:
                                p.ricochet -= 1
                                p.hit_enemies.discard(hit)

                                excluded_ids = {id(enemy) for enemy in p.hit_enemies}
                                excluded_ids.add(id(hit))
                                new_target = enemy_batch_index.nearest_enemy(p.pos, excluded=excluded_ids)
                                if new_target:
                                    p.vel = (new_target.pos - p.pos).normalize() * PROJECTILE_SPEED
                                else:
                                    p.kill()
                            elif len(p.hit_enemies) > p.pierce:
                                p.kill()

            for p in list(enemy_projectiles):
                if p.rect.colliderect(player.rect) and player.iframes <= 0:
                    player.hp -= p.dmg * (1.0 - DAMAGE_RES)
                    player.iframes = 0.5
                    play_sfx("hurt")
                    shake_timer = 0.22
                    shake_strength = 9
                    p.kill()
                    if THORNS_PERCENT > 0:
                        owner = getattr(p, "owner", None)
                        if owner and owner.hp > 0:
                            reflected_dmg = p.dmg * THORNS_PERCENT
                            owner.hp -= reflected_dmg
                            damage_texts.add(DamageText(owner.pos, int(reflected_dmg), False, (255, 0, 255)))

            for g in list(gems):
                if g.rect.colliderect(player.rect):
                    xp += int(GEM_XP * (1.0 + XP_BONUS_PCT)); g.kill(); play_sfx("gem")

            for d in list(drops):
                if d.rect.colliderect(player.rect):
                    if d.kind == "coin":
                        coin_value = 50 * _spawn_diff.get("gold_mult", 1.0) * GOLD_RUN_MULT
                        run_gold_collected += coin_value
                        save_data["gold"] += coin_value
                        achievements_data["total_gold_accumulated"] = achievements_data.get("total_gold_accumulated", 0.0) + coin_value
                        update_mission_progress("gold", coin_value)
                        play_sfx("drop")
                        d.kill()
                    elif d.kind == "chest":
                        auto_pickup = settings["gameplay"].get("auto_pickup_chest", "On") == "On"
                        if not auto_pickup and not is_control_pressed(keys, "dash"):
                            continue

                        chest_loot = pick_upgrades_with_synergy(list(UPGRADE_POOL.keys()), player_upgrades, k=3)
                        auto_apply = settings["gameplay"].get("auto_apply_chest_reward", "On") == "On"
                        if auto_apply:
                            for loot in chest_loot:
                                apply_upgrade(loot)
                            chest_loot = []
                        else:
                            state = "CHEST_UI"
                            chest_ui_timer = 5.0
                        d.kill()

            for p in list(puddles):
                if p.hitbox.colliderect(player.rect) and player.iframes <= 0:
                    player.hp -= 0.5 * dt

            if xp >= current_xp_to_level:
                level += 1
                session_max_level = max(session_max_level, level)
                update_mission_progress("level", level, is_absolute=True)
                xp = 0
                state = "UPGRADE"
                play_sfx("levelup")
                up_keys, up_rarities = [], []
                options = pick_upgrades_with_synergy(list(UPGRADE_POOL.keys()), player_upgrades, k=5)
                for opt in options:
                    rarity_roll = random.random()
                    chosen_rarity = "COMUM"
                    for r_name, r_data in RARITIES.items():
                        if rarity_roll < r_data["chance"]: chosen_rarity = r_name; break
                    up_keys.append(opt)
                    up_rarities.append((chosen_rarity, RARITIES[chosen_rarity]))

            if player.hp <= 0:
                play_sfx("lose")
                state = "GAME_OVER"
                save_run_slot(0)
                save_data["stats"]["deaths"] += 1
                save_data["stats"]["total_time"] += game_time
                save_data["stats"]["max_level_reached"] = max(save_data["stats"]["max_level_reached"], session_max_level)
                check_achievements()
                _check_achievements()
                # Award profile XP based on time survived and difficulty
                if profile_mgr and profile_mgr.has_active_profile():
                    _xp_rate = PROFILE_XP_RATES.get(selected_difficulty, 10)
                    _xp_earned = int(game_time / 60 * _xp_rate)
                    if _xp_earned > 0:
                        _ap = profile_mgr.get_active_profile()
                        _old_lv = ProfileManager.xp_to_level(_ap.get("profile_xp", 0))[0]
                        profile_mgr.update_xp(_ap["id"], _xp_earned)
                        _new_lv = ProfileManager.xp_to_level(_ap.get("profile_xp", 0))[0]
                        if _new_lv > _old_lv:
                            _unlocked_now = ProfileManager.level_unlocked_avatars(_new_lv)
                            _unlocked_prev = ProfileManager.level_unlocked_avatars(_old_lv)
                            _new_av_count = _unlocked_now - _unlocked_prev
                            _lv_def = {
                                "icon": "",
                                "name": f"NÍVEL DE PERFIL {_new_lv}!",
                                "desc": f"+{_xp_earned} XP" + (f"  •  {_new_av_count} novo(s) avatar(es)" if _new_av_count > 0 else ""),
                            }
                            _achievement_notifs.append([_lv_def, 5.0])
                save_game()

        elif state == "CHEST_UI":
            auto_apply = settings["gameplay"].get("auto_apply_chest_reward", "On") == "On"
            if auto_apply:
                chest_ui_timer -= dt
                if chest_ui_timer <= 0:
                    for loot in chest_loot:
                        apply_upgrade(loot)
                    chest_loot = []
                    state = "PLAYING"

        # 4. Desenho na Tela
        screen.fill((0, 0, 0))

        # Lógica de desenho baseada no estado
        if state == "PROFILE_SELECT":
            draw_menu_background(screen, m_pos, dt, overlay_alpha=60)
            _draw_profile_select(screen, font_s, font_m, font_l, m_pos,
                                 _prof_mode, _prof_sel_idx, _prof_new_name,
                                 _prof_new_ci, _prof_new_char, _prof_name_focus, _prof_del_confirm)

        elif state == "MENU":
            draw_menu_background(screen, m_pos, dt)

            # Logo centralizada horizontalmente sobre os botões do menu
            if menu_logo_img is not None:
                logo_x = menu_btns[0].rect.centerx - menu_logo_img.get_width() // 2
                logo_y = int(SCREEN_H * 0.04)
                screen.blit(menu_logo_img, (logo_x, logo_y))

            hovered_menu_btn = None
            for idx, b in enumerate(menu_btns):
                b.check_hover(m_pos, snd_hover)
                if b.is_hovered:
                    hovered_menu_btn = b
                delay = idx * 0.04
                slide_ratio = max(0.0, min(1.0, (menu_intro_timer - delay) / 0.25))
                exit_progress = 0.0
                if menu_pending_action is not None and MENU_EXIT_DURATION > 0:
                    exit_progress = 1.0 - max(0.0, min(1.0, menu_exit_timer / MENU_EXIT_DURATION))
                offset_y = int(80 * slide_ratio - 110 * exit_progress)
                b.draw(screen, offset_y=offset_y)

            _menu_profile_widget_rect = _draw_profile_widget(screen, font_s, font_m, m_pos)

            # ── Botões de links externos (Site Oficial / Steam) ─────────────
            if _site_btn_surf is not None:
                screen.blit(_site_btn_surf, menu_site_rect.topleft)

            if _steam_btn_surf is not None:
                screen.blit(_steam_btn_surf, menu_steam_rect.topleft)

            # Overlay de perfil/conquistas (abre ao clicar no widget)
            if menu_profile_open:
                _draw_profile_viewer(screen, font_s, font_m, font_l, m_pos, show_change_btn=True)

        elif state == "SAVES":
            draw_menu_background(screen, m_pos, dt)
            overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA); overlay.fill((0, 0, 0, 180)); screen.blit(overlay, (0, 0))
            draw_screen_title(screen, font_l, "SAVES / PROGRESSO", SCREEN_W//2, int(SCREEN_H*0.14))

            for idx, btn in enumerate(saves_slot_btns):
                slot_path = get_run_slot_path(idx)
                slot_exists = os.path.exists(slot_path)
                btn.text = f"SLOT {idx + 1} - {'DISPONÍVEL' if slot_exists else 'VAZIO'}"
                btn.color = (40, 90, 40) if slot_exists else (60, 60, 70)
                btn.check_hover(m_pos, snd_hover)
                btn.draw(screen)

            saves_back_btn.check_hover(m_pos, snd_hover)
            saves_back_btn.draw(screen)

        elif state == "MISSIONS":
            draw_menu_background(screen, m_pos, dt)
            overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA); overlay.fill((0, 0, 0, 180)); screen.blit(overlay, (0, 0))
            draw_screen_title(screen, font_l, "MISSÕES DIÁRIAS", SCREEN_W//2, int(SCREEN_H*0.12), text_color=(255, 215, 0))

            now_dt = datetime.now()
            next_reset = (now_dt + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            remaining = max(0, int((next_reset - now_dt).total_seconds()))
            rem_h = remaining // 3600
            rem_m = (remaining % 3600) // 60
            rem_s = remaining % 60
            timer_txt = font_s.render(f"RESET EM: {rem_h:02}:{rem_m:02}:{rem_s:02}", True, (255, 240, 140))
            screen.blit(timer_txt, timer_txt.get_rect(center=(SCREEN_W//2, SCREEN_H*0.18)))
            
            for i, m in enumerate(save_data["daily_missions"]["active"]):
                y_base = int(SCREEN_H * 0.22) + i * 74
                box_rect = pygame.Rect(SCREEN_W//2 - 310, y_base, 620, 66)
                pygame.draw.rect(screen, (30, 30, 50, 200), box_rect, border_radius=8)
                pygame.draw.rect(screen, (100, 100, 255), box_rect, 2, border_radius=8)
                title = font_m.render(m['name'], True, (255, 255, 100))
                screen.blit(title, (box_rect.x + 14, box_rect.y + 6))
                _prog_pct = min(1.0, m['progress'] / max(1, m['goal']))
                _prog_txt = font_s.render(f"{m['progress']}/{m['goal']}", True, (180, 220, 180))
                screen.blit(_prog_txt, (box_rect.x + 14, box_rect.y + 34))
                prog_bar_rect = pygame.Rect(box_rect.x + 130, box_rect.y + 38, 240, 12)
                pygame.draw.rect(screen, (0, 0, 0), prog_bar_rect)
                pygame.draw.rect(screen, (0, 220, 80), (prog_bar_rect.x, prog_bar_rect.y, int(prog_bar_rect.width * _prog_pct), prog_bar_rect.height))
                pygame.draw.rect(screen, (180, 180, 180), prog_bar_rect, 1)
                _rew_txt = font_s.render(f"+{m['reward']}G", True, (255, 200, 60))
                screen.blit(_rew_txt, (box_rect.right - 110, box_rect.y + 6))
                if m['completed']:
                    if m['claimed']:
                        claim_txt = font_s.render("COLETADO!", True, (100, 255, 100))
                        screen.blit(claim_txt, (box_rect.right - 110, box_rect.centery - 8))
                    else:
                        mission_claim_btns[i].rect.midright = (box_rect.right - 6, box_rect.centery)
                        mission_claim_btns[i].check_hover(m_pos, snd_hover)
                        mission_claim_btns[i].draw(screen)
            mission_btns[0].check_hover(m_pos, snd_hover); mission_btns[0].draw(screen)

        elif state == "SHOP":
            draw_menu_background(screen, m_pos, dt)
            overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
            overlay.fill((UI_THEME["void_black"][0], UI_THEME["void_black"][1], UI_THEME["void_black"][2], 185))
            screen.blit(overlay, (0, 0))

            shop_header = pygame.Rect(int(SCREEN_W * 0.08), int(SCREEN_H * 0.06), int(SCREEN_W * 0.84), 105)
            draw_dark_panel(screen, shop_header, alpha=180, border_color=UI_THEME["old_gold"])

            draw_screen_title(screen, font_l, "ÁRVORE DE TALENTOS", SCREEN_W//2, int(SCREEN_H*0.1))
            gold_txt = font_m.render(f"OURO: {save_data['gold']}", True, UI_THEME["faded_gold"])
            screen.blit(gold_txt, gold_txt.get_rect(topright=(SCREEN_W - 30, 20)))

            path_names = list(TALENT_TREE.keys())
            for p_idx, p_name in enumerate(path_names):
                path = TALENT_TREE[p_name]
                px = int(SCREEN_W * 0.1)
                py = int(SCREEN_H * (SHOP_PATH_TOP_RATIO + p_idx * SHOP_PATH_GAP_RATIO))
                
                row_panel = pygame.Rect(px - 20, py - 16, int(SCREEN_W * 0.80), SHOP_ROW_PANEL_HEIGHT)
                draw_dark_panel(screen, row_panel, alpha=175, border_color=UI_THEME["iron"])

                p_title = font_m.render(path["title"], True, UI_THEME["parchment"])
                screen.blit(p_title, (px, py))
                p_desc = font_s.render(path["desc"], True, UI_THEME["mist"])
                screen.blit(p_desc, (px, py + 40))

                skill_keys = list(path["skills"].keys())
                for s_idx, s_key in enumerate(skill_keys):
                    skill = path["skills"][s_key]
                    lvl = save_data["perm_upgrades"].get(s_key, 0)
                    sy = py + SHOP_SKILL_TOP_OFFSET + s_idx * SHOP_SKILL_GAP
                    
                    s_txt = font_s.render(f"{skill['name']} ({lvl}/{skill['max']})", True, UI_THEME["old_gold"])
                    screen.blit(s_txt, (px + 50, sy))
                    sd_txt = load_body_font(18).render(skill["desc"], True, (200, 200, 200))
                    screen.blit(sd_txt, (px + 300, sy + 5))

                    btn_found = shop_talent_btn_map[(p_name, s_key)]
                    if lvl < skill["max"]:
                        price = skill["cost"][lvl]
                        btn_found.text = f"{price} G"
                        btn_found.color = (40, 100, 40) if save_data["gold"] >= price else (100, 40, 40)
                    else:
                        btn_found.text = "MAX"
                        btn_found.color = (60, 60, 60)
                    
                    btn_found.check_hover(m_pos, snd_hover)
                    btn_found.draw(screen)

            shop_back_btn.check_hover(m_pos, snd_hover); shop_back_btn.draw(screen)

        elif state == "ITEM_SHOP":
            draw_menu_background(screen, m_pos, dt)
            _ov = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
            _ov.fill((UI_THEME["void_black"][0], UI_THEME["void_black"][1], UI_THEME["void_black"][2], 185))
            screen.blit(_ov, (0, 0))

            # Título (sem painel/retângulo de fundo)
            draw_screen_title(screen, font_l, "LOJA DE ITENS", SCREEN_W // 2, int(SCREEN_H * 0.075))
            _is_gold_txt = font_m.render(f"OURO: {save_data['gold']}", True, UI_THEME["faded_gold"])
            screen.blit(_is_gold_txt, _is_gold_txt.get_rect(topright=(SCREEN_W - 30, 20)))

            # Abas (tabs) — desenhadas manualmente para controle total de cor
            _tab_w_actual = max(180, SCREEN_W // (len(ITEM_SHOP_TABS) + 1))
            for _ti, _tlabel in enumerate(ITEM_SHOP_TABS):
                _tbtn = item_shop_tab_btns[_ti]
                _tbtn.rect.width   = _tab_w_actual
                _tbtn.rect.height  = 42
                _tbtn.rect.topleft = (int(SCREEN_W * 0.05) + _ti * (_tab_w_actual + 8), int(SCREEN_H * 0.135))
                _is_active   = (_ti == item_shop_active_tab)
                _is_tab_lock = (_ti in (2,))   # UTILITÁRIOS ainda em breve

                # Fundo da aba
                if _is_active:
                    _tab_bg = (50, 40, 28)
                elif _ti == _ITEM_SHOP_SELL_TAB:
                    _tab_bg = (30, 20, 20)
                else:
                    _tab_bg = (28, 22, 16)
                pygame.draw.rect(screen, _tab_bg, _tbtn.rect, border_radius=6)
                # Borda
                if _is_active:
                    _tab_border = (180, 160, 100)
                elif _ti == _ITEM_SHOP_SELL_TAB:
                    _tab_border = (140, 60, 60)
                else:
                    _tab_border = (60, 50, 40)
                pygame.draw.rect(screen, _tab_border, _tbtn.rect, 1, border_radius=6)

                # Texto da aba
                if _is_active:
                    _tab_color = (220, 200, 140)
                elif _is_tab_lock:
                    _tab_color = (200, 60, 60)
                elif _ti == _ITEM_SHOP_SELL_TAB:
                    _tab_color = (220, 120, 100)
                else:
                    _tab_color = (200, 180, 120)
                _tab_surf  = font_s.render(_tlabel, True, _tab_color)
                screen.blit(_tab_surf, _tab_surf.get_rect(center=_tbtn.rect.center))

            # Painel de conteúdo (área clipeada)
            _cx0     = int(SCREEN_W * 0.05)
            _cy0     = int(SCREEN_H * 0.21)
            _cw      = int(SCREEN_W * 0.90)
            _ch      = int(SCREEN_H * 0.67)
            _SB_W    = 14          # largura da scrollbar
            _grid_w  = _cw - _SB_W - 8  # largura usável para o grid
            _cpanel  = pygame.Rect(_cx0, _cy0, _cw, _ch)
            draw_dark_panel(screen, _cpanel, alpha=160, border_color=UI_THEME["iron"])

            if item_shop_active_tab == 0:
                _SLOT = 72
                _PAD  = 8
                _COLS = max(1, (_grid_w - 16) // (_SLOT + _PAD))
                _itens_dir = os.path.join("assets", "ui", "itens")

                # ── 1ª passagem: calcular altura total do conteúdo ─────────────
                _total_h = 0
                for _cdat in ITEM_SHOP_CATEGORIES.values():
                    _rows = math.ceil(_cdat["count"] / _COLS)
                    _total_h += 30 + _rows * (_SLOT + _PAD) + 10

                # Limite de scroll
                _max_scroll = max(0, _total_h - _ch + 16)
                item_shop_scroll_y = max(0, min(item_shop_scroll_y, _max_scroll))

                # ── 2ª passagem: desenhar itens com clip ───────────────────────
                _clip_rect = pygame.Rect(_cx0 + 4, _cy0 + 4, _grid_w, _ch - 8)
                screen.set_clip(_clip_rect)

                _draw_x = _cx0 + 12
                _draw_y = _cy0 + 12 - item_shop_scroll_y

                _tooltip_data = None   # (rect, stat_dict) do item em hover
                for _cname, _cdat in ITEM_SHOP_CATEGORIES.items():
                    # Rótulo da subcategoria
                    _cat_lbl = font_s.render(f"— {_cname} —", True, UI_THEME["old_gold"])
                    screen.blit(_cat_lbl, (_draw_x, _draw_y))
                    _draw_y += 30
                    _col = 0
                    _draw_x = _cx0 + 12

                    _stats_list = ITEM_SHOP_STATS.get(_cname, [])

                    for _n in range(1, _cdat["count"] + 1):
                        _fname = f"{_cdat['prefix']} ({_n}).png"

                        # Carrega e faz cache da imagem
                        if _fname not in _item_shop_img_cache:
                            _fp = os.path.join(_itens_dir, _fname)
                            if os.path.exists(_fp):
                                try:
                                    _raw = pygame.image.load(_fp).convert_alpha()
                                    _item_shop_img_cache[_fname] = pygame.transform.smoothscale(
                                        _raw, (_SLOT - 10, _SLOT - 10))
                                except Exception:
                                    _item_shop_img_cache[_fname] = None
                            else:
                                _item_shop_img_cache[_fname] = None

                        _idx  = _n - 1
                        _st   = _stats_list[_idx] if _idx < len(_stats_list) else {}
                        _owned = {"category": _cname, "idx": _idx} in save_data["purchased_items"]

                        _sr   = pygame.Rect(_draw_x, _draw_y, _SLOT, _SLOT)
                        _shov = _sr.collidepoint(m_pos) and _clip_rect.collidepoint(m_pos)

                        # Fundo: verde escuro se comprado, laranja se hover, normal se não
                        if _owned:
                            _scol = (20, 60, 20)
                        elif _shov:
                            _scol = (65, 52, 32)
                        else:
                            _scol = (35, 28, 20)
                        pygame.draw.rect(screen, _scol, _sr, border_radius=5)

                        # Borda: ouro se hover/comprado, ferro se normal
                        _border_col = UI_THEME["old_gold"] if (_shov or _owned) else UI_THEME["iron"]
                        pygame.draw.rect(screen, _border_col, _sr, 2 if (_shov or _owned) else 1, border_radius=5)

                        # Ícone de comprado (✓)
                        if _owned:
                            _chk = font_s.render("✓", True, (80, 220, 80))
                            screen.blit(_chk, (_sr.right - _chk.get_width() - 3, _sr.top + 2))

                        _img = _item_shop_img_cache.get(_fname)
                        if _img:
                            screen.blit(_img, _img.get_rect(center=_sr.center))

                        if _shov and _st:
                            _tooltip_data = (_sr, _st)

                        _col += 1
                        if _col >= _COLS:
                            _col = 0
                            _draw_x  = _cx0 + 12
                            _draw_y += _SLOT + _PAD
                        else:
                            _draw_x += _SLOT + _PAD

                    if _col > 0:
                        _draw_x  = _cx0 + 12
                        _draw_y += _SLOT + _PAD
                    _draw_y += 10  # espaço entre subcategorias

                screen.set_clip(None)

                # ── Scrollbar vertical ─────────────────────────────────────────
                _sb_x    = _cx0 + _cw - _SB_W - 4
                _sb_rect = pygame.Rect(_sb_x, _cy0 + 4, _SB_W, _ch - 8)
                pygame.draw.rect(screen, (30, 25, 18), _sb_rect, border_radius=6)
                if _max_scroll > 0:
                    _th = max(30, int(_sb_rect.height * _ch / _total_h))
                    _ty = _sb_rect.top + int((_sb_rect.height - _th) * item_shop_scroll_y / _max_scroll)
                    _thumb = pygame.Rect(_sb_x + 2, _ty, _SB_W - 4, _th)
                    pygame.draw.rect(screen, UI_THEME["faded_gold"], _thumb, border_radius=5)
                    pygame.draw.rect(screen, UI_THEME["old_gold"], _thumb, 1, border_radius=5)

                # Tooltip do item em hover (desenhado por cima de tudo)
                if _tooltip_data:
                    _tsr, _tst = _tooltip_data
                    _tname  = _tst.get("name", "")
                    _tatk   = _tst.get("atk", 0)
                    _tdef   = _tst.get("def", 0)
                    _tspd   = _tst.get("spd", 0)
                    _tprice = _tst.get("price", 0)
                    _treqlv = _tst.get("level", 1)
                    _tlines = [_tname]
                    if _tatk > 0: _tlines.append(f"ATQ: +{_tatk}")
                    if _tdef > 0: _tlines.append(f"DEF: +{_tdef}")
                    if _tspd > 0: _tlines.append(f"VEL: +{_tspd}")
                    _tlines.append(f"Preco: {_tprice} ouro")
                    _tlines.append(f"Req. Nivel: {_treqlv}")
                    _tpad = 8
                    _tw   = max(font_s.size(l)[0] for l in _tlines) + _tpad * 2
                    _th   = len(_tlines) * 20 + _tpad * 2
                    _tx   = min(_tsr.right + 4, SCREEN_W - _tw - 4)
                    _ty   = max(4, _tsr.top - _th // 2)
                    _trect = pygame.Rect(_tx, _ty, _tw, _th)
                    _t_surf = pygame.Surface((_tw, _th), pygame.SRCALPHA)
                    _t_surf.fill((18, 14, 10, 220))
                    screen.blit(_t_surf, _trect.topleft)
                    pygame.draw.rect(screen, UI_THEME["old_gold"], _trect, 1, border_radius=4)
                    _cur_lv_tt = get_active_profile_level()
                    for _li, _ll in enumerate(_tlines):
                        _lc = UI_THEME["old_gold"] if _li == 0 else (200, 190, 160)
                        if "ATQ" in _ll: _lc = (220, 100, 60)
                        elif "DEF" in _ll: _lc = (80, 160, 220)
                        elif "VEL" in _ll: _lc = (80, 220, 130)
                        elif "Preco" in _ll: _lc = UI_THEME["faded_gold"]
                        elif "Req. Nivel" in _ll:
                            _lc = (240, 80, 80) if _cur_lv_tt < _treqlv else (100, 220, 100)
                        screen.blit(font_s.render(_ll, True, _lc), (_tx + _tpad, _ty + _tpad + _li * 20))

            if item_shop_active_tab == 1:
                _SLOT = 72
                _PAD  = 8
                _COLS = max(1, (_grid_w - 16) // (_SLOT + _PAD))

                _total_h = 0
                for _acdat in ARMOR_SHOP_CATEGORIES.values():
                    _rows = math.ceil(_acdat["count"] / _COLS)
                    _total_h += 30 + _rows * (_SLOT + _PAD) + 10

                _max_scroll = max(0, _total_h - _ch + 16)
                item_shop_scroll_y = max(0, min(item_shop_scroll_y, _max_scroll))

                _clip_rect = pygame.Rect(_cx0 + 4, _cy0 + 4, _grid_w, _ch - 8)
                screen.set_clip(_clip_rect)

                _draw_x = _cx0 + 12
                _draw_y = _cy0 + 12 - item_shop_scroll_y

                _tooltip_data = None
                for _acname, _acdat in ARMOR_SHOP_CATEGORIES.items():
                    _cat_lbl = font_s.render(f"— {_acname} —", True, UI_THEME["old_gold"])
                    screen.blit(_cat_lbl, (_draw_x, _draw_y))
                    _draw_y += 30
                    _col = 0
                    _draw_x = _cx0 + 12

                    _stats_list = ITEM_SHOP_STATS.get(_acname, [])

                    for _n, _afname in enumerate(_acdat["files"]):
                        _cache_key = f"armor_{_acname}_{_afname}"
                        if _cache_key not in _item_shop_img_cache:
                            _fp = os.path.join(_acdat["folder"], _afname)
                            if os.path.exists(_fp):
                                try:
                                    _raw = pygame.image.load(_fp).convert_alpha()
                                    _item_shop_img_cache[_cache_key] = pygame.transform.smoothscale(
                                        _raw, (_SLOT - 10, _SLOT - 10))
                                except Exception:
                                    _item_shop_img_cache[_cache_key] = None
                            else:
                                _item_shop_img_cache[_cache_key] = None

                        _idx  = _n
                        _st   = _stats_list[_idx] if _idx < len(_stats_list) else {}
                        _owned = {"category": _acname, "idx": _idx} in save_data["purchased_items"]

                        _sr   = pygame.Rect(_draw_x, _draw_y, _SLOT, _SLOT)
                        _shov = _sr.collidepoint(m_pos) and _clip_rect.collidepoint(m_pos)

                        if _owned:
                            _scol = (20, 60, 20)
                        elif _shov:
                            _scol = (65, 52, 32)
                        else:
                            _scol = (35, 28, 20)
                        pygame.draw.rect(screen, _scol, _sr, border_radius=5)

                        _border_col = UI_THEME["old_gold"] if (_shov or _owned) else UI_THEME["iron"]
                        pygame.draw.rect(screen, _border_col, _sr, 2 if (_shov or _owned) else 1, border_radius=5)

                        if _owned:
                            _chk = font_s.render("✓", True, (80, 220, 80))
                            screen.blit(_chk, (_sr.right - _chk.get_width() - 3, _sr.top + 2))

                        _img = _item_shop_img_cache.get(_cache_key)
                        if _img:
                            screen.blit(_img, _img.get_rect(center=_sr.center))

                        if _shov and _st:
                            _tooltip_data = (_sr, _st)

                        _col += 1
                        if _col >= _COLS:
                            _col = 0
                            _draw_x  = _cx0 + 12
                            _draw_y += _SLOT + _PAD
                        else:
                            _draw_x += _SLOT + _PAD

                    if _col > 0:
                        _draw_x  = _cx0 + 12
                        _draw_y += _SLOT + _PAD
                    _draw_y += 10

                screen.set_clip(None)

                _sb_x    = _cx0 + _cw - _SB_W - 4
                _sb_rect = pygame.Rect(_sb_x, _cy0 + 4, _SB_W, _ch - 8)
                pygame.draw.rect(screen, (30, 25, 18), _sb_rect, border_radius=6)
                if _max_scroll > 0:
                    _th = max(30, int(_sb_rect.height * _ch / _total_h))
                    _ty = _sb_rect.top + int((_sb_rect.height - _th) * item_shop_scroll_y / _max_scroll)
                    _thumb = pygame.Rect(_sb_x + 2, _ty, _SB_W - 4, _th)
                    pygame.draw.rect(screen, UI_THEME["faded_gold"], _thumb, border_radius=5)
                    pygame.draw.rect(screen, UI_THEME["old_gold"], _thumb, 1, border_radius=5)

                # Tooltip do item em hover (desenhado por cima de tudo)
                if _tooltip_data:
                    _tsr, _tst = _tooltip_data
                    _tname  = _tst.get("name", "")
                    _tdef   = _tst.get("def", 0)
                    _tspd   = _tst.get("spd", 0)
                    _tprice = _tst.get("price", 0)
                    _treqlv = _tst.get("level", 1)
                    _tlines = [_tname]
                    if _tdef > 0: _tlines.append(f"DEF: +{_tdef}")
                    if _tspd > 0: _tlines.append(f"VEL: +{_tspd}")
                    _tlines.append(f"Preco: {_tprice} ouro")
                    _tlines.append(f"Req. Nivel: {_treqlv}")
                    _tpad = 8
                    _tw   = max(font_s.size(l)[0] for l in _tlines) + _tpad * 2
                    _th   = len(_tlines) * 20 + _tpad * 2
                    _tx   = min(_tsr.right + 4, SCREEN_W - _tw - 4)
                    _ty   = max(4, _tsr.top - _th // 2)
                    _trect = pygame.Rect(_tx, _ty, _tw, _th)
                    _t_surf = pygame.Surface((_tw, _th), pygame.SRCALPHA)
                    _t_surf.fill((18, 14, 10, 220))
                    screen.blit(_t_surf, _trect.topleft)
                    pygame.draw.rect(screen, UI_THEME["old_gold"], _trect, 1, border_radius=4)
                    _cur_lv_tt2 = get_active_profile_level()
                    for _li, _ll in enumerate(_tlines):
                        _lc = UI_THEME["old_gold"] if _li == 0 else (200, 190, 160)
                        if "DEF" in _ll: _lc = (80, 160, 220)
                        elif "VEL" in _ll: _lc = (80, 220, 130)
                        elif "Preco" in _ll: _lc = UI_THEME["faded_gold"]
                        elif "Req. Nivel" in _ll:
                            _lc = (240, 80, 80) if _cur_lv_tt2 < _treqlv else (100, 220, 100)
                        screen.blit(font_s.render(_ll, True, _lc), (_tx + _tpad, _ty + _tpad + _li * 20))

            # ── Aba VENDER ────────────────────────────────────────────────────
            if item_shop_active_tab == _ITEM_SHOP_SELL_TAB:
                _sv_SLOT = 72; _sv_PAD = 8
                _sv_cx0  = int(SCREEN_W * 0.05); _sv_cy0 = int(SCREEN_H * 0.21)
                _sv_cw   = int(SCREEN_W * 0.90); _sv_ch  = int(SCREEN_H * 0.67)
                _sv_SB_W = 14; _sv_gw = _sv_cw - _sv_SB_W - 8
                _sv_COLS = max(1, (_sv_gw - 16) // (_sv_SLOT + _sv_PAD))
                _sv_itens_dir = os.path.join("assets", "ui", "itens")

                # Lista de itens vendáveis: chest + inventários (exceto soulbound)
                _sv_all = []
                for _svi in save_data["chest_items"]:
                    if not _svi.get("soulbound"):
                        _sv_all.append({"item": _svi, "source": "chest", "cid": None})
                for _svcid, _svinv in save_data["char_inventories"].items():
                    for _svi in _svinv:
                        if not _svi.get("soulbound"):
                            _sv_all.append({"item": _svi, "source": "inventory", "cid": _svcid})

                # Altura total para scroll
                _sv_rows  = math.ceil(len(_sv_all) / _sv_COLS) if _sv_all else 1
                _sv_total = _sv_rows * (_sv_SLOT + _sv_PAD) + 40
                _sv_max_s = max(0, _sv_total - _sv_ch + 16)
                item_shop_scroll_y = max(0, min(item_shop_scroll_y, _sv_max_s))

                _sv_clip = pygame.Rect(_sv_cx0+4, _sv_cy0+4, _sv_gw, _sv_ch-8)
                screen.set_clip(_sv_clip)

                _sv_dx = _sv_cx0 + 12
                _sv_dy = _sv_cy0 + 12 - item_shop_scroll_y

                # Subtítulo
                _sv_lbl = font_s.render("Clique uma vez para selecionar • Clique novamente para confirmar venda (50% do preço)", True, (160,130,90))
                screen.blit(_sv_lbl, (_sv_dx, _sv_dy))
                _sv_dy += 28

                _sv_tooltip_data = None

                if not _sv_all:
                    screen.set_clip(None)
                    _sv_empty = font_m.render("Nenhum item para vender.", True, (140, 120, 80))
                    screen.blit(_sv_empty, _sv_empty.get_rect(center=(_sv_cx0+_sv_cw//2, _sv_cy0+_sv_ch//2)))
                else:
                    for _svi2, _sventry in enumerate(_sv_all):
                        _sv_it  = _sventry["item"]
                        _sv_cat = _sv_it.get("category",""); _sv_idx = _sv_it.get("idx",0)
                        _sv_fp_p, _sv_ck = _item_img_path(_sv_cat, _sv_idx)
                        _sv_fn  = _sv_ck
                        _sv_st2 = ITEM_SHOP_STATS.get(_sv_cat,[{}])
                        _sv_st2 = _sv_st2[_sv_idx] if _sv_idx < len(_sv_st2) else {}
                        _sv_sell_price = max(1, _sv_st2.get("price",0)//2)

                        _svr = pygame.Rect(_sv_dx, _sv_dy, _sv_SLOT, _sv_SLOT)
                        _sv_hov = _svr.collidepoint(m_pos) and _sv_clip.collidepoint(m_pos)
                        _sv_is_sel = (item_shop_sell_selected is not None and
                                      item_shop_sell_selected.get("item") == _sv_it and
                                      item_shop_sell_selected.get("source") == _sventry["source"] and
                                      item_shop_sell_selected.get("cid") == _sventry["cid"])

                        if _sv_is_sel:
                            _sv_bg = (70, 20, 20)
                            _sv_brd = (220, 80, 60); _sv_brd_w = 2
                        elif _sv_hov:
                            _sv_bg = (55, 30, 20)
                            _sv_brd = (180, 100, 60); _sv_brd_w = 1
                        else:
                            _sv_bg = (35, 28, 20)
                            _sv_brd = UI_THEME["iron"]; _sv_brd_w = 1
                        pygame.draw.rect(screen, _sv_bg, _svr, border_radius=5)
                        pygame.draw.rect(screen, _sv_brd, _svr, _sv_brd_w, border_radius=5)

                        # Imagem
                        if _sv_fp_p and _sv_fn not in _item_shop_img_cache:
                            if os.path.exists(_sv_fp_p):
                                try:
                                    _sv_raw = pygame.image.load(_sv_fp_p).convert_alpha()
                                    _item_shop_img_cache[_sv_fn] = pygame.transform.smoothscale(_sv_raw, (_sv_SLOT-10, _sv_SLOT-10))
                                except Exception: _item_shop_img_cache[_sv_fn] = None
                            else: _item_shop_img_cache[_sv_fn] = None
                        _sv_img = _item_shop_img_cache.get(_sv_fn) if _sv_fp_p else None
                        if _sv_img: screen.blit(_sv_img, _sv_img.get_rect(center=_svr.center))

                        # Badge selecionado
                        if _sv_is_sel:
                            _sv_badge = font_s.render("?", True, (255, 180, 80))
                            screen.blit(_sv_badge, (_svr.right - _sv_badge.get_width() - 2, _svr.top + 2))

                        if _sv_hov:
                            _sv_tooltip_data = (_svr, _sv_st2, _sv_sell_price, _sv_is_sel, _sventry)

                        _sv_c = (_svi2+1) % _sv_COLS
                        if _sv_c == 0: _sv_dx = _sv_cx0+12; _sv_dy += _sv_SLOT + _sv_PAD
                        else: _sv_dx += _sv_SLOT + _sv_PAD

                    screen.set_clip(None)

                    # Scrollbar
                    _sv_sb_x   = _sv_cx0 + _sv_cw - _sv_SB_W - 4
                    _sv_sb_rect = pygame.Rect(_sv_sb_x, _sv_cy0+4, _sv_SB_W, _sv_ch-8)
                    pygame.draw.rect(screen, (30,25,18), _sv_sb_rect, border_radius=6)
                    if _sv_max_s > 0:
                        _sv_th2 = max(30, int(_sv_sb_rect.height * _sv_ch / max(1, _sv_total)))
                        _sv_ty2 = _sv_sb_rect.top + int((_sv_sb_rect.height-_sv_th2)*item_shop_scroll_y/max(1,_sv_max_s))
                        _sv_thumb = pygame.Rect(_sv_sb_x+2, _sv_ty2, _sv_SB_W-4, _sv_th2)
                        pygame.draw.rect(screen, UI_THEME["faded_gold"], _sv_thumb, border_radius=5)
                        pygame.draw.rect(screen, UI_THEME["old_gold"], _sv_thumb, 1, border_radius=5)

                    # Tooltip (desenhado por cima de tudo, inclusive da scrollbar)
                    if _sv_tooltip_data:
                        _svtr, _svtst, _svtp, _svtsel, _svtentry = _sv_tooltip_data
                        _svtlines = [_svtst.get("name", "")]
                        _sva = _svtst.get("atk",0); _svd = _svtst.get("def",0)
                        if _sva: _svtlines.append(f"ATQ: +{_sva}")
                        if _svd: _svtlines.append(f"DEF: +{_svd}")
                        _sv_src_lbl = "Baú" if _svtentry["source"]=="chest" else f"Inventário ({CHAR_DATA.get(int(_svtentry['cid'] or 0),{}).get('name','Herói')})"
                        _svtlines.append(f"Origem: {_sv_src_lbl}")
                        if _svtsel:
                            _svtlines.append(f"► Clique novamente p/ vender: {_svtp} ouro")
                        else:
                            _svtlines.append(f"Vender por: {_svtp} ouro")
                        _svtw = max(font_s.size(l)[0] for l in _svtlines)+16
                        _svth = len(_svtlines)*20+12
                        _svtx = min(_svtr.right+4, SCREEN_W-_svtw-4)
                        _svty = max(4, _svtr.top-_svth//2)
                        _svts = pygame.Surface((_svtw,_svth), pygame.SRCALPHA); _svts.fill((18,14,10,230))
                        screen.blit(_svts, (_svtx,_svty))
                        pygame.draw.rect(screen, (180,80,60), pygame.Rect(_svtx,_svty,_svtw,_svth), 1, border_radius=4)
                        for _svtli, _svtll in enumerate(_svtlines):
                            _svtc = UI_THEME["old_gold"] if _svtli==0 else (200,190,160)
                            if "ATQ" in _svtll: _svtc=(220,100,60)
                            elif "DEF" in _svtll: _svtc=(80,160,220)
                            elif "Vender" in _svtll or "vender" in _svtll: _svtc=(220,200,80)
                            elif "Origem" in _svtll: _svtc=(140,130,100)
                            screen.blit(font_s.render(_svtll,True,_svtc), (_svtx+8,_svty+6+_svtli*20))

            item_shop_back_btn.check_hover(m_pos, snd_hover)
            item_shop_back_btn.draw(screen)

            # ── Diálogo de confirmação de venda ───────────────────────────────
            if item_shop_sell_confirm is not None:
                _scf  = item_shop_sell_confirm
                _scf_st   = _scf.get("st", {})
                _scf_name = _scf_st.get("name", "Item")
                _scf_price = _scf["price"]
                _scf_atk  = _scf_st.get("atk", 0)
                _scf_def  = _scf_st.get("def", 0)
                _scfe = _scf["entry"]
                _scf_cat = _scfe["item"].get("category", ""); _scf_idx2 = _scfe["item"].get("idx", 0)

                _scfd_w = 420; _scfd_h = 200
                _scfd_x = (SCREEN_W - _scfd_w) // 2
                _scfd_y = (SCREEN_H - _scfd_h) // 2

                _scfd_ov = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
                _scfd_ov.fill((0, 0, 0, 140))
                screen.blit(_scfd_ov, (0, 0))

                _scfd_bg = pygame.Surface((_scfd_w, _scfd_h), pygame.SRCALPHA)
                _scfd_bg.fill((14, 8, 8, 245))
                screen.blit(_scfd_bg, (_scfd_x, _scfd_y))
                pygame.draw.rect(screen, (180, 80, 60), pygame.Rect(_scfd_x, _scfd_y, _scfd_w, _scfd_h), 2, border_radius=10)

                # Imagem do item
                _scfd_itens_dir = os.path.join("assets", "ui", "itens")
                _scfd_cdat = ITEM_SHOP_CATEGORIES.get(_scf_cat, {})
                _scfd_fn   = f"{_scfd_cdat.get('prefix', _scf_cat)} ({_scf_idx2 + 1}).png"
                if _scfd_fn not in _item_shop_img_cache:
                    _scfd_fp = os.path.join(_scfd_itens_dir, _scfd_fn)
                    if os.path.exists(_scfd_fp):
                        try:
                            _scfd_raw = pygame.image.load(_scfd_fp).convert_alpha()
                            _item_shop_img_cache[_scfd_fn] = pygame.transform.smoothscale(_scfd_raw, (56, 56))
                        except Exception: _item_shop_img_cache[_scfd_fn] = None
                    else: _item_shop_img_cache[_scfd_fn] = None
                _scfd_img = _item_shop_img_cache.get(_scfd_fn)
                _scfd_img_r = pygame.Rect(_scfd_x + 20, _scfd_y + 20, 56, 56)
                pygame.draw.rect(screen, (30, 28, 22), _scfd_img_r, border_radius=6)
                pygame.draw.rect(screen, (180, 80, 60), _scfd_img_r, 1, border_radius=6)
                if _scfd_img: screen.blit(_scfd_img, _scfd_img_r.topleft)

                _scfd_name_s = font_m.render(_scf_name, True, (220, 160, 80))
                screen.blit(_scfd_name_s, (_scfd_x + 88, _scfd_y + 22))
                _scfd_parts = []
                if _scf_atk: _scfd_parts.append(f"ATQ: +{_scf_atk}")
                if _scf_def: _scfd_parts.append(f"DEF: +{_scf_def}")
                _scfd_parts.append(f"Venda: {_scf_price} ouro")
                _scfd_stat_s = font_s.render("  |  ".join(_scfd_parts), True, (180, 170, 130))
                screen.blit(_scfd_stat_s, (_scfd_x + 88, _scfd_y + 50))

                pygame.draw.line(screen, (120, 70, 50),
                                 (_scfd_x + 16, _scfd_y + 80), (_scfd_x + _scfd_w - 16, _scfd_y + 80), 1)

                _scfd_q = font_m.render("Tem certeza que deseja vender?", True, (220, 210, 180))
                screen.blit(_scfd_q, _scfd_q.get_rect(centerx=_scfd_x + _scfd_w // 2, top=_scfd_y + 88))

                _scfd_sim = pygame.Rect(_scfd_x + 40,  _scfd_y + 130, 140, 44)
                _scfd_nao = pygame.Rect(_scfd_x + 240, _scfd_y + 130, 140, 44)
                _scfd_sh = _scfd_sim.collidepoint(m_pos)
                _scfd_nh = _scfd_nao.collidepoint(m_pos)

                pygame.draw.rect(screen, (30, 65, 30) if _scfd_sh else (20, 45, 20), _scfd_sim, border_radius=8)
                pygame.draw.rect(screen, (80, 200, 80) if _scfd_sh else (50, 140, 50), _scfd_sim, 2, border_radius=8)
                screen.blit(font_m.render("SIM", True, (140, 240, 140) if _scfd_sh else (100, 200, 100)),
                            font_m.render("SIM", True, (140, 240, 140)).get_rect(center=_scfd_sim.center))

                pygame.draw.rect(screen, (65, 20, 20) if _scfd_nh else (45, 14, 14), _scfd_nao, border_radius=8)
                pygame.draw.rect(screen, (200, 70, 70) if _scfd_nh else (140, 50, 50), _scfd_nao, 2, border_radius=8)
                screen.blit(font_m.render("NÃO", True, (240, 120, 120) if _scfd_nh else (200, 90, 90)),
                            font_m.render("NÃO", True, (240, 120, 120)).get_rect(center=_scfd_nao.center))

                _scfd_esc = font_s.render("ESC — Cancelar", True, (90, 80, 60))
                screen.blit(_scfd_esc, _scfd_esc.get_rect(centerx=_scfd_x + _scfd_w // 2, bottom=_scfd_y + _scfd_h - 6))

            # ── Diálogo de confirmação de compra ──────────────────────────────
            if item_shop_confirm is not None:
                _cf = item_shop_confirm
                _cf_st = _cf.get("st", {})
                _cf_name  = _cf_st.get("name", _cf["category"])
                _cf_price = _cf["price"]
                _cf_atk   = _cf_st.get("atk", 0)
                _cf_def   = _cf_st.get("def", 0)

                _cfd_w = 420; _cfd_h = 230
                _cfd_x = (SCREEN_W - _cfd_w) // 2
                _cfd_y = (SCREEN_H - _cfd_h) // 2

                # Escurecimento de fundo
                _cfd_ov = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
                _cfd_ov.fill((0, 0, 0, 140))
                screen.blit(_cfd_ov, (0, 0))

                # Janela
                _cfd_bg = pygame.Surface((_cfd_w, _cfd_h), pygame.SRCALPHA)
                _cfd_bg.fill((18, 14, 10, 245))
                screen.blit(_cfd_bg, (_cfd_x, _cfd_y))
                pygame.draw.rect(screen, UI_THEME.get("old_gold", (200, 170, 60)),
                                 pygame.Rect(_cfd_x, _cfd_y, _cfd_w, _cfd_h), 2, border_radius=10)

                # Imagem do item
                _cfd_itens_dir = os.path.join("assets", "ui", "itens")
                _cfd_cdat = ITEM_SHOP_CATEGORIES.get(_cf["category"], {})
                _cfd_fn   = f"{_cfd_cdat.get('prefix', _cf['category'])} ({_cf['idx'] + 1}).png"
                if _cfd_fn not in _item_shop_img_cache:
                    _cfd_fp = os.path.join(_cfd_itens_dir, _cfd_fn)
                    if os.path.exists(_cfd_fp):
                        try:
                            _cfd_raw = pygame.image.load(_cfd_fp).convert_alpha()
                            _item_shop_img_cache[_cfd_fn] = pygame.transform.smoothscale(_cfd_raw, (56, 56))
                        except Exception: _item_shop_img_cache[_cfd_fn] = None
                    else: _item_shop_img_cache[_cfd_fn] = None
                _cfd_img = _item_shop_img_cache.get(_cfd_fn)
                _cfd_img_x = _cfd_x + 20; _cfd_img_y = _cfd_y + 20
                _cfd_img_r = pygame.Rect(_cfd_img_x, _cfd_img_y, 56, 56)
                pygame.draw.rect(screen, (30, 28, 22), _cfd_img_r, border_radius=6)
                pygame.draw.rect(screen, UI_THEME.get("old_gold", (200, 170, 60)), _cfd_img_r, 1, border_radius=6)
                if _cfd_img: screen.blit(_cfd_img, _cfd_img_r.topleft)

                # Nome e stats
                _cfd_name_s = font_m.render(_cf_name, True, UI_THEME.get("old_gold", (220, 180, 80)))
                screen.blit(_cfd_name_s, (_cfd_x + 88, _cfd_y + 22))
                _cfd_stat_parts = []
                if _cf_atk: _cfd_stat_parts.append(f"ATQ: +{_cf_atk}")
                if _cf_def: _cfd_stat_parts.append(f"DEF: +{_cf_def}")
                _cfd_stat_parts.append(f"Preço: {_cf_price} ouro")
                _cfd_stat_s = font_s.render("  |  ".join(_cfd_stat_parts), True, (180, 170, 130))
                screen.blit(_cfd_stat_s, (_cfd_x + 88, _cfd_y + 50))

                # Linha divisória
                pygame.draw.line(screen, UI_THEME.get("faded_gold", (130, 110, 50)),
                                 (_cfd_x + 16, _cfd_y + 90), (_cfd_x + _cfd_w - 16, _cfd_y + 90), 1)

                # Pergunta
                _cfd_q1 = font_m.render("Você deseja realmente comprar", True, (220, 210, 180))
                _cfd_q2 = font_m.render("este item?", True, (220, 210, 180))
                screen.blit(_cfd_q1, _cfd_q1.get_rect(centerx=_cfd_x + _cfd_w // 2, top=_cfd_y + 100))
                screen.blit(_cfd_q2, _cfd_q2.get_rect(centerx=_cfd_x + _cfd_w // 2, top=_cfd_y + 124))

                # Botões SIM / NÃO
                _cfd_sim = pygame.Rect(_cfd_x + 40,  _cfd_y + 163, 140, 44)
                _cfd_nao = pygame.Rect(_cfd_x + 240, _cfd_y + 163, 140, 44)
                _cfd_sim_hov = _cfd_sim.collidepoint(m_pos)
                _cfd_nao_hov = _cfd_nao.collidepoint(m_pos)

                pygame.draw.rect(screen, (30, 65, 30) if _cfd_sim_hov else (20, 45, 20), _cfd_sim, border_radius=8)
                pygame.draw.rect(screen, (80, 200, 80) if _cfd_sim_hov else (50, 140, 50), _cfd_sim, 2, border_radius=8)
                _sim_s = font_m.render("SIM", True, (140, 240, 140) if _cfd_sim_hov else (100, 200, 100))
                screen.blit(_sim_s, _sim_s.get_rect(center=_cfd_sim.center))

                pygame.draw.rect(screen, (65, 20, 20) if _cfd_nao_hov else (45, 14, 14), _cfd_nao, border_radius=8)
                pygame.draw.rect(screen, (200, 70, 70) if _cfd_nao_hov else (140, 50, 50), _cfd_nao, 2, border_radius=8)
                _nao_s = font_m.render("NÃO", True, (240, 120, 120) if _cfd_nao_hov else (200, 90, 90))
                screen.blit(_nao_s, _nao_s.get_rect(center=_cfd_nao.center))

                # Dica ESC
                _cfd_esc = font_s.render("ESC — Cancelar", True, (90, 80, 60))
                screen.blit(_cfd_esc, _cfd_esc.get_rect(centerx=_cfd_x+_cfd_w//2, bottom=_cfd_y+_cfd_h-6))

        elif state == "CHAR_SELECT":
            draw_menu_background(screen, m_pos, dt)

            # ----------------------------------------------------------------
            # Painel grade — selecionarpersonagem.png
            # ----------------------------------------------------------------
            meta    = char_select_panel_meta
            ox      = meta.get("ox", 0)
            oy      = meta.get("oy", 50)
            pscale  = meta.get("scale", 1.0)
            COL_CX  = meta.get("col_cx", [215, 394, 574, 754, 934, 1113, 1293])
            ROW_CY  = meta.get("row_cy", [215, 394, 574, 752])
            CHALF   = meta.get("cell_half", 61)

            if char_select_panel_img:
                screen.blit(char_select_panel_img, (ox, oy))

            # --- Título com moldura ornamental ---
            _tit_text = "SELECIONAR HERÓI"
            _tit_sf   = load_title_font(19, bold=True).render(
                _tit_text, True, UI_THEME["old_gold"])
            _tit_cy   = oy // 2          # centro vertical da margem superior
            if char_select_title_frame is not None:
                _fw = char_select_title_frame.get_width()
                _fh = char_select_title_frame.get_height()
                _fx = SCREEN_W // 2 - _fw // 2
                _fy = _tit_cy - _fh // 2
                screen.blit(char_select_title_frame, (_fx, _fy))
                screen.blit(_tit_sf, _tit_sf.get_rect(center=(SCREEN_W // 2, _tit_cy)))
            else:
                draw_dark_panel(screen,
                    pygame.Rect(SCREEN_W // 2 - 200, _tit_cy - 16, 400, 32),
                    alpha=200, border_color=UI_THEME["old_gold"])
                screen.blit(_tit_sf, _tit_sf.get_rect(center=(SCREEN_W // 2, _tit_cy)))

            # ----------------------------------------------------------------
            char_ids  = list(CHAR_DATA.keys())
            time_ms   = pygame.time.get_ticks()
            frame_idx = int(time_ms / 130)   # cadência da idle

            hovered_char_idx = -1
            # chw igual para todos — calculado uma vez
            chw = max(int(CHALF * pscale), 32)

            # Multiplicadores de tamanho por personagem (guerreiro e mago maiores)
            _SIZE_MULT = {0: 2.20, 1: 1.85, 2: 2.45, 3: 2.00, 4: 2.30, 5: 2.40, 6: 2.10, 7: 2.10}

            for i in range(len(char_ids)):
                btn   = char_btns[i]
                cdata = CHAR_DATA[char_ids[i]]

                # Idle animation — mesmo sprite do jogo parado
                idle = menu_idle_anims[i] if i < len(menu_idle_anims) else menu_char_anims[i]

                # Chars 0-6 na linha 0; chars extras preenchem a linha 1 na ordem das colunas
                _n_cols = len(COL_CX)
                _grid_col = i % _n_cols
                _grid_row = i // _n_cols
                cx = ox + int(COL_CX[_grid_col] * pscale)
                # Descer +50% do raio da célula para enquadrar personagem no quadrado
                cy = oy + int(ROW_CY[_grid_row] * pscale) + int(chw * 0.50)

                cell_rect = pygame.Rect(cx - chw, cy - chw, chw * 2, chw * 2)
                btn.rect  = cell_rect

                btn.check_hover(m_pos, snd_hover)
                is_hovered = btn.is_hovered and not btn.locked

                if is_hovered:
                    hovered_char_idx = i
                    glow_a = int(55 + 45 * math.sin(time_ms / 180.0))
                    glow_s = pygame.Surface((chw * 2 + 12, chw * 2 + 12), pygame.SRCALPHA)
                    glow_s.fill((220, 180, 60, glow_a))
                    screen.blit(glow_s, (cx - chw - 6, cy - chw - 6))
                    pygame.draw.rect(screen, UI_THEME["old_gold"], cell_rect, 2, border_radius=3)
                elif btn.locked:
                    pygame.draw.rect(screen, UI_THEME["blood_red"], cell_rect, 1, border_radius=3)

                # Sprite idle animado — escala por personagem
                img = idle[frame_idx % len(idle)]
                fw_i, fh_i = img.get_width(), img.get_height()
                if fw_i > 0 and fh_i > 0:
                    mult     = _SIZE_MULT.get(i, 1.85)
                    target   = int(chw * mult)          # alvo = mult × raio
                    sc       = max(target / fw_i, target / fh_i)
                    img = pygame.transform.smoothscale(
                        img, (max(1, int(fw_i * sc)), max(1, int(fh_i * sc))))

                if btn.locked:
                    img = img.copy()
                    img.fill((0, 0, 0, 160), special_flags=pygame.BLEND_RGBA_MULT)

                # Flutuação suave + ancoragem
                float_off = int(math.sin((time_ms + i * 600) / 400.0) * 3)
                screen.blit(img, img.get_rect(center=(cx, cy + float_off)))

                if btn.locked:
                    lk = load_title_font(14, bold=True).render(
                        "🔒", True, UI_THEME["blood_red"])
                    screen.blit(lk, lk.get_rect(center=(cx, cy)))

            # ----------------------------------------------------------------
            # Painel de status (hover) — lado DIREITO, fora da grade
            # ----------------------------------------------------------------
            if hovered_char_idx >= 0:
                h_idx  = hovered_char_idx
                cdata  = CHAR_DATA[char_ids[h_idx]]
                btn    = char_btns[h_idx]
                anim   = menu_char_anims[h_idx]

                SP_W, SP_H = 280, 400
                sp_x = SCREEN_W - SP_W - 20
                sp_y = max(oy, (SCREEN_H - SP_H) // 2)

                # Fundo
                bg_s = pygame.Surface((SP_W, SP_H), pygame.SRCALPHA)
                bg_s.fill((8, 5, 3, 235))
                screen.blit(bg_s, (sp_x, sp_y))
                sp_rect = pygame.Rect(sp_x, sp_y, SP_W, SP_H)
                pygame.draw.rect(screen, UI_THEME["old_gold"], sp_rect, 2, border_radius=7)

                pad   = 14
                cur_y = sp_y + pad

                # Nome
                col_name = UI_THEME["blood_red"] if btn.locked else UI_THEME["old_gold"]
                nm = load_title_font(22, bold=True).render(cdata["name"], True, col_name)
                screen.blit(nm, nm.get_rect(centerx=sp_x + SP_W // 2, top=cur_y))
                cur_y += nm.get_height() + 8

                # Sprite animado grande (aqui mantemos animação no painel de status)
                big = anim[int((time_ms / 100) % len(anim))]
                mbw, mbh = SP_W - pad * 2, 140
                if big.get_width() > 0 and big.get_height() > 0:
                    bsc = min(mbw / big.get_width(), mbh / big.get_height())
                    big = pygame.transform.smoothscale(
                        big, (max(1, int(big.get_width() * bsc)),
                              max(1, int(big.get_height() * bsc))))
                if btn.locked:
                    big = big.copy()
                    big.fill((0, 0, 0, 160), special_flags=pygame.BLEND_RGBA_MULT)
                screen.blit(big, big.get_rect(centerx=sp_x + SP_W // 2, top=cur_y))
                cur_y += mbh + 10

                # Linha separadora
                pygame.draw.line(screen, UI_THEME["iron"],
                                 (sp_x + pad, cur_y), (sp_x + SP_W - pad, cur_y), 1)
                cur_y += 8

                # Barras de stats
                BW = SP_W - pad * 2
                BH = 12

                def _bar(label, val, max_v, color, yy):
                    ls = load_body_font(13).render(label, True, UI_THEME["mist"])
                    screen.blit(ls, (sp_x + pad, yy))
                    bx, by = sp_x + pad, yy + ls.get_height() + 1
                    filled  = int(BW * min(val / max_v, 1.0))
                    pygame.draw.rect(screen, (25, 25, 25), (bx, by, BW, BH), border_radius=3)
                    if filled > 0:
                        pygame.draw.rect(screen, color, (bx, by, filled, BH), border_radius=3)
                    pygame.draw.rect(screen, UI_THEME["iron"], (bx, by, BW, BH), 1, border_radius=3)
                    return by + BH + 6

                cur_y = _bar("HP",         cdata["hp"],    10,  UI_THEME["blood_red"],  cur_y)
                cur_y = _bar("VELOCIDADE", cdata["speed"], 400, (80, 200, 255),          cur_y)
                cur_y = _bar("DANO",       cdata["damage"], 5,  UI_THEME["faded_gold"],  cur_y)
                cur_y += 6

                # Linha separadora
                pygame.draw.line(screen, UI_THEME["iron"],
                                 (sp_x + pad, cur_y), (sp_x + SP_W - pad, cur_y), 1)
                cur_y += 6

                # Ultimate
                ult = load_body_font(13).render(cdata["desc"], True, UI_THEME["mana_blue"])
                screen.blit(ult, ult.get_rect(centerx=sp_x + SP_W // 2, top=cur_y))
                cur_y += ult.get_height() + 6

                if btn.locked:
                    lk2 = load_title_font(13, bold=True).render(
                        "🔒 BLOQUEADO", True, UI_THEME["blood_red"])
                    screen.blit(lk2, lk2.get_rect(centerx=sp_x + SP_W // 2, top=cur_y))
                    if btn.lock_req:
                        rq = load_body_font(11).render(btn.lock_req, True, (170, 130, 110))
                        screen.blit(rq, rq.get_rect(centerx=sp_x + SP_W // 2, top=cur_y + 18))
                else:
                    ht = load_body_font(12).render("Clique para selecionar", True, (150, 150, 120))
                    screen.blit(ht, ht.get_rect(centerx=sp_x + SP_W // 2,
                                                 top=sp_y + SP_H - 22))

            char_back_btn.check_hover(m_pos, snd_hover)
            char_back_btn.draw(screen)
        
        elif state == "DIFF_SELECT":
            draw_menu_background(screen, m_pos, dt)

            if diff_screen_imgs:
                now_ms_d = pygame.time.get_ticks()

                # Título
                t_img = diff_screen_imgs.get("title")
                if t_img:
                    screen.blit(t_img, t_img.get_rect(center=(SCREEN_W // 2, int(SCREEN_H * 0.11))))

                # Botões de dificuldade
                diff_order_keys = ["FÁCIL", "MÉDIO", "DIFÍCIL", "HARDCORE"]
                for btn, key in zip(diff_btns, diff_order_keys):
                    btn.check_hover(m_pos, snd_hover)
                    # HARDCORE: sprite muda conforme estado de bloqueio
                    if key == "HARDCORE":
                        spr = diff_screen_imgs.get("HARDCORE") if btn.locked else diff_screen_imgs.get("HARDCORE_UNLOCK", diff_screen_imgs.get("HARDCORE"))
                    else:
                        spr = diff_screen_imgs.get(key)
                    if spr:
                        spr_rect = spr.get_rect(center=btn.rect.center)
                        if btn.locked:
                            # Sprite bloqueado com escurecimento leve
                            dark = spr.copy()
                            ov = pygame.Surface(spr.get_size(), pygame.SRCALPHA)
                            ov.fill((0, 0, 0, 90))
                            dark.blit(ov, (0, 0))
                            screen.blit(dark, spr_rect.topleft)
                        else:
                            screen.blit(spr, spr_rect.topleft)
                        # Tooltip de requisito ao passar o mouse em botão bloqueado
                        if btn.locked and btn.is_hovered and btn.lock_req:
                            mx, my = pygame.mouse.get_pos()
                            tt = load_body_font(15).render(btn.lock_req, True, (210, 185, 165))
                            tip_r = pygame.Rect(mx + 14, my - 10, tt.get_width() + 18, tt.get_height() + 12)
                            pygame.draw.rect(screen, (20, 10, 8), tip_r, border_radius=3)
                            pygame.draw.rect(screen, (110, 55, 40), tip_r, 1, border_radius=3)
                            screen.blit(tt, (tip_r.x + 9, tip_r.y + 6))
                    else:
                        btn.draw(screen)

                # Botão Voltar
                diff_back_btn.check_hover(m_pos, snd_hover)
                voltar_spr = diff_screen_imgs.get("VOLTAR")
                if voltar_spr:
                    vr = voltar_spr.get_rect(center=diff_back_btn.rect.center)
                    screen.blit(voltar_spr, vr.topleft)
                else:
                    diff_back_btn.draw(screen)
            else:
                # Fallback procedural
                draw_screen_title(screen, font_l, "SELECIONE A DIFICULDADE", SCREEN_W // 2, int(SCREEN_H * 0.15))
                for btn in diff_btns:
                    btn.check_hover(m_pos, snd_hover)
                    btn.draw(screen)
                diff_back_btn.check_hover(m_pos, snd_hover)
                diff_back_btn.draw(screen)

        elif (state == "HUB" and hub_scene is not None) or (state == "MARKET" and market_scene is not None) or state == "REWARD_ROOM":
            # ── Mapa + jogador ─────────────────────────────────────────────
            if state == "HUB":
                hub_scene.draw(screen)
                if hub_scene.player_near_chest and not hub_chest_open:
                    _chest_sp = hub_scene.chest_screen_pos
                    _f_now    = pygame.time.get_ticks()
                    _f_bob    = math.sin(_f_now / 400.0) * 4
                    _f_surf   = font_s.render("[F]  Abrir Baú", True, (240, 220, 100))
                    _f_bg     = pygame.Surface((_f_surf.get_width() + 16, _f_surf.get_height() + 8), pygame.SRCALPHA)
                    _f_bg.fill((10, 8, 6, 180))
                    _f_rect   = _f_bg.get_rect(centerx=int(_chest_sp.x), bottom=int(_chest_sp.y - 150 + _f_bob))
                    screen.blit(_f_bg, _f_rect)
                    pygame.draw.rect(screen, (200, 170, 60), _f_rect, 1, border_radius=4)
                    screen.blit(_f_surf, _f_surf.get_rect(center=_f_rect.center))
            elif state == "MARKET":
                market_scene.draw(screen)

                # ── Label "FERREIRO" acima do NPC + hint [F] quando perto ──
                _ferr_sp  = market_scene.ferreiro_screen_pos
                _ferr_now = pygame.time.get_ticks()
                _ferr_bob = math.sin(_ferr_now / 400.0) * 4
                _fn_surf  = font_s.render("FERREIRO", True, (255, 180, 60))
                _fn_bg    = pygame.Surface((_fn_surf.get_width() + 12, _fn_surf.get_height() + 6), pygame.SRCALPHA)
                _fn_bg.fill((10, 8, 6, 160))
                _fn_rect  = _fn_bg.get_rect(centerx=int(_ferr_sp.x), bottom=int(_ferr_sp.y - 72 + _ferr_bob))
                screen.blit(_fn_bg, _fn_rect)
                pygame.draw.rect(screen, (200, 130, 40), _fn_rect, 1, border_radius=3)
                screen.blit(_fn_surf, _fn_surf.get_rect(center=_fn_rect.center))
                if market_scene.player_near_ferreiro and not hub_status_open and not hub_profile_open:
                    _fi_label = "[F] Fechar FERREIRO" if craft_open else "[F] FERREIRO"
                    _fi_surf = font_s.render(_fi_label, True, (255, 200, 80))
                    _fi_bg   = pygame.Surface((_fi_surf.get_width() + 16, _fi_surf.get_height() + 8), pygame.SRCALPHA)
                    _fi_bg.fill((10, 8, 6, 180))
                    _fi_rect = _fi_bg.get_rect(centerx=int(_ferr_sp.x), bottom=_fn_rect.top - 4)
                    screen.blit(_fi_bg, _fi_rect)
                    pygame.draw.rect(screen, (200, 130, 40), _fi_rect, 1, border_radius=4)
                    screen.blit(_fi_surf, _fi_surf.get_rect(center=_fi_rect.center))

                # ── Label "LOJA DE ITENS" acima do NPC esquerdo ──────────────
                _loja_sp  = market_scene.loja_screen_pos
                _loja_bob = math.sin(_ferr_now / 400.0 + 1.0) * 4
                _ln_surf  = font_s.render("LOJA DE ITENS", True, (100, 200, 255))
                _ln_bg    = pygame.Surface((_ln_surf.get_width() + 12, _ln_surf.get_height() + 6), pygame.SRCALPHA)
                _ln_bg.fill((10, 8, 6, 160))
                _ln_rect  = _ln_bg.get_rect(centerx=int(_loja_sp.x), bottom=int(_loja_sp.y - 72 + _loja_bob))
                screen.blit(_ln_bg, _ln_rect)
                pygame.draw.rect(screen, (60, 140, 200), _ln_rect, 1, border_radius=3)
                screen.blit(_ln_surf, _ln_surf.get_rect(center=_ln_rect.center))
                if market_scene.player_near_loja and not hub_status_open and not hub_profile_open and not craft_open:
                    _li_surf = font_s.render("[F] LOJA DE ITENS", True, (140, 220, 255))
                    _li_bg   = pygame.Surface((_li_surf.get_width() + 16, _li_surf.get_height() + 8), pygame.SRCALPHA)
                    _li_bg.fill((10, 8, 6, 180))
                    _li_rect = _li_bg.get_rect(centerx=int(_loja_sp.x), bottom=_ln_rect.top - 4)
                    screen.blit(_li_bg, _li_rect)
                    pygame.draw.rect(screen, (60, 140, 200), _li_rect, 1, border_radius=4)
                    screen.blit(_li_surf, _li_surf.get_rect(center=_li_rect.center))

            else:
                # ── SALA DE RECOMPENSA ──────────────────────────────────────
                if _reward_room_bg is not None:
                    screen.blit(_reward_room_bg, (0, 0))
                else:
                    screen.fill((18, 14, 10))
                # Desenha minérios (abaixo do jogador)
                if _mining_system is not None and reward_room_player_pos is not None:
                    _mining_system.render(screen, reward_room_player_pos, font_s, font_m)
                # Desenha jogador com animação direcional
                if player is not None and reward_room_player_pos is not None:
                    _rr_img = getattr(player, "image", None)
                    if _rr_img is not None:
                        screen.blit(_rr_img, _rr_img.get_rect(center=(int(reward_room_player_pos.x),
                                                                        int(reward_room_player_pos.y))))
                # Dica de teclas
                if not hub_equip_open and not hub_status_open:
                    _rr_hint_parts = ["[I] Inventário", "[C] Status", "[ESC] Sair"]
                    _rr_hint = font_s.render("   ".join(_rr_hint_parts), True, (220, 200, 140))
                    _rr_hint_bg = pygame.Surface((_rr_hint.get_width() + 20, _rr_hint.get_height() + 8), pygame.SRCALPHA)
                    _rr_hint_bg.fill((8, 6, 4, 180))
                    _rr_hint_rect = _rr_hint_bg.get_rect(centerx=SCREEN_W // 2, top=14)
                    screen.blit(_rr_hint_bg, _rr_hint_rect)
                    screen.blit(_rr_hint, _rr_hint.get_rect(center=_rr_hint_rect.center))
                # Botão "Sair"
                _rr_sair_rect = pygame.Rect(SCREEN_W // 2 - 110, SCREEN_H - 78, 220, 54)
                _rr_sair_hov  = _rr_sair_rect.collidepoint(m_pos)
                _rr_sair_col  = (120, 50, 50) if _rr_sair_hov else (80, 30, 30)
                pygame.draw.rect(screen, _rr_sair_col, _rr_sair_rect, border_radius=10)
                pygame.draw.rect(screen, (200, 160, 60), _rr_sair_rect, 2, border_radius=10)
                _rr_sair_lbl  = font_m.render("SAIR", True, (240, 220, 180))
                screen.blit(_rr_sair_lbl, _rr_sair_lbl.get_rect(center=_rr_sair_rect.center))

            # ── Janela de Inventário / Equipamento (tecla I) ───────────────
            if hub_equip_open:
                _ie_cid  = player.char_id if player else 0
                _ie_inv  = get_char_inventory(_ie_cid)
                _ie_eq   = get_char_equipped(_ie_cid)
                _ie_GOLD = UI_THEME.get("old_gold", (200, 170, 60))
                _ie_dir  = os.path.join("assets", "ui", "itens")

                # ── Escalar e cachear inventario.png ──────────────────────
                # Quando crafting aberto, inventário fica à direita
                if craft_open:
                    _ie_sc = min(SCREEN_W * 0.44 / 1128, SCREEN_H * 0.80 / 1254)
                else:
                    _ie_sc = min(SCREEN_W * 0.42 / 1128, SCREEN_H * 0.80 / 1254)
                _ie_PW   = int(1128 * _ie_sc); _ie_PH = int(1254 * _ie_sc)
                _ie_PX   = (SCREEN_W - _ie_PW - 8) if craft_open else (SCREEN_W - _ie_PW) // 2
                _ie_PY   = (SCREEN_H - _ie_PH) // 2
                _ie_ckey = (_ie_PW, _ie_PH)
                if _ie_ckey not in _inv_panel_cache:
                    try:
                        _raw_inv = pygame.image.load(
                            os.path.join("assets", "ui", "panels", "inventario.png")
                        ).convert_alpha()
                        _inv_panel_cache[_ie_ckey] = pygame.transform.smoothscale(_raw_inv, (_ie_PW, _ie_PH))
                    except Exception:
                        _inv_panel_cache[_ie_ckey] = None
                _ie_bg = _inv_panel_cache.get(_ie_ckey)
                if _ie_bg:
                    screen.blit(_ie_bg, (_ie_PX, _ie_PY))
                else:
                    # fallback: painel escuro simples
                    _fb = pygame.Surface((_ie_PW, _ie_PH), pygame.SRCALPHA)
                    _fb.fill((12, 10, 8, 240))
                    screen.blit(_fb, (_ie_PX, _ie_PY))
                    pygame.draw.rect(screen, _ie_GOLD, pygame.Rect(_ie_PX, _ie_PY, _ie_PW, _ie_PH), 2, border_radius=8)

                # ── Helper: obter imagem do item escalada ─────────────────
                def _ie_get_img(cat, idx, size):
                    _fp, _ck = _item_img_path(cat, idx)
                    if _fp is None:
                        return None
                    _key = (_ck, size)
                    if _key not in _item_shop_img_cache:
                        if os.path.exists(_fp):
                            try:
                                _raw = pygame.image.load(_fp).convert_alpha()
                                _item_shop_img_cache[_key] = pygame.transform.smoothscale(_raw, (size, size))
                            except Exception:
                                _item_shop_img_cache[_key] = None
                        else:
                            _item_shop_img_cache[_key] = None
                    return _item_shop_img_cache.get(_key)

                # ── Helper: tooltip (acumulador — desenhado por último) ───
                _ie_pending_tt = [None]   # [itm, anchor] ou None

                def _ie_tooltip(itm, anchor):
                    _ie_pending_tt[0] = (itm, anchor)

                def _ie_draw_pending_tooltip():
                    if not _ie_pending_tt[0]: return
                    itm, anchor = _ie_pending_tt[0]
                    _tc = itm.get("category",""); _ti = itm.get("idx",0)
                    # ── Minérios: tooltip especial ────────────────────────
                    if _tc == "Minérios":
                        if 0 <= _ti < len(MINING_ORE_DEFS):
                            _ore_def = MINING_ORE_DEFS[_ti]
                            _tls2 = [_ore_def["name"], "Minério", "Qtd: %d" % itm.get("qty", 1)]
                            _ttw2 = max(font_s.size(_l)[0] for _l in _tls2) + 20
                            _tth2 = len(_tls2) * 20 + 14
                            _ttx2 = min(anchor.right + 4, SCREEN_W - _ttw2 - 4)
                            _tty2 = max(4, anchor.top)
                            _ts2 = pygame.Surface((_ttw2, _tth2), pygame.SRCALPHA); _ts2.fill((18,14,10,230))
                            screen.blit(_ts2, (_ttx2, _tty2))
                            pygame.draw.rect(screen, _ie_GOLD, pygame.Rect(_ttx2,_tty2,_ttw2,_tth2), 1, border_radius=4)
                            _c2_map = [_ie_GOLD, (160,200,220), (140,160,130)]
                            for _tli2, _tll2 in enumerate(_tls2):
                                screen.blit(font_s.render(_tll2, True, _c2_map[_tli2]),
                                            (_ttx2+8, _tty2+6+_tli2*20))
                        return
                    # ── Itens normais ─────────────────────────────────────
                    _tst = ITEM_SHOP_STATS.get(_tc,[{}])
                    _tst = _tst[_ti] if _ti < len(_tst) else {}
                    if not _tst: return
                    _tls = [_tst.get("name", _tc)]
                    _ta = _tst.get("atk",0); _td = _tst.get("def",0)
                    _tlv = _tst.get("level", 1)
                    if _ta: _tls.append("ATQ: +%d" % _ta)
                    if _td: _tls.append("DEF: +%d" % _td)
                    _tls.append("Req. Nivel: %d" % _tlv)
                    if itm.get("soulbound"): _tls.append("★ Vinculada (nao vendavel)")
                    _ttw = max(font_s.size(_l)[0] for _l in _tls) + 16
                    _tth = len(_tls) * 20 + 12
                    _ttx = min(anchor.right + 4, SCREEN_W - _ttw - 4)
                    _tty = max(4, anchor.top)
                    _ts = pygame.Surface((_ttw, _tth), pygame.SRCALPHA); _ts.fill((18,14,10,230))
                    screen.blit(_ts, (_ttx, _tty))
                    pygame.draw.rect(screen, _ie_GOLD, pygame.Rect(_ttx,_tty,_ttw,_tth), 1, border_radius=4)
                    _cur_lv_ie = get_active_profile_level()
                    for _tli, _tll in enumerate(_tls):
                        _tc2 = _ie_GOLD if _tli==0 else (200,190,160)
                        if "ATQ" in _tll: _tc2=(220,100,60)
                        elif "DEF" in _tll: _tc2=(80,160,220)
                        elif "Req. Nivel" in _tll: _tc2=(240,80,80) if _cur_lv_ie < _tlv else (100,220,100)
                        screen.blit(font_s.render(_tll, True, _tc2), (_ttx+8, _tty+6+_tli*20))

                # ── Slots de equipamento (posições da imagem 1128×1254) ───
                _ie_eqdef = {
                    "helmet": (295,143,110,104),
                    "weapon": (141,266,106,105),
                    "shield": (457,266,106,105),
                    "armor":  (295,381,110,104),
                    "legs":   (295,509,110,104),
                    "boots":  (295,637,110,100),
                }
                _ie_labels = {"helmet":"Capacete","weapon":"Arma","armor":"Armadura",
                              "shield":"Escudo","legs":"Calças","boots":"Botas"}
                _ie_active = {"weapon","shield","helmet","armor","legs","boots"}

                for _sk_ie, (ex,ey,ew,eh) in _ie_eqdef.items():
                    _sr_ie = pygame.Rect(_ie_PX+int(ex*_ie_sc), _ie_PY+int(ey*_ie_sc),
                                         int(ew*_ie_sc), int(eh*_ie_sc))
                    _eq_it = _ie_eq.get(_sk_ie)
                    _is_drag_src = (_drag_active and _drag_item is not None and
                                    _drag_item["from"]=="equip" and _drag_item["_slot"]==_sk_ie)
                    # Destaque de drop quando arrastrando item compatível
                    _is_drop_tgt = (_drag_active and _drag_item is not None and
                                    _sr_ie.collidepoint(m_pos))
                    if _is_drop_tgt:
                        _hl = pygame.Surface((_sr_ie.width, _sr_ie.height), pygame.SRCALPHA)
                        _hl.fill((255, 220, 80, 60))
                        screen.blit(_hl, _sr_ie.topleft)
                        pygame.draw.rect(screen, (255, 220, 80), _sr_ie, 2, border_radius=4)
                    if _eq_it and not _is_drag_src:
                        _img_ie = _ie_get_img(_eq_it["category"], _eq_it["idx"], min(_sr_ie.width,_sr_ie.height)-8)
                        if _img_ie:
                            screen.blit(_img_ie, _img_ie.get_rect(center=_sr_ie.center))
                        if _sr_ie.collidepoint(m_pos): _ie_tooltip(_eq_it, _sr_ie)
                    elif not _eq_it:
                        _lbl_ie = font_s.render(_ie_labels.get(_sk_ie, _sk_ie), True, (80,72,55))
                        screen.blit(_lbl_ie, _lbl_ie.get_rect(center=_sr_ie.center))
                    elif _is_drag_src:
                        # Slot vazio enquanto item está sendo arrastado
                        _emp = pygame.Surface((_sr_ie.width, _sr_ie.height), pygame.SRCALPHA)
                        _emp.fill((20, 18, 15, 80))
                        screen.blit(_emp, _sr_ie.topleft)
                        pygame.draw.rect(screen, (100, 90, 60), _sr_ie, 1, border_radius=4)

                # ── Grade de inventário (8 colunas × 5 linhas) ────────────
                _ie_COLS  = 8
                _ie_gx0   = _ie_PX + int(53  * _ie_sc)
                _ie_gy0   = _ie_PY + int(807 * _ie_sc)
                _ie_sw    = int(93  * _ie_sc)
                _ie_sh    = int(85  * _ie_sc)
                _ie_stpx  = int(95  * _ie_sc)
                _ie_stpy  = int(88  * _ie_sc)
                _ie_isize = min(_ie_sw, _ie_sh) - 8

                for _ii_ie in range(_ie_COLS * 5):
                    _col_ie = _ii_ie % _ie_COLS; _row_ie = _ii_ie // _ie_COLS
                    _gr_ie = pygame.Rect(_ie_gx0+_col_ie*_ie_stpx, _ie_gy0+_row_ie*_ie_stpy,
                                         _ie_sw, _ie_sh)
                    _has_item = _ii_ie < len(_ie_inv)
                    _is_drag_src2 = (_drag_active and _drag_item is not None and
                                     _drag_item["from"]=="inventory" and _drag_item["_idx"]==_ii_ie)
                    _is_drop_tgt2 = (_drag_active and _drag_item is not None and
                                     _gr_ie.collidepoint(m_pos))
                    if _is_drop_tgt2:
                        _hl2 = pygame.Surface((_ie_sw, _ie_sh), pygame.SRCALPHA)
                        _hl2.fill((255, 220, 80, 50))
                        screen.blit(_hl2, _gr_ie.topleft)
                        pygame.draw.rect(screen, (255, 220, 80), _gr_ie, 2, border_radius=3)
                    if _has_item and not _is_drag_src2:
                        _it_ie = _ie_inv[_ii_ie]
                        _img_g = _ie_get_img(_it_ie.get("category",""), _it_ie.get("idx", 0), _ie_isize)
                        if _img_g: screen.blit(_img_g, _img_g.get_rect(center=_gr_ie.center))
                        # Badge de quantidade para itens empilháveis (ex: minérios)
                        _it_qty = _it_ie.get("qty", 0)
                        if _it_qty > 1:
                            _qty_s = font_s.render(str(_it_qty), True, (240, 230, 160))
                            _qty_bg = pygame.Surface((_qty_s.get_width() + 6, _qty_s.get_height() + 2), pygame.SRCALPHA)
                            _qty_bg.fill((10, 8, 6, 200))
                            _qty_r  = _qty_bg.get_rect(right=_gr_ie.right - 2, bottom=_gr_ie.bottom - 2)
                            screen.blit(_qty_bg, _qty_r)
                            screen.blit(_qty_s, _qty_s.get_rect(center=_qty_r.center))
                        if _gr_ie.collidepoint(m_pos): _ie_tooltip(_it_ie, _gr_ie)
                    elif _is_drag_src2:
                        _emp2 = pygame.Surface((_ie_sw, _ie_sh), pygame.SRCALPHA)
                        _emp2.fill((15, 12, 10, 70))
                        screen.blit(_emp2, _gr_ie.topleft)

                # ── Painel de stats (lado direito da imagem) ──────────────
                _ie_sx0  = _ie_PX + int(640 * _ie_sc)   # x=640 na imagem = início da área de stats
                _ie_sy0  = _ie_PY + int(130 * _ie_sc)
                _ie_sw2  = _ie_PX + _ie_PW - _ie_sx0 - int(30 * _ie_sc)
                _GOLD_ie = _ie_GOLD
                _FGOLD_ie= UI_THEME.get("faded_gold", (140, 110, 40))

                # Nome do personagem
                _ie_cname = CHAR_DATA.get(_ie_cid, {}).get("name", "Herói")
                _ie_cn = font_m.render(_ie_cname, True, (220, 200, 160))
                screen.blit(_ie_cn, _ie_cn.get_rect(centerx=_ie_sx0+_ie_sw2//2, top=_ie_sy0))
                pygame.draw.line(screen, _FGOLD_ie,
                                 (_ie_sx0, _ie_sy0+_ie_cn.get_height()+4),
                                 (_ie_sx0+_ie_sw2, _ie_sy0+_ie_cn.get_height()+4), 1)

                # Calcular stats
                _ie_eq_w = _ie_eq.get("weapon"); _ie_eq_s = _ie_eq.get("shield")
                _ie_base_atk = CHAR_DATA.get(_ie_cid, {}).get("damage", 25)
                _ie_bon_atk = 0; _ie_bon_def = 0
                _ie_wname = None; _ie_sname = None
                if _ie_eq_w:
                    _wst = ITEM_SHOP_STATS.get(_ie_eq_w["category"], [])
                    if _ie_eq_w["idx"] < len(_wst):
                        _ie_bon_atk = _wst[_ie_eq_w["idx"]].get("atk", 0)
                        _ie_wname   = _wst[_ie_eq_w["idx"]].get("name", "")
                if _ie_eq_s:
                    _sst = ITEM_SHOP_STATS.get(_ie_eq_s["category"], [])
                    if _ie_eq_s["idx"] < len(_sst):
                        _ie_bon_def = _sst[_ie_eq_s["idx"]].get("def", 0)
                        _ie_sname   = _sst[_ie_eq_s["idx"]].get("name", "")
                _ie_bon_armor = 0
                _ie_armor_names = {}
                for _ie_aslot, _ie_albl in [("helmet","Capacete"),("armor","Armadura"),("legs","Calcas"),("boots","Botas")]:
                    _ie_aitem = _ie_eq.get(_ie_aslot)
                    if _ie_aitem:
                        _ie_ac = _ie_aitem.get("category",""); _ie_ai = _ie_aitem.get("idx",0)
                        _ie_as = ITEM_SHOP_STATS.get(_ie_ac,[])
                        if _ie_ai < len(_ie_as):
                            _ie_bon_armor += _ie_as[_ie_ai].get("def",0)
                            _ie_armor_names[_ie_albl] = _ie_as[_ie_ai].get("name","")
                _ie_def_pct = min(80, int(save_data["perm_upgrades"].get("aura_res", 0) * 10 + (_ie_bon_def + _ie_bon_armor) / 3.0))

                def _ie_stat(label, val_str, lbl_col, val_col, y_off):
                    _ls = font_s.render(label, True, lbl_col)
                    _vs = font_s.render(val_str, True, val_col)
                    screen.blit(_ls, (_ie_sx0, _ie_sy0 + y_off))
                    screen.blit(_vs, _vs.get_rect(right=_ie_sx0+_ie_sw2, top=_ie_sy0+y_off))

                _ie_sy = _ie_cn.get_height() + 14
                _ie_stat("HP", str(CHAR_DATA.get(_ie_cid,{}).get("hp", player.base_hp if player else 100)),
                         (200,80,80), (240,140,140), _ie_sy); _ie_sy += 22
                if _ie_bon_atk:
                    _ie_stat("ATQ base", str(_ie_base_atk), (180,140,80), (220,180,120), _ie_sy); _ie_sy += 20
                    _ie_stat("+ Arma", "+%d" % _ie_bon_atk, (180,140,80), (255,160,60), _ie_sy); _ie_sy += 20
                    _ie_stat("TOTAL", str(_ie_base_atk+_ie_bon_atk), (220,180,80), (255,210,60), _ie_sy); _ie_sy += 22
                else:
                    _ie_stat("ATQ", str(_ie_base_atk), (180,140,80), (220,180,120), _ie_sy); _ie_sy += 22
                if _ie_bon_def or _ie_bon_armor:
                    if _ie_bon_def:
                        _ie_stat("DEF escudo", "+%d" % _ie_bon_def, (80,130,200), (120,180,240), _ie_sy); _ie_sy += 18
                    if _ie_bon_armor:
                        _ie_stat("DEF armadura", "+%d" % _ie_bon_armor, (80,130,200), (120,180,240), _ie_sy); _ie_sy += 18
                    _ie_stat("Resistência", "%d%%" % _ie_def_pct, (80,130,200), (100,200,255), _ie_sy); _ie_sy += 22
                else:
                    _ie_stat("DEF", "%d%%" % _ie_def_pct, (80,130,200), (120,180,240), _ie_sy); _ie_sy += 22
                _ie_boots_item = _ie_eq.get("boots")
                _ie_boots_spd = 0
                if _ie_boots_item:
                    _ieb_cat = _ie_boots_item.get("category",""); _ieb_idx = _ie_boots_item.get("idx",0)
                    _ieb_sts = ITEM_SHOP_STATS.get(_ieb_cat,[])
                    if _ieb_idx < len(_ieb_sts): _ie_boots_spd = _ieb_sts[_ieb_idx].get("spd",0)
                _ie_base_spd = CHAR_DATA.get(_ie_cid,{}).get("speed",280)
                if _ie_boots_spd:
                    _ie_stat("VEL base", str(_ie_base_spd), (100,180,100),(140,220,140), _ie_sy); _ie_sy += 18
                    _ie_stat("+ Botas", "+%d" % _ie_boots_spd, (100,180,100),(140,220,140), _ie_sy); _ie_sy += 18
                    _ie_stat("VEL total", str(_ie_base_spd+_ie_boots_spd), (120,210,120),(160,240,160), _ie_sy); _ie_sy += 22
                else:
                    _ie_stat("VEL", str(_ie_base_spd), (100,180,100),(140,220,140), _ie_sy); _ie_sy += 22
                if player:
                    _ie_stat("HP atual", str(int(player.hp)), (160,80,80), (200,110,110), _ie_sy); _ie_sy += 24

                pygame.draw.line(screen, _FGOLD_ie,
                                 (_ie_sx0, _ie_sy0+_ie_sy),
                                 (_ie_sx0+_ie_sw2, _ie_sy0+_ie_sy), 1)
                _ie_sy += 8
                _eq_lbl = font_s.render("Equipamento", True, (160,140,90))
                screen.blit(_eq_lbl, _eq_lbl.get_rect(centerx=_ie_sx0+_ie_sw2//2, top=_ie_sy0+_ie_sy)); _ie_sy += 20
                _wlbl = font_s.render(("Arma: " + _ie_wname[:16]) if _ie_wname else "Sem arma", True,
                                      (220,170,70) if _ie_wname else (100,90,65))
                screen.blit(_wlbl, (_ie_sx0, _ie_sy0+_ie_sy)); _ie_sy += 20
                _slbl = font_s.render(("Escudo: " + _ie_sname[:14]) if _ie_sname else "Sem escudo", True,
                                      (100,170,220) if _ie_sname else (70,100,130))
                screen.blit(_slbl, (_ie_sx0, _ie_sy0+_ie_sy)); _ie_sy += 20
                for _ie_albl_s, _ie_aname_s in _ie_armor_names.items():
                    _ie_ar_s = font_s.render(_ie_aname_s[:20], True, (160, 180, 140))
                    screen.blit(_ie_ar_s, (_ie_sx0, _ie_sy0+_ie_sy)); _ie_sy += 18

                # Dica de fechar
                _ie_hint = font_s.render("I / ESC — Fechar", True, (90,80,58))
                screen.blit(_ie_hint, _ie_hint.get_rect(centerx=_ie_PX+_ie_PW//2, bottom=_ie_PY+_ie_PH-8))

                # ── Ouro — abaixo do 2° slot da última linha ──────────────
                _ie_gold_cx = _ie_gx0 + _ie_stpx + _ie_sw // 2   # centro do slot [4,1]
                _ie_gold_ty = _ie_gy0 + 4 * _ie_stpy + _ie_sh + 4
                _ie_gold_str = "Ouro: %d" % int(save_data.get("gold", 0))
                _ie_gs  = font_s.render(_ie_gold_str, True, (220, 190, 60))
                _ie_gsbg = pygame.Surface((_ie_gs.get_width()+12, _ie_gs.get_height()+4), pygame.SRCALPHA)
                _ie_gsbg.fill((10, 8, 4, 200))
                _ie_gr  = _ie_gsbg.get_rect(centerx=_ie_gold_cx, top=_ie_gold_ty)
                _ie_gr.clamp_ip(pygame.Rect(_ie_PX, _ie_PY, _ie_PW, _ie_PH))
                screen.blit(_ie_gsbg, _ie_gr)
                pygame.draw.rect(screen, (160, 130, 30), _ie_gr, 1, border_radius=3)
                screen.blit(_ie_gs, _ie_gs.get_rect(center=_ie_gr.center))

                # ── Painel de Crafting — FERREIRO (à esquerda) ───────────────
                if craft_open:
                    _cf_PW  = _ie_PX - 16
                    _cf_PH  = _ie_PH
                    _cf_PX  = 8
                    _cf_PY  = _ie_PY
                    if _cf_PW < 160:
                        pass   # tela muito pequena, não desenha
                    else:
                        # Fundo
                        _cf_surf = pygame.Surface((_cf_PW, _cf_PH), pygame.SRCALPHA)
                        _cf_surf.fill((14, 11, 8, 235))
                        screen.blit(_cf_surf, (_cf_PX, _cf_PY))
                        pygame.draw.rect(screen, (200, 130, 40),
                                         pygame.Rect(_cf_PX, _cf_PY, _cf_PW, _cf_PH), 2, border_radius=8)

                        # Título
                        _cf_title = font_m.render("FERREIRO", True, (255, 190, 60))
                        screen.blit(_cf_title, _cf_title.get_rect(centerx=_cf_PX + _cf_PW // 2, top=_cf_PY + 10))
                        _cf_th = _cf_title.get_height()
                        pygame.draw.line(screen, (150, 100, 30),
                                         (_cf_PX + 12, _cf_PY + 14 + _cf_th),
                                         (_cf_PX + _cf_PW - 12, _cf_PY + 14 + _cf_th), 1)
                        _cf_y0 = _cf_PY + 14 + _cf_th + 6

                        # Divisão esq/dir
                        _cf_lw  = int(_cf_PW * 0.48)
                        _cf_rx  = _cf_PX + _cf_lw + 8
                        _cf_rw  = _cf_PW - _cf_lw - 16
                        _cf_lh  = _cf_PH - (_cf_y0 - _cf_PY) - 4

                        # Lista de receitas (esquerda)
                        _cf_list_r = pygame.Rect(_cf_PX + 4, _cf_y0, _cf_lw, _cf_lh)
                        pygame.draw.rect(screen, (20, 16, 12), _cf_list_r, border_radius=4)
                        pygame.draw.rect(screen, (80, 60, 30), _cf_list_r, 1, border_radius=4)

                        _cf_REC = 44; _cf_REC_PAD = 5
                        _cf_COLS_r = max(1, _cf_lw // (_cf_REC + _cf_REC_PAD))

                        # Altura total de conteúdo para scroll
                        _cf_total_h2 = 0
                        for _cfc in CRAFT_CATEGORY_ORDER:
                            if _cfc in CRAFTED_CATEGORIES:
                                _cfc_rows = math.ceil(len(CRAFTED_CATEGORIES[_cfc]["files"]) / _cf_COLS_r)
                                _cf_total_h2 += 22 + _cfc_rows * (_cf_REC + _cf_REC_PAD)
                        _cf_max_sc = max(0, _cf_total_h2 - _cf_lh + 12)
                        _craft_scroll_y = int(max(0, min(_craft_scroll_y, _cf_max_sc)))

                        screen.set_clip(_cf_list_r.inflate(-2, -2))
                        _cf_draw_y = _cf_y0 + 6 - _craft_scroll_y
                        _cf_rects_map = {}

                        for _cfc in CRAFT_CATEGORY_ORDER:
                            if _cfc not in CRAFTED_CATEGORIES:
                                continue
                            _cfc_lbl = font_s.render(_cfc, True, (180, 140, 60))
                            screen.blit(_cfc_lbl, (_cf_PX + 6, _cf_draw_y))
                            _cf_draw_y += 22
                            _cf_col_r = 0
                            _cf_draw_xr = _cf_PX + 6
                            for _cf_idx2, _cf_fn2 in enumerate(CRAFTED_CATEGORIES[_cfc]["files"]):
                                _cf_ckey2 = f"cfr_{_cfc}_{_cf_fn2}_{_cf_REC}"
                                if _cf_ckey2 not in _craft_img_cache:
                                    _cf_path2 = os.path.join("assets", "ui", "itens_craft",
                                                              CRAFTED_CATEGORIES[_cfc]["folder"], _cf_fn2)
                                    try:
                                        _cf_raw2 = pygame.image.load(_cf_path2).convert_alpha()
                                        _craft_img_cache[_cf_ckey2] = pygame.transform.smoothscale(
                                            _cf_raw2, (_cf_REC - 6, _cf_REC - 6))
                                    except Exception:
                                        _craft_img_cache[_cf_ckey2] = None
                                _cf_img2  = _craft_img_cache.get(_cf_ckey2)
                                _cf_sr3   = pygame.Rect(_cf_draw_xr, _cf_draw_y, _cf_REC, _cf_REC)
                                _cf_rects_map[(_cfc, _cf_idx2)] = _cf_sr3
                                _cf_sel3  = (_craft_selected == (_cfc, _cf_idx2))
                                _cf_hov3  = _cf_sr3.collidepoint(m_pos) and _cf_list_r.collidepoint(m_pos)
                                _cf_bg3   = (65, 48, 18) if _cf_sel3 else ((50, 38, 14) if _cf_hov3 else (28, 22, 10))
                                _cf_brd3  = (240, 190, 60) if _cf_sel3 else ((180, 140, 50) if _cf_hov3 else (75, 60, 30))
                                pygame.draw.rect(screen, _cf_bg3, _cf_sr3, border_radius=4)
                                pygame.draw.rect(screen, _cf_brd3, _cf_sr3, 2 if _cf_sel3 else 1, border_radius=4)
                                if _cf_img2:
                                    screen.blit(_cf_img2, _cf_img2.get_rect(center=_cf_sr3.center))
                                _cf_col_r += 1
                                if _cf_col_r >= _cf_COLS_r:
                                    _cf_col_r = 0
                                    _cf_draw_xr = _cf_PX + 6
                                    _cf_draw_y += _cf_REC + _cf_REC_PAD
                                else:
                                    _cf_draw_xr += _cf_REC + _cf_REC_PAD
                            if _cf_col_r != 0:
                                _cf_draw_y += _cf_REC + _cf_REC_PAD
                        screen.set_clip(None)

                        # Resultado selecionado (direita)
                        _cf_ry2  = _cf_y0 + 4
                        _cf_scat, _cf_sidx = _craft_selected
                        _cf_sts2 = ITEM_SHOP_STATS.get(_cf_scat, [])
                        _cf_st2  = _cf_sts2[_cf_sidx] if _cf_sidx < len(_cf_sts2) else {}
                        _cf_nm2  = _cf_st2.get("name", "?")
                        _cf_ak2  = _cf_st2.get("atk", 0)
                        _cf_df2  = _cf_st2.get("def", 0)
                        _cf_lv2  = _cf_st2.get("level", 1)

                        _cf_BIG  = 72
                        _cf_bfn  = CRAFTED_CATEGORIES.get(_cf_scat, {}).get("files", [])
                        _cf_bfn  = _cf_bfn[_cf_sidx] if _cf_sidx < len(_cf_bfn) else None
                        _cf_bimg = None
                        if _cf_bfn:
                            _cf_bkey = f"cfb_{_cf_scat}_{_cf_bfn}_{_cf_BIG}"
                            if _cf_bkey not in _craft_img_cache:
                                _cf_bpath = os.path.join("assets", "ui", "itens_craft",
                                                         CRAFTED_CATEGORIES[_cf_scat]["folder"], _cf_bfn)
                                try:
                                    _cf_braw = pygame.image.load(_cf_bpath).convert_alpha()
                                    _craft_img_cache[_cf_bkey] = pygame.transform.smoothscale(_cf_braw, (_cf_BIG, _cf_BIG))
                                except Exception:
                                    _craft_img_cache[_cf_bkey] = None
                            _cf_bimg = _craft_img_cache.get(_cf_bkey)

                        # Ícone centrado no topo da coluna direita
                        _cf_ico_cx = _cf_rx + _cf_rw // 2
                        _cf_ico_r  = pygame.Rect(0, 0, _cf_BIG + 4, _cf_BIG + 4)
                        _cf_ico_r.centerx = _cf_ico_cx; _cf_ico_r.top = _cf_ry2
                        pygame.draw.rect(screen, (40, 32, 12), _cf_ico_r, border_radius=6)
                        pygame.draw.rect(screen, (200, 160, 50), _cf_ico_r, 1, border_radius=6)
                        if _cf_bimg:
                            screen.blit(_cf_bimg, _cf_bimg.get_rect(center=_cf_ico_r.center))
                        _cf_ry2 = _cf_ico_r.bottom + 5

                        # Nome — centralizado, truncado para caber na largura
                        _cf_max_chars = max(8, (_cf_rw - 8) // max(1, font_s.size("A")[0]))
                        _cf_nm_s = font_s.render(_cf_nm2[:_cf_max_chars], True, (255, 220, 80))
                        screen.blit(_cf_nm_s, _cf_nm_s.get_rect(centerx=_cf_ico_cx, top=_cf_ry2))
                        _cf_ry2 += _cf_nm_s.get_height() + 3

                        # Stats em linhas independentes, centralizados
                        for _cf_stat_txt, _cf_stat_col in [
                            (f"ATQ +{_cf_ak2}", (255, 160, 60)) if _cf_ak2 else None,
                            (f"DEF +{_cf_df2}", (80, 180, 240)) if _cf_df2 else None,
                            (f"Nv. {_cf_lv2}",  (160, 130, 80)),
                            ("Vinculada",        (200, 80, 200)),
                        ]:
                            if _cf_stat_txt is None: continue
                            _cf_ss = font_s.render(_cf_stat_txt, True, _cf_stat_col)
                            screen.blit(_cf_ss, _cf_ss.get_rect(centerx=_cf_ico_cx, top=_cf_ry2))
                            _cf_ry2 += _cf_ss.get_height() + 2

                        pygame.draw.line(screen, (100, 70, 25),
                                         (_cf_rx, _cf_ry2), (_cf_PX + _cf_PW - 8, _cf_ry2), 1)
                        _cf_ry2 += 8

                        # Label ingredientes
                        _cf_ing_l = font_s.render("Ingredientes:", True, (160, 140, 80))
                        screen.blit(_cf_ing_l, _cf_ing_l.get_rect(centerx=_cf_ico_cx, top=_cf_ry2))
                        _cf_ry2 += _cf_ing_l.get_height() + 5

                        # 3 slots de ingredientes
                        _cf_SL = min(62, (_cf_rw - 20) // 3)
                        _cf_sg = (_cf_rw - 3 * _cf_SL) // 4
                        _cf_slot_rects2: list[pygame.Rect] = []
                        for _si2 in range(3):
                            _cf_sx2 = _cf_rx + _cf_sg + _si2 * (_cf_SL + _cf_sg)
                            _cf_sr4 = pygame.Rect(_cf_sx2, _cf_ry2, _cf_SL, _cf_SL)
                            _cf_slot_rects2.append(_cf_sr4)
                            _cf_sl2 = _craft_slots[_si2]
                            _cf_drag_src2 = (_drag_active and _drag_item is not None and
                                             _drag_item.get("from") == "craft_slot" and
                                             _drag_item.get("_slot_n") == _si2)
                            _cf_drop_tgt2 = (_drag_active and _drag_item is not None and
                                             _drag_item.get("from") in ("inventory",) and
                                             _cf_sr4.collidepoint(m_pos))
                            if _cf_drop_tgt2:
                                pygame.draw.rect(screen, (80, 70, 20), _cf_sr4, border_radius=5)
                                pygame.draw.rect(screen, (255, 220, 80), _cf_sr4, 2, border_radius=5)
                            elif _cf_sl2 and not _cf_drag_src2:
                                pygame.draw.rect(screen, (42, 34, 12), _cf_sr4, border_radius=5)
                                pygame.draw.rect(screen, (200, 160, 50), _cf_sr4, 2, border_radius=5)
                                _cf_sl_img2 = _ie_get_img(_cf_sl2.get("category",""),
                                                           _cf_sl2.get("idx", 0), _cf_SL - 8)
                                if _cf_sl_img2:
                                    screen.blit(_cf_sl_img2, _cf_sl_img2.get_rect(center=_cf_sr4.center))
                                _cf_ql2 = _cf_sl2.get("qty", 0)
                                if _cf_ql2 > 1:
                                    _cf_q_s2 = font_s.render(str(_cf_ql2), True, (240, 230, 160))
                                    screen.blit(_cf_q_s2, _cf_q_s2.get_rect(right=_cf_sr4.right-2,
                                                                              bottom=_cf_sr4.bottom-2))
                            else:
                                pygame.draw.rect(screen, (22, 18, 10), _cf_sr4, border_radius=5)
                                pygame.draw.rect(screen, (70, 55, 25), _cf_sr4, 1, border_radius=5)
                                _cf_n_l2 = font_s.render(str(_si2 + 1), True, (55, 45, 22))
                                screen.blit(_cf_n_l2, _cf_n_l2.get_rect(center=_cf_sr4.center))

                        _cf_ry2 += _cf_SL + 12

                        # Botão FORJAR
                        _cf_BW = min(120, _cf_rw - 12)
                        _cf_BH = 40
                        _cf_BR = pygame.Rect(_cf_rx + (_cf_rw - _cf_BW) // 2, _cf_ry2, _cf_BW, _cf_BH)
                        _cf_bhov = _cf_BR.collidepoint(m_pos)
                        _cf_bcol = (85, 58, 10) if _cf_bhov else (55, 38, 8)
                        _cf_bbrd = (255, 200, 60) if _cf_bhov else (180, 140, 40)
                        pygame.draw.rect(screen, _cf_bcol, _cf_BR, border_radius=7)
                        pygame.draw.rect(screen, _cf_bbrd, _cf_BR, 2, border_radius=7)
                        _cf_blbl = font_m.render("FORJAR", True, (255, 220, 80))
                        screen.blit(_cf_blbl, _cf_blbl.get_rect(center=_cf_BR.center))

                        _cf_ry2 += _cf_BH + 8
                        _cf_sb_w = font_s.render("Vinculada — nao vendavel", True, (170, 70, 170))
                        screen.blit(_cf_sb_w, _cf_sb_w.get_rect(
                            centerx=_cf_rx + _cf_rw // 2, top=_cf_ry2))

                        # Armazena rects para event handling no próximo frame
                        setattr(main, "_cf_ui_rects", {
                            "slot_rects":   _cf_slot_rects2,
                            "btn_forge":    _cf_BR,
                            "recipe_rects": _cf_rects_map,
                        })

                # Tooltip por cima de tudo (desenhado por último)
                _ie_draw_pending_tooltip()

            # ── Mensagem de nível insuficiente ─────────────────────────────
            if _equip_err_msg and pygame.time.get_ticks() - _equip_err_msg_start < 3000:
                _em_surf = font_m.render(_equip_err_msg, True, (240, 80, 80))
                _em_bg   = pygame.Surface((_em_surf.get_width() + 24, _em_surf.get_height() + 14), pygame.SRCALPHA)
                _em_bg.fill((30, 8, 8, 210))
                _em_rect = _em_bg.get_rect(centerx=SCREEN_W // 2, centery=int(SCREEN_H * 0.25))
                screen.blit(_em_bg, _em_rect)
                pygame.draw.rect(screen, (200, 60, 60), _em_rect, 2, border_radius=6)
                screen.blit(_em_surf, _em_surf.get_rect(center=_em_rect.center))

            # ── Janela de Baú (tecla F) — painel compacto lado a lado ──────
            elif hub_chest_open:
                _cid_w   = player.char_id if player else 0
                _chest_w = save_data["chest_items"]
                _inv_wl  = get_char_inventory(_cid_w)
                _GOLD_W  = UI_THEME.get("old_gold", (200, 170, 60))
                _FGOLD_W = UI_THEME.get("faded_gold", (140, 110, 40))
                # ── Dimensões ampliadas com abas ───────────────────────────
                _SL_W  = 68; _PD_W = 8; _COLS_C = 4
                _PNL_W = _COLS_C * (_SL_W + _PD_W) - _PD_W + 20   # 316
                _WW = min(int(SCREEN_W * 0.98), _PNL_W * 2 + 60)
                _WH = int(SCREEN_H * 0.95)
                _WX = (SCREEN_W - _WW) // 2; _WY = (SCREEN_H - _WH) // 2
                _ROWS_C = max(4, min(8, (_WH - 136 + _PD_W) // (_SL_W + _PD_W)))
                _PNL_H = _ROWS_C * (_SL_W + _PD_W) - _PD_W + 4
                _wbg = pygame.Surface((_WW, _WH), pygame.SRCALPHA)
                _wbg.fill((12, 10, 8, 230)); screen.blit(_wbg, (_WX, _WY))
                pygame.draw.rect(screen, _GOLD_W, pygame.Rect(_WX,_WY,_WW,_WH), 2, border_radius=10)
                _t_w = font_m.render("BAU  |  INVENTARIO", True, _GOLD_W)
                screen.blit(_t_w, _t_w.get_rect(centerx=_WX+_WW//2, top=_WY+10))
                pygame.draw.line(screen, _FGOLD_W, (_WX+14,_WY+46), (_WX+_WW-14,_WY+46), 1)
                # ── Abas ──────────────────────────────────────────────────
                _tab_cx_r = _WX + _WW // 2
                _tab_itens_r = pygame.Rect(_tab_cx_r - 116, _WY + 50, 108, 26)
                _tab_min_r   = pygame.Rect(_tab_cx_r + 8,   _WY + 50, 108, 26)
                _tab_is_itens = (_chest_tab == "itens")
                pygame.draw.rect(screen, (50,42,28) if _tab_is_itens else (18,14,8), _tab_itens_r, border_radius=5)
                pygame.draw.rect(screen, _GOLD_W if _tab_is_itens else _FGOLD_W, _tab_itens_r, 1, border_radius=5)
                pygame.draw.rect(screen, (14,32,44) if not _tab_is_itens else (10,18,24), _tab_min_r, border_radius=5)
                pygame.draw.rect(screen, (60,180,220) if not _tab_is_itens else (30,80,110), _tab_min_r, 1, border_radius=5)
                _tl_i = font_s.render("ITENS", True, _GOLD_W if _tab_is_itens else _FGOLD_W)
                _tl_m = font_s.render("MINERIOS", True, (60,200,240) if not _tab_is_itens else (30,90,110))
                screen.blit(_tl_i, _tl_i.get_rect(center=_tab_itens_r.center))
                screen.blit(_tl_m, _tl_m.get_rect(center=_tab_min_r.center))
                # ── Layout ────────────────────────────────────────────────
                _divider_x = _WX + _WW // 2
                _iy0_d  = _WY + 108
                pygame.draw.line(screen, _FGOLD_W, (_divider_x,_WY+80), (_divider_x,_WY+_WH-28), 1)
                _cox_d  = _WX + (_WW // 2 - _PNL_W) // 2
                _iox_d  = _WX + _WW // 2 + (_WW // 2 - _PNL_W) // 2
                _lbl1 = font_s.render("BAU", True, (170,150,95))
                screen.blit(_lbl1, _lbl1.get_rect(centerx=_cox_d+_PNL_W//2, top=_WY+82))
                _lbl2 = font_s.render("INVENTARIO", True, (170,150,95))
                screen.blit(_lbl2, _lbl2.get_rect(centerx=_iox_d+_PNL_W//2, top=_WY+82))
                # ── Filtrar por aba ───────────────────────────────────────
                if _chest_tab == "minerios":
                    _vis_chest = [(i,it) for i,it in enumerate(_chest_w) if it.get("category")=="Minérios"]
                    _vis_inv   = [(i,it) for i,it in enumerate(_inv_wl)   if it.get("category")=="Minérios"]
                else:
                    _vis_chest = [(i,it) for i,it in enumerate(_chest_w) if it.get("category")!="Minérios"]
                    _vis_inv   = [(i,it) for i,it in enumerate(_inv_wl)   if it.get("category")!="Minérios"]

                def _draw_grid_chest(vis_items, ox, panel_tag):
                    """Desenha grade ROWS_C×COLS_C; vis_items = [(orig_idx, item), ...]."""
                    _rects_g = []
                    for _row in range(_ROWS_C):
                        for _col in range(_COLS_C):
                            _vi  = _row * _COLS_C + _col
                            _gx  = ox + _col * (_SL_W + _PD_W)
                            _gy  = _iy0_d + _row * (_SL_W + _PD_W)
                            _gr  = pygame.Rect(_gx, _gy, _SL_W, _SL_W)
                            _has = _vi < len(vis_items)
                            _orig_i = vis_items[_vi][0] if _has else -1
                            _gitem  = vis_items[_vi][1] if _has else None
                            _is_src = (_drag_active and _drag_item is not None and
                                       _drag_item["from"] == panel_tag and
                                       _drag_item["_idx"] == _orig_i and _has)
                            _is_tgt = (_drag_active and _drag_item is not None and
                                       _gr.collidepoint(m_pos))
                            if _is_tgt:
                                pygame.draw.rect(screen, (40,34,18), _gr, border_radius=5)
                                pygame.draw.rect(screen, (255,220,80), _gr, 2, border_radius=5)
                            elif _is_src:
                                pygame.draw.rect(screen, (15,12,10), _gr, border_radius=5)
                                pygame.draw.rect(screen, (80,70,40), _gr, 1, border_radius=5)
                            elif _has:
                                pygame.draw.rect(screen, (28,22,16), _gr, border_radius=5)
                                pygame.draw.rect(screen, (90,76,44), _gr, 1, border_radius=5)
                            else:
                                pygame.draw.rect(screen, (16,13,10), _gr, border_radius=5)
                                pygame.draw.rect(screen, (45,38,26), _gr, 1, border_radius=5)
                            if _has and not _is_src and _gitem is not None:
                                _gcat = _gitem.get("category",""); _gidx = _gitem.get("idx",0)
                                _gfp, _gck = _item_img_path(_gcat, _gidx)
                                _gkey = (_gck, _SL_W - 10)
                                if _gfp and _gkey not in _item_shop_img_cache:
                                    _item_shop_img_cache[_gkey] = None
                                    if os.path.exists(_gfp):
                                        try:
                                            _graw = pygame.image.load(_gfp).convert_alpha()
                                            _item_shop_img_cache[_gkey] = pygame.transform.smoothscale(
                                                _graw, (_SL_W-10, _SL_W-10))
                                        except Exception:
                                            pass
                                _gimg = _item_shop_img_cache.get(_gkey) if _gfp else None
                                if _gimg:
                                    screen.blit(_gimg, _gimg.get_rect(center=_gr.center))
                                _gqty = _gitem.get("qty", 0)
                                if _gqty > 1:
                                    _qs = font_s.render(str(_gqty), True, (240,230,160))
                                    _qbg = pygame.Surface((_qs.get_width()+4, _qs.get_height()+2), pygame.SRCALPHA)
                                    _qbg.fill((10,8,6,200))
                                    _qr = _qbg.get_rect(right=_gr.right-2, bottom=_gr.bottom-2)
                                    screen.blit(_qbg, _qr)
                                    screen.blit(_qs, _qs.get_rect(center=_qr.center))
                            if _has:
                                _rects_g.append((_orig_i, _gr))
                    return _rects_g

                _chest_rects_d = _draw_grid_chest(_vis_chest, _cox_d, "chest")
                if not _vis_chest:
                    _es = font_s.render("Bau vazio", True, (90,78,52))
                    screen.blit(_es, _es.get_rect(centerx=_cox_d+_PNL_W//2, top=_iy0_d+10))
                _inv_rects_d = _draw_grid_chest(_vis_inv, _iox_d, "inventory")
                if not _vis_inv:
                    _ei_s = font_s.render("Inventario vazio", True, (90,78,52))
                    screen.blit(_ei_s, _ei_s.get_rect(centerx=_iox_d+_PNL_W//2, top=_iy0_d+10))

                def _tip_chest(itm_c, anchor_c):
                    _tc = itm_c.get("category",""); _ti = itm_c.get("idx",0)
                    if _tc == "Minérios":
                        if 0 <= _ti < len(MINING_ORE_DEFS):
                            _od = MINING_ORE_DEFS[_ti]
                            _tls = [_od["name"], "Minerio", "Qtd: %d" % itm_c.get("qty",1)]
                            _ttw = max(font_s.size(_l)[0] for _l in _tls)+20; _tth = len(_tls)*20+14
                            _ttx = min(anchor_c.right+4, SCREEN_W-_ttw-4); _tty = max(4, anchor_c.top)
                            _ts = pygame.Surface((_ttw,_tth), pygame.SRCALPHA); _ts.fill((18,14,10,230))
                            screen.blit(_ts, (_ttx,_tty))
                            pygame.draw.rect(screen, _GOLD_W, pygame.Rect(_ttx,_tty,_ttw,_tth), 1, border_radius=4)
                            for _tli, _tll in enumerate(_tls):
                                _tc2 = _GOLD_W if _tli==0 else (140,180,200)
                                screen.blit(font_s.render(_tll,True,_tc2), (_ttx+8,_tty+6+_tli*20))
                        return
                    _tst = ITEM_SHOP_STATS.get(_tc,[{}]); _tst = _tst[_ti] if _ti<len(_tst) else {}
                    if not _tst: return
                    _tls = [_tst.get("name",_tc)]
                    _ta = _tst.get("atk",0); _td = _tst.get("def",0); _tlv = _tst.get("level",1)
                    if _ta: _tls.append("ATQ: +%d" % _ta)
                    if _td: _tls.append("DEF: +%d" % _td)
                    _tls.append("Req. Nivel: %d" % _tlv)
                    _ttw = max(font_s.size(_l)[0] for _l in _tls)+16; _tth = len(_tls)*20+12
                    _ttx = min(anchor_c.right+4, SCREEN_W-_ttw-4); _tty = max(4, anchor_c.top)
                    _ts = pygame.Surface((_ttw,_tth), pygame.SRCALPHA); _ts.fill((18,14,10,230))
                    screen.blit(_ts, (_ttx,_tty))
                    pygame.draw.rect(screen, _GOLD_W, pygame.Rect(_ttx,_tty,_ttw,_tth), 1, border_radius=4)
                    _cur_lv_tc = get_active_profile_level()
                    for _tli, _tll in enumerate(_tls):
                        _tc2 = _GOLD_W if _tli==0 else (200,190,160)
                        if "ATQ" in _tll: _tc2=(220,100,60)
                        elif "DEF" in _tll: _tc2=(80,160,220)
                        elif "Req. Nivel" in _tll: _tc2=(240,80,80) if _cur_lv_tc < _tlv else (100,220,100)
                        screen.blit(font_s.render(_tll,True,_tc2), (_ttx+8,_tty+6+_tli*20))
                for _gi5, _cr5 in _chest_rects_d:
                    if _cr5.collidepoint(m_pos): _tip_chest(_chest_w[_gi5], _cr5)
                for _gi6, _ir5 in _inv_rects_d:
                    if _ir5.collidepoint(m_pos): _tip_chest(_inv_wl[_gi6], _ir5)
                _hint_c = font_s.render("Arraste itens  |  F / ESC — Fechar", True, (90,80,58))
                screen.blit(_hint_c, _hint_c.get_rect(centerx=_WX+_WW//2, bottom=_WY+_WH-8))

            # ── Item flutuando no cursor durante drag ──────────────────────
            if _drag_active and _drag_item is not None:
                _df_item = _drag_item["item"]
                _df_cat  = _df_item.get("category",""); _df_idx = _df_item.get("idx",0)
                _df_size = 44
                _df_fp_p, _df_ck = _item_img_path(_df_cat, _df_idx)
                _df_key  = (_df_ck, _df_size)
                if _df_fp_p and _df_key not in _item_shop_img_cache:
                    if os.path.exists(_df_fp_p):
                        try:
                            _df_raw = pygame.image.load(_df_fp_p).convert_alpha()
                            _item_shop_img_cache[_df_key] = pygame.transform.smoothscale(_df_raw, (_df_size, _df_size))
                        except Exception:
                            _item_shop_img_cache[_df_key] = None
                    else:
                        _item_shop_img_cache[_df_key] = None
                _df_img = _item_shop_img_cache.get(_df_key)
                _df_mx, _df_my = m_pos
                # Sombra do item arrastado
                _df_shadow = pygame.Surface((_df_size+4, _df_size+4), pygame.SRCALPHA)
                _df_shadow.fill((0,0,0,100))
                screen.blit(_df_shadow, (_df_mx - _df_size//2 + 3, _df_my - _df_size//2 + 3))
                # Fundo levemente transparente
                _df_bg = pygame.Surface((_df_size, _df_size), pygame.SRCALPHA)
                _df_bg.fill((20,16,12,160))
                screen.blit(_df_bg, (_df_mx-_df_size//2, _df_my-_df_size//2))
                if _df_img:
                    _df_surf = _df_img.copy(); _df_surf.set_alpha(210)
                    screen.blit(_df_surf, (_df_mx-_df_size//2, _df_my-_df_size//2))
                pygame.draw.rect(screen, (220,190,80),
                                 pygame.Rect(_df_mx-_df_size//2, _df_my-_df_size//2, _df_size, _df_size),
                                 1, border_radius=3)
                # Indicador visual: "Largar para descartar" quando item está fora do painel
                if _df_cat != "":
                    _dc_sc3  = min(SCREEN_W * 0.42 / 1128, SCREEN_H * 0.80 / 1254)
                    _dc_PW3  = int(1128 * _dc_sc3); _dc_PH3 = int(1254 * _dc_sc3)
                    _dc_PX3  = (SCREEN_W - _dc_PW3) // 2; _dc_PY3 = (SCREEN_H - _dc_PH3) // 2
                    _panel_r3 = pygame.Rect(_dc_PX3, _dc_PY3, _dc_PW3, _dc_PH3)
                    if not _panel_r3.collidepoint((_df_mx, _df_my)):
                        _dh_txt = font_s.render("Largar aqui para descartar", True, (240, 90, 90))
                        _dh_bg  = pygame.Surface((_dh_txt.get_width()+14, _dh_txt.get_height()+6), pygame.SRCALPHA)
                        _dh_bg.fill((40, 10, 10, 200))
                        _dh_r   = _dh_bg.get_rect(centerx=_df_mx, top=_df_my + _df_size//2 + 6)
                        _dh_r.clamp_ip(screen.get_rect())
                        screen.blit(_dh_bg, _dh_r)
                        pygame.draw.rect(screen, (180, 50, 50), _dh_r, 1, border_radius=3)
                        screen.blit(_dh_txt, _dh_txt.get_rect(center=_dh_r.center))

            # ── Diálogo de confirmação de descarte ───────────────────────────
            if _discard_confirm is not None:
                _dc_w, _dc_h = 420, 210
                _dc_x = (SCREEN_W - _dc_w) // 2; _dc_y = (SCREEN_H - _dc_h) // 2
                # Fundo
                _dc_surf2 = pygame.Surface((_dc_w, _dc_h), pygame.SRCALPHA)
                _dc_surf2.fill((16, 12, 10, 248))
                screen.blit(_dc_surf2, (_dc_x, _dc_y))
                pygame.draw.rect(screen, (180, 50, 50), pygame.Rect(_dc_x, _dc_y, _dc_w, _dc_h), 2, border_radius=10)
                # Nome do item
                _dc_it2  = _discard_confirm["item"]
                _dc_cat2 = _dc_it2.get("category", "")
                _dc_idx2 = _dc_it2.get("idx", 0)
                if _dc_cat2 == "Minérios" and 0 <= _dc_idx2 < len(MINING_ORE_DEFS):
                    _dc_name2 = MINING_ORE_DEFS[_dc_idx2]["name"]
                else:
                    _dc_sts2  = ITEM_SHOP_STATS.get(_dc_cat2, [])
                    _dc_name2 = _dc_sts2[_dc_idx2].get("name", _dc_cat2) if _dc_idx2 < len(_dc_sts2) else _dc_cat2
                # Textos
                _dc_l1 = font_m.render("Descartar item?", True, (230, 90, 90))
                _dc_l2 = font_s.render(_dc_name2, True, (220, 200, 160))
                _dc_l3 = font_s.render("Esta ação não pode ser desfeita.", True, (140, 110, 80))
                screen.blit(_dc_l1, _dc_l1.get_rect(centerx=_dc_x+_dc_w//2, top=_dc_y+16))
                screen.blit(_dc_l2, _dc_l2.get_rect(centerx=_dc_x+_dc_w//2, top=_dc_y+52))
                screen.blit(_dc_l3, _dc_l3.get_rect(centerx=_dc_x+_dc_w//2, top=_dc_y+80))
                # Botões Sim / Não
                _dc_sim_r2 = pygame.Rect(_dc_x+40,  _dc_y+138, 148, 50)
                _dc_nao_r2 = pygame.Rect(_dc_x+232, _dc_y+138, 148, 50)
                _dc_sh2 = _dc_sim_r2.collidepoint(m_pos)
                _dc_nh2 = _dc_nao_r2.collidepoint(m_pos)
                pygame.draw.rect(screen, (130,35,35) if _dc_sh2 else (80,22,22), _dc_sim_r2, border_radius=8)
                pygame.draw.rect(screen, (210,60,60), _dc_sim_r2, 2, border_radius=8)
                pygame.draw.rect(screen, (40,80,45) if _dc_nh2 else (25,55,30), _dc_nao_r2, border_radius=8)
                pygame.draw.rect(screen, (70,160,80), _dc_nao_r2, 2, border_radius=8)
                _dc_ls = font_m.render("Sim", True, (250,160,160))
                _dc_ln = font_m.render("Não", True, (160,250,160))
                screen.blit(_dc_ls, _dc_ls.get_rect(center=_dc_sim_r2.center))
                screen.blit(_dc_ln, _dc_ln.get_rect(center=_dc_nao_r2.center))

            # ── Janela de Status do Personagem (C) ──────────────────────────
            if hub_status_open and player is not None:
                _ST_W  = 310
                _ST_H  = min(500, int(SCREEN_H * 0.76))
                _ST_X  = 10
                _ST_Y  = (SCREEN_H - _ST_H) // 2
                _GOLD  = UI_THEME.get("old_gold", (200, 170, 60))
                _FGOLD = UI_THEME.get("faded_gold", (140, 110, 40))

                # status.png como fundo
                _stpk = (_ST_W, _ST_H)
                if _stpk not in _status_panel_cache:
                    try:
                        _stp_raw = pygame.image.load(
                            os.path.join("assets", "ui", "panels", "status.png")
                        ).convert_alpha()
                        _status_panel_cache[_stpk] = pygame.transform.smoothscale(_stp_raw, _stpk)
                    except Exception:
                        _status_panel_cache[_stpk] = None
                _stp_img = _status_panel_cache.get(_stpk)
                if _stp_img:
                    screen.blit(_stp_img, (_ST_X, _ST_Y))
                else:
                    _st_bg = pygame.Surface((_ST_W, _ST_H), pygame.SRCALPHA)
                    _st_bg.fill((10, 8, 6, 230))
                    screen.blit(_st_bg, (_ST_X, _ST_Y))
                    pygame.draw.rect(screen, _GOLD, pygame.Rect(_ST_X, _ST_Y, _ST_W, _ST_H), 2, border_radius=8)

                # Nome do personagem no header da imagem (divisor dourado a 9.4% / ~45px)
                _st_char_name = CHAR_DATA.get(player.char_id, {}).get("name", "Herói")
                _st_cn = font_m.render(_st_char_name, True, (220, 200, 160))
                screen.blit(_st_cn, _st_cn.get_rect(centerx=_ST_X + _ST_W // 2, centery=_ST_Y + int(_ST_H * 0.047)))

                # Calcular stats com equipamento
                _st_equipped = get_char_equipped(player.char_id)
                _st_eq_w = _st_equipped.get("weapon")
                _st_eq_s = _st_equipped.get("shield")
                _base_atk  = CHAR_DATA.get(player.char_id, {}).get("damage", 25)
                _bonus_atk = 0
                _bonus_def = 0
                _eq_weapon_name = None
                _eq_shield_name = None
                if _st_eq_w:
                    _wst2 = ITEM_SHOP_STATS.get(_st_eq_w["category"], [])
                    if _st_eq_w["idx"] < len(_wst2):
                        _bonus_atk = _wst2[_st_eq_w["idx"]].get("atk", 0)
                        _eq_weapon_name = _wst2[_st_eq_w["idx"]].get("name", "")
                if _st_eq_s:
                    _sst2 = ITEM_SHOP_STATS.get(_st_eq_s["category"], [])
                    if _st_eq_s["idx"] < len(_sst2):
                        _bonus_def = _sst2[_st_eq_s["idx"]].get("def", 0)
                        _eq_shield_name = _sst2[_st_eq_s["idx"]].get("name", "")
                _bonus_armor_def = 0
                _eq_armor_names = {}
                for _arm_slot, _arm_lbl in [("helmet","Capacete"),("armor","Armadura"),("legs","Calças"),("boots","Botas")]:
                    _arm_item = _st_equipped.get(_arm_slot)
                    if _arm_item:
                        _arcat = _arm_item.get("category","")
                        _aridx = _arm_item.get("idx",0)
                        _arsts = ITEM_SHOP_STATS.get(_arcat,[])
                        if _aridx < len(_arsts):
                            _bonus_armor_def += _arsts[_aridx].get("def", 0)
                            _eq_armor_names[_arm_lbl] = _arsts[_aridx].get("name","")
                _def_pct = min(55, int(save_data["perm_upgrades"].get("aura_res", 0) * 8 + (_bonus_def + _bonus_armor_def) / 6.0))

                # Margens exatas da borda interna do frame status.png
                # Original 1024px: borda esq x=140, borda dir x=880
                # Escalado p/ 310px: x=43 (esq) a x=267 (dir) → usar _ST_MX=47 e _ST_RX=263
                _ST_MX = _ST_X + 47          # margem esquerda dentro do frame
                _ST_RX = _ST_X + _ST_W - 48  # borda direita para right-align

                # Linha de stat
                def _draw_stat(label, value_str, lbl_col, val_col, y_off):
                    _ls = font_s.render(label, True, lbl_col)
                    _vs = font_s.render(value_str, True, val_col)
                    screen.blit(_ls, (_ST_MX, _ST_Y + y_off))
                    screen.blit(_vs, (_vs.get_rect(right=_ST_RX, top=_ST_Y + y_off)))

                # Stats — seção superior do frame (abaixo da 1ª divisória ~y=47px)
                _sy = int(_ST_H * 0.10)
                _draw_stat("HP", f"{CHAR_DATA.get(player.char_id,{}).get('hp', player.base_hp)}", (200, 80, 80), (240, 140, 140), _sy)
                _sy += 22
                if _bonus_atk:
                    _draw_stat("ATQ base", str(_base_atk), (180, 140, 80), (220, 180, 120), _sy); _sy += 20
                    _draw_stat("+ Arma",   f"+{_bonus_atk}", (180, 140, 80), (255, 160, 60), _sy); _sy += 20
                    _draw_stat("TOTAL",    str(_base_atk + _bonus_atk), (220, 180, 80), (255, 210, 60), _sy); _sy += 22
                else:
                    _draw_stat("ATQ", str(_base_atk), (180, 140, 80), (220, 180, 120), _sy); _sy += 22
                if _bonus_def or _bonus_armor_def:
                    if _bonus_def:
                        _draw_stat("DEF escudo", f"+{_bonus_def}", (80, 130, 200), (120, 180, 240), _sy); _sy += 18
                    if _bonus_armor_def:
                        _draw_stat("DEF armadura", f"+{_bonus_armor_def}", (80, 130, 200), (120, 180, 240), _sy); _sy += 18
                    _draw_stat("Resist.", f"{_def_pct}%", (80, 130, 200), (100, 200, 255), _sy); _sy += 22
                else:
                    _draw_stat("DEF", f"{_def_pct}%", (80, 130, 200), (120, 180, 240), _sy); _sy += 22
                _st_boots_item = _st_equipped.get("boots")
                _st_boots_spd = 0
                if _st_boots_item:
                    _stb_cat = _st_boots_item.get("category", "")
                    _stb_idx = _st_boots_item.get("idx", 0)
                    _stb_sts = ITEM_SHOP_STATS.get(_stb_cat, [])
                    if _stb_idx < len(_stb_sts):
                        _st_boots_spd = _stb_sts[_stb_idx].get("spd", 0)
                _st_base_spd = CHAR_DATA.get(player.char_id, {}).get("speed", 280)
                if _st_boots_spd:
                    _draw_stat("VEL base", str(_st_base_spd), (100, 180, 100), (140, 220, 140), _sy); _sy += 18
                    _draw_stat("+ Botas", f"+{_st_boots_spd}", (100, 180, 100), (140, 220, 140), _sy); _sy += 18
                    _draw_stat("VEL total", str(_st_base_spd + _st_boots_spd), (120, 210, 120), (160, 240, 160), _sy); _sy += 22
                else:
                    _draw_stat("VEL", str(_st_base_spd), (100, 180, 100), (140, 220, 140), _sy); _sy += 22
                _draw_stat("HP atual", f"{int(player.hp)}", (160, 80, 80), (200, 110, 110), _sy); _sy += 24

                # Equipamento — seção inferior do frame (abaixo da 2ª divisória ~y=61.6%)
                _sy = max(_sy, int(_ST_H * 0.63))
                _eq_lbl = font_s.render("Equipamento", True, (160, 140, 90))
                screen.blit(_eq_lbl, _eq_lbl.get_rect(centerx=_ST_X + _ST_W // 2, top=_ST_Y + _sy)); _sy += 20
                if _eq_weapon_name:
                    _ew_s = font_s.render("Arma: " + _eq_weapon_name[:12], True, (220, 170, 70))
                    screen.blit(_ew_s, (_ST_MX, _ST_Y + _sy)); _sy += 20
                else:
                    _ew_s = font_s.render("Sem arma", True, (110, 100, 70))
                    screen.blit(_ew_s, (_ST_MX, _ST_Y + _sy)); _sy += 20
                if _eq_shield_name:
                    _es_s = font_s.render("Escudo: " + _eq_shield_name[:10], True, (100, 170, 220))
                    screen.blit(_es_s, (_ST_MX, _ST_Y + _sy)); _sy += 20
                else:
                    _es_s = font_s.render("Sem escudo", True, (70, 110, 140))
                    screen.blit(_es_s, (_ST_MX, _ST_Y + _sy)); _sy += 20
                for _albl, _aname in _eq_armor_names.items():
                    _ea_s = font_s.render(_aname[:16], True, (160, 180, 140))
                    screen.blit(_ea_s, (_ST_MX, _ST_Y + _sy)); _sy += 18

                # Dica de fechar — dentro do frame (borda inferior ~97% da altura)
                _st_close = font_s.render("C / ESC — Fechar", True, (100, 90, 65))
                screen.blit(_st_close, _st_close.get_rect(centerx=_ST_X + _ST_W // 2, bottom=_ST_Y + _ST_H - 22))

            # ── Painel lateral direito ──────────────────────────────────────
            if state == "HUB":
                _hp_x = int(SCREEN_W * 0.84)
                _hp_w = SCREEN_W - _hp_x
                _cx   = _hp_x + _hp_w // 2
                _panel = pygame.Surface((_hp_w, SCREEN_H), pygame.SRCALPHA)
                _panel.fill((10, 8, 6, 215))
                screen.blit(_panel, (_hp_x, 0))
                _sh_key = (_hp_w, SCREEN_H)
                if _sh_key not in _sala_heroi_cache:
                    try:
                        _sh_raw = pygame.image.load(
                            os.path.join("assets", "ui", "panels", "sala_do_heroi.png")
                        ).convert_alpha()
                        _sala_heroi_cache[_sh_key] = pygame.transform.smoothscale(_sh_raw, _sh_key)
                    except Exception:
                        _sala_heroi_cache[_sh_key] = None
                _sh_img = _sala_heroi_cache.get(_sh_key)
                if _sh_img:
                    screen.blit(_sh_img, (_hp_x, 0))
                pygame.draw.line(screen, UI_THEME.get("old_gold", (180, 150, 80)), (_hp_x, 0), (_hp_x, SCREEN_H), 2)
                _title_s = font_s.render("Sala do Herói", True, UI_THEME.get("old_gold", (220, 180, 80)))
                screen.blit(_title_s, _title_s.get_rect(centerx=_cx, top=int(SCREEN_H * 0.03)))
                _area_names = {"exterior": "Exterior", "interior_1": "1º Andar", "interior_2": "2º Andar"}
                _area_key   = hub_scene.current_map_name if hub_scene else "exterior"
                _area_s = font_s.render(_area_names.get(_area_key, _area_key), True, (160, 150, 120))
                screen.blit(_area_s, _area_s.get_rect(centerx=_cx, top=int(SCREEN_H * 0.08)))
                if player is not None:
                    _char_name = CHAR_DATA.get(player.char_id, {}).get("name", "")
                    _name_s = font_s.render(_char_name, True, (220, 210, 180))
                    screen.blit(_name_s, _name_s.get_rect(centerx=_cx, top=int(SCREEN_H * 0.13)))
                    _hp_s = font_s.render(f"HP: {int(player.hp)}/{PLAYER_MAX_HP}", True, (220, 80, 80))
                    screen.blit(_hp_s, _hp_s.get_rect(centerx=_cx, top=int(SCREEN_H * 0.19)))
                _rb_rw = _hp_w - int(_hp_w * 0.20)
                _rb_rx = _hp_x + int(_hp_w * 0.10)
                _rb_h  = 50
                _market_rect = pygame.Rect(_rb_rx, int(SCREEN_H * 0.373) - _rb_h//2, _rb_rw, _rb_h)
                _talent_rect = pygame.Rect(_rb_rx, int(SCREEN_H * 0.453) - _rb_h//2, _rb_rw, _rb_h)
                _pronto_rect = pygame.Rect(_rb_rx, int(SCREEN_H * 0.562) - _rb_h//2, _rb_rw, _rb_h)
                for _r, _lbl in [(_market_rect, "Mercado"), (_talent_rect, "Talentos")]:
                    _hov = _r.collidepoint(m_pos)
                    _ls = font_s.render(_lbl, True, (240, 220, 160) if _hov else (200, 180, 120))
                    screen.blit(_ls, _ls.get_rect(center=_r.center))
                hub_pronto_btn.check_hover(m_pos, snd_hover)
                _pr_hov = _pronto_rect.collidepoint(m_pos) or hub_pronto_btn.is_hovered
                _pr_col = (200, 255, 200) if _pr_hov else (140, 220, 140)
                _pr_s   = font_m.render("PRONTO", True, _pr_col)
                screen.blit(_pr_s, _pr_s.get_rect(center=_pronto_rect.center))
                if hub_countdown_active:
                    _cd_text = f"Em {int(hub_countdown_timer) + 1}..."
                    _cd_s = font_s.render(_cd_text, True, (255, 220, 60))
                    screen.blit(_cd_s, _cd_s.get_rect(centerx=_cx, top=int(SCREEN_H * 0.55)))
                if selected_difficulty == "HARDCORE":
                    _hc_unlocked = save_data.get("hardcore_stages", {}).get("unlocked", 1)
                    _hc_lbl = font_s.render("Fase Hardcore:", True, (220, 100, 100))
                    screen.blit(_hc_lbl, _hc_lbl.get_rect(centerx=_cx, top=int(SCREEN_H * 0.66)))
                    _hc_arr_y = int(SCREEN_H * 0.72)
                    _hc_larr = pygame.Rect(_cx - 80, _hc_arr_y - 16, 32, 32)
                    _hc_rarr = pygame.Rect(_cx + 48, _hc_arr_y - 16, 32, 32)
                    _hcl_hov = _hc_larr.collidepoint(m_pos)
                    _hcr_hov = _hc_rarr.collidepoint(m_pos)
                    pygame.draw.rect(screen, (160, 60, 60) if _hcl_hov else (100, 40, 40), _hc_larr, border_radius=6)
                    pygame.draw.rect(screen, (160, 60, 60) if _hcr_hov else (100, 40, 40), _hc_rarr, border_radius=6)
                    _hcl_s = font_s.render("<", True, (240, 200, 100))
                    _hcr_s = font_s.render(">", True, (240, 200, 100))
                    screen.blit(_hcl_s, _hcl_s.get_rect(center=_hc_larr.center))
                    screen.blit(_hcr_s, _hcr_s.get_rect(center=_hc_rarr.center))
                    _hc_stage_s = font_m.render(f"{current_hardcore_stage} / {_hc_unlocked}", True, (255, 200, 80))
                    screen.blit(_hc_stage_s, _hc_stage_s.get_rect(centerx=_cx, centery=_hc_arr_y))
                    if _hc_unlocked > 1:
                        _hc_hint = font_s.render(f"Fases desbloqueadas: {_hc_unlocked}", True, (160, 120, 60))
                        screen.blit(_hc_hint, _hc_hint.get_rect(centerx=_cx, top=int(SCREEN_H * 0.76)))
                    main._hc_larr = _hc_larr
                    main._hc_rarr = _hc_rarr
                _BG_LABELS = {"dungeon": "Dungeon", "volcano": "Vulcão", "moon": "Lua", "forest": "Floresta"}
                _biome_y   = int(SCREEN_H * 0.81)
                _bg_lbl_s  = font_s.render("Bioma", True, (180, 160, 100))
                screen.blit(_bg_lbl_s, _bg_lbl_s.get_rect(centerx=_cx, top=_biome_y))
                _bg_name_s = font_s.render(_BG_LABELS.get(selected_bg, selected_bg.capitalize()), True, (240, 210, 130))
                screen.blit(_bg_name_s, _bg_name_s.get_rect(centerx=_cx, top=_biome_y + 22))
                _bg_name_w  = font_s.size(_BG_LABELS.get(selected_bg, selected_bg.capitalize()))[0]
                _bg_arr_cy  = _biome_y + 32
                _biome_larr = pygame.Rect(_cx - _bg_name_w//2 - 46, _bg_arr_cy - 16, 38, 32)
                _biome_rarr = pygame.Rect(_cx + _bg_name_w//2 + 8,  _bg_arr_cy - 16, 38, 32)
                for _ar, _ch in ((_biome_larr, "<"), (_biome_rarr, ">")):
                    _hov = _ar.collidepoint(m_pos)
                    pygame.draw.rect(screen, (150, 110, 50) if _hov else (85, 65, 25), _ar, border_radius=5)
                    pygame.draw.rect(screen, (200, 160, 80), _ar, 1, border_radius=5)
                    _ch_s = font_m.render(_ch, True, (255, 220, 120) if _hov else (200, 170, 80))
                    screen.blit(_ch_s, _ch_s.get_rect(center=_ar.center))
                main._biome_larr = _biome_larr
                main._biome_rarr = _biome_rarr
                _hint_i = font_s.render("[I] Inventário", True, (100, 120, 160))
                _hint_c = font_s.render("[C] Status", True, (100, 160, 100))
                _hint_l = font_s.render("[L] Perfil / Conquistas", True, (160, 130, 200))
                _esc_s  = font_s.render("ESC → Voltar", True, (120, 110, 90))
                _hint_top = _pronto_rect.bottom + 10
                screen.blit(_hint_i, _hint_i.get_rect(centerx=_cx, top=_hint_top))
                screen.blit(_hint_c, _hint_c.get_rect(centerx=_cx, top=_hint_top + 22))
                screen.blit(_hint_l, _hint_l.get_rect(centerx=_cx, top=_hint_top + 44))
                screen.blit(_esc_s,  _esc_s.get_rect(centerx=_cx,  bottom=int(SCREEN_H * 0.97)))

            else:
                # ── Painel lateral direito (Mercado) ─────────────────────────
                # Quando craft_open: painel fica oculto e só aparece ao encostar o cursor na borda direita
                _mkt_panel_edge_trigger = SCREEN_W - 60
                _show_mkt_panel = (not craft_open) or (m_pos[0] >= _mkt_panel_edge_trigger)
                if not _show_mkt_panel:
                    # Mostra aba estreita na borda para indicar que o painel existe
                    _tab_w = 14
                    _tab_surf = pygame.Surface((_tab_w, SCREEN_H), pygame.SRCALPHA)
                    _tab_surf.fill((10, 8, 6, 160))
                    screen.blit(_tab_surf, (SCREEN_W - _tab_w, 0))
                    pygame.draw.line(screen, (120, 100, 60), (SCREEN_W - _tab_w, 0), (SCREEN_W - _tab_w, SCREEN_H), 1)
                if _show_mkt_panel:
                    _hp_x = int(SCREEN_W * 0.84)
                    _hp_w = SCREEN_W - _hp_x
                    _cx   = _hp_x + _hp_w // 2
                    _panel = pygame.Surface((_hp_w, SCREEN_H), pygame.SRCALPHA)
                    _panel.fill((10, 8, 6, 215))
                    screen.blit(_panel, (_hp_x, 0))
                    _sh_key = (_hp_w, SCREEN_H)
                    if _sh_key not in _sala_heroi_cache:
                        try:
                            _sh_raw = pygame.image.load(
                                os.path.join("assets", "ui", "panels", "sala_do_heroi.png")
                            ).convert_alpha()
                            _sala_heroi_cache[_sh_key] = pygame.transform.smoothscale(_sh_raw, _sh_key)
                        except Exception:
                            _sala_heroi_cache[_sh_key] = None
                    _sh_img = _sala_heroi_cache.get(_sh_key)
                    if _sh_img:
                        screen.blit(_sh_img, (_hp_x, 0))
                    pygame.draw.line(screen, UI_THEME.get("old_gold", (180, 150, 80)), (_hp_x, 0), (_hp_x, SCREEN_H), 2)
                    _title_s = font_s.render("Mercado", True, UI_THEME.get("old_gold", (220, 180, 80)))
                    screen.blit(_title_s, _title_s.get_rect(centerx=_cx, top=int(SCREEN_H * 0.03)))
                    _area_s = font_s.render("Mercado", True, (160, 150, 120))
                    screen.blit(_area_s, _area_s.get_rect(centerx=_cx, top=int(SCREEN_H * 0.08)))
                    if player is not None:
                        _char_name = CHAR_DATA.get(player.char_id, {}).get("name", "")
                        _name_s = font_s.render(_char_name, True, (220, 210, 180))
                        screen.blit(_name_s, _name_s.get_rect(centerx=_cx, top=int(SCREEN_H * 0.13)))
                        _hp_s = font_s.render(f"HP: {int(player.hp)}/{PLAYER_MAX_HP}", True, (220, 80, 80))
                        screen.blit(_hp_s, _hp_s.get_rect(centerx=_cx, top=int(SCREEN_H * 0.19)))
                    _rb_rw = _hp_w - int(_hp_w * 0.20)
                    _rb_rx = _hp_x + int(_hp_w * 0.10)
                    _rb_h  = 50
                    _pronto_rect = pygame.Rect(_rb_rx, int(SCREEN_H * 0.562) - _rb_h//2, _rb_rw, _rb_h)
                    for _r, _lbl in [
                        (pygame.Rect(_rb_rx, int(SCREEN_H * 0.373) - _rb_h//2, _rb_rw, _rb_h), "Missões"),
                        (pygame.Rect(_rb_rx, int(SCREEN_H * 0.453) - _rb_h//2, _rb_rw, _rb_h), "Talentos"),
                    ]:
                        _hov = _r.collidepoint(m_pos)
                        _ls = font_s.render(_lbl, True, (240, 220, 160) if _hov else (200, 180, 120))
                        screen.blit(_ls, _ls.get_rect(center=_r.center))
                    _vol_hov = _pronto_rect.collidepoint(m_pos)
                    _vol_s = font_m.render("VOLTAR", True, (200, 255, 200) if _vol_hov else (140, 220, 140))
                    screen.blit(_vol_s, _vol_s.get_rect(center=_pronto_rect.center))
                    _hint_i = font_s.render("[I] Inventário", True, (100, 120, 160))
                    _hint_c = font_s.render("[C] Status", True, (100, 160, 100))
                    _hint_l = font_s.render("[L] Perfil / Conquistas", True, (160, 130, 200))
                    _esc_s  = font_s.render("ESC → Voltar", True, (120, 110, 90))
                    _hint_top = _pronto_rect.bottom + 10
                    screen.blit(_hint_i, _hint_i.get_rect(centerx=_cx, top=_hint_top))
                    screen.blit(_hint_c, _hint_c.get_rect(centerx=_cx, top=_hint_top + 22))
                    screen.blit(_hint_l, _hint_l.get_rect(centerx=_cx, top=_hint_top + 44))
                    screen.blit(_esc_s,  _esc_s.get_rect(centerx=_cx,  bottom=int(SCREEN_H * 0.97)))

                # ── Overlay flutuante de Talentos (Mercado) ──────────────────
                if market_shop_open:
                    _mko = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
                    _mko.fill((0, 0, 0, 200))
                    screen.blit(_mko, (0, 0))
                    shop_header = pygame.Rect(int(SCREEN_W * 0.08), int(SCREEN_H * 0.06), int(SCREEN_W * 0.84), 105)
                    draw_dark_panel(screen, shop_header, alpha=180, border_color=UI_THEME["old_gold"])
                    draw_screen_title(screen, font_l, "ÁRVORE DE TALENTOS", SCREEN_W//2, int(SCREEN_H*0.1))
                    _mko_gold = font_m.render(f"OURO: {save_data['gold']}", True, UI_THEME["faded_gold"])
                    screen.blit(_mko_gold, _mko_gold.get_rect(topright=(SCREEN_W - 30, 20)))
                    for p_idx, p_name in enumerate(path_names):
                        path = TALENT_TREE[p_name]
                        px = int(SCREEN_W * 0.1)
                        py = int(SCREEN_H * (SHOP_PATH_TOP_RATIO + p_idx * SHOP_PATH_GAP_RATIO))
                        row_panel = pygame.Rect(px - 20, py - 16, int(SCREEN_W * 0.80), SHOP_ROW_PANEL_HEIGHT)
                        draw_dark_panel(screen, row_panel, alpha=175, border_color=UI_THEME["iron"])
                        p_title = font_m.render(path["title"], True, UI_THEME["parchment"])
                        screen.blit(p_title, (px, py))
                        p_desc = font_s.render(path["desc"], True, UI_THEME["mist"])
                        screen.blit(p_desc, (px, py + 40))
                        skill_keys = list(path["skills"].keys())
                        for s_idx, s_key in enumerate(skill_keys):
                            skill = path["skills"][s_key]
                            lvl = save_data["perm_upgrades"].get(s_key, 0)
                            sy = py + SHOP_SKILL_TOP_OFFSET + s_idx * SHOP_SKILL_GAP
                            s_txt = font_s.render(f"{skill['name']} ({lvl}/{skill['max']})", True, UI_THEME["old_gold"])
                            screen.blit(s_txt, (px + 50, sy))
                            sd_txt = load_body_font(18).render(skill["desc"], True, (200, 200, 200))
                            screen.blit(sd_txt, (px + 300, sy + 5))
                            btn_found = shop_talent_btn_map[(p_name, s_key)]
                            if lvl < skill["max"]:
                                price = skill["cost"][lvl]
                                btn_found.text = f"{price} G"
                                btn_found.color = (40, 100, 40) if save_data["gold"] >= price else (100, 40, 40)
                            else:
                                btn_found.text = "MAX"
                                btn_found.color = (60, 60, 60)
                            btn_found.check_hover(m_pos, snd_hover)
                            btn_found.draw(screen)
                    shop_back_btn.check_hover(m_pos, snd_hover)
                    shop_back_btn.draw(screen)

                # ── Overlay flutuante de Missões (Mercado) ───────────────────
                elif market_missions_open:
                    _mko = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
                    _mko.fill((0, 0, 0, 200))
                    screen.blit(_mko, (0, 0))
                    draw_screen_title(screen, font_l, "MISSÕES DIÁRIAS", SCREEN_W//2, int(SCREEN_H*0.12), text_color=(255, 215, 0))
                    _now_dt = datetime.now()
                    _next_reset = (_now_dt + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
                    _remaining = max(0, int((_next_reset - _now_dt).total_seconds()))
                    _rem_h = _remaining // 3600; _rem_m = (_remaining % 3600) // 60; _rem_s = _remaining % 60
                    _timer_txt = font_s.render(f"RESET EM: {_rem_h:02}:{_rem_m:02}:{_rem_s:02}", True, (255, 240, 140))
                    screen.blit(_timer_txt, _timer_txt.get_rect(center=(SCREEN_W//2, SCREEN_H*0.18)))
                    for i, m in enumerate(save_data["daily_missions"]["active"]):
                        y_base = int(SCREEN_H * 0.22) + i * 74
                        box_rect = pygame.Rect(SCREEN_W//2 - 310, y_base, 620, 66)
                        pygame.draw.rect(screen, (30, 30, 50, 200), box_rect, border_radius=8)
                        pygame.draw.rect(screen, (100, 100, 255), box_rect, 2, border_radius=8)
                        title = font_m.render(m['name'], True, (255, 255, 100))
                        screen.blit(title, (box_rect.x + 14, box_rect.y + 6))
                        _prog_pct = min(1.0, m['progress'] / max(1, m['goal']))
                        _prog_txt = font_s.render(f"{m['progress']}/{m['goal']}", True, (180, 220, 180))
                        screen.blit(_prog_txt, (box_rect.x + 14, box_rect.y + 34))
                        prog_bar_rect = pygame.Rect(box_rect.x + 130, box_rect.y + 38, 240, 12)
                        pygame.draw.rect(screen, (0, 0, 0), prog_bar_rect)
                        pygame.draw.rect(screen, (0, 220, 80), (prog_bar_rect.x, prog_bar_rect.y, int(prog_bar_rect.width * _prog_pct), prog_bar_rect.height))
                        pygame.draw.rect(screen, (180, 180, 180), prog_bar_rect, 1)
                        _rew_txt = font_s.render(f"+{m['reward']}G", True, (255, 200, 60))
                        screen.blit(_rew_txt, (box_rect.right - 110, box_rect.y + 6))
                        if m['completed']:
                            if m['claimed']:
                                claim_txt = font_s.render("COLETADO!", True, (100, 255, 100))
                                screen.blit(claim_txt, (box_rect.right - 110, box_rect.centery - 8))
                            else:
                                mission_claim_btns[i].rect.midright = (box_rect.right - 6, box_rect.centery)
                                mission_claim_btns[i].check_hover(m_pos, snd_hover)
                                mission_claim_btns[i].draw(screen)
                    mission_btns[0].check_hover(m_pos, snd_hover)
                    mission_btns[0].draw(screen)

        elif state == "PACT_SELECT":
            draw_menu_background(screen, m_pos, dt)
            draw_screen_title(screen, font_l, "ESCOLHA SEU PACTO", SCREEN_W//2, int(SCREEN_H*0.12), text_color=UI_THEME["blood_red"])
            pact_names = list(PACTOS.keys())
            for i, btn in enumerate(pact_btns):
                btn.check_hover(m_pos, snd_hover)
                btn.draw(screen)
                pact_key  = pact_names[i]
                pact_data = PACTOS[pact_key]
                # Descrição centralizada abaixo do bar sprite
                desc_col = (200, 175, 120) if btn.is_hovered else (155, 135, 85)
                desc_s   = font_s.render(pact_data["desc"], True, desc_col)
                screen.blit(desc_s, desc_s.get_rect(center=(SCREEN_W // 2, btn.rect.bottom + 13)))
                # Indicador de selecionado (✓ à direita do bar)
                if pact_key == selected_pact:
                    sel_s = font_s.render("✓", True, pact_data["color"])
                    screen.blit(sel_s, sel_s.get_rect(midleft=(btn.rect.right + 8, btn.rect.centery)))
            pact_back_btn.check_hover(m_pos, snd_hover)
            pact_back_btn.draw(screen)

        elif state == "SETTINGS":
            draw_settings_menu(screen, settings, temp_settings, settings_category, m_pos, font_l, font_m, font_s, clock, dt)
            
        elif state == "BG_SELECT":
            draw_menu_background(screen, m_pos, dt)
            overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA); overlay.fill((0, 0, 0, 180)); screen.blit(overlay, (0, 0))
            draw_screen_title(screen, font_l, "SELECIONAR BIOMA", SCREEN_W//2, int(SCREEN_H*0.12), text_color=(0, 220, 255))
            for i, b in enumerate(bg_btns):
                b.check_hover(m_pos, snd_hover)
                b.draw(screen)
                bg_key = bg_choices[i]
                preview_name = BG_DATA[bg_key]["name"]
                preview_img = loader.load_image(preview_name, (80, 80))
                preview_rect = preview_img.get_rect(midright=(b.rect.left - 20, b.rect.centery))
                screen.blit(preview_img, preview_rect)
                if bg_key == selected_bg:
                    pygame.draw.rect(screen, (0, 255, 0), b.rect.inflate(10, 10), 3, border_radius=14)
            bg_back_btn.check_hover(m_pos, snd_hover); bg_back_btn.draw(screen)
            
        elif state in ["PLAYING", "UPGRADE", "CHEST_UI", "GAME_OVER", "PAUSED"] and player is not None:
            cam = pygame.Vector2(SCREEN_W/2, SCREEN_H/2) - player.pos + shake_offset
            
            if 'darkness_timer' not in locals(): darkness_timer = 0.0
            if state == "PLAYING" and darkness_timer > 0: darkness_timer -= dt
            
            bg_w, bg_h = ground_img.get_size()
            if _bg_cache_src is not ground_img:
                # Reconstrói cache ao trocar de bioma (1 blit por tile, feito uma vez)
                _bg_cache = pygame.Surface((SCREEN_W + bg_w, SCREEN_H + bg_h))
                for _cx in range(0, SCREEN_W + bg_w, bg_w):
                    for _cy in range(0, SCREEN_H + bg_h, bg_h):
                        _bg_cache.blit(ground_img, (_cx, _cy))
                _bg_cache_src = ground_img
            screen.blit(_bg_cache, (int(cam.x % bg_w) - bg_w, int(cam.y % bg_h) - bg_h))

            # Decorações animadas da floresta (fogueira, bandeira) — desenhadas sobre o chão
            if selected_bg == "forest" and forest_deco_manager is not None:
                forest_deco_manager.draw(screen, SCREEN_W, SCREEN_H)

            # Decorações de chão do dungeon (pentagrama, BDS, dinossauro)
            if selected_bg == "dungeon" and dungeon_deco_manager is not None:
                dungeon_deco_manager.draw_floor(screen, SCREEN_W, SCREEN_H)

            # Decorações do volcano (poças de lava, rochas, geiseres, ossos)
            if selected_bg == "volcano" and volcano_deco_manager is not None:
                volcano_deco_manager.draw_floor(screen, SCREEN_W, SCREEN_H)

            # Decorações do moon (óleo, rachaduras, rochas)
            if selected_bg == "moon" and moon_deco_manager is not None:
                moon_deco_manager.draw_floor(screen, SCREEN_W, SCREEN_H)

            # Culling: só blita sprites visíveis na tela
            _scr_rect = screen.get_rect()
            screen.blits([(s.image, s.rect) for s in puddles if _scr_rect.colliderect(s.rect)])
            doom_seals.draw(screen)
            screen.blits([(s.image, s.rect) for s in obstacles if _scr_rect.colliderect(s.rect)])
            screen.blits([(s.image, s.rect) for s in gems if _scr_rect.colliderect(s.rect)])
            screen.blits([(s.image, s.rect) for s in drops if _scr_rect.colliderect(s.rect)])
            screen.blits([(s.image, s.rect) for s in projectiles if _scr_rect.colliderect(s.rect)])
            screen.blits([(s.image, s.rect) for s in enemy_projectiles if _scr_rect.colliderect(s.rect)])
            screen.blits([(e.image, e.rect) for e in enemies if _scr_rect.colliderect(e.rect)])
            screen.blits([(d.image, d.rect) for d in death_anims if _scr_rect.colliderect(d.rect)])

            for e in enemies:
                if not _scr_rect.colliderect(e.rect):
                    continue
                if e.hp < e.max_hp or e.kind in ["boss", "mini_boss", "agis", "elite", "orc"]:
                    if e.kind == "boss":
                        bar_w, bar_h = 120, 10
                    elif e.kind in ("mini_boss", "agis"):
                        bar_w, bar_h = 110, 10
                    elif e.kind in ("elite", "orc"):
                        bar_w, bar_h = 60, 6
                    else:
                        bar_w, bar_h = 40, 6
                    bar_x = e.rect.centerx - bar_w // 2
                    bar_y = e.rect.top - 15
                    pygame.draw.rect(screen, (200, 0, 0), (bar_x, bar_y, bar_w, bar_h))
                    ratio = max(0, e.hp / e.max_hp)
                    if e.kind == "agis":
                        bar_color = (180, 0, 255)
                    elif e.kind == "mini_boss":
                        bar_color = (255, 140, 0)
                    else:
                        bar_color = (0, 255, 0)
                    pygame.draw.rect(screen, bar_color, (bar_x, bar_y, int(bar_w * ratio), bar_h))
                    pygame.draw.rect(screen, (0, 0, 0), (bar_x, bar_y, bar_w, bar_h), 1)

            show_offscreen_arrows = settings["gameplay"].get("show_offscreen_arrows", "On") == "On"
            if show_offscreen_arrows:
                for e in enemies:
                    if e.kind not in ("boss", "mini_boss", "agis") or screen.get_rect().colliderect(e.rect):
                        continue
                    center = pygame.Vector2(SCREEN_W//2, SCREEN_H//2)
                    target = pygame.Vector2(e.rect.center)
                    direction = target - center
                    if direction.length() > 0: direction = direction.normalize()
                    margin = 40
                    arrow_pos = center + direction * (min(SCREEN_W, SCREEN_H)//2 - margin)
                    arrow_pos.x = max(margin, min(SCREEN_W - margin, arrow_pos.x))
                    arrow_pos.y = max(margin, min(SCREEN_H - margin, arrow_pos.y))
                    angle = math.atan2(direction.y, direction.x)
                    p1 = arrow_pos + pygame.Vector2(math.cos(angle), math.sin(angle)) * 20
                    p2 = arrow_pos + pygame.Vector2(math.cos(angle + 2.5), math.sin(angle + 2.5)) * 15
                    p3 = arrow_pos + pygame.Vector2(math.cos(angle - 2.5), math.sin(angle - 2.5)) * 15
                    pygame.draw.polygon(screen, (255, 0, 0), [p1, p2, p3])
                        
            if show_offscreen_arrows:
                for d in drops:
                    if d.kind != "chest" or screen.get_rect().colliderect(d.rect):
                        continue
                    center = pygame.Vector2(SCREEN_W//2, SCREEN_H//2)
                    target = pygame.Vector2(d.rect.center)
                    direction = target - center
                    if direction.length() > 0: direction = direction.normalize()
                    margin = 40
                    arrow_pos = center + direction * (min(SCREEN_W, SCREEN_H)//2 - margin)
                    arrow_pos.x = max(margin, min(SCREEN_W - margin, arrow_pos.x))
                    arrow_pos.y = max(margin, min(SCREEN_H - margin, arrow_pos.y))
                    angle = math.atan2(direction.y, direction.x)
                    p1 = arrow_pos + pygame.Vector2(math.cos(angle), math.sin(angle)) * 20
                    p2 = arrow_pos + pygame.Vector2(math.cos(angle + 2.5), math.sin(angle + 2.5)) * 15
                    p3 = arrow_pos + pygame.Vector2(math.cos(angle - 2.5), math.sin(angle - 2.5)) * 15
                    pygame.draw.polygon(screen, (255, 215, 0), [p1, p2, p3])

            screen.blits([(p.image, p.rect) for p in particles if _scr_rect.colliderect(p.rect)])
            damage_texts.draw(screen)

            if 'darkness_timer' in locals() and darkness_timer > 0:
                _ds_key = (SCREEN_W, SCREEN_H)
                if not hasattr(main, "_dark_surf_cache") or main._dark_surf_cache[0] != _ds_key:
                    _ds = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
                    _ds.fill((0, 0, 0, 230))
                    pygame.draw.circle(_ds, (0, 0, 0, 0), (SCREEN_W//2, SCREEN_H//2), 250)
                    main._dark_surf_cache = (_ds_key, _ds)
                screen.blit(main._dark_surf_cache[1], (0, 0))
            
            if ORB_COUNT > 0:
                if not hasattr(main, "_orb_img_cache") or main._orb_img_cache[0] != has_serras:
                    main._orb_img_cache = (has_serras, pygame.transform.scale(orb_img, (80, 80)) if has_serras else orb_img)
                _orb_img = main._orb_img_cache[1]
                _orb_blits = []
                for i in range(ORB_COUNT):
                    rad = math.radians(orb_rot_angle + i * (360/ORB_COUNT))
                    orb_p = player.pos + pygame.Vector2(math.cos(rad), math.sin(rad)) * ORB_DISTANCE
                    _orb_blits.append((_orb_img, _orb_img.get_rect(center=orb_p + cam)))
                screen.blits(_orb_blits)

            if player.ult_active:
                _ult_frame = player.get_ult_anim_frame() if hasattr(player, 'get_ult_anim_frame') else None
                if _ult_frame is not None:
                    # Exibe no tamanho carregado, centralizado no jogador
                    screen.blit(_ult_frame, _ult_frame.get_rect(center=(SCREEN_W // 2, SCREEN_H // 2)))
                elif player.should_draw_tornado_effect():
                    if _tornado_rot_cache:
                        img = _tornado_rot_cache[int(pygame.time.get_ticks() / 25) % _TORNADO_STEPS]
                    else:
                        img = pygame.transform.rotate(tornado_img, (pygame.time.get_ticks() / 5) % 360)
                    screen.blit(img, img.get_rect(center=(SCREEN_W//2, SCREEN_H//2)), special_flags=pygame.BLEND_RGBA_ADD)

            for exp in active_explosions:
                exp.draw(screen, cam)

            screen.blit(player.image, player.rect)

            if state == "UPGRADE":
                overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA); overlay.fill((0,0,0,180)); screen.blit(overlay, (0,0))
                msg = font_l.render("NOVO NÍVEL!", True, (255,215,0))
                msg_sh = font_l.render("NOVO NÍVEL!", True, (80,40,0))
                msg_x = SCREEN_W//2 - msg.get_width()//2
                msg_y = int(SCREEN_H*0.08)
                screen.blit(msg_sh, (msg_x + 3, msg_y + 3))
                screen.blit(msg, (msg_x, msg_y))
                up_options = []
                CARD_W, CARD_H = 560, 108
                _card_gap = 12
                _total_cards_h = len(up_keys) * (CARD_H + _card_gap) - _card_gap
                _start_y = max(110, (SCREEN_H - _total_cards_h) // 2 + 20)
                for i, key in enumerate(up_keys):
                    y_pos = _start_y + i * (CARD_H + _card_gap)
                    rect = pygame.Rect(SCREEN_W//2 - CARD_W//2, y_pos, CARD_W, CARD_H)
                    up_options.append(rect)
                    rarity_name, rarity_data = up_rarities[i]
                    hovered = rect.collidepoint(m_pos)

                    # Sprite base (skills.png carta medieval, cicla entre os 3 sprites disponíveis)
                    if skill_card_sprites:
                        _si = i % len(skill_card_sprites)
                        spr = skill_card_sprites_hover[_si] if hovered else skill_card_sprites[_si]
                        screen.blit(spr, rect.topleft)
                    else:
                        pygame.draw.rect(screen, (30,30,40), rect, border_radius=10)

                    # Borda colorida pela raridade (cached por cor+tamanho para evitar Surface por frame)
                    if not hasattr(main, "_border_surf_cache"):
                        main._border_surf_cache = {}
                    _border_key = (tuple(rarity_data["color"][:3]), CARD_W, CARD_H)
                    if _border_key not in main._border_surf_cache:
                        _bs = pygame.Surface((CARD_W, CARD_H), pygame.SRCALPHA)
                        r, g, b = _border_key[0]
                        pygame.draw.rect(_bs, (r, g, b, 55),  _bs.get_rect(), border_radius=9)
                        pygame.draw.rect(_bs, (r, g, b, 200), _bs.get_rect(), 3, border_radius=9)
                        main._border_surf_cache[_border_key] = _bs
                    screen.blit(main._border_surf_cache[_border_key], rect.topleft)

                    # Ícone do upgrade
                    icon = upg_images.get(key, loader.load_image("icon_default", (64, 64)))
                    screen.blit(icon, (rect.x + 14, rect.centery - 28))

                    # Cores de texto estilo pergaminho medieval
                    txt_col    = (255, 215, 100) if hovered else (220, 190, 120)
                    shadow_col = (80,  40,  0)   if hovered else (60,  30,  0)
                    desc_col   = (215, 190, 130) if hovered else (180, 158, 100)

                    # Nome do upgrade
                    title_surf = font_m.render(key, True, txt_col)
                    title_sh   = font_m.render(key, True, shadow_col)
                    tx, ty = rect.x + 90, rect.y + 10
                    screen.blit(title_sh, (tx + 2, ty + 2))
                    screen.blit(title_surf, (tx, ty))

                    # Descrição
                    desc_surf = font_s.render(get_upgrade_description(key), True, desc_col)
                    screen.blit(desc_surf, (rect.x + 90, rect.y + 52))

                    # Badge de raridade (canto superior direito)
                    rarity_txt = font_s.render(rarity_name, True, rarity_data["color"])
                    screen.blit(rarity_txt, (rect.right - rarity_txt.get_width() - 14, rect.y + 10))

                    # Número de atalho (1–5)
                    shortcut = font_s.render(str(i + 1), True, (180, 180, 180))
                    screen.blit(shortcut, (rect.x + 14, rect.y + 10))


            if state == "CHEST_UI":
                overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA); overlay.fill((0,0,0,200)); screen.blit(overlay, (0,0))
                box_w, box_h = 700, 100 + len(chest_loot) * 80
                box_rect = pygame.Rect(SCREEN_W/2 - box_w/2, SCREEN_H/2 - box_h/2, box_w, box_h)
                pygame.draw.rect(screen, (50, 40, 30), box_rect, border_radius=15)
                pygame.draw.rect(screen, (255, 215, 0), box_rect, 3, border_radius=15)
                title = font_l.render("BAÚ DE TESOUROS!", True, (255, 215, 0))
                screen.blit(title, title.get_rect(center=(SCREEN_W//2, box_rect.top - 60)))

                for i, loot in enumerate(chest_loot):
                    base_y = box_rect.y + 60 + i * 80
                    icon_size = 64
                    padding_left = 40
                    icon_x = box_rect.left + padding_left + icon_size // 2
                    text_x = box_rect.left + padding_left + icon_size + 25

                    if loot in upg_images:
                        icon = upg_images[loot]
                        icon_rect = icon.get_rect(center=(icon_x, base_y))
                        screen.blit(icon, icon_rect)

                    text_color = (255, 100, 255) if loot in EVOLUTIONS else (255, 255, 255)
                    desc = get_upgrade_description(loot)
                        
                    txt = font_s.render(f"+ {loot} {('- ' + desc) if desc else ''}", True, text_color)
                    screen.blit(txt, (text_x, base_y - txt.get_height() // 2))
                        
                auto_txt = font_s.render("RECOMPENSA(S) APLICADA(S) AUTOMATICAMENTE", True, (150, 150, 150))
                screen.blit(auto_txt, auto_txt.get_rect(center=(SCREEN_W//2, box_rect.bottom + 40)))

                timer_txt = font_s.render(f"Voltando em {max(0, chest_ui_timer):.1f}s...", True, (120, 120, 120))
                auto_apply = settings["gameplay"].get("auto_apply_chest_reward", "On") == "On"
                if auto_apply:
                    screen.blit(timer_txt, timer_txt.get_rect(center=(SCREEN_W//2, box_rect.bottom + 75)))
                else:
                    click_txt = font_s.render("CLIQUE EM UMA OPÇÃO PARA APLICAR", True, (255, 220, 120))
                    screen.blit(click_txt, click_txt.get_rect(center=(SCREEN_W//2, box_rect.bottom + 75)))

            if show_reward_dialog:
                if not hasattr(main, "_rrd_ov"): main._rrd_ov = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
                main._rrd_ov.fill((0, 0, 0, 190))
                screen.blit(main._rrd_ov, (0, 0))
                _rrd_w = 460; _rrd_h = 210
                _rrd_x = SCREEN_W // 2 - _rrd_w // 2; _rrd_y = SCREEN_H // 2 - _rrd_h // 2
                pygame.draw.rect(screen, (28, 20, 12), (_rrd_x, _rrd_y, _rrd_w, _rrd_h), border_radius=14)
                pygame.draw.rect(screen, (200, 160, 50), (_rrd_x, _rrd_y, _rrd_w, _rrd_h), 3, border_radius=14)
                _rrd_title = font_l.render("AGIS DERROTADO!", True, (255, 215, 0))
                screen.blit(_rrd_title, _rrd_title.get_rect(centerx=SCREEN_W // 2, top=_rrd_y + 18))
                _rrd_sub = font_s.render("Entrar na Sala de Recompensas?", True, (220, 200, 160))
                screen.blit(_rrd_sub, _rrd_sub.get_rect(centerx=SCREEN_W // 2, top=_rrd_y + 72))
                _rrd_sim = pygame.Rect(_rrd_x + 40,  _rrd_y + 140, 160, 48)
                _rrd_nao = pygame.Rect(_rrd_x + 260, _rrd_y + 140, 160, 48)
                for _rb, _rl, _rc in [(_rrd_sim, "SIM", (40, 120, 40)), (_rrd_nao, "NÃO", (120, 40, 40))]:
                    _rhov = _rb.collidepoint(m_pos)
                    _rfc = tuple(min(255, c + 35) for c in _rc) if _rhov else _rc
                    pygame.draw.rect(screen, _rfc, _rb, border_radius=8)
                    pygame.draw.rect(screen, (200, 170, 60), _rb, 2, border_radius=8)
                    _rls = font_m.render(_rl, True, (240, 230, 200))
                    screen.blit(_rls, _rls.get_rect(center=_rb.center))

            if show_stage_victory:
                if not hasattr(main, "_svo"): main._svo = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
                main._svo.fill((0, 0, 0, 200))
                screen.blit(main._svo, (0, 0))
                _sv_bw, _sv_bh = 420, 320
                _sv_bx = SCREEN_W // 2 - _sv_bw // 2
                _sv_by = SCREEN_H // 2 - _sv_bh // 2
                pygame.draw.rect(screen, (30, 20, 10), (_sv_bx, _sv_by, _sv_bw, _sv_bh), border_radius=14)
                pygame.draw.rect(screen, (200, 160, 50), (_sv_bx, _sv_by, _sv_bw, _sv_bh), 3, border_radius=14)
                _sv_title = font_l.render("AGIS DERROTADO!", True, (255, 215, 0))
                screen.blit(_sv_title, _sv_title.get_rect(centerx=SCREEN_W // 2, top=_sv_by + 18))
                _sv_sub = font_s.render(f"Fase {current_hardcore_stage} / 10 — Modo Hardcore", True, (200, 160, 100))
                screen.blit(_sv_sub, _sv_sub.get_rect(centerx=SCREEN_W // 2, top=_sv_by + 60))
                _sv_btn_w, _sv_btn_h = 340, 48
                _sv_btn_x = SCREEN_W // 2 - _sv_btn_w // 2
                _sv_btns = [
                    (_sv_btn_x, _sv_by + 120, _sv_btn_w, _sv_btn_h, "Continuar na fase atual", (60, 180, 60), "continue"),
                    (_sv_btn_x, _sv_by + 182, _sv_btn_w, _sv_btn_h, "Proximo Nivel", (60, 120, 200), "next"),
                    (_sv_btn_x, _sv_by + 244, _sv_btn_w, _sv_btn_h, "Ir para ROOM", (160, 80, 60), "hub"),
                ]
                if not hasattr(main, "_sv_btns_rects"): main._sv_btns_rects = []
                main._sv_btns_rects = []
                for _bx2, _by2, _bw2, _bh2, _blbl, _bcol, _bact in _sv_btns:
                    _br = pygame.Rect(_bx2, _by2, _bw2, _bh2)
                    main._sv_btns_rects.append((_br, _bact))
                    _bhov = _br.collidepoint(m_pos)
                    _bfill = tuple(min(255, c + 40) for c in _bcol) if _bhov else _bcol
                    pygame.draw.rect(screen, _bfill, _br, border_radius=8)
                    pygame.draw.rect(screen, (220, 190, 80), _br, 2, border_radius=8)
                    _bsurf = font_s.render(_blbl, True, (240, 230, 200))
                    screen.blit(_bsurf, _bsurf.get_rect(center=_br.center))
                if current_hardcore_stage >= 10:
                    _sv_max = font_s.render("Parabens! Todas as fases concluidas!", True, (255, 215, 0))
                    screen.blit(_sv_max, _sv_max.get_rect(centerx=SCREEN_W // 2, bottom=_sv_by + _sv_bh - 12))

            if state == "PAUSED":
                overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
                overlay.fill((UI_THEME["void_black"][0], UI_THEME["void_black"][1], UI_THEME["void_black"][2], 195))
                screen.blit(overlay, (0, 0))
                    
                msg = font_l.render("JOGO PAUSADO", True, UI_THEME["old_gold"])
                screen.blit(msg, (SCREEN_W//2 - msg.get_width()//2, SCREEN_H * 0.15))
                    
                panel_w, panel_h = 450, 660
                panel_x = int(SCREEN_W * 0.15)
                panel_y = int(SCREEN_H * 0.22)
                panel_rect = pygame.Rect(panel_x, panel_y, panel_w, panel_h)

                draw_dark_panel(screen, panel_rect, alpha=190, border_color=UI_THEME["old_gold"])

                stat_title = font_m.render("STATUS DO HEROI", True, UI_THEME["old_gold"])
                screen.blit(stat_title, stat_title.get_rect(center=(panel_rect.centerx, panel_rect.y + 30)))

                stats_lines = [
                        f"VIDA MÁXIMA: {int(PLAYER_MAX_HP)}",
                        f"VELOCIDADE: {int(PLAYER_SPEED)}",
                        f"DANO BASE: {PROJECTILE_DMG}",
                        f"CRÍTICO: {int(CRIT_CHANCE*100)}%",
                        f"PROJÉTEIS (QTD): {PROJ_COUNT}",
                        f"PERFURAÇÃO: {PROJ_PIERCE}",
                        f"RECARGA: {SHOT_COOLDOWN:.2f}s",
                        f"RAIO EXPLOSÃO: {EXPLOSION_RADIUS}",
                        f"ORBES: {ORB_COUNT}",
                        f"ALCANCE (ÍMÃ): {int(PICKUP_RANGE)}"
                    ]

                start_y = panel_rect.y + 70
                for idx, line in enumerate(stats_lines):
                        line_txt = font_s.render(line, True, UI_THEME["mist"])
                        screen.blit(line_txt, (panel_rect.x + 30, start_y + (idx * 35)))

                # ── Seção de equipamentos ──────────────────────────────────────
                _p_eq_sep_y = start_y + len(stats_lines) * 35 + 10
                pygame.draw.line(screen, UI_THEME.get("faded_gold", (120,95,40)),
                                 (panel_rect.x + 20, _p_eq_sep_y),
                                 (panel_rect.x + panel_w - 20, _p_eq_sep_y), 1)
                _p_eq_sep_y += 8
                _p_eq_title = font_s.render("EQUIPAMENTO", True, UI_THEME["old_gold"])
                screen.blit(_p_eq_title, _p_eq_title.get_rect(
                    center=(panel_rect.centerx, _p_eq_sep_y + _p_eq_title.get_height()//2)))
                _p_eq_sep_y += _p_eq_title.get_height() + 6

                _p_cid  = player.char_id if player else 0
                _p_ceq  = save_data.get("char_equipped", {}).get(str(_p_cid), {})
                _p_eqw  = _p_ceq.get("weapon")
                _p_eqs  = _p_ceq.get("shield")
                _p_watk = ITEM_SHOP_STATS.get(_p_eqw["category"],[{}]*(_p_eqw["idx"]+1))[_p_eqw["idx"]].get("atk",0) if _p_eqw else 0
                _p_wnam = ITEM_SHOP_STATS.get(_p_eqw["category"],[{}]*(_p_eqw["idx"]+1))[_p_eqw["idx"]].get("name","") if _p_eqw else ""
                _p_sdef = ITEM_SHOP_STATS.get(_p_eqs["category"],[{}]*(_p_eqs["idx"]+1))[_p_eqs["idx"]].get("def",0) if _p_eqs else 0
                _p_snam = ITEM_SHOP_STATS.get(_p_eqs["category"],[{}]*(_p_eqs["idx"]+1))[_p_eqs["idx"]].get("name","") if _p_eqs else ""
                _p_eq_lines = [
                    ("Arma",    _p_wnam if _p_wnam else "Sem arma",  f"+{_p_watk} ATQ" if _p_watk else ""),
                    ("Escudo",  _p_snam if _p_snam else "Sem escudo", f"+{_p_sdef} DEF" if _p_sdef else ""),
                ]
                for _lbl, _nm, _bonus in _p_eq_lines:
                    _lbl_s = font_s.render(_lbl + ":", True, (160, 140, 80))
                    screen.blit(_lbl_s, (panel_rect.x + 30, _p_eq_sep_y))
                    _nm_col = (220, 200, 140) if _nm != "Sem arma" and _nm != "Sem escudo" else (90, 80, 60)
                    _nm_s = font_s.render(_nm[:22], True, _nm_col)
                    screen.blit(_nm_s, (panel_rect.x + 110, _p_eq_sep_y))
                    if _bonus:
                        _bon_s = font_s.render(_bonus, True, (100, 220, 100))
                        screen.blit(_bon_s, (panel_rect.x + panel_w - 20 - _bon_s.get_width(), _p_eq_sep_y))
                    _p_eq_sep_y += 30

                for b in pause_btns: 
                        b.check_hover(m_pos, snd_hover)
                        b.draw(screen)
                for b in pause_save_btns:
                    b.check_hover(m_pos, snd_hover)
                    b.draw(screen)
                if pause_save_feedback_timer > 0:
                    saved_txt = font_s.render("SLOT SALVO COM SUCESSO", True, (120, 255, 120))
                    saved_rect = saved_txt.get_rect(center=(int(SCREEN_W * 0.70), int(SCREEN_H * 0.76)))
                    screen.blit(saved_txt, saved_rect)

            if state == "GAME_OVER":
                # Full dark vignette
                overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
                overlay.fill((6, 4, 6, 215))
                screen.blit(overlay, (0, 0))

                panel_w, panel_h = 960, 460
                go_panel = pygame.Rect(SCREEN_W // 2 - panel_w // 2, SCREEN_H // 2 - panel_h // 2 - 30, panel_w, panel_h)
                draw_dark_panel(screen, go_panel, alpha=220, border_color=UI_THEME["blood_red"])

                # Pulsing "GAME OVER" title
                _go_pulse = int(135 + 120 * math.sin(pygame.time.get_ticks() / 280.0))
                go_color = (_go_pulse, 0, 0)
                msg = font_l.render("GAME OVER", True, go_color)
                msg_rect = msg.get_rect(center=(SCREEN_W // 2, go_panel.top + 58))
                # Red glow behind text
                glow_s = pygame.Surface((msg.get_width() + 60, msg.get_height() + 30), pygame.SRCALPHA)
                glow_s.fill((160, 0, 0, int(60 + 40 * math.sin(pygame.time.get_ticks() / 280.0))))
                screen.blit(glow_s, glow_s.get_rect(center=msg_rect.center))
                screen.blit(msg, msg_rect)

                # Separator after title
                sep_y = go_panel.top + 100
                pygame.draw.line(screen, UI_THEME["blood_red"],
                                 (go_panel.left + 30, sep_y), (go_panel.right - 30, sep_y), 1)

                # ── Stats grid: two columns ──────────────────────────────────────
                _go_min = int(game_time // 60)
                _go_sec = int(game_time % 60)
                left_stats = [
                    ("TEMPO SOBREVIVIDO", f"{_go_min:02}:{_go_sec:02}", UI_THEME["old_gold"]),
                    ("INIMIGOS ELIMINADOS", str(kills),                  UI_THEME["blood_red"]),
                    ("OURO COLETADO",       str(int(run_gold_collected)), UI_THEME["faded_gold"]),
                ]
                right_stats = [
                    ("NÍVEL ATINGIDO", str(level),      UI_THEME["mana_blue"]),
                    ("XP TOTAL",       str(int(xp)),    (180, 255, 180)),
                    ("UPGRADES PEGOS", str(len(player_upgrades)), UI_THEME["mist"]),
                ]
                col_left_x  = go_panel.left + panel_w // 4
                col_right_x = go_panel.left + panel_w * 3 // 4
                row_start_y = sep_y + 28
                row_h = 72

                for col_x, stat_list in ((col_left_x, left_stats), (col_right_x, right_stats)):
                    for ri, (lbl, val, col) in enumerate(stat_list):
                        by = row_start_y + ri * row_h
                        row_rect = pygame.Rect(col_x - 190, by, 380, 58)
                        pygame.draw.rect(screen, (22, 10, 12, 180), row_rect, border_radius=8)
                        pygame.draw.rect(screen, UI_THEME["charcoal"], row_rect, 1, border_radius=8)
                        lbl_surf = font_s.render(lbl, True, UI_THEME["mist"])
                        val_surf = font_m.render(val, True, col)
                        screen.blit(lbl_surf, lbl_surf.get_rect(midleft=(row_rect.left + 14, row_rect.centery - 10)))
                        screen.blit(val_surf, val_surf.get_rect(midright=(row_rect.right - 14, row_rect.centery + 10)))

                # Vertical divider between columns
                div_x = SCREEN_W // 2
                pygame.draw.line(screen, UI_THEME["iron"],
                                 (div_x, sep_y + 6), (div_x, go_panel.bottom - 110), 1)

                # ── Achievements unlocked ────────────────────────────────────────
                if new_unlocks_this_session:
                    ach_y = go_panel.bottom - 100
                    pygame.draw.line(screen, (40, 100, 40),
                                     (go_panel.left + 30, ach_y - 6), (go_panel.right - 30, ach_y - 6), 1)
                    ul_title = font_s.render("★  NOVAS CONQUISTAS  ★", True, (80, 255, 120))
                    screen.blit(ul_title, ul_title.get_rect(center=(SCREEN_W // 2, ach_y + 10)))
                    names_str = "  ·  ".join(new_unlocks_this_session[:4])
                    names_surf = font_s.render(names_str, True, (180, 255, 180))
                    screen.blit(names_surf, names_surf.get_rect(center=(SCREEN_W // 2, ach_y + 36)))

                game_over_btn.check_hover(m_pos, snd_hover)
                game_over_btn.draw(screen)

        ui_multiplier = max(0.6, min(1.0, settings["accessibility"].get("ui_size", 100) / 100.0))
        hud_scale = 0.6 * ui_multiplier
        high_contrast = settings["accessibility"].get("high_contrast", "Off") == "On"

        # A interface é desenhada por último para garantir a sobreposição total
        # sobre cenário, partículas, inimigos e demais sprites.
        draw_ui(
            screen,
            player,
            state,
            font_s,
            font_m,
            font_l,
            hud_scale,
            high_contrast,
            level,
            xp,
            current_xp_to_level,
            game_time,
            kills,
            dt,
        )

        PERF.end_frame()

        if debug_overlay_on:
            _draw_debug_overlay(screen, font_s, clock)

        draw_state_transition_overlay(screen, transition_timer)

        # ── Overlay de Perfil/Conquistas no Hub / Mercado (tecla L) ──────────
        if state in ("HUB", "MARKET") and hub_profile_open:
            _draw_profile_viewer(screen, font_s, font_m, font_l, m_pos)

        # ── Minicard de perfil no canto superior-esquerdo (HUB / Mercado) ─
        if state in ("HUB", "MARKET") and not hub_profile_open:
            _hub_profile_widget_rect = _draw_profile_widget(screen, font_s, font_m, m_pos, align_right=False)
        else:
            _hub_profile_widget_rect = None

        # ── Indicador de autosave ─────────────────────────────────────────
        if autosave_feedback_timer > 0 and state in ("PLAYING", "PAUSED", "UPGRADE", "CHEST_UI", "REWARD_ROOM"):
            _as_alpha = min(255, int(255 * min(1.0, autosave_feedback_timer / 0.5)))
            _as_txt = font_s.render("JOGO SALVO", True, (120, 255, 120))
            _as_txt.set_alpha(_as_alpha)
            _as_x = SCREEN_W - _as_txt.get_width() - 14
            _as_y = SCREEN_H - _as_txt.get_height() - 14
            screen.blit(_as_txt, (_as_x, _as_y))

        # ── Toast de conquista desbloqueada ───────────────────────────────
        if _achievement_notifs:
            _achievement_notifs[0][1] -= dt
            if _achievement_notifs[0][1] <= 0:
                _achievement_notifs.pop(0)
            elif _achievement_notifs:
                _draw_achievement_toast(screen, _achievement_notifs[0][0], font_s, font_m)

        # Cursor personalizado — desenhado por último, sempre por cima de tudo
        if _dev_console_open or _dev_console_msg_timer > 0.0:
            _dc_h = 54 if _dev_console_open else 34
            _dc_rect = pygame.Rect(18, SCREEN_H - _dc_h - 18, SCREEN_W - 36, _dc_h)
            _dc_bg = pygame.Surface((_dc_rect.width, _dc_rect.height), pygame.SRCALPHA)
            _dc_bg.fill((8, 8, 8, 210))
            screen.blit(_dc_bg, _dc_rect.topleft)
            pygame.draw.rect(screen, (160, 140, 90), _dc_rect, 1, border_radius=6)

            if _dev_console_open:
                _cmd_lbl = font_s.render("Console > " + _dev_console_input, True, (220, 220, 220))
                screen.blit(_cmd_lbl, (_dc_rect.x + 10, _dc_rect.y + 8))
                _hint_lbl = font_s.render("Enter=executar  Esc=fechar", True, (140, 130, 110))
                screen.blit(_hint_lbl, (_dc_rect.x + 10, _dc_rect.y + 28))

            if _dev_console_msg_timer > 0.0 and _dev_console_msg:
                _msg_lbl = font_s.render(_dev_console_msg, True, (255, 215, 120))
                _msg_y = _dc_rect.y + (28 if _dev_console_open else 8)
                screen.blit(_msg_lbl, (_dc_rect.x + 280, _msg_y))

        if cursor_img is not None:
            mx, my = pygame.mouse.get_pos()
            screen.blit(cursor_img, (mx, my))

        pygame.display.flip()

    pygame.quit()

# --- Variáveis do Menu de Configurações ---
settings_category = "main"  # 'main', 'video', 'audio', 'controls', 'gameplay', 'accessibility'
temp_settings = {}
settings_control_waiting = None
settings_dragging_slider = None
settings_anim_prev_category = "main"
settings_anim_timer = 0.0
settings_anim_dir = 1

# --- Fontes temporárias para criação dos botões de configurações (fora do main) ---
# Esses botões são criados no escopo global; as fontes serão recriadas dentro do main().
_tmp_font_m = None  # Será inicializado após pygame.init() no main()
_tmp_font_s = None

# --- Funções do Menu de Configurações ---
def draw_settings_menu(screen, settings, temp_settings, category, m_pos, font_l, font_m, font_s, clock, dt):
    global settings_anim_prev_category, settings_anim_timer, settings_anim_dir

    draw_menu_background(screen, m_pos, dt)
    overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 180))
    screen.blit(overlay, (0, 0))

    category_order = ["main", "video", "audio", "controls", "gameplay", "accessibility"]
    prev_category = settings_anim_prev_category
    if category != settings_anim_prev_category:
        try:
            prev_idx = category_order.index(settings_anim_prev_category)
            new_idx = category_order.index(category)
            settings_anim_dir = 1 if new_idx >= prev_idx else -1
        except ValueError:
            settings_anim_dir = 1
        settings_anim_prev_category = category
        settings_anim_timer = 0.22
    settings_anim_timer = max(0.0, settings_anim_timer - dt)

    # ── Título "CONFIGURAÇÕES" com sprite config.png ──────────────────────
    _cfg_title_w = 420
    _cfg_title_h = 58
    _cfg_title_x = SCREEN_W // 2 - _cfg_title_w // 2
    _cfg_title_y = int(SCREEN_H * 0.1) - _cfg_title_h // 2
    if config_title_spr:
        screen.blit(config_title_spr, (_cfg_title_x, _cfg_title_y))
    else:
        draw_screen_title(screen, font_l, "CONFIGURAÇÕES", SCREEN_W // 2, int(SCREEN_H * 0.1))
    _title_surf = font_l.render("CONFIGURAÇÕES", True, UI_THEME["old_gold"])
    _title_sh   = font_l.render("CONFIGURAÇÕES", True, (30, 15, 0))
    _title_rect = _title_surf.get_rect(center=(SCREEN_W // 2, int(SCREEN_H * 0.1)))
    screen.blit(_title_sh,   (_title_rect.x + 2, _title_rect.y + 2))
    screen.blit(_title_surf, _title_rect)

    # ── Subtítulo (seção atual) com barra menor de config.png ─────────────
    category_labels = {
        "main": "SEÇÕES",
        "video": "VIDEO",
        "audio": "AUDIO",
        "controls": "CONTROLES",
        "gameplay": "GAMEPLAY",
        "accessibility": "ACESSIBILIDADE",
    }
    _tag_w = 280
    _tag_h = 36
    _tag_x = SCREEN_W // 2 - _tag_w // 2
    _tag_y = int(SCREEN_H * 0.145)
    ratio = settings_anim_timer / 0.22 if settings_anim_timer > 0 else 0.0
    ratio_eased = ratio ** 3
    tag_offset = int(settings_anim_dir * 170 * ratio_eased)
    if config_tag_spr:
        screen.blit(config_tag_spr, (_tag_x, _tag_y))
    else:
        tag_panel = pygame.Rect(_tag_x, _tag_y, _tag_w, _tag_h)
        draw_dark_panel(screen, tag_panel, alpha=150, border_color=UI_THEME["iron"])
    tag_text = font_s.render(category_labels.get(category, "SEÇÕES"), True, UI_THEME["old_gold"])
    tag_sh   = font_s.render(category_labels.get(category, "SEÇÕES"), True, (30, 15, 0))
    _tag_cx  = SCREEN_W // 2 + tag_offset
    _tag_cy  = _tag_y + _tag_h // 2
    screen.blit(tag_sh,   tag_sh.get_rect(center=(_tag_cx + 1, _tag_cy + 1)))
    screen.blit(tag_text, tag_text.get_rect(center=(_tag_cx, _tag_cy)))

    version_text = font_s.render(f"v1.1.0", True, (200, 200, 200))
    screen.blit(version_text, (20, 20))

    fps_text = font_s.render(f"FPS: {int(clock.get_fps())}", True, (200, 200, 200))
    screen.blit(fps_text, fps_text.get_rect(topright=(SCREEN_W - 20, 20)))

    # Slide do conteúdo interno das abas (entrada + saída) com easing cúbico e fade.
    slide_dist = 220
    incoming_offset = int(settings_anim_dir * slide_dist * ratio_eased)
    incoming_layer = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
    incoming_mouse = (m_pos[0] - incoming_offset, m_pos[1])
    _draw_settings_category_content(incoming_layer, category, temp_settings, incoming_mouse, font_m, font_s)
    # Fade in the incoming layer (alpha grows as ratio drops 1→0)
    incoming_alpha = int(255 * (1.0 - ratio_eased))
    incoming_layer.set_alpha(incoming_alpha)

    if settings_anim_timer > 0 and prev_category != category:
        progress_eased = (1.0 - ratio) ** 3  # ease-in exit (slow start, fast departure)
        outgoing_offset = int(-settings_anim_dir * slide_dist * progress_eased)
        outgoing_layer = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        outgoing_mouse = (m_pos[0] - outgoing_offset, m_pos[1])
        _draw_settings_category_content(outgoing_layer, prev_category, temp_settings, outgoing_mouse, font_m, font_s)
        outgoing_layer.set_alpha(int(255 * ratio_eased))  # fade out as animation progresses
        screen.blit(outgoing_layer, (outgoing_offset, 0))

    screen.blit(incoming_layer, (incoming_offset, 0))

    # Botões de Ação
    for btn in settings_action_btns.values():
        btn.check_hover(m_pos, snd_hover)
        btn.draw(screen)


def _draw_settings_category_content(surface, category, temp_settings, m_pos, font_m, font_s):
    if category == "main":
        draw_main_settings(surface, m_pos, font_m)
    elif category == "video":
        draw_video_settings(surface, temp_settings, m_pos, font_m, font_s)
    elif category == "audio":
        draw_audio_settings(surface, temp_settings, m_pos, font_m, font_s)
    elif category == "controls":
        draw_controls_settings(surface, temp_settings, m_pos, font_m, font_s)
    elif category == "gameplay":
        draw_gameplay_settings(surface, temp_settings, m_pos, font_m, font_s)
    elif category == "accessibility":
        draw_accessibility_settings(surface, temp_settings, m_pos, font_m, font_s)

def draw_main_settings(screen, m_pos, font_m):
    for btn in settings_main_btns:
        btn.check_hover(m_pos, snd_hover)
        btn.draw(screen)

def draw_video_settings(screen, temp_settings, m_pos, font_m, font_s):
    available_resolutions = _get_available_resolutions()
    current_res = str(temp_settings["video"].get("resolution", ""))
    if current_res not in available_resolutions:
        temp_settings["video"]["resolution"] = "1920x1080" if "1920x1080" in available_resolutions else available_resolutions[-1]

    options = [
        ("Resolução", temp_settings["video"]["resolution"], available_resolutions),
        ("Tela cheia", temp_settings["video"]["fullscreen"], ["Off", "On"]),
        ("VSync", temp_settings["video"]["vsync"], ["Off", "On"]),
        ("Limite de FPS", str(temp_settings["video"]["fps_limit"]), ["30", "60", "120"]),
        ("Mostrar FPS", temp_settings["video"]["show_fps"], ["Off", "On"])
    ]

    for i, (label, value, _) in enumerate(options):
        y_pos = SCREEN_H * 0.25 + i * 70
        draw_setting_option(screen, y_pos, label, value, font_m, font_s, m_pos)

def draw_setting_option(screen, y_pos, label, value, font_m, font_s, m_pos):
    row_rect = pygame.Rect(int(SCREEN_W * 0.16), int(y_pos), int(SCREEN_W * 0.68), 54)
    pygame.draw.rect(screen, (18, 14, 10, 210), row_rect, border_radius=3)
    pygame.draw.rect(screen, UI_THEME["iron"], row_rect, 1, border_radius=3)

    label_text = font_m.render(label, True, UI_THEME["parchment"])
    label_rect = label_text.get_rect(midleft=(row_rect.x + 20, row_rect.centery))
    screen.blit(label_text, label_rect)

    value_rect = pygame.Rect(row_rect.right - 280, row_rect.y + 5, 260, row_rect.height - 10)
    is_hovered = value_rect.collidepoint(m_pos)

    vbg = (50, 38, 22) if is_hovered else (30, 23, 15)
    vborder = UI_THEME["old_gold"] if is_hovered else UI_THEME["iron"]
    pygame.draw.rect(screen, vbg, value_rect, border_radius=3)
    pygame.draw.rect(screen, vborder, value_rect, 1, border_radius=3)

    value_text = font_s.render(f"< {value} >", True, UI_THEME["faded_gold"])
    screen.blit(value_text, value_text.get_rect(center=value_rect.center))

    return value_rect

def draw_audio_settings(screen, temp_settings, m_pos, font_m, font_s):
    options = [
        ("Música", temp_settings["audio"]["music"], range(0, 101, 10)),
        ("SFX", temp_settings["audio"]["sfx"], range(0, 101, 10)),
        ("Mudo", temp_settings["audio"]["mute"], ["Off", "On"])
    ]

    for i, (label, value, _) in enumerate(options):
        y_pos = SCREEN_H * 0.25 + i * 70
        # Para os sliders de volume, o valor é um número, então tratamos de forma diferente
        if label in ["Música", "SFX"]:
            draw_slider_option(screen, y_pos, label, value, font_m, font_s, m_pos)
        else:
            draw_setting_option(screen, y_pos, label, value, font_m, font_s, m_pos)

def draw_slider_option(screen, y_pos, label, value, font_m, font_s, m_pos):
    row_rect = pygame.Rect(int(SCREEN_W * 0.16), int(y_pos), int(SCREEN_W * 0.68), 54)
    pygame.draw.rect(screen, (18, 14, 10, 210), row_rect, border_radius=3)
    pygame.draw.rect(screen, UI_THEME["iron"], row_rect, 1, border_radius=3)

    label_text = font_m.render(label, True, UI_THEME["parchment"])
    label_rect = label_text.get_rect(midleft=(row_rect.x + 20, row_rect.centery))
    screen.blit(label_text, label_rect)

    slider_rect = pygame.Rect(row_rect.right - 340, row_rect.y + 18, 240, 18)
    # Engraved trough
    pygame.draw.rect(screen, (14, 10, 8), slider_rect, border_radius=2)
    pygame.draw.rect(screen, UI_THEME["iron"], slider_rect, 1, border_radius=2)

    handle_pos = slider_rect.x + int((value / 100) * slider_rect.width)
    fill_rect = pygame.Rect(slider_rect.x, slider_rect.y, max(0, handle_pos - slider_rect.x), slider_rect.height)
    pygame.draw.rect(screen, UI_THEME["old_gold"], fill_rect, border_radius=2)
    # Handle: small iron knob
    pygame.draw.rect(screen, UI_THEME["parchment"], (handle_pos - 5, slider_rect.y - 4, 10, slider_rect.height + 8), border_radius=2)
    pygame.draw.rect(screen, UI_THEME["iron"], (handle_pos - 5, slider_rect.y - 4, 10, slider_rect.height + 8), 1, border_radius=2)

    value_text = font_s.render(f"{value}%", True, UI_THEME["faded_gold"])
    value_rect = value_text.get_rect(midleft=(slider_rect.right + 14, slider_rect.centery))
    screen.blit(value_text, value_rect)

    return slider_rect



# --- Lógica de Desenho e Interação do Menu de Configurações ---

# (Esta seção será preenchida com a lógica de desenho e interação)

# interação para cada submenu de configurações)

# configurações)


# --- Criação dos Botões do Menu de Configurações ---
# Os botões são inicializados em init_settings_buttons(), chamado dentro do main()
settings_main_btns = []
settings_action_btns = {}

def init_settings_buttons(font_m):
    """Inicializa os botões do menu de configurações. Deve ser chamado após pygame.init()."""
    global settings_main_btns, settings_action_btns
    _labels = ["Vídeo", "Áudio", "Controles", "Gameplay", "Acessibilidade"]
    settings_main_btns = [
        Button(0.5, 0.3 + i * 0.1, BTN_W, BTN_H, lbl, font_m)
        for i, lbl in enumerate(_labels)
    ]
    for i, btn in enumerate(settings_main_btns):
        btn.sprite_idx = i

    settings_action_btns = {
        "apply":   Button(0.25, 0.92, BTN_SM_W, BTN_SM_H, "Aplicar",          font_m, color=(40, 100, 40)),
        "default": Button(0.5,  0.92, BTN_W,    BTN_SM_H, "Restaurar Padrão", font_m, color=(100, 100, 40)),
        "back":    Button(0.75, 0.92, BTN_SM_W, BTN_SM_H, "Voltar",           font_m, color=(100, 40, 40)),
    }
    settings_action_btns["apply"].sprite_idx   = 2
    settings_action_btns["default"].sprite_idx = 5
    settings_action_btns["back"].sprite_idx    = 6


def handle_settings_clicks(m_pos):
    global state, settings_category, temp_settings, settings

    if settings_category == "main":
        if settings_main_btns[0].check_hover(m_pos): settings_category = "video"; temp_settings = json.loads(json.dumps(settings))
        elif settings_main_btns[1].check_hover(m_pos): settings_category = "audio"; temp_settings = json.loads(json.dumps(settings))
        elif settings_main_btns[2].check_hover(m_pos): settings_category = "controls"; temp_settings = json.loads(json.dumps(settings))
        elif settings_main_btns[3].check_hover(m_pos): settings_category = "gameplay"; temp_settings = json.loads(json.dumps(settings))
        elif settings_main_btns[4].check_hover(m_pos): settings_category = "accessibility"; temp_settings = json.loads(json.dumps(settings))
        
        # O botão de voltar no menu principal de configurações retorna ao menu do jogo
        if settings_action_btns["back"].check_hover(m_pos):
            state = "MENU"

    else: # Estamos em um submenu
        # 1. Verificar botões de ação primeiro (Back, Apply, Default)
        # Usamos o evento MOUSEBUTTONDOWN processado no loop principal para evitar cliques múltiplos
        # Mas como handle_settings_clicks é chamado dentro de MOUSEBUTTONDOWN, podemos usar m_pos
        
        if settings_action_btns["back"].rect.collidepoint(m_pos):
            settings_category = "main"
            temp_settings = {}
            if snd_click: snd_click.play()
            return

        if settings_action_btns["apply"].rect.collidepoint(m_pos):
            settings = json.loads(json.dumps(temp_settings))
            save_settings(settings)
            apply_settings(settings)
            load_all_assets()
            settings_category = "main"
            if snd_click: snd_click.play()
            return

        if settings_action_btns["default"].rect.collidepoint(m_pos):
            default_settings = load_settings() 
            temp_settings[settings_category] = default_settings[settings_category]
            if snd_click: snd_click.play()
            return

        # 2. Se não clicou em ações, processar cliques específicos do submenu
        if settings_category == "video":
            handle_video_settings_clicks(m_pos)
        elif settings_category == "audio":
            handle_audio_settings_clicks(m_pos)
        elif settings_category == "controls":
            handle_controls_settings_clicks(m_pos)
        elif settings_category == "gameplay":
            handle_gameplay_settings_clicks(m_pos)
        elif settings_category == "accessibility":
            handle_accessibility_settings_clicks(m_pos)

def draw_controls_settings(screen, temp_settings, m_pos, font_m, font_s):
    if "controls" not in temp_settings or not isinstance(temp_settings["controls"], dict):
        temp_settings["controls"] = _deepcopy_settings(load_settings(force_default=True))["controls"]

    control_labels = {
        "up": "Cima",
        "down": "Baixo",
        "left": "Esquerda",
        "right": "Direita",
        "dash": "Dash",
        "ultimate": "Ultimate",
        "pause": "Pause"
    }

    options = [
        ("up", temp_settings["controls"]["up"]),
        ("down", temp_settings["controls"]["down"]),
        ("left", temp_settings["controls"]["left"]),
        ("right", temp_settings["controls"]["right"]),
        ("dash", temp_settings["controls"]["dash"]),
        ("ultimate", temp_settings["controls"]["ultimate"]),
        ("pause", temp_settings["controls"]["pause"])
    ]

    for i, (key_name, value) in enumerate(options):
        y_pos = SCREEN_H * 0.2 + i * 60
        display_value = value.upper()
        if settings_control_waiting == key_name:
            display_value = "PRESSIONE UMA TECLA..."
        draw_setting_option(screen, y_pos, control_labels[key_name], display_value, font_m, font_s, m_pos)

    reset_btn = Button(0.5, 0.8, BTN_W, BTN_SM_H, "Resetar para Padrão", font_m, color=(120, 60, 60))
    reset_btn.sprite_idx = 5
    reset_btn.check_hover(m_pos, snd_hover)
    reset_btn.draw(screen)

def handle_audio_settings_clicks(m_pos):
    global temp_settings, settings
    options = {
        "Música": {"key": "music", "values": list(range(0, 101, 10))},
        "SFX": {"key": "sfx", "values": list(range(0, 101, 10))},
        "Mudo": {"key": "mute", "values": ["Off", "On"]}
    }

    y_pos_start = SCREEN_H * 0.25
    for i, (label, data) in enumerate(options.items()):
        y_pos = y_pos_start + i * 70
        key = data["key"]
        values = data["values"]

        if label in ["Música", "SFX"]:
            row_rect = pygame.Rect(int(SCREEN_W * 0.16), int(y_pos), int(SCREEN_W * 0.68), 54)
            slider_rect = pygame.Rect(row_rect.right - 340, row_rect.y + 17, 240, 20)
            if slider_rect.collidepoint(m_pos) and pygame.mouse.get_pressed()[0]:
                new_value = int(((m_pos[0] - slider_rect.x) / slider_rect.width) * 100)
                temp_settings["audio"][key] = max(0, min(100, new_value))
                settings = _deepcopy_settings(temp_settings)
                save_settings(settings)
                apply_audio_runtime(settings)
        else:
            row_rect = pygame.Rect(int(SCREEN_W * 0.16), int(y_pos), int(SCREEN_W * 0.68), 54)
            option_rect = pygame.Rect(row_rect.right - 280, row_rect.y + 4, 260, row_rect.height - 8)
            if option_rect.collidepoint(m_pos):
                current_value = temp_settings["audio"][key]
                current_index = values.index(str(current_value))
                new_index = (current_index + 1) % len(values)
                temp_settings["audio"][key] = values[new_index]
                settings = _deepcopy_settings(temp_settings)
                save_settings(settings)
                apply_audio_runtime(settings)

def draw_gameplay_settings(screen, temp_settings, m_pos, font_m, font_s):
    options = [
        ("Auto Coleta de Baú", temp_settings["gameplay"]["auto_pickup_chest"]),
        ("Auto Aplicar Recompensa", temp_settings["gameplay"]["auto_apply_chest_reward"]),
        ("Setas Fora da Tela", temp_settings["gameplay"]["show_offscreen_arrows"])
    ]

    for i, (label, value) in enumerate(options):
        y_pos = SCREEN_H * 0.25 + i * 70
        draw_setting_option(screen, y_pos, label, value, font_m, font_s, m_pos)

def handle_controls_settings_clicks(m_pos):
    global temp_settings, settings_control_waiting, settings
    if "controls" not in temp_settings or not isinstance(temp_settings["controls"], dict):
        temp_settings["controls"] = _deepcopy_settings(load_settings(force_default=True))["controls"]

    control_rows = [
        ("up", SCREEN_H * 0.2 + 0 * 60),
        ("down", SCREEN_H * 0.2 + 1 * 60),
        ("left", SCREEN_H * 0.2 + 2 * 60),
        ("right", SCREEN_H * 0.2 + 3 * 60),
        ("dash", SCREEN_H * 0.2 + 4 * 60),
        ("ultimate", SCREEN_H * 0.2 + 5 * 60),
        ("pause", SCREEN_H * 0.2 + 6 * 60),
    ]

    for action_name, y_pos in control_rows:
        value_rect = pygame.Rect(int(SCREEN_W * 0.16) + int(SCREEN_W * 0.68) - 280, int(y_pos) + 4, 260, 46)
        if value_rect.collidepoint(m_pos):
            settings_control_waiting = action_name
            return

    reset_btn_rect = pygame.Rect(SCREEN_W * 0.5 - 150, SCREEN_H * 0.8 - 25, 300, 50)
    if reset_btn_rect.collidepoint(m_pos):
        default_controls = {
            "up": "w", "down": "s", "left": "a", "right": "d",
            "dash": "space", "ultimate": "e", "pause": "p"
        }
        temp_settings["controls"] = default_controls
        settings = _deepcopy_settings(temp_settings)
        save_settings(settings)
        settings_control_waiting = None

def draw_accessibility_settings(screen, temp_settings, m_pos, font_m, font_s):
    options = [
        ("Screen Shake", temp_settings["accessibility"]["screen_shake"]),
        ("Tamanho da UI", temp_settings["accessibility"]["ui_size"]),
        ("Alto Contraste", temp_settings["accessibility"]["high_contrast"])
    ]

    for i, (label, value) in enumerate(options):
        y_pos = SCREEN_H * 0.25 + i * 70
        if label in ["Screen Shake", "Tamanho da UI"]:
            draw_slider_option(screen, y_pos, label, value, font_m, font_s, m_pos)
        else:
            draw_setting_option(screen, y_pos, label, value, font_m, font_s, m_pos)

def handle_gameplay_settings_clicks(m_pos):
    global temp_settings, settings
    options = {
        "Auto Coleta de Baú": {"key": "auto_pickup_chest", "values": ["Off", "On"]},
        "Auto Aplicar Recompensa": {"key": "auto_apply_chest_reward", "values": ["Off", "On"]},
        "Setas Fora da Tela": {"key": "show_offscreen_arrows", "values": ["Off", "On"]}
    }

    y_pos_start = SCREEN_H * 0.25
    for i, (label, data) in enumerate(options.items()):
        y_pos = y_pos_start + i * 70
        row_rect = pygame.Rect(int(SCREEN_W * 0.16), int(y_pos), int(SCREEN_W * 0.68), 54)
        option_rect = pygame.Rect(row_rect.right - 280, row_rect.y + 4, 260, row_rect.height - 8)
        if option_rect.collidepoint(m_pos):
            key = data["key"]
            values = data["values"]
            current_value = temp_settings["gameplay"][key]
            current_index = values.index(str(current_value))
            new_index = (current_index + 1) % len(values)
            temp_settings["gameplay"][key] = values[new_index]
            settings = _deepcopy_settings(temp_settings)
            save_settings(settings)

def handle_accessibility_settings_clicks(m_pos):
    global temp_settings, settings
    options = {
        "Screen Shake": {"key": "screen_shake", "values": list(range(0, 101, 10))},
        "Tamanho da UI": {"key": "ui_size", "values": [60, 80, 100]},
        "Alto Contraste": {"key": "high_contrast", "values": ["Off", "On"]}
    }

    y_pos_start = SCREEN_H * 0.25
    for i, (label, data) in enumerate(options.items()):
        y_pos = y_pos_start + i * 70
        key = data["key"]
        values = data["values"]

        if label in ["Screen Shake", "Tamanho da UI"]:
            row_rect = pygame.Rect(int(SCREEN_W * 0.16), int(y_pos), int(SCREEN_W * 0.68), 54)
            slider_rect = pygame.Rect(row_rect.right - 340, row_rect.y + 17, 240, 20)
            if slider_rect.collidepoint(m_pos) and pygame.mouse.get_pressed()[0]:
                if label == "Screen Shake":
                    new_value = int(((m_pos[0] - slider_rect.x) / slider_rect.width) * 100)
                    temp_settings["accessibility"][key] = max(0, min(100, new_value))
                else: # Tamanho da UI
                    new_value = int(60 + ((m_pos[0] - slider_rect.x) / slider_rect.width) * 40)
                    temp_settings["accessibility"][key] = max(60, min(100, new_value))
                settings = _deepcopy_settings(temp_settings)
                save_settings(settings)
        else:
            row_rect = pygame.Rect(int(SCREEN_W * 0.16), int(y_pos), int(SCREEN_W * 0.68), 54)
            option_rect = pygame.Rect(row_rect.right - 280, row_rect.y + 4, 260, row_rect.height - 8)
            if option_rect.collidepoint(m_pos):
                current_value = temp_settings["accessibility"][key]
                current_index = values.index(str(current_value))
                new_index = (current_index + 1) % len(values)
                temp_settings["accessibility"][key] = values[new_index]
                settings = _deepcopy_settings(temp_settings)
                save_settings(settings)

def handle_video_settings_clicks(m_pos):
    global temp_settings, settings
    options = {
        "Resolução": {"key": "resolution", "values": _get_available_resolutions()},
        "Tela cheia": {"key": "fullscreen", "values": ["Off", "On"]},
        "VSync": {"key": "vsync", "values": ["Off", "On"]},
        "Limite de FPS": {"key": "fps_limit", "values": ["30", "60", "120"]},
        "Mostrar FPS": {"key": "show_fps", "values": ["Off", "On"]}
    }
    
    y_pos_start = SCREEN_H * 0.25
    for i, (label, data) in enumerate(options.items()):
        y_pos = y_pos_start + i * 70
        row_rect = pygame.Rect(int(SCREEN_W * 0.16), int(y_pos), int(SCREEN_W * 0.68), 54)
        option_rect = pygame.Rect(row_rect.right - 280, row_rect.y + 4, 260, row_rect.height - 8)
        if option_rect.collidepoint(m_pos):
            key = data["key"]
            values = data["values"]
            current_value = temp_settings["video"][key]
            if str(current_value) not in values:
                # Valor salvo inválido: reposiciona para uma opção segura.
                current_value = "1920x1080" if (key == "resolution" and "1920x1080" in values) else values[0]
                temp_settings["video"][key] = current_value
            current_index = values.index(str(current_value))
            new_index = (current_index + 1) % len(values)
            new_value = values[new_index]
            
            if key == "fps_limit":
                new_value = int(new_value)

            temp_settings["video"][key] = new_value
            settings = _deepcopy_settings(temp_settings)
            save_settings(settings)


def _slider_rect_for_category(category, key, y_pos):
    row_rect = pygame.Rect(int(SCREEN_W * 0.16), int(y_pos), int(SCREEN_W * 0.68), 54)
    if category == "audio" and key in ["music", "sfx"]:
        return pygame.Rect(row_rect.right - 340, row_rect.y + 17, 240, 20)
    if category == "accessibility" and key in ["screen_shake", "ui_size"]:
        return pygame.Rect(row_rect.right - 340, row_rect.y + 17, 240, 20)
    return None


def start_settings_drag(click_pos):
    global settings_dragging_slider
    settings_dragging_slider = None

    rows = []
    if settings_category == "audio":
        rows = [("music", SCREEN_H * 0.25 + 0 * 70), ("sfx", SCREEN_H * 0.25 + 1 * 70)]
    elif settings_category == "accessibility":
        rows = [("screen_shake", SCREEN_H * 0.25 + 0 * 70), ("ui_size", SCREEN_H * 0.25 + 1 * 70)]

    for key, y_pos in rows:
        s_rect = _slider_rect_for_category(settings_category, key, y_pos)
        if s_rect and s_rect.collidepoint(click_pos):
            settings_dragging_slider = (settings_category, key, s_rect)
            update_settings_drag(click_pos)
            break


def update_settings_drag(mouse_pos):
    global temp_settings, settings
    if not settings_dragging_slider:
        return

    category, key, s_rect = settings_dragging_slider
    ratio = (mouse_pos[0] - s_rect.x) / max(1, s_rect.width)
    ratio = max(0.0, min(1.0, ratio))

    if category == "audio":
        temp_settings["audio"][key] = int(ratio * 100)
        settings = _deepcopy_settings(temp_settings)
        save_settings(settings)
        apply_audio_runtime(settings)
    elif category == "accessibility":
        if key == "screen_shake":
            temp_settings["accessibility"][key] = int(ratio * 100)
        else:
            temp_settings["accessibility"][key] = int(60 + ratio * 40)
        settings = _deepcopy_settings(temp_settings)
        save_settings(settings)


def stop_settings_drag():
    global settings_dragging_slider
    settings_dragging_slider = None


if __name__ == "__main__":
    main()
