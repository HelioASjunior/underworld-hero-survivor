#!/usr/bin/env python3
"""
Script para testar detecção de resoluções disponíveis
"""

import pygame
import sys

pygame.init()

print("=" * 70)
print("TESTE DE RESOLUÇÕES DISPONÍVEIS")
print("=" * 70)

# Informações do monitor
info = pygame.display.Info()
print(f"\nInformações do Monitor:")
print(f"  Resolução atual: {info.current_w}x{info.current_h}")
print(f"  Largura máxima: {info.current_w}")
print(f"  Altura máxima: {info.current_h}")

# Testar pygame.display.list_modes()
print(f"\npygame.display.list_modes() retorna:")
modes = pygame.display.list_modes()
if modes is None:
    print("  None (driver não reporta resoluções)")
elif modes == -1:
    print("  -1 (driver suporta qualquer resolução)")
elif isinstance(modes, list):
    print(f"  Lista com {len(modes)} resoluções:")
    for mode in modes[:20]:  # Mostrar primeiras 20
        print(f"    {mode[0]}x{mode[1]}")
    if len(modes) > 20:
        print(f"    ... e mais {len(modes) - 20} resoluções")
else:
    print(f"  Tipo desconhecido: {type(modes)}")

# Agora importar a função do jogo
sys.path.insert(0, '.')
try:
    from jogo_final import _get_available_resolutions
    resolutions = _get_available_resolutions()
    print(f"\n_get_available_resolutions() retorna {len(resolutions)} resoluções:")
    for res in resolutions:
        print(f"  {res}")
except Exception as e:
    print(f"\nErro ao chamar _get_available_resolutions(): {e}")

print("\n" + "=" * 70)
