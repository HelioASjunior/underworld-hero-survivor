import math
import random
import pygame
import os
import json
import threading
from datetime import datetime, timedelta

from characters import CharacterCombatContext, CharacterDependencies, create_player
import hud as dark_hud
from forest_biome import build_forest_ground, ForestDecoManager
from dungeon_biome import DungeonDecoManager
from drops import Drop as ModularDrop
from enemies import Enemy as ModularEnemy, EnemyProjectile as ModularEnemyProjectile
from upgrades import (
    get_upgrade_description as get_upgrade_description_mod,
    pick_upgrades_with_synergy as pick_upgrades_with_synergy_mod,
)
from combat.projectiles import (
    MeleeSlash as CoreMeleeSlash,
    Projectile as CoreProjectile,
    projectile_enemy_collision as core_projectile_enemy_collision,
)
from spatial_index import EnemyBatchIndex, ObstacleGridIndex, PERF, _CYTHON_ACTIVE

# =========================================================
# CONFIGURAÇÕES DE PERSISTÊNCIA (SETTINGS.JSON)
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
            "default_difficulty": "Médio"
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
    """Detecta resoluções suportadas pelo monitor via pygame.display.list_modes().
    Resultado é cacheado — a lista não muda durante a execução."""
    global _resolution_cache
    if _resolution_cache is not None:
        return _resolution_cache

    modes = pygame.display.list_modes()
    native_w, native_h = _native_resolution()

    if not modes or modes == -1:
        # Monitor reporta suporte a qualquer resolução — monta lista manual
        candidates = [
            (1280, 720), (1366, 768), (1600, 900), (1920, 1080),
            (2560, 1440), (3440, 1440), (3840, 2160),
        ]
        modes = [m for m in candidates if m[0] <= native_w and m[1] <= native_h]

    seen: set[str] = set()
    result: list[str] = []
    for w, h in modes:
        # Filtra: mínimo 1280×720, máximo resolução nativa do monitor
        if w >= 1280 and h >= 720 and w <= native_w and h <= native_h:
            key = f"{w}x{h}"
            if key not in seen:
                seen.add(key)
                result.append(key)

    # list_modes() vem em ordem decrescente; inverte para crescente
    result.reverse()

    # Garante que pelo menos 1280x720 e a nativa estão presentes
    if "1280x720" not in seen:
        result.insert(0, "1280x720")
    native_key = f"{native_w}x{native_h}"
    if native_key not in seen:
        result.append(native_key)

    _resolution_cache = result
    return result

def apply_settings(settings_dict):
    global SCREEN_W, SCREEN_H, screen, FPS, MUSIC_VOLUME, SFX_VOLUME

    # Resolução: usa a salva ou auto-detecta para "auto"
    raw_res = settings_dict["video"].get("resolution", "auto")
    native_w, native_h = _native_resolution()
    if raw_res == "auto":
        res_w, res_h = native_w, native_h
    else:
        try:
            res_w, res_h = map(int, raw_res.split('x'))
        except ValueError:
            res_w, res_h = native_w, native_h
        # Se a resolução salva não cabe no monitor, usa nativo
        if res_w > native_w or res_h > native_h:
            res_w, res_h = native_w, native_h

    SCREEN_W, SCREEN_H = res_w, res_h

    fullscreen = settings_dict["video"].get("fullscreen") == "On"
    vsync      = settings_dict["video"].get("vsync")     == "On"

    # Monta flags progressivamente com fallback para garantir que o jogo abre
    flags = 0
    if fullscreen:
        flags |= pygame.FULLSCREEN
    if vsync:
        flags |= pygame.SCALED   # SCALED + vsync é mais compatível que HWSURFACE em HW antigo
    try:
        screen = pygame.display.set_mode((SCREEN_W, SCREEN_H), flags)
    except pygame.error:
        # Fallback seguro: janela sem flags especiais na resolução nativa
        SCREEN_W, SCREEN_H = _native_resolution()
        screen = pygame.display.set_mode((SCREEN_W, SCREEN_H), 0)

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


def load_dark_font(size, bold=False):
    """Carrega a fonte temática do projeto com fallback seguro.

    Regras:

    - Primeiro tentamos a fonte do projeto em assets/fonts/fonte_dark.ttf.
    - Se o arquivo não existir, usamos Georgia como fallback seguro.
    - O cache evita recriar o mesmo objeto de fonte o tempo todo, o que ajuda
      tanto na performance quanto na consistência visual.
    """

    return dark_hud.load_dark_font(size, bold=bold, asset_dir=ASSET_DIR)

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
    "CHAR_0", "CHAR_1", "CHAR_2", "CHAR_3", "CHAR_4", "CHAR_5", "DIFF_FÁCIL", "DIFF_MÉDIO"
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
    }
}

# Definição das Missões Diárias
DAILY_MISSIONS_POOL = [
    {"id": "kill_100", "name": "CAÇADOR DIÁRIO", "desc": "Mate 100 inimigos em uma partida", "goal": 100, "reward": 500, "type": "kills"},
    {"id": "survive_5m", "name": "SOBREVIVENTE", "desc": "Sobreviva por 5 minutos", "goal": 300, "reward": 800, "type": "time"},
    {"id": "boss_1", "name": "MATADOR DE GIGANTES", "desc": "Derrote 1 Chefão", "goal": 1, "reward": 1200, "type": "boss"},
    {"id": "level_15", "name": "TREINAMENTO INTENSO", "desc": "Alcance o Nível 15", "goal": 15, "reward": 1000, "type": "level"},
    {"id": "gold_200", "name": "GANÂNCIA", "desc": "Colete 200 de Ouro em uma partida", "goal": 200, "reward": 600, "type": "gold"}
]

# Definição das Conquistas e Requisitos
ACHIEVEMENTS = {
    "CHAR_1": {"type": "char", "name": "CAÇADOR", "desc": "Mate 500 inimigos no total", "req": lambda s: s["total_kills"] >= 500},
    "CHAR_2": {"type": "char", "name": "MAGO", "desc": "Derrote 1 Chefão", "req": lambda s: s["boss_kills"] >= 1},
    "CHAR_3": {"type": "char", "name": "VAMPIRE", "desc": "Derrote 3 Chefões", "req": lambda s: s["boss_kills"] >= 3},
    "CHAR_4": {"type": "char", "name": "DEMÔNIO", "desc": "Derrote 5 Chefões", "req": lambda s: s["boss_kills"] >= 5},
    "CHAR_5": {"type": "char", "name": "GOLEM", "desc": "Derrote 8 Chefões", "req": lambda s: s["boss_kills"] >= 8},
    
    "DIFF_DIFÍCIL": {"type": "diff", "name": "DIFÍCIL", "desc": "Sobreviva 10 min (total)", "req": lambda s: s["total_time"] >= 600},
    "DIFF_HARDCORE": {"type": "diff", "name": "HARDCORE", "desc": "Derrote 5 Chefões", "req": lambda s: s["boss_kills"] >= 5},

    "TIRO MÚLTIPLO": {"type": "upg", "name": "TIRO MÚLTIPLO", "desc": "Alcance Nível 10 em uma partida", "req": lambda s: s["max_level_reached"] >= 10},
    "AURA MÁGICA": {"type": "upg", "name": "AURA MÁGICA", "desc": "Colete 200 Ouro no total", "req": lambda s: True}, # Desbloqueio fácil exemplo
    "EXPLOSÃO": {"type": "upg", "name": "EXPLOSÃO", "desc": "Mate 1000 inimigos no total", "req": lambda s: s["total_kills"] >= 1000},
    "ORBES MÁGICOS": {"type": "upg", "name": "ORBES MÁGICOS", "desc": "Jogue 3 partidas", "req": lambda s: s["games_played"] >= 3},
    "PERFURAÇÃO": {"type": "upg", "name": "PERFURAÇÃO", "desc": "Mate 1500 inimigos", "req": lambda s: s["total_kills"] >= 1500},
    "SORTE": {"type": "upg", "name": "SORTE", "desc": "Morra 1 vez (Piedade)", "req": lambda s: s["deaths"] >= 1},
    "RICOCHE": {"type": "upg", "name": "RICOCHE", "desc": "Desbloqueie o Caçador", "req": lambda s: "CHAR_1" in save_data["unlocks"]},
    "EXECUÇÃO": {"type": "upg", "name": "EXECUÇÃO", "desc": "Derrote 3 Chefões", "req": lambda s: s["boss_kills"] >= 3},
    "FÚRIA": {"type": "upg", "name": "FÚRIA", "desc": "Chegue a 10% de HP (em uma run)", "req": lambda s: True}, # Lógica especial ingame
    "ÍMÃ DE XP": {"type": "upg", "name": "ÍMÃ DE XP", "desc": "Sobreviva 5 min totais", "req": lambda s: s["total_time"] >= 300},
}

def load_save():
    global save_data
    if os.path.exists(SAVE_FILE):
        try:
            with open(SAVE_FILE, "r") as f:
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
        except: pass
    check_daily_reset()

def check_daily_reset():
    global save_data
    today = datetime.now().strftime("%Y-%m-%d")
    if save_data["daily_missions"]["last_reset"] != today:
        save_data["daily_missions"]["last_reset"] = today
        # Sorteia 3 missões novas (preciso corrigir isso depois)
        new_missions = random.sample(DAILY_MISSIONS_POOL, 3)
        save_data["daily_missions"]["active"] = []
        for m in new_missions:
            m_copy = m.copy()
            m_copy["progress"] = 0
            m_copy["completed"] = False
            m_copy["claimed"] = False
            save_data["daily_missions"]["active"].append(m_copy)
        save_game()

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
    with open(SAVE_FILE, "w") as f:
        json.dump(save_data, f)


def get_run_slot_path(slot_index):
    idx = max(0, min(len(RUN_SLOT_FILES) - 1, slot_index))
    return RUN_SLOT_FILES[idx]


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
            "crit_dmg": {"name": "GOLPE FATAL", "desc": "+20% Dano Crítico", "cost": [300, 600, 1200], "max": 3, "icon": "talent_chaos"},
            "exp_size": {"name": "INSTABILIDADE", "desc": "+15% Raio de Explosão", "cost": [400, 800, 1600], "max": 3, "icon": "talent_chaos"},
            "chaos_bolt": {"name": "FAÍSCA CAÓTICA", "desc": "Tiros têm chance de explodir", "cost": [1000], "max": 1, "icon": "talent_chaos"}
        }
    },
    "GUARDIÃO": {
        "title": "CAMINHO DO GUARDIÃO",
        "desc": "Foco em defesa, regeneração e aura.",
        "skills": {
            "regen": {"name": "VIGOR", "desc": "Cura 0.1 HP/seg", "cost": [500, 1000, 2000], "max": 3, "icon": "talent_guardian"},
            "aura_res": {"name": "ESCUDO ESPIRITUAL", "desc": "+10% Resistência a Dano", "cost": [400, 800, 1600], "max": 3, "icon": "talent_guardian"},
            "thorns": {"name": "ESPINHOS", "desc": "Reflete 20% do dano recebido", "cost": [1200], "max": 1, "icon": "talent_guardian"}
        }
    },
    "FOGO": {
        "title": "CAMINHO DO FOGO",
        "desc": "Foco em dano mágico e aura.",
        "skills": {
            "fire_dmg": {"name": "PIROMANCIA", "desc": "+15% Dano de Aura", "cost": [300, 600, 1200], "max": 3, "icon": "talent_fire"},
            "burn_area": {"name": "TERRA QUEIMADA", "desc": "+20% Área de Aura", "cost": [400, 800, 1600], "max": 3, "icon": "talent_fire"},
            "inferno": {"name": "INFERNO", "desc": "Inimigos na aura pegam fogo", "cost": [1500], "max": 1, "icon": "talent_fire"}
        }
    }
}

DIFFICULTIES = {
    "FÁCIL":    {"hp_mult": 0.7, "spd_mult": 0.8, "dmg_mult": 0.5, "gold_mult": 0.8, "color": (100, 255, 100), "desc": "Para relaxar. Inimigos fracos.", "id": "DIFF_FÁCIL"},
    "MÉDIO":    {"hp_mult": 1.0, "spd_mult": 1.0, "dmg_mult": 1.0, "gold_mult": 1.0, "color": (255, 255, 100), "desc": "A experiência padrão.", "id": "DIFF_MÉDIO"},
    "DIFÍCIL":  {"hp_mult": 1.5, "spd_mult": 1.15, "dmg_mult": 1.5, "gold_mult": 1.4, "color": (255, 150, 50), "desc": "Novos Monstros! +40% Ouro.", "id": "DIFF_DIFÍCIL"},
    "HARDCORE": {"hp_mult": 2.5, "spd_mult": 1.3, "dmg_mult": 2.0, "gold_mult": 2.0, "color": (255, 50, 50),   "desc": "Pesadelo. +100% Ouro.", "id": "DIFF_HARDCORE"}
}

# Atributos Modificáveis (Base)
PLAYER_SPEED = 280.0
PLAYER_MAX_HP = 8
SHOT_COOLDOWN = 0.35
HAS_FURY = False
PROJECTILE_DMG = 2
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
BOSS_SPAWN_TIME = 300.0  # 5 Minutos para cada boss
BOSS_MAX_HP = 500
MINI_BOSS_SPAWN_TIME = 10.0  # TESTE: mini boss aparece logo no início
AGIS_SPAWN_TIME = 120.0       # Agis nasce no minuto 2
SHOOTER_PROJ_IMAGE = "enemy_arrow" 

# Dados dos Personagens - MENU DE ANIME FRAMES - QUANTIDADE DE IMAGENS
CHAR_DATA = {
    0: {
        "name": "GUERREIRO", "hp": 8, "speed": 280, "damage": 2,
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
        "name": "CAÇADOR", "hp": 5, "speed": 340, "damage": 3,
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
        "name": "MAGO", "hp": 6, "speed": 260, "damage": 2,
        "desc": "Ult: Congelamento Temporal", "size": (300, 300), "menu_size": (350, 350),
        "anim_frames": 8, "menu_anim_frames": 8,
        "dash_duration": 0.20, "dash_cooldown": 2.5,
        "id": "CHAR_2",
        # Walk: 1200x150 px, 8 frames de 150x150 px.
        "spritesheet": "sprite/mago",
        "spritesheet_frame_w": 150,
        "spritesheet_frame_h": 150,
        "anim_speed": 0.10,
        # Idle: 1200x150 px, 8 frames de 150x150 px.
        "spritesheet_idle": "sprite/magoidle",
        "spritesheet_idle_frame_w": 150,
        "spritesheet_idle_frame_h": 150,
        "idle_anim_frames": 8,
        "idle_anim_speed": 0.12,
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
        "name": "VAMPIRE", "hp": 7, "speed": 300, "damage": 3,
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
        "name": "DEMÔNIO", "hp": 6, "speed": 290, "damage": 3,
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
        "name": "GOLEM", "hp": 9, "speed": 240, "damage": 4,
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
}

# Constantes
WORLD_GRID = 64
BG_COLOR = (14, 14, 18)
PLAYER_IFRAMES = 1.0
GEM_XP = 10
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
    "AURA MÁGICA": "Dano contínuo ao redor do jogador",
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
}

UPGRADE_TAGS = {
    "DANO ++": {"dano"},
    "TIRO RÁPIDO": {"cadencia"},
    "VELOCIDADE ++": {"movimento"},
    "TIRO MÚLTIPLO": {"projeteis"},
    "PERFURAÇÃO": {"projeteis"},
    "EXPLOSÃO": {"explosao"},
    "AURA MÁGICA": {"aura"},
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
}

EVOLUTIONS = {
    "BAZUCA": {"base": "TIRO MÚLTIPLO", "passive": "EXPLOSÃO", "desc": "EVOLUÇÃO: Poder de fogo extremo, com dano explosivo ampliado!"},
    "BURACO NEGRO": {"base": "AURA MÁGICA", "passive": "ÍMÃ DE XP", "desc": "EVOLUÇÃO: Aura magnética que suga e esmaga inimigos!"},
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
    "AURA MÁGICA": "icon_aura",
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
    "SYNERGY_MIDAS": "synergy_midas"
}
RARITY = {
    "COMUM": {"chance": 0.72, "mult": 1.0, "color": (200,200,200)},
    "RARO":  {"chance": 0.23, "mult": 1.35, "color": (80,170,255)},
    "EPICO": {"chance": 0.05, "mult": 1.75, "color": (200,80,255)},
}

# Alias para compatibilidade (RARITIES = RARITY)
RARITIES = RARITY

# Pool de upgrades disponíveis (filtrada pelos unlocks)
UPGRADE_POOL = {k: v for k, v in ALL_UPGRADES_POOL.items() if k in DEFAULT_UNLOCKS or True}

# Pactos disponíveis
PACTOS = {
    "NENHUM":     {"name": "SEM PACTO",       "desc": "Sem modificadores.",                     "hp": 0,  "color": (200, 200, 200)},
    "VELOCIDADE": {"name": "PACTO DA PRESSA",  "desc": "Inimigos 50% mais rápidos, +50% Ouro.",  "hp": 0,  "color": (255, 200, 0)},
    "FRÁGIL":     {"name": "PACTO FRÁGIL",     "desc": "Começa com -2 HP máximo, +30% XP.",       "hp": -2, "color": (255, 100, 100)},
    "SOMBRA":     {"name": "PACTO DA SOMBRA",  "desc": "Inimigos invisíveis, +80% Ouro.",          "hp": 0,  "color": (150, 0, 200)},
}

# Dados dos biomas / backgrounds
BG_DATA = {
    "dungeon":  {"name": "bg_dungeon",  "music": "music_dungeon",  "type": "normal"},
    "forest":   {"name": "bg_forest",   "music": "music_forest",   "type": "normal"},
    "volcano":  {"name": "bg_volcano",  "music": "music_volcano",  "type": "volcano"},
    "ice":      {"name": "bg_ice",      "music": "music_ice",      "type": "ice"},
}

# Multiplicadores permanentes (serão sobrescritos em reset_game)
CRIT_DMG_MULT = 2.0
EXPLOSION_SIZE_MULT = 1.0
REGEN_RATE = 0.0
DAMAGE_RES = 0.0
THORNS_PERCENT = 0.0
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
# BTN_W é largo o suficiente para "CONFIGURAÇÕES" + padding nas pontas ornamentais
# =========================================================
BTN_W    = 440   # largura padrão de todos os botões primários
BTN_H    = 52    # altura padrão
BTN_SM_W = 320   # botões secundários (VOLTAR, ações)
BTN_SM_H = 52

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
                    icon_surf = load_dark_font(17, bold=True).render(str(self.icon), True, UI_THEME["faded_gold"])
                    screen.blit(icon_surf, icon_surf.get_rect(center=icon_rect.center))

        # ── subtext / bloqueado ────────────────────────────────────────────
        if self.subtext and not self.locked:
            sub = load_dark_font(14).render(self.subtext, True, (160, 140, 110))
            sub.set_alpha(200)
            screen.blit(sub, sub.get_rect(center=(cx, cy + 11)))

        if self.locked:
            lock_txt = load_dark_font(15, bold=True).render("BLOQUEADO", True, (180, 90, 70))
            screen.blit(lock_txt, lock_txt.get_rect(center=(cx, cy + 11)))
            if self.is_hovered and self.lock_req:
                mx, my = pygame.mouse.get_pos()
                tt = load_dark_font(15).render(self.lock_req, True, (210, 185, 165))
                tip_rect = pygame.Rect(mx + 14, my - 10, tt.get_width() + 18, tt.get_height() + 12)
                pygame.draw.rect(screen, (20, 10, 8), tip_rect, border_radius=3)
                pygame.draw.rect(screen, (110, 55, 40), tip_rect, 1, border_radius=3)
                screen.blit(tt, (tip_rect.x + 9, tip_rect.y + 6))
        elif self.subtext:
            stxt = load_dark_font(15).render(self.subtext, True, UI_THEME["mist"])
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
    def __init__(self, pos, color, size, speed, life):
        super().__init__()
        self.color = color
        self.original_size = size
        self.size = size
        self.life = life
        self.max_life = life
        self.image = pygame.Surface((int(size), int(size)))
        self.image.fill(color)
        self.rect = self.image.get_rect(center=pos)
        self.pos = pygame.Vector2(pos)
        angle = random.uniform(0, 360)
        rad = math.radians(angle)
        speed_var = random.uniform(speed * 0.5, speed * 1.5)
        self.vel = pygame.Vector2(math.cos(rad), math.sin(rad)) * speed_var

    def update(self, dt, cam):
        self.pos += self.vel * dt
        self.vel *= 0.92  
        self.life -= dt
        if self.life <= 0:
            self.kill()
        else:
            # Otimização: Reduzir frequência de redimensionamento
            if int(self.life * 10) != int((self.life + dt) * 10):
                ratio = self.life / self.max_life
                new_size = max(1, int(self.original_size * ratio))
                if new_size != self.size:
                    self.size = new_size
                    self.image = pygame.Surface((new_size, new_size))
                    self.image.fill(self.color)
        self.rect.center = self.pos + cam

class DamageText(pygame.sprite.Sprite):
    def __init__(self, pos, amount, is_crit=False, color=(255, 255, 255)):
        super().__init__()
        size = 36 if is_crit else 22
        final_color = (255, 215, 0) if is_crit else color
        text_content = f"{amount}!" if is_crit else str(amount)

        font = load_dark_font(size, bold=True)
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

def build_character_dependencies():
    """Cria o pacote de dependências enviado ao módulo characters.

    A função existe para deixar a integração explícita e didática: tudo o que o
    sistema de personagens usa vem daqui, de forma centralizada.
    """

    return CharacterDependencies(
        char_data_map=CHAR_DATA,
        control_reader=is_control_pressed,
        particle_cls=Particle,
        damage_text_cls=DamageText,
        projectile_cls=lambda pos, vel, dmg, frames: CoreProjectile(
            pos,
            vel,
            dmg,
            frames,
            pierce=PROJ_PIERCE,
            ricochet=PROJ_RICOCHET,
            screen_size_getter=lambda: (SCREEN_W, SCREEN_H),
        ),
        melee_slash_cls=CoreMeleeSlash,
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
    global PROJ_COUNT, PROJ_PIERCE, EXPLOSION_RADIUS, ORB_COUNT
    global CRIT_CHANCE, EXECUTE_THRESH, HAS_FURY, player, player_upgrades
    global has_bazuca, has_buraco_negro, has_serras, has_tesla, has_ceifador, has_berserk
    global PROJ_RICOCHET

    feed_color = UI_THEME["old_gold"] if key in EVOLUTIONS else UI_THEME["faded_gold"]
    feed_prefix = "Evolução" if key in EVOLUTIONS else "Upgrade"
    
    player_upgrades.append(key)
    
    # Evoluções
    if key == "BAZUCA":
        has_bazuca = True
        push_upgrade_notification(f"{feed_prefix}: {key}", feed_color)
        return
    elif key == "BURACO NEGRO":
        has_buraco_negro = True
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
    elif key == "AURA MÁGICA":   AURA_DMG = max(AURA_DMG, 1); AURA_DMG += int(1 * mult)
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


def load_all_assets():
    """Carrega (ou recarrega) todos os assets gráficos e de áudio do jogo."""
    global ground_img, menu_bg_img, aura_frames, explosion_frames_raw
    global projectile_frames_raw, slash_frames_raw, orb_img, tornado_img
    global upg_images, menu_char_anims, menu_idle_anims, loader, current_bg_name
    global menu_btn_sprites, menu_btn_sprites_hover, menu_logo_img, char_panel_imgs, select_title_img, diff_screen_imgs
    global char_select_panel_img, char_select_panel_meta, char_select_title_frame
    global skill_card_sprites, skill_card_sprites_hover
    global config_title_spr, config_tag_spr
    global forest_deco_manager, dungeon_deco_manager
    global cursor_img

    bg_name = BG_DATA.get(selected_bg, BG_DATA["dungeon"])["name"]
    current_bg_name = bg_name

    dark_hud.init_stat_sprites(ASSET_DIR)

    # Bioma Forest: usa tilemap composto em vez de imagem estática
    if selected_bg == "forest":
        ground_img = build_forest_ground(loader)
        if forest_deco_manager is None:
            forest_deco_manager = ForestDecoManager(ASSET_DIR)
        forest_deco_manager.load_frames()
    else:
        ground_img = loader.load_image(bg_name, (256, 256), ((20, 20, 30), (10, 10, 20)))

    # Bioma Dungeon: decorações de chão (pentagrama, BDS, dinossauro)
    if selected_bg == "dungeon":
        if dungeon_deco_manager is None:
            dungeon_deco_manager = DungeonDecoManager(ASSET_DIR)
        dungeon_deco_manager.load_frames()
    menu_bg_img = loader.load_image("menu_bg", (SCREEN_W, SCREEN_H), ((10, 5, 20), (5, 0, 10)))
    menu_btn_sprites, menu_btn_sprites_hover = load_menu_btn_sprites(350, 46)
    skill_card_sprites, skill_card_sprites_hover = load_skill_card_sprites(600, 130)
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

    # aura2.png — 576x72, 1 linha × 8 frames de 72x72 px
    # Carregado diretamente via subsurface para garantir sequência esq→dir.
    try:
        _aura_path = os.path.join(ASSET_DIR, "sprite", "aura2.png")
        _aura_surf = pygame.image.load(_aura_path).convert_alpha()
        _aura_fw = 72
        aura_frames = [
            _aura_surf.subsurface(pygame.Rect(i * _aura_fw, 0, _aura_fw, _aura_surf.get_height())).copy()
            for i in range(_aura_surf.get_width() // _aura_fw)
        ]
        print(f"[ASSETS] aura2.png OK: {len(aura_frames)} frames de {_aura_fw}x{_aura_surf.get_height()}")
    except Exception as _e:
        print(f"[ASSETS] aura2.png fallback: {_e}")
        aura_frames = loader.load_animation("aura", 4, (400, 400), fallback_colors=((100, 0, 200, 80), (80, 0, 160, 60)))
    ExplosionAnimation._frame_cache.clear()   # invalida cache ao recarregar assets
    explosion_frames_raw = load_explosion_frames(loader, (128, 128))
    projectile_frames_raw = loader.load_animation("projectile", 4, (40, 20), fallback_colors=((255, 255, 100), (200, 200, 0)))
    slash_frames_raw = loader.load_animation("slash", 6, (120, 120), fallback_colors=((255, 255, 200, 180), (200, 200, 150, 120)))
    orb_img = loader.load_image("orb", (50, 50), ((0, 200, 255), (0, 100, 200)))
    tornado_img = loader.load_image("tornado", (300, 300), ((200, 200, 255, 150), (150, 150, 200, 100)))
    cursor_img = loader.load_image("seta", (56, 56))
    
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
    global PROJ_RICOCHET
    global obstacle_grid_index, enemy_batch_index, last_obstacle_count
    global pending_horde_queue, obstacle_spawn_t, obstacle_spawn_interval
    global obstacle_total_placed
    global doom_seals
    
    save_data["stats"]["games_played"] += 1
    
    # Resetar stats base
    char_data = CHAR_DATA.get(char_id, CHAR_DATA[0])
    PLAYER_MAX_HP = char_data["hp"]
    PLAYER_SPEED = char_data["speed"]
    PROJECTILE_DMG = char_data.get("damage", 2)
    SHOT_COOLDOWN = 0.35
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
    CRIT_DMG_MULT = 2.0 + pu.get("crit_dmg", 0) * 0.20
    # 0.08 por nível → máx ~1.6x em 8 upgrades (era 0.15 → ficava grande demais)
    EXPLOSION_SIZE_MULT = 1.0 + pu.get("exp_size", 0) * 0.08
    HAS_CHAOS_BOLT = pu.get("chaos_bolt", 0) >= 1
    REGEN_RATE = pu.get("regen", 0) * 0.1
    DAMAGE_RES = pu.get("aura_res", 0) * 0.10
    THORNS_PERCENT = 0.20 if pu.get("thorns", 0) >= 1 else 0.0
    FIRE_DMG_MULT = 1.0 + pu.get("fire_dmg", 0) * 0.15
    BURN_AURA_MULT = 1.0 + pu.get("burn_area", 0) * 0.20
    HAS_INFERNO = pu.get("inferno", 0) >= 1
    
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
    obstacle_grid_index = ObstacleGridIndex(cell_size=WORLD_GRID)
    enemy_batch_index = EnemyBatchIndex()
    last_obstacle_count = 0
    
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
    global doom_seals

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
    obstacle_grid_index = ObstacleGridIndex(cell_size=WORLD_GRID)
    enemy_batch_index = EnemyBatchIndex()
    last_obstacle_count = 0

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
# TELA DE CARREGAMENTO
# =========================================================

def show_loading_screen(screen, load_fn, font_path=None):
    """Exibe tela de carregamento animada enquanto load_fn() roda em background thread."""
    sw, sh = screen.get_size()

    # --- Background ---
    loading_bg_path = os.path.join(BASE_DIR, "assets", "ui", "loading.png")
    if os.path.exists(loading_bg_path):
        raw_bg = pygame.image.load(loading_bg_path).convert()
        bg_surf = pygame.transform.smoothscale(raw_bg, (sw, sh))
    else:
        bg_surf = pygame.Surface((sw, sh))
        bg_surf.fill((10, 5, 20))

    # Overlay escuro para legibilidade
    overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 140))

    # --- Fontes ---
    def _make_font(size, bold=False):
        if font_path and os.path.exists(font_path):
            try:
                return pygame.font.Font(font_path, size)
            except Exception:
                pass
        return pygame.font.SysFont("arial", size, bold=bold)

    font_title  = _make_font(52, bold=True)
    font_label  = _make_font(28, bold=True)
    font_tip    = _make_font(20)

    # --- Dimensões da barra de progresso ---
    bar_w   = int(sw * 0.50)
    bar_h   = 22
    bar_x   = (sw - bar_w) // 2
    bar_y   = int(sh * 0.80)
    corner  = bar_h // 2   # borda arredondada

    # --- Thread de carregamento ---
    _done    = [False]
    _error   = [None]

    def _worker():
        try:
            load_fn()
        except Exception as e:
            _error[0] = e
        finally:
            _done[0] = True

    t = threading.Thread(target=_worker, daemon=True)
    t.start()

    # --- Loop de animação ---
    clock      = pygame.time.Clock()
    elapsed    = 0.0          # segundos desde início
    fake_prog  = 0.0          # 0.0 – 1.0 progresso fake suave
    dot_timer  = 0.0
    dot_count  = 0

    # Gradiente da barra: dourado → laranja claro
    _bar_color_l = (220, 170, 40)
    _bar_color_r = (255, 210, 80)

    # Cor do brilho superior
    _shine_color = (255, 255, 200, 60)

    # Pré-render do texto estático
    title_surf = font_title.render("Carregando", True, (240, 220, 140))
    title_rect = title_surf.get_rect(center=(sw // 2, int(sh * 0.70)))

    tip_texts = [
        "Explore o mundo e enfrente hordas de inimigos.",
        "Colete gemas para evoluir seu personagem.",
        "Combine upgrades para criar sinergias poderosas.",
        "Cada run é única — adapte sua estratégia.",
    ]
    tip_surf  = font_tip.render(random.choice(tip_texts), True, (160, 155, 170))
    tip_rect  = tip_surf.get_rect(center=(sw // 2, bar_y + bar_h + 38))

    while not (_done[0] and fake_prog >= 0.995 and elapsed >= 5.0):
        dt = clock.tick(60) / 1000.0
        elapsed   += dt
        dot_timer += dt
        if dot_timer >= 0.40:
            dot_timer = 0.0
            dot_count = (dot_count + 1) % 4

        # Progresso fake: sobe rápido até 85%, depois aguarda _done
        if not _done[0]:
            target = 0.85
        else:
            target = 1.0
        fake_prog += (target - fake_prog) * min(1.0, dt * 2.2)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                raise SystemExit

        # --- Desenho ---
        screen.blit(bg_surf, (0, 0))
        screen.blit(overlay, (0, 0))

        # Título pulsante
        pulse = 0.85 + 0.15 * math.sin(elapsed * 2.5)
        alpha = int(255 * pulse)
        title_surf.set_alpha(alpha)
        screen.blit(title_surf, title_rect)

        # Pontos animados
        dots_surf = font_title.render("." * dot_count, True, (240, 220, 140))
        dots_rect = dots_surf.get_rect(midleft=(title_rect.right + 4, title_rect.centery))
        dots_surf.set_alpha(alpha)
        screen.blit(dots_surf, dots_rect)

        # Fundo da barra (trilho)
        pygame.draw.rect(screen, (30, 25, 40), (bar_x - 2, bar_y - 2, bar_w + 4, bar_h + 4), border_radius=corner + 2)
        pygame.draw.rect(screen, (55, 48, 70), (bar_x, bar_y, bar_w, bar_h), border_radius=corner)

        # Preenchimento com gradiente horizontal simulado
        fill_w = max(corner * 2, int(bar_w * fake_prog))
        if fill_w > 0:
            for i in range(fill_w):
                t_grad = i / bar_w
                r = int(_bar_color_l[0] + (_bar_color_r[0] - _bar_color_l[0]) * t_grad)
                g = int(_bar_color_l[1] + (_bar_color_r[1] - _bar_color_l[1]) * t_grad)
                b = int(_bar_color_l[2] + (_bar_color_r[2] - _bar_color_l[2]) * t_grad)
                pygame.draw.line(screen, (r, g, b),
                                 (bar_x + i, bar_y + 2), (bar_x + i, bar_y + bar_h - 2))
            # Clip arredondado na barra preenchida
            fill_clip = pygame.Surface((fill_w, bar_h), pygame.SRCALPHA)
            pygame.draw.rect(fill_clip, (0, 0, 0, 0), fill_clip.get_rect(), border_radius=corner)
            # Brilho superior
            shine = pygame.Surface((fill_w, bar_h // 2), pygame.SRCALPHA)
            shine.fill(_shine_color)
            screen.blit(shine, (bar_x, bar_y), special_flags=pygame.BLEND_RGBA_ADD)

        # Borda da barra
        pygame.draw.rect(screen, (100, 85, 130), (bar_x, bar_y, bar_w, bar_h), width=1, border_radius=corner)

        # Percentual
        pct_surf = font_label.render(f"{int(fake_prog * 100)}%", True, (210, 195, 120))
        pct_rect = pct_surf.get_rect(center=(sw // 2, bar_y - 28))
        screen.blit(pct_surf, pct_rect)

        # Dica
        screen.blit(tip_surf, tip_rect)

        pygame.display.flip()

    if _error[0]:
        raise _error[0]

    # Fade out suave
    fade = pygame.Surface((sw, sh))
    fade.fill((0, 0, 0))
    for alpha in range(0, 256, 8):
        screen.blit(bg_surf, (0, 0))
        screen.blit(overlay, (0, 0))
        fade.set_alpha(alpha)
        screen.blit(fade, (0, 0))
        pygame.display.flip()
        clock.tick(60)


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
    global player, enemies, projectiles, enemy_projectiles, gems, drops, particles, obstacles, puddles, damage_texts
    global kills, game_time, level, xp, shot_t, aura_t, aura_anim_timer, aura_frame_idx, orb_rot_angle
    global spawn_t, bosses_spawned, session_boss_kills, session_max_level, triggered_hordes
    global player_upgrades, has_bazuca, has_buraco_negro, has_serras, has_tesla, has_ceifador, has_berserk
    global chest_loot, chest_ui_timer, new_unlocks_this_session, up_options, up_keys, up_rarities, active_explosions
    global ground_img, menu_bg_img, aura_frames, explosion_frames_raw, projectile_frames_raw, slash_frames_raw, orb_img, tornado_img
    global PROJ_RICOCHET, temp_settings, settings_control_waiting, settings_dragging_slider
    global obstacle_grid_index, enemy_batch_index, last_obstacle_count

    # Configuração da tela (Já feita no apply_settings, mas garantindo o caption)
    pygame.display.set_caption("Sobrevivente do Caos")
    clock = pygame.time.Clock()

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

    # Fontes
    font_s = load_dark_font(18, bold=True)
    font_m = load_dark_font(28, bold=True)
    font_l = load_dark_font(46, bold=True)

    obstacle_grid_index = ObstacleGridIndex(cell_size=WORLD_GRID)
    enemy_batch_index = EnemyBatchIndex()
    last_obstacle_count = 0

    # Inicializar botões de configurações (precisam das fontes)
    init_settings_buttons(font_m)

    # Carregar todos os assets gráficos com tela de carregamento
    def _load_everything():
        load_all_assets()
        init_menu_particles()

    show_loading_screen(screen, _load_everything, font_path=FONT_DARK_PATH)

    # Criar todos os botões da interface
    # Menu reposicionado para o canto inferior esquerdo conforme imagem
    menu_btns = [
        Button(0.15, 0.52, BTN_W, BTN_H, "JOGAR",         font_m, color=(32, 86, 52), hover_color=(48, 120, 70)),
        Button(0.15, 0.59, BTN_W, BTN_H, "MISSÕES",       font_m),
        Button(0.15, 0.66, BTN_W, BTN_H, "TALENTOS",      font_m),
        Button(0.15, 0.73, BTN_W, BTN_H, "SAVES",         font_m),
        Button(0.15, 0.80, BTN_W, BTN_H, "BIOMA",         font_m),
        Button(0.15, 0.87, BTN_W, BTN_H, "CONFIGURAÇÕES", font_m),
        Button(0.15, 0.94, BTN_W, BTN_H, "SAIR",          font_m, color=(80, 30, 30), hover_color=(120, 42, 42)),
    ]
    menu_icons = ["play", "missions", "talents", "saves", "biome", "settings", "exit"]
    for idx, (btn, icon) in enumerate(zip(menu_btns, menu_icons)):
        btn.icon = load_menu_icon_surface(loader, icon, size=(20, 20))
        btn.sprite_idx = idx

    menu_preview_map = {
        "JOGAR": ("Iniciar Jornada", "Selecione heroi, dificuldade e pacto para começar uma nova run de sobrevivencia."),
        "MISSÕES": ("Rotina Diaria", "Acompanhe objetivos diarios, resgate recompensas e acelere sua progressao."),
        "TALENTOS": ("Arvore de Talentos", "Invista ouro em melhorias permanentes e desbloqueie builds mais fortes."),
        "SAVES": ("Gerenciar Saves", "Carregue e acompanhe slots de progresso para alternar entre campanhas."),
        "BIOMA": ("Escolher Bioma", "Troque o tema visual e o clima da arena para variar o estilo da partida."),
        "CONFIGURAÇÕES": ("Ajustes do Jogo", "Video, audio, controles e acessibilidade com aplicacao imediata."),
        "SAIR": ("Encerrar", "Salva progresso atual e fecha o jogo com seguranca."),
    }

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
        Button(0.75, 0.25 + i * 0.12, BTN_SM_W, BTN_H, "COLETAR", font_m, color=(40, 100, 40))
        for i in range(3)
    ]
    for btn in mission_claim_btns:
        btn.sprite_idx = 3

    # Layout compartilhado da tela de talentos para manter painel, textos e botões sincronizados.
    SHOP_PATH_TOP_RATIO = 0.18
    SHOP_PATH_GAP_RATIO = 0.23
    SHOP_SKILL_TOP_OFFSET = 78
    SHOP_SKILL_GAP = 42
    SHOP_ROW_PANEL_HEIGHT = 210
    SHOP_BTN_X_RATIO = 0.80
    SHOP_BTN_Y_OFFSET = 11

    shop_back_btn = Button(0.5, 0.93, BTN_SM_W, BTN_SM_H, "VOLTAR", font_m, color=(80, 30, 30))
    shop_back_btn.sprite_idx = 6
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
        btn = Button(0.5, 0.28 + i * 0.14, BTN_W, BTN_H, bg_key.upper(), font_m)
        btn.sprite_idx = i % 7
        bg_btns.append(btn)

    pause_btns = [
        Button(0.5, 0.55, BTN_W, BTN_H, "CONTINUAR",    font_m, color=(30, 80, 30)),
        Button(0.5, 0.68, BTN_W, BTN_H, "MENU PRINCIPAL", font_m, color=(80, 30, 30)),
    ]
    pause_btns[0].sprite_idx = 0
    pause_btns[1].sprite_idx = 6
    pause_save_btns = [
        Button(0.70, 0.54, BTN_SM_W, BTN_H, "SALVAR SLOT 1", font_s, color=(35, 80, 35)),
        Button(0.70, 0.61, BTN_SM_W, BTN_H, "SALVAR SLOT 2", font_s, color=(35, 80, 35)),
        Button(0.70, 0.68, BTN_SM_W, BTN_H, "SALVAR SLOT 3", font_s, color=(35, 80, 35)),
    ]
    for i, btn in enumerate(pause_save_btns):
        btn.sprite_idx = i + 1
    game_over_btn = Button(0.5, 0.78, BTN_W, BTN_H, "VOLTAR AO MENU PRINCIPAL", font_m, color=(80, 30, 30))
    game_over_btn.sprite_idx = 6

    # Variáveis de estado do jogo
    state = "MENU"
    running = True
    m_pos = (0, 0)
    hitstop_timer = 0.0
    shake_timer = 0.0
    shake_strength = 0
    shake_offset = pygame.Vector2(0, 0)
    up_options = []
    run_gold_collected = 0.0
    autosave_timer = 0.0
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
    # Fila de horda e obstáculos graduais (inicializados aqui para o caso
    # de o loop começar antes de reset_game ser chamado)
    pending_horde_queue    = []
    obstacle_spawn_t       = 0.0
    obstacle_spawn_interval = 18.0
    obstacle_total_placed  = 0
    OBSTACLE_MAX_GRADUAL   = 28
    while running:
        # 1. Delta Time (dt) com Clamp
        PERF.begin_frame()
        dt_raw = clock.tick(FPS) / 1000.0
        dt = min(dt_raw, 1/30.0) # Evita bugs de física com lag

        if pause_save_feedback_timer > 0:
            pause_save_feedback_timer = max(0.0, pause_save_feedback_timer - dt_raw)
        
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

                if event.key == pygame.K_ESCAPE:
                    if state == "PLAYING": state = "PAUSED"
                    elif state == "PAUSED": state = "PLAYING"
                    elif state == "SETTINGS":
                        if settings_category == "main":
                            state = "MENU"
                        else:
                            settings_category = "main"
                            temp_settings = json.loads(json.dumps(settings))
                    elif state in ["CHAR_SELECT", "MISSIONS", "SHOP", "BG_SELECT", "SAVES"]:
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
            
            if event.type == pygame.MOUSEBUTTONDOWN:
                    click_pos = event.pos

                    if state == "SETTINGS":
                        start_settings_drag(click_pos)

                    if state == "MENU":
                        if menu_pending_action is None and menu_exit_timer <= 0.0:
                            if menu_btns[0].rect.collidepoint(click_pos):
                                menu_pending_action = "CHAR_SELECT"
                            elif menu_btns[1].rect.collidepoint(click_pos):
                                menu_pending_action = "MISSIONS"
                            elif menu_btns[2].rect.collidepoint(click_pos):
                                menu_pending_action = "SHOP"
                            elif menu_btns[3].rect.collidepoint(click_pos):
                                menu_pending_action = "SAVES"
                            elif menu_btns[4].rect.collidepoint(click_pos):
                                menu_pending_action = "BG_SELECT"
                            elif menu_btns[5].rect.collidepoint(click_pos):
                                menu_pending_action = "SETTINGS"
                            elif menu_btns[6].rect.collidepoint(click_pos):
                                menu_pending_action = "QUIT"

                            if menu_pending_action is not None:
                                if snd_click:
                                    snd_click.play()
                                menu_exit_timer = MENU_EXIT_DURATION

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
                                    play_sfx("win")
                                    save_game()

                    elif state == "SHOP":
                        if shop_back_btn.rect.collidepoint(click_pos):
                            save_game()
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
                                reset_game(player.char_id if player else 0)
                                run_gold_collected = 0.0
                                autosave_timer = 0.0
                                if p_data["hp"] > 0: player.hp = p_data["hp"]
                                state = "PLAYING"

                    elif state == "BG_SELECT":
                        if bg_back_btn.rect.collidepoint(click_pos):
                            state = "MENU"
                        else:
                            for i, btn in enumerate(bg_btns):
                                if btn.rect.collidepoint(click_pos):
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
                            clear_current_run_state()
                            run_gold_collected = 0.0
                            state = "MENU"

                    elif state == "UPGRADE":
                        for i in range(len(up_keys)):
                            y_pos = SCREEN_H*0.3 + i*150
                            rect = pygame.Rect(SCREEN_W/2 - 300, y_pos, 600, 120)
                            if rect.collidepoint(click_pos):
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
                        elif pause_btns[1].rect.collidepoint(click_pos):
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

            if event.type == pygame.MOUSEMOTION and state == "SETTINGS":
                update_settings_drag(event.pos)

            if event.type == pygame.MOUSEBUTTONUP and state == "SETTINGS":
                stop_settings_drag()

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
                    elif state in ["CHAR_SELECT", "MISSIONS", "SHOP", "BG_SELECT", "SAVES"]:
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

        # 3. Atualização da Lógica do Jogo
        if state == "PLAYING" and player and player.hp > 0:

            current_xp_to_level = int(80 + (level-1)*22 + ((level-1)**1.12)*6)

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
            update_mission_progress("time", dt)
            
            if REGEN_RATE > 0:
                player.hp = min(PLAYER_MAX_HP, player.hp + REGEN_RATE * dt)

            update_skill_feed(dt)

            time_scale = 1.0 + (game_time / 60.0) * 0.20
            
            current_spawn_rate = max(0.1, SPAWN_EVERY_BASE - (game_time / 500.0)) 
            
            biome_type = BG_DATA[selected_bg]["type"]
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

            if AURA_DMG > 0:
                aura_anim_timer += dt
                if aura_anim_timer > 0.1: aura_anim_timer = 0; aura_frame_idx = (aura_frame_idx + 1) % len(aura_frames)
                aura_t += dt
                if aura_t >= 0.4: 
                    aura_t = 0
                    current_aura_range = AURA_RANGE * 2 if has_buraco_negro else AURA_RANGE
                    current_aura_range *= BURN_AURA_MULT
                    current_aura_dmg = AURA_DMG * 3 if has_buraco_negro else AURA_DMG
                    current_aura_dmg *= FIRE_DMG_MULT
                    
                    for e in enemies:
                        if player.pos.distance_to(e.pos) < current_aura_range:
                            dmg_dealt = current_aura_dmg
                            
                            if HAS_INFERNO:
                                e.flash_timer = 0.5
                                dmg_dealt *= 1.25
                            is_crit = random.random() < CRIT_CHANCE
                            if is_crit:
                                dmg_dealt *= 2
                                hitstop_timer = 0.03
                            
                            e.hp -= dmg_dealt
                            e.flash_timer = 0.1 
                            damage_texts.add(DamageText(e.pos, dmg_dealt, is_crit, (200, 100, 255))) 
                            
                            if has_buraco_negro:
                                pull_dir = (player.pos - e.pos).normalize() if (player.pos - e.pos).length() > 0 else pygame.Vector2(0,0)
                                e.knockback += pull_dir * 18.0
                            
                            if e.hp <= 0: 
                                if player.ult_charge < player.ult_max: player.ult_charge += 1
                                gems.add(Gem(e.pos, loader)); e.kill(); kills += 1
            
            if ORB_COUNT > 0:
                rot_speed = 450 if has_serras else 150
                orb_rot_angle += rot_speed * dt
                current_orb_dmg = (ORB_DMG * 3) if has_serras else ORB_DMG
                
                for i in range(ORB_COUNT):
                    rad = math.radians(orb_rot_angle + i * (360/ORB_COUNT))
                    orb_p = player.pos + pygame.Vector2(math.cos(rad), math.sin(rad)) * ORB_DISTANCE
                    for e in enemies:
                        if orb_p.distance_to(e.pos) < 50:
                            tick_dmg = current_orb_dmg * dt * 10
                            if random.random() < CRIT_CHANCE: tick_dmg *= 2
                            
                            e.hp -= tick_dmg; 
                            if e.hp <= 0: 
                                if player.ult_charge < player.ult_max: player.ult_charge += 1
                                gems.add(Gem(e.pos, loader)); e.kill(); kills += 1

            spawn_t += dt

            # ── OBSTÁCULOS GRADUAIS ──────────────────────────────────────────────
            # Espalhados pelo mundo desde o início, sem explosão ao nascer.
            # Usamos posições fixas de mundo (não relativas ao player) para que
            # o jogador vá encontrando-os à medida que explora/corre.
            obstacle_spawn_t += dt
            if (obstacle_spawn_t >= obstacle_spawn_interval
                    and obstacle_total_placed < OBSTACLE_MAX_GRADUAL):
                obstacle_spawn_t -= obstacle_spawn_interval
                # Distribui obstáculos em anel largo ao redor da posição atual
                # (600-1800 px) — longe o suficiente para não surgir na tela
                angle_rand = random.uniform(0, 2 * math.pi)
                dist_rand  = random.uniform(600, 1800)
                obs_pos    = player.pos + pygame.Vector2(
                    math.cos(angle_rand) * dist_rand,
                    math.sin(angle_rand) * dist_rand,
                )
                obstacles.add(Obstacle(obs_pos, loader, random.randint(0, 3)))
                obstacle_total_placed += 1
                # Intervalo diminui gradualmente (mais obstáculos por minuto)
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
                        DIFFICULTIES[selected_difficulty],
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
                enemies.add(create_enemy("boss", boss_pos, DIFFICULTIES[selected_difficulty], time_scale=time_scale, boss_tier=bosses_spawned))
                warn_txt = font_l.render("⚠️ ALERTA DE CHEFÃO ⚠️", True, (255, 0, 0))
                screen.blit(warn_txt, warn_txt.get_rect(center=(SCREEN_W//2, SCREEN_H//2 - 200)))
                play_sfx("ult")

            # --- Mini Boss ---
            if game_time >= MINI_BOSS_SPAWN_TIME and "mini_boss_test" not in triggered_hordes:
                triggered_hordes.add("mini_boss_test")
                mb_pos = player.pos + pygame.Vector2(1000, 0)
                enemies.add(create_enemy("mini_boss", mb_pos, DIFFICULTIES[selected_difficulty], time_scale=time_scale))
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
                    enemies.add(create_enemy("agis", agis_pos, DIFFICULTIES[selected_difficulty],
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
                for i in range(16):   # reduzido de 24→16 para ser menos agressivo
                    angle    = math.radians(i * (360 / 16))
                    wall_pos = player.pos + pygame.Vector2(math.cos(angle), math.sin(angle)) * 700
                    obstacles.add(Obstacle(wall_pos, loader, random.randint(0, 3)))
                
            if spawn_t >= current_spawn_rate:
                spawn_t = 0
                sp = player.pos + pygame.Vector2(random.choice([-1,1])*1100, random.randint(-600,600))

                if game_time < 30:
                    # Fase inicial: bat e runner
                    kind_early = random.choices(["bat", "runner"], weights=[60, 40], k=1)[0]
                    enemies.add(create_enemy(kind_early, sp, DIFFICULTIES[selected_difficulty], time_scale=time_scale))
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

                    if selected_difficulty in ["DIFÍCIL", "HARDCORE"]:
                        spawn_list.extend(["slime", "minotauro"])
                        spawn_weights.extend([15, 15])
                        # Rat — apenas nas dificuldades harder, a partir de 2 min
                        if game_time >= 120:
                            spawn_list.append("rat")
                            spawn_weights.append(20)

                    chosen_enemy = random.choices(spawn_list, weights=spawn_weights, k=1)[0]
                    elite_chance = min(0.15, 0.03 + (game_time / 480.0) * 0.05)
                    is_elite     = random.random() < elite_chance

                    enemies.add(create_enemy(chosen_enemy, sp, DIFFICULTIES[selected_difficulty], time_scale=time_scale, is_elite=is_elite))

            enemies.update(
                dt,
                player.pos,
                cam,
                obstacles,
                enemy_projectiles,
                puddles,
                loader,
                selected_pact,
                ModularEnemyProjectile,
                Puddle,
                SHOOTER_PROJ_IMAGE,
                obstacle_grid_index,
            )
            puddles.update(dt, cam)
            doom_seals.update(dt, cam)

            # --- Projéteis do Agis ---
            for e in list(enemies):
                if e.kind != "agis":
                    continue
                agis_dmg = 1.5 * DIFFICULTIES[selected_difficulty].get("dmg_mult", 1.0)

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
            for e in list(enemies):
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

            # --- Separação de inimigos (evita empilhamento) ---
            SEP_DIST  = 52
            SEP_FORCE = 18.0
            enemy_list = list(enemies)
            for i, ea in enumerate(enemy_list):
                if ea.kind in ("boss", "agis"):
                    continue
                for eb in enemy_list[i + 1:]:
                    if eb.kind in ("boss", "agis"):
                        continue
                    diff = ea.pos - eb.pos
                    d    = diff.length()
                    if 0 < d < SEP_DIST:
                        push = diff.normalize() * SEP_FORCE * dt
                        ea.pos += push
                        eb.pos -= push

            # Decorações animadas da floresta
            if selected_bg == "forest" and forest_deco_manager is not None:
                forest_deco_manager.update(dt, cam, SCREEN_W, SCREEN_H, player.pos)

            # Decorações do dungeon + colisão BDS
            if selected_bg == "dungeon" and dungeon_deco_manager is not None:
                dungeon_deco_manager.update(dt, cam, SCREEN_W, SCREEN_H, player.pos)
                dungeon_deco_manager.push_player(player)

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
                
                hits = pygame.sprite.spritecollide(p, enemies, False, projectile_enemy_collision)
                for hit in hits:
                    if hit not in p.hit_enemies:
                        dmg_dealt = p.dmg
                        is_crit = random.random() < CRIT_CHANCE
                        if is_crit:
                            dmg_dealt *= CRIT_DMG_MULT
                            hitstop_timer = 0.03
                        
                        hit.hp -= dmg_dealt
                        p.hit_enemies.append(hit)
                        play_sfx("hit") 

                        if EXECUTE_THRESH > 0 and hit.kind != "boss":
                            if hit.hp > 0 and (hit.hp / hit.max_hp) <= EXECUTE_THRESH:
                                hit.hp = 0
                        
                        hit.flash_timer = 0.1 
                        
                        if is_melee:
                            knock_dir = (hit.pos - player.pos).normalize()
                            knock_force = 15.0 
                        else:
                            knock_dir = p.vel.normalize() if p.vel.length() > 0 else pygame.Vector2(1,0)
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
                            
                            exp_pos = pygame.Vector2(p.pos)
                            active_explosions.append(ExplosionAnimation(exp_pos, current_exp_rad, explosion_frames_raw))
                            play_sfx("explosion") 
                            for e in enemy_batch_index.enemies_in_radius(exp_pos, current_exp_rad):
                                if exp_pos.distance_to(e.pos) < current_exp_rad: 
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
                            for _ in range(burst_count):
                                particles.add(Particle(hit.pos, kill_color, random.randint(4, 8), random.randint(120, 240), random.uniform(0.25, 0.55)))
                            if hit.kind == "boss":
                                shake_timer = 0.6; shake_strength = 18
                            elif hit.kind == "agis":
                                shake_timer = 0.7; shake_strength = 22
                            elif hit.kind == "mini_boss":
                                shake_timer = 0.4; shake_strength = 12
                            gems.add(Gem(hit.pos, loader)); hit.kill(); kills += 1
                            save_data["stats"]["total_kills"] += 1
                            update_mission_progress("kills", 1)
                            if hit.kind == "boss":
                                session_boss_kills += 1
                                save_data["stats"]["boss_kills"] += 1
                                update_mission_progress("boss", 1)
                                drops.add(create_drop(hit.pos, "chest"))
                            elif hit.kind == "agis":
                                # Agis dropa baú + várias moedas
                                session_boss_kills += 1
                                save_data["stats"]["boss_kills"] += 1
                                update_mission_progress("boss", 1)
                                drops.add(create_drop(hit.pos, "chest"))
                                gold_count = getattr(hit, "gold_drops", 15)
                                for gi in range(gold_count):
                                    offset = pygame.Vector2(random.randint(-80, 80), random.randint(-80, 80))
                                    drops.add(create_drop(hit.pos + offset, "coin"))
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
                                p.hit_enemies.pop()

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
                    xp += GEM_XP; g.kill(); play_sfx("gem")

            for d in list(drops):
                if d.rect.colliderect(player.rect):
                    if d.kind == "coin":
                        coin_value = 50 * DIFFICULTIES[selected_difficulty]["gold_mult"]
                        run_gold_collected += coin_value
                        save_data["gold"] += coin_value
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
                options = pick_upgrades_with_synergy(list(UPGRADE_POOL.keys()), player_upgrades)
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
        if state == "MENU":
            draw_menu_background(screen, m_pos, dt)

            # Logo alinhada ao lado esquerdo, acima dos botões do menu
            if menu_logo_img is not None:
                logo_x = menu_btns[0].rect.left
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

            selected_btn = hovered_menu_btn or menu_btns[0]
            pv_title, pv_desc = menu_preview_map.get(selected_btn.text, ("Modo", "Selecione uma opcao."))
            preview_rect = pygame.Rect(int(SCREEN_W * 0.55), int(SCREEN_H * 0.56), int(SCREEN_W * 0.38), 210)
            draw_dark_panel(screen, preview_rect, alpha=170, border_color=UI_THEME["faded_gold"])
            screen.blit(font_m.render(pv_title, True, UI_THEME["old_gold"]), (preview_rect.x + 20, preview_rect.y + 18))

            words = pv_desc.split(" ")
            lines = []
            current = []
            max_w = preview_rect.width - 40
            for w in words:
                candidate = " ".join(current + [w]).strip()
                if font_s.render(candidate, True, UI_THEME["mist"]).get_width() <= max_w:
                    current.append(w)
                else:
                    if current:
                        lines.append(" ".join(current))
                    current = [w]
            if current:
                lines.append(" ".join(current))

            for i, line in enumerate(lines[:3]):
                screen.blit(font_s.render(line, True, UI_THEME["mist"]), (preview_rect.x + 20, preview_rect.y + 66 + i * 28))

            hint = load_dark_font(16, bold=True).render("Dica: ENTER inicia quando estiver na selecao.", True, UI_THEME["faded_gold"])
            screen.blit(hint, (preview_rect.x + 20, preview_rect.bottom - 34))

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
                y_base = SCREEN_H * 0.29 + i * 120
                box_rect = pygame.Rect(SCREEN_W/2 - 300, y_base, 600, 100)
                pygame.draw.rect(screen, (30, 30, 50, 200), box_rect, border_radius=10)
                pygame.draw.rect(screen, (100, 100, 255), box_rect, 2, border_radius=10)

                title = font_m.render(m['name'], True, (255, 255, 100))
                screen.blit(title, (box_rect.x + 20, box_rect.y + 10))
                desc = font_s.render(m['desc'], True, (200, 200, 200))
                screen.blit(desc, (box_rect.x + 20, box_rect.y + 55))

                progress = m['progress'] / m['goal']
                prog_bar_rect = pygame.Rect(box_rect.x + 20, box_rect.y + 80, 300, 15)
                pygame.draw.rect(screen, (0,0,0), prog_bar_rect)
                pygame.draw.rect(screen, (0, 255, 0), (prog_bar_rect.x, prog_bar_rect.y, prog_bar_rect.width * progress, prog_bar_rect.height))
                pygame.draw.rect(screen, (255,255,255), prog_bar_rect, 1)

                if m['completed']:
                    if m['claimed']:
                        claim_txt = font_s.render("COLETADO!", True, (100, 255, 100))
                        screen.blit(claim_txt, (box_rect.right - 150, box_rect.centery - 10))
                    else:
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
                    sd_txt = load_dark_font(18).render(skill["desc"], True, (200, 200, 200))
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
            _tit_sf   = load_dark_font(19, bold=True).render(
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
            _SIZE_MULT = {0: 2.20, 1: 1.85, 2: 2.45, 3: 2.00, 4: 2.30, 5: 2.40}   # 0=guerreiro 1=caçador 2=mago 3=vampire 4=demônio 5=golem

            for i in range(len(char_ids)):
                btn   = char_btns[i]
                cdata = CHAR_DATA[char_ids[i]]

                # Idle animation — mesmo sprite do jogo parado
                idle = menu_idle_anims[i] if i < len(menu_idle_anims) else menu_char_anims[i]

                cx = ox + int(COL_CX[i] * pscale)
                # Descer +50% do raio da célula para enquadrar personagem no quadrado
                cy = oy + int(ROW_CY[0] * pscale) + int(chw * 0.50)

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
                    lk = load_dark_font(14, bold=True).render(
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
                nm = load_dark_font(22, bold=True).render(cdata["name"], True, col_name)
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
                    ls = load_dark_font(13).render(label, True, UI_THEME["mist"])
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
                ult = load_dark_font(13).render(cdata["desc"], True, UI_THEME["mana_blue"])
                screen.blit(ult, ult.get_rect(centerx=sp_x + SP_W // 2, top=cur_y))
                cur_y += ult.get_height() + 6

                if btn.locked:
                    lk2 = load_dark_font(13, bold=True).render(
                        "🔒 BLOQUEADO", True, UI_THEME["blood_red"])
                    screen.blit(lk2, lk2.get_rect(centerx=sp_x + SP_W // 2, top=cur_y))
                    if btn.lock_req:
                        rq = load_dark_font(11).render(btn.lock_req, True, (170, 130, 110))
                        screen.blit(rq, rq.get_rect(centerx=sp_x + SP_W // 2, top=cur_y + 18))
                else:
                    ht = load_dark_font(12).render("Clique para selecionar", True, (150, 150, 120))
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
                            tt = load_dark_font(15).render(btn.lock_req, True, (210, 185, 165))
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
            st_x, st_y = int(cam.x % bg_w) - bg_w, int(cam.y % bg_h) - bg_h
            for x in range(st_x, SCREEN_W + bg_w, bg_w):
                if x + bg_w < 0 or x > SCREEN_W: continue
                for y in range(st_y, SCREEN_H + bg_h, bg_h):
                    if y + bg_h < 0 or y > SCREEN_H: continue
                    screen.blit(ground_img, (x, y))

            # Decorações animadas da floresta (fogueira, bandeira) — desenhadas sobre o chão
            if selected_bg == "forest" and forest_deco_manager is not None:
                forest_deco_manager.draw(screen, SCREEN_W, SCREEN_H)

            # Decorações de chão do dungeon (pentagrama, BDS, dinossauro)
            if selected_bg == "dungeon" and dungeon_deco_manager is not None:
                dungeon_deco_manager.draw_floor(screen, SCREEN_W, SCREEN_H)

            puddles.draw(screen)
            doom_seals.draw(screen)
            obstacles.draw(screen); gems.draw(screen); drops.draw(screen); projectiles.draw(screen); enemy_projectiles.draw(screen); enemies.draw(screen)
            
            for e in enemies:
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

            particles.draw(screen)
            damage_texts.draw(screen) 

            if 'darkness_timer' in locals() and darkness_timer > 0:
                dark_surf = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
                dark_surf.fill((0, 0, 0, 230))
                pygame.draw.circle(dark_surf, (0, 0, 0, 0), (SCREEN_W//2, SCREEN_H//2), 250)
                screen.blit(dark_surf, (0, 0))
            
            if AURA_DMG > 0:
                current_aura_range = AURA_RANGE * 2 if has_buraco_negro else AURA_RANGE
                _aura_stale = (
                    not hasattr(main, "_last_aura_range")
                    or main._last_aura_range != current_aura_range
                    or not hasattr(main, "_aura_cache")
                    or len(main._aura_cache) != len(aura_frames)
                )
                if _aura_stale:
                    main._last_aura_range = current_aura_range
                    _asize = current_aura_range * 2
                    _scaled = []
                    for f in aura_frames:
                        # Usa surface SRCALPHA para premultiplicar alpha e evitar
                        # quadrados brancos causados por pixels transparentes com RGB != 0
                        _tmp = pygame.Surface((_asize, _asize), pygame.SRCALPHA)
                        _tmp.fill((0, 0, 0, 0))
                        _tmp.blit(pygame.transform.scale(f, (_asize, _asize)), (0, 0))
                        _scaled.append(_tmp)
                    main._aura_cache = _scaled
                    if has_buraco_negro:
                        for f in main._aura_cache: f.fill((100, 0, 150), special_flags=pygame.BLEND_RGB_MULT)

                img = main._aura_cache[aura_frame_idx % len(main._aura_cache)]
                # Overlay intermediário para blending aditivo correto (sem quadrados brancos)
                if not hasattr(main, "_aura_overlay") or main._aura_overlay.get_size() != (SCREEN_W, SCREEN_H):
                    main._aura_overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
                main._aura_overlay.fill((0, 0, 0, 0))
                main._aura_overlay.blit(img, img.get_rect(center=(SCREEN_W // 2, SCREEN_H // 2)))
                screen.blit(main._aura_overlay, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
                
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
                CARD_W, CARD_H = 600, 130
                for i, key in enumerate(up_keys):
                    y_pos = int(SCREEN_H*0.28 + i*157)
                    rect = pygame.Rect(SCREEN_W//2 - CARD_W//2, y_pos, CARD_W, CARD_H)
                    up_options.append(rect)
                    rarity_name, rarity_data = up_rarities[i]
                    hovered = rect.collidepoint(m_pos)

                    # Sprite base (skills.png carta medieval)
                    if skill_card_sprites and i < len(skill_card_sprites):
                        spr = skill_card_sprites_hover[i] if hovered else skill_card_sprites[i]
                        screen.blit(spr, rect.topleft)
                    else:
                        pygame.draw.rect(screen, (30,30,40), rect, border_radius=10)

                    # Borda colorida pela raridade (cached por cor para evitar Surface por frame)
                    if not hasattr(main, "_border_surf_cache"):
                        main._border_surf_cache = {}
                    _border_key = tuple(rarity_data["color"][:3])
                    if _border_key not in main._border_surf_cache:
                        _bs = pygame.Surface((CARD_W, CARD_H), pygame.SRCALPHA)
                        r, g, b = _border_key
                        pygame.draw.rect(_bs, (r, g, b, 55),  _bs.get_rect(), border_radius=9)
                        pygame.draw.rect(_bs, (r, g, b, 200), _bs.get_rect(), 3, border_radius=9)
                        main._border_surf_cache[_border_key] = _bs
                    screen.blit(main._border_surf_cache[_border_key], rect.topleft)

                    # Ícone do upgrade
                    icon = upg_images.get(key, loader.load_image("icon_default", (64, 64)))
                    screen.blit(icon, (rect.x + 18, rect.centery - 32))

                    # Cores de texto estilo pergaminho medieval
                    txt_col    = (255, 215, 100) if hovered else (220, 190, 120)
                    shadow_col = (80,  40,  0)   if hovered else (60,  30,  0)
                    desc_col   = (215, 190, 130) if hovered else (180, 158, 100)

                    # Nome do upgrade
                    title_surf = font_m.render(key, True, txt_col)
                    title_sh   = font_m.render(key, True, shadow_col)
                    tx, ty = rect.x + 100, rect.y + 12
                    screen.blit(title_sh, (tx + 2, ty + 2))
                    screen.blit(title_surf, (tx, ty))

                    # Descrição
                    desc_surf = font_s.render(get_upgrade_description(key), True, desc_col)
                    screen.blit(desc_surf, (rect.x + 100, rect.y + 60))

                    # Badge de raridade (canto superior direito)
                    rarity_txt = font_s.render(rarity_name, True, rarity_data["color"])
                    screen.blit(rarity_txt, (rect.right - rarity_txt.get_width() - 14, rect.y + 10))


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

            if state == "PAUSED":
                overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
                overlay.fill((UI_THEME["void_black"][0], UI_THEME["void_black"][1], UI_THEME["void_black"][2], 195)) 
                screen.blit(overlay, (0, 0))
                    
                msg = font_l.render("JOGO PAUSADO", True, UI_THEME["old_gold"])
                screen.blit(msg, (SCREEN_W//2 - msg.get_width()//2, SCREEN_H * 0.15))
                    
                panel_w, panel_h = 450, 550
                panel_x = int(SCREEN_W * 0.15)
                panel_y = int(SCREEN_H * 0.3)
                panel_rect = pygame.Rect(panel_x, panel_y, panel_w, panel_h)
                    
                draw_dark_panel(screen, panel_rect, alpha=190, border_color=UI_THEME["old_gold"])
                    
                stat_title = font_m.render("STATUS DO HEROI", True, UI_THEME["old_gold"])
                screen.blit(stat_title, stat_title.get_rect(center=(panel_rect.centerx, panel_rect.y + 40)))
                    
                stats_lines = [
                        f"VIDA MÁXIMA: {int(PLAYER_MAX_HP)}",
                        f"VELOCIDADE: {int(PLAYER_SPEED)}",
                        f"DANO BASE: {PROJECTILE_DMG}",
                        f"CRÍTICO: {int(CRIT_CHANCE*100)}%",
                        f"PROJÉTEIS (QTD): {PROJ_COUNT}",
                        f"PERFURAÇÃO: {PROJ_PIERCE}",
                        f"TEMPO DE RECARGA: {SHOT_COOLDOWN:.2f}s",
                        f"RAIO DE EXPLOSÃO: {EXPLOSION_RADIUS}",
                        f"DANO DE AURA: {AURA_DMG}",
                        f"QTD DE ORBES: {ORB_COUNT}",
                        f"ALCANCE (ÍMÃ): {int(PICKUP_RANGE)}"
                    ]
                    
                start_y = panel_rect.y + 100
                for idx, line in enumerate(stats_lines):
                        line_txt = font_s.render(line, True, UI_THEME["mist"])
                        screen.blit(line_txt, (panel_rect.x + 30, start_y + (idx * 40)))

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

        # Cursor personalizado — desenhado por último, sempre por cima de tudo
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
    options = [
        ("Resolução", temp_settings["video"]["resolution"], _get_available_resolutions()),
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
        "Setas Fora da Tela": {"key": "show_offscreen_arrows", "values": ["Off", "On"]},
        "Dificuldade Padrão": {"key": "default_difficulty", "values": ["Fácil", "Médio", "Difícil", "Hardcore"]}
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
