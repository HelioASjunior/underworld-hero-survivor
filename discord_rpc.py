"""
Discord Rich Presence para UnderWorld Hero.

Requisito: pip install pypresence

Para configurar:
  1. Acesse https://discord.com/developers/applications
  2. Clique em "New Application" e nomeie "UnderWorld Hero"
  3. Copie o "Application ID" e cole em CLIENT_ID abaixo
  4. No menu esquerdo vá em "Rich Presence" → "Art Assets"
  5. Faça upload das imagens com os seguintes nomes:
       icone   → ícone principal do jogo
       dungeon → screenshot/arte da Masmorra
       forest  → screenshot/arte da Floresta
       volcano → screenshot/arte do Vulcão
       moon    → screenshot/arte da Lua
"""

import time

CLIENT_ID = "1511032792933335190"

try:
    from pypresence import Presence, DiscordNotFound, DiscordError, PipeClosed
    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False

_rpc = None
_connected = False
_last_payload: dict = {}
_last_send: float = 0.0
_MIN_INTERVAL = 15.0  # segundos — limite do Discord


def connect() -> bool:
    global _rpc, _connected
    if not _AVAILABLE:
        print("[Discord RPC] pypresence não instalado. Execute: pip install pypresence")
        return False
    if CLIENT_ID == "SEU_APPLICATION_ID_AQUI":
        print("[Discord RPC] CLIENT_ID não configurado em discord_rpc.py")
        return False
    try:
        _rpc = Presence(CLIENT_ID)
        _rpc.connect()
        _connected = True
        print("[Discord RPC] Conectado ao Discord com sucesso.")
        return True
    except Exception as e:
        print(f"[Discord RPC] Não foi possível conectar ao Discord: {e}")
        _connected = False
        return False


def update(payload: dict) -> None:
    """Atualiza a presença se o payload mudou ou já passaram 15 s."""
    global _last_payload, _last_send, _connected
    if not _connected or _rpc is None:
        return
    changed = payload != _last_payload
    elapsed = time.time() - _last_send
    if not changed and elapsed < _MIN_INTERVAL:
        return
    try:
        _rpc.update(**payload)
        _last_payload = dict(payload)
        _last_send = time.time()
    except Exception as e:
        print(f"[Discord RPC] Erro ao atualizar presença: {e}")
        _connected = False


def clear() -> None:
    global _connected
    if _rpc and _connected:
        try:
            _rpc.clear()
        except Exception:
            pass


def close() -> None:
    global _rpc, _connected
    if _rpc and _connected:
        try:
            _rpc.clear()
            _rpc.close()
        except Exception:
            pass
    _connected = False
    _rpc = None
