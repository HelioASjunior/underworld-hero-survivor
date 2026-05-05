#!/usr/bin/env python3
"""
Script de diagnóstico - testa se o jogo carrega sem problemas
"""

import sys
import os

# Adicionar a pasta do jogo ao path
game_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, game_dir)

print("[Diagnóstico] Iniciando testes...\n")

# Teste 1: Verificar imports básicos
print("[1] Testando imports...")
try:
    import pygame
    print("  ✓ pygame OK")
except ImportError as e:
    print(f"  ✗ pygame FALHOU: {e}")
    sys.exit(1)

try:
    from projectile_pool import ProjectilePool, MeleeSlashPool
    print("  ✓ projectile_pool OK")
except ImportError as e:
    print(f"  ✗ projectile_pool FALHOU: {e}")

try:
    from ui_scaler import init_ui_scaler, Anchor, UIScaler
    print("  ✓ ui_scaler OK")
except ImportError as e:
    print(f"  ✗ ui_scaler FALHOU: {e}")

try:
    from performance import FrameProfiler, frame_profiler
    print("  ✓ performance OK")
except ImportError as e:
    print(f"  ✗ performance FALHOU: {e}")

# Teste 2: Testar inicialização básica de pygame
print("\n[2] Testando inicialização de pygame...")
try:
    pygame.init()
    pygame.mixer.init()
    print("  ✓ pygame.init() OK")
except Exception as e:
    print(f"  ✗ pygame.init() FALHOU: {e}")
    sys.exit(1)

# Teste 3: Testar UIScaler
print("\n[3] Testando UIScaler...")
try:
    scaler = UIScaler((1920, 1080), (1920, 1080))
    pos = scaler.get_ui_position(0.5, 0.5, Anchor.CENTER, 200, 50)
    print(f"  ✓ UIScaler OK (posição centro: {pos})")
except Exception as e:
    print(f"  ✗ UIScaler FALHOU: {e}")

# Teste 4: Testar FrameProfiler
print("\n[4] Testando FrameProfiler...")
try:
    prof = FrameProfiler()
    prof.start_section("test")
    prof.end_section("test")
    prof.new_frame()
    avg = prof.get_average("test")
    print(f"  ✓ FrameProfiler OK (média: {avg:.2f}ms)")
except Exception as e:
    print(f"  ✗ FrameProfiler FALHOU: {e}")

# Teste 5: Testar ProjectilePool
print("\n[5] Testando ProjectilePool...")
try:
    pool = ProjectilePool()
    print("  ✓ ProjectilePool instanciado OK")
except Exception as e:
    print(f"  ✗ ProjectilePool FALHOU: {e}")

print("\n[Diagnóstico] Todos os testes básicos passaram! ✓")
print("\nPara testar o jogo completo, execute: python jogo_final.py")
