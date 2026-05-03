# UnderWorld Hero

![Python](https://img.shields.io/badge/Python-3.12-blue?style=for-the-badge&logo=python)
![Pygame-CE](https://img.shields.io/badge/Pygame--CE-2.5.7-green?style=for-the-badge)
![NumPy](https://img.shields.io/badge/NumPy-2.4.4-013243?style=for-the-badge&logo=numpy)
![Numba](https://img.shields.io/badge/Numba-0.65-00A3E0?style=for-the-badge)
![Status](https://img.shields.io/badge/Status-Em_Desenvolvimento-yellow?style=for-the-badge)

Jogo de sobrevivência estilo bullet hell desenvolvido em Python com Pygame-CE, com foco em combate rápido, progressão por upgrades, múltiplos personagens, sistema de pactos e pipeline de performance baseado em indexação espacial (NumPy + Numba JIT + Cython opcional).

English version: [README.en.md](README.en.md)

## Sumário

- [Visão geral](#visao-geral)
- [Personagens](#personagens)
- [Inimigos e Chefes](#inimigos-e-chefes)
- [Sistemas de jogo](#sistemas-de-jogo)
- [Interface e UI medieval](#interface-e-ui-medieval)
- [Arquitetura do projeto](#arquitetura-do-projeto)
- [Requisitos](#requisitos)
- [Instalação e execução](#instalacao-e-execucao)
- [Performance e build](#performance-e-build)
- [Distribuição com PyInstaller](#distribuicao-com-pyinstaller)
- [Controles](#controles)
- [Configurações, save e persistência](#configuracoes-save-e-persistencia)
- [Resolução e compatibilidade](#resolucao-e-compatibilidade)
- [Debug e benchmark de performance](#debug-e-benchmark-de-performance)
- [Estrutura de pastas](#estrutura-de-pastas)
- [Roadmap](#roadmap)
- [Contribuição](#contribuicao)
- [Licença](#licenca)

---

## Visão geral

UnderWorld Hero é um survivor roguelike onde o jogador enfrenta ondas crescentes de inimigos, escolhe upgrades a cada nível e tenta sobreviver o maior tempo possível. A cada run é possível escolher personagem, dificuldade, pacto e bioma, gerando combinações distintas de desafio e estilo.

Destaques gerais:

- Combate em tempo real com alto volume de inimigos em tela.
- Progressão por nível com seleção de upgrades e evoluções sinérgicas.
- 7 personagens jogáveis com estilos e ultimates próprios.
- 4 níveis de dificuldade e 4 pactos com modificadores de risco/recompensa.
- Missões diárias, meta-progresso e árvore de talentos permanente.
- 3 slots de run independentes com estado completo salvo.
- Interface 100% temática medieval com sprites ornamentados.

---

## Personagens

| Personagem | HP | Velocidade | Dano | Mana | Ultimate | Desbloqueio |
|---|---|---|---|---|---|---|
| Guerreiro | 100 | 280 | 25 | 50 | Fúria do Guerreiro | Padrão |
| Caçador | 63 | 340 | 38 | 75 | Chuva de Flechas | Padrão |
| Mago | 75 | 260 | 25 | 200 | Congelamento Temporal | Padrão |
| Vampire | 88 | 300 | 38 | 100 | Tempestade Sombria | Padrão |
| Demônio | 75 | 290 | 38 | 100 | Chama Infernal | Padrão |
| Golem | 113 | 240 | 50 | 50 | Golpe da Terra | Padrão |
| Esqueleto | 95 | 265 | 44 | 75 | Frenesi Sanguinário | Derrote 12 Chefões |
| Furacão | 80 | 285 | 40 | 85 | Vórtice da Tempestade | Derrote 15 Chefões |

Todos os personagens possuem spritesheets direcionais (cima/baixo/esquerda/direita) com animações de andar, idle e atacar carregadas via `characters.py`.

---

## Inimigos e Chefes

### Inimigos — Todas as dificuldades

| Tipo | HP base | Vel. base | Aparição | Descrição |
|---|---|---|---|---|
| Bat | 28 | 145 | 0s | Morcego com movimento senoidal |
| Runner | 50 | 150 | 0s | Corredor rápido em linha reta |
| Tank | 260 | 65 | 30s | Alto HP, lento, corpo a corpo |
| Shooter | 80 | 90 | 30s | Atira projéteis à distância |
| Goblin | 80 | 160 | 1 min | Rápido com zigzag moderado |
| Beholder | 200 | 85 | 1.5 min | Flutuante, movimento suave |
| Orc | 300 | 75 | 3 min | Grande, corpo a corpo tanque |
| Elite | 1500 | 85 | 30s+ | Versão reforçada com drop de ouro garantido |

> HP e velocidade escalam com o multiplicador de dificuldade e com o tempo de jogo (+20 % de HP/dano por minuto até 6×).

### Inimigos — Somente Difícil / Hardcore

| Tipo | HP base | Vel. base | Aparição | Descrição |
|---|---|---|---|---|
| Slime | 130 | 110 | 30s | Inimigo equilibrado com aura escura |
| Minotauro | 200 | 130 | 30s | Corpo a corpo, perseguição direta |
| Rat | 150 | 135 | 2 min | Grande (220px), zigzag agressivo |

### Inimigos — Exclusivos do Bioma Vulcão

Aparecem somente quando o bioma selecionado é Vulcão, a partir de 2 minutos de jogo.

| Tipo | HP base | Vel. base | Aparição | Descrição |
|---|---|---|---|---|
| Slime Fire | 280 | 125 | 2 min | Arrancada de fogo (2.8× vel), alto dano de contato |
| Slime Red | 220 | 110 | 2 min | Tanque lento com alto HP |
| Slime Yellow | 160 | 145 | 2 min | Ágil, menos HP, ataque rápido |

### Inimigos — Exclusivos dos Biomas Lua e Vulcão

Aparecem nos biomas Lua e Vulcão, a partir de 2 minutos de jogo.

| Tipo | HP base | Vel. base | Aparição | Descrição |
|---|---|---|---|---|
| Ghost | 200 | 120 | 2 min | Flutuação senoidal com arrancada fantasmal (2.5× vel); animação de morte própria |

### Chefes

| Tipo | HP base | Aparição | Descrição |
|---|---|---|---|
| Mini Boss | 6000 | ~10 min | Barra de vida própria, escala com tempo (+30 % × time_scale) |
| Chefe | escalável | 5 min (a cada 5 min) | Multi-fase, fica mais forte a cada onda |
| Agis | 10000 | 15 min (selo de invocação) | Boss lento, orbe dupla + magia em área a cada 5s (+25 % × time_scale) |

**Agis** é invocado por um selo animado (`doom_agis.png`) que aparece próximo ao herói ~30s antes do spawn. Possui ataque básico de projétil (orbe dupla roxa) e magia em área que dispara 8 orbes em todas as direções. Dropa baú + 15 moedas ao morrer.

Hordas são processadas em fila assíncrona (6 inimigos/frame) eliminando travamentos de CPU. Obstáculos surgem gradualmente desde o início da run — não em massa durante hordas.

---

## Sistemas de jogo

### Upgrades e Evoluções

- Pool de **218 upgrades** com 4 raridades: Comum, Raro, Épico, Lendário.
- A cada nível o jogador escolhe **1 entre 5 opções** (teclas 1–5 ou mouse).
- Sinergia: upgrades anteriores influenciam as opções oferecidas.
- Evoluções desbloqueiam versões aprimoradas ao atingir nível máximo.
- `TREVO SORTE` aumenta a raridade das próximas ofertas.
- Notificações visuais com fade-out ao aplicar upgrades.

#### Categorias de Upgrades (218 no total)

| Categoria | Quantidade | Exemplos de efeitos |
|---|---|---|
| Dano e Ataque | 30 | +dano, +crítico, execute, cadência |
| Projéteis | 25 | +projéteis, pierce, ricochete, velocidade |
| Defesa | 30 | +HP, regen, espinhos, lifesteal, vampirismo |
| Velocidade | 20 | +velocidade do herói, coleta |
| Magia / Orbes | 25 | orbes orbitais, explosões mágicas, combinações |
| Explosão | 15 | raio de explosão, dano em área |
| Utilidade | 30 | magnetismo, ouro, bônus de XP, cura |
| Especial | 25 | habilidades raras e combinações únicas |
| Upgrades clássicos | 18 | Fúria Demoníaca, Barreira de Gelo, etc. |

Novos mecânicos introduzidos pelos upgrades:
- **Lifesteal** — percentual do dano causado devolvido como HP.
- **Multiplicador de ouro** — aumenta o valor de moedas coletadas na run.
- **Bônus de XP** — aumenta XP ganho por gemas durante a run.

### Pactos

Modificadores opcionais escolhidos antes da run:

| Pacto | Efeito | Bônus |
|---|---|---|
| Sem Pacto | Nenhum modificador | — |
| Pacto da Pressa | Inimigos 50% mais rápidos | +50% Ouro |
| Pacto Frágil | -2 HP máximo | +30% XP |

### Dificuldades

| Dificuldade | HP inimigos | Velocidade | Dano | Ouro |
|---|---|---|---|---|
| Fácil | 0.7x | 0.8x | 0.5x | 0.8x |
| Médio | 1.0x | 1.0x | 1.0x | 1.0x |
| Difícil | 1.5x | 1.15x | 1.5x | 1.4x |
| Hardcore | 2.5x | 1.3x | 2.0x | 2.0x |

Difícil e Hardcore são desbloqueados por missões específicas.

### Biomas

| Bioma | Decorações | Trilha | Inimigos exclusivos |
|---|---|---|---|
| Dungeon | Decorações de chão animadas (pentagrama, dinossauro) via `DungeonDecoManager` | Sim | — |
| Floresta | Tilemap composto com tiles animados (fogueira, bandeira) via `ForestDecoManager` | Sim | — |
| Vulcão | Rochas, geiseres e colisões de ambiente via `VolcanoDecoManager` | Sim | Slime Fire, Slime Red, Slime Yellow, Ghost |
| Lua | Decorações temáticas de superfície lunar via `MoonDecoManager` | Sim | Ghost |

### Loja de Itens

A loja possui quatro abas principais:

| Aba | Categorias | Total de itens |
|---|---|---|
| Armas | Espadas, Machados, Lanças, Arcos, Cajados | 60 |
| Armaduras | Capacetes (12), Armaduras (12), Calças (12), Botas (10) | 46 |
| Utilitários | (em desenvolvimento) | — |
| Vender | Todos os itens do inventário | — |

Itens são comprados com ouro, ficam no inventário e podem ser arrastados para os slots de equipamento (drag-and-drop). Cada categoria tem estatísticas balanceadas com a progressão do jogo:

- **Armas**: aumentam ATK do personagem.
- **Escudos**: aumentam DEF e contribuem para Resistência a Dano.
- **Capacetes, Armaduras, Calças e Botas**: cada peça tem valor de DEF que contribui para Resistência a Dano (DEF / 600 por peça, cap total 55%).

### Sistema de Armaduras

Cada peça de armadura equipada reduz o dano recebido:

```
DAMAGE_RES = min(0.55, shield_def / 600 + soma(armor_def) / 600)
```

O painel de Status (tecla C) exibe os nomes das peças equipadas e a porcentagem de Resistência resultante.

### Missões e Talentos

- Missões com recompensas em ouro.
- Árvore de talentos permanente com painel expandido para acomodar todos os talentos por caminho.
- Unlocks de personagens, dificuldades e cosméticos por conquistas.

---

## Interface e UI medieval

Toda a interface usa sprites ornamentados medievais com fundo transparente (Photoroom). O texto é sempre renderizado dinamicamente por cima — nenhum texto fica gravado na imagem.

| Elemento | Sprite |
|---|---|
| Botões de todos os menus | `Barras de interface medieval ornamentada-Photoroom.png` (7 barras) |
| Cartas de seleção de skill (level-up) | `skills.png` (3 cartas) |
| Título e seção de configurações | `config.png` (barra grande + barra pequena) |
| Painéis de seleção de personagem | `painelguerreiro.png`, `painelcacador.png`, `painelmago.png` |
| Tela de seleção de dificuldade | `selecionar_dificuldade.png` |
| Sala do Herói (hub) | `sala_do_heroi.png` — botões Loja, Talentos e Pronto alinhados aos retângulos da imagem |
| Status do personagem (C) | `status.png` — nome, atributos e equipamentos alinhados às zonas da imagem |
| Inventário e equipamentos (I) | `inventario.png` — grade de itens + slots de arma, escudo, capacete, armadura, calças e botas |

O `AssetLoader` usa cache recursivo (`_build_cache`): arquivos podem estar em qualquer subpasta de `assets/` e são encontrados pelo nome sem alterar nenhuma chamada de código.

---

## Arquitetura do projeto

### Módulos principais

| Arquivo | Responsabilidade |
|---|---|
| `jogo_final.py` | Loop principal, estados de jogo, UI |
| `balance.py` | Fórmulas de progressão: XP, escala de inimigos, custo de upgrades, drop rates |
| `characters.py` | Classes de personagem, habilidades e ultimates |
| `enemies.py` | Inimigos, IA direcional, spritesheets, projéteis inimigos |
| `hud.py` | HUD in-game, tema visual, notificações de upgrade |
| `upgrades.py` | Pool de upgrades, sinergia, evoluções |
| `drops.py` | Gemas, itens e lógica de coleta |
| `combat/projectiles.py` | Projéteis, slashes e explosões com cache de frames |
| `forest_biome.py` | Tilemap de floresta, decorações animadas |
| `dungeon_biome.py` | Decorações de chão do dungeon |
| `volcano_biome.py` | Decorações, rochas e geiseres do vulcão |
| `moon_biome.py` | Decorações da superfície lunar |
| `spatial_index.py` | Índices espaciais, pathfinding A* em grid, métricas |
| `hot_kernels.py` | Kernels NumPy + Numba JIT com detecção automática de backend Cython |
| `hot_kernels_cy.pyx` | Implementação acelerada opcional em Cython |

### Decisões técnicas

- **Fila de spawn de hordas**: producer/consumer (6 inimigos/frame) — elimina picos de CPU.
- **Cache de explosões**: indexado por `(id(raw_frames), size)` — evita reescalonamento repetido.
- **AssetLoader recursivo**: `os.walk` em `assets/` mapeia stem → path completo; mover arquivos não quebra o código.
- **Resolução dinâmica**: `pygame.display.list_modes()` detecta modos do monitor em tempo real.
- **Spawn gradual de obstáculos**: timer decrescente desde o início da run em vez de bulk em hordas.
- **Fallback em camadas**: Cython opcional → Numba JIT → NumPy puro → Python puro, tudo automático.
- **Double buffering**: `pygame.DOUBLEBUF` ativo por padrão — reduz tearing e habilita aceleração de hardware no SDL2.

---

## Requisitos

- Python 3.12+
- Windows, Linux ou macOS
- Dependências runtime:
  - `pygame-ce` 2.5.7+ (Community Edition com SDL 2.32.10 ou superior)
  - `numpy` 2.4.4+
  - `numba` 0.65+ (JIT de kernels críticos; opcional mas recomendado)

> **Atenção:** O projeto usa **pygame-ce** (Community Edition), não o pygame original. Instalar ambos simultaneamente causa conflito — desinstale `pygame` antes de instalar `pygame-ce`.

### Por que Pygame-CE?

O projeto migrou para **Pygame Community Edition** (Pygame-CE) pelos seguintes benefícios:

1. **Drop-in replacement** — API 100% compatível com pygame original, sem refatoração necessária.
2. **Melhor performance** — Otimizações em drivers SDL2, redução de overhead em renderização e eventos.
3. **Suporte SDL3 (futuro)** — Aceleração GPU via SDL3: melhor FPS em cenas complexas com muitos sprites.
4. **Manutenção ativa** — Comunidade open-source mantendo e atualizando regularmente.
5. **Recursos extras** — Suporte aprimorado a spritesheets, efeitos de blending e transformações.

No contexto deste jogo (survivor com 100+ inimigos + UI animada), o Pygame-CE proporciona FPS mais consistente, especialmente em modos difíceis com muitas partículas e projéteis.

---

## Instalação e execução

### 1) Clonar repositório

```bash
git clone https://github.com/HelioASjunior/underworld-hero-survivor.git
cd underworld-hero-survivor
```

### 2) Criar ambiente virtual

Windows:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Linux/macOS:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

### 3) Instalar dependências

```bash
pip install -r requirements.txt
```

Isso instala:
- `pygame-ce` 2.5.7 (Community Edition)
- `numpy` 2.4.4 (processamento rápido de arrays para IA espacial)
- `numba` (compilador JIT para o kernel de separação de inimigos)

> Se já tiver `pygame` (original) instalado, remova com `pip uninstall pygame` antes.

### 4) Verificar instalação

```bash
python -c "import pygame; print(f'Pygame-CE versão: {pygame.version.vernum}')"
python -c "import numpy; print(f'NumPy versão: {numpy.__version__}')"
python -c "import hot_kernels; print('NUMBA_ACTIVE =', hot_kernels.NUMBA_ACTIVE)"
```

### 5) Executar

```bash
python jogo_final.py
```

Sem ativar o venv (Windows):

```powershell
.\venv\Scripts\python.exe jogo_final.py
```

**Primeira execução:** O jogo criará `settings.json` e `save_v2.json` na primeira vez. Na primeira inicialização com Numba, o kernel de separação é compilado e cacheado em disco (~2s extra uma única vez).

---

## Performance e build

### Performance base

O jogo já é otimizado em múltiplas camadas:

| Camada | Mecanismo | Benefício |
|---|---|---|
| Display | `pygame.DOUBLEBUF` ativo por padrão | Double buffering, reduz tearing |
| Renderização | Pygame-CE com SDL2 | Mais eficiente que pygame original |
| Cache de chão | Surface pré-renderizada do tilemap | ~54 blits/frame → 1 blit/frame no fundo |
| Frame time | Média móvel de 6 frames no `dt` | Elimina micro-stutters do Windows Scheduler |
| Separação de inimigos | Numba `@njit(cache=True)` | Kernel JIT compilado para código nativo |
| Consultas espaciais | NumPy vetorizado (`EnemyBatchIndex`) | Buscas O(n) em array sem loop Python |
| Spawn de hordas | Fila assíncrona (6/frame) | Elimina picos de CPU ao spawnar grupos |
| Cache de frames | Indexado por `(id(raw_frames), size)` | Sprites efeito pre-escalados, sem recomputar |

### Build opcional com Cython (avançado)

Para ganho adicional de performance nos kernels de pathfinding e IA, compile a extensão Cython. **Sem ela o jogo funciona normalmente via Numba + NumPy** — a compilação é totalmente opcional.

#### Kernels disponíveis

| Kernel | Função | Ganho típico |
|---|---|---|
| `radius_indices` | Inimigos dentro de raio (colisão de projéteis, pick-up range) | 4–6× vs Python puro |
| `nearest_index` | Inimigo mais próximo respeitando máscara de exclusão (targeting) | 4–6× vs Python puro |
| `batch_directions` | Direção normalizada para N inimigos de uma vez (movimento em batch) | 6–10× vs Python puro |
| `astar_cy` | Pathfinding A* com variáveis C internas, sem overhead de atributo Python | 4–8× vs Python puro |
| `positions_in_rect` | Índices dentro de retângulo para ataques AOE (slash, cone) | 4–6× vs Python puro |
| `enemy_separation` | Separação/repulsão entre inimigos (Numba `@njit`) | 3–6× vs Python puro |

O módulo `hot_kernels.py` detecta automaticamente qual backend está disponível e usa fallback individualmente: Cython → Numba JIT → NumPy → Python puro.

#### Benchmarks medidos (Intel i5, Python 3.12, GCC 15.2 -O3)

| Teste | Tempo |
|---|---|
| `radius_indices` × 1000 chamadas | ~12.6 ms |
| `batch_directions` × 1000 chamadas | ~14.5 ms |
| `astar_cy` × 500 chamadas | ~59.5 ms |

#### Instalar dependências de build

```bash
pip install -r requirements-dev.txt
```

#### Opção A: WinLibs GCC (recomendado, ~255 MB)

```powershell
winget install BrechtSanders.WinLibs.POSIX.UCRT
```

Após instalar, abra um novo terminal e compile:

```bash
python build_cython.py build_ext --inplace
```

#### Opção B: Visual C++ Build Tools

Instale o **Visual C++ Build Tools 2019+** e compile:

```bash
python build_cython.py build_ext --inplace
```

#### Verificar backends ativos

```bash
python -c "import hot_kernels; print('CYTHON_ACTIVE =', hot_kernels.CYTHON_ACTIVE, '| NUMBA_ACTIVE =', hot_kernels.NUMBA_ACTIVE)"
```

---

## Distribuição

O projeto inclui dois scripts de empacotamento para distribuir o jogo sem Python instalado.

### PyInstaller — empacota com interpretador (mais compatível)

```bash
pip install -r requirements-dev.txt

python build_dist.py              # pasta dist/UnderWorldHero/
python build_dist.py --onefile    # executável único dist/UnderWorldHero.exe
python build_dist.py --clean      # limpa antes de empacotar
```

**Resultado:** `dist/UnderWorldHero/UnderWorldHero.exe` ou `dist/UnderWorldHero.exe`

### Nuitka — compila para binário nativo (mais rápido)

Nuitka converte Python → C → executável nativo. Inicialização mais rápida, ~10–30% de ganho de velocidade em execução vs PyInstaller.

**Pré-requisito:** compilador C no PATH (WinLibs GCC ou Visual C++ Build Tools).

```bash
pip install -r requirements-dev.txt

python build_nuitka.py              # pasta dist-nuitka/jogo_final.dist/
python build_nuitka.py --onefile    # executável único
python build_nuitka.py --clean      # limpa antes de compilar
```

**Resultado:** `dist-nuitka/jogo_final.dist/jogo_final.exe` ou `dist-nuitka/jogo_final.exe`

---

## Controles

Reconfiguráveis em **Configurações → Controles**:

| Ação | Padrão |
|---|---|
| Movimentação | W A S D |
| Dash | Space |
| Ultimate | E |
| Pausar / Retomar | P |
| Menu rápido | Esc |
| Overlay de debug | F3 |
| Selecionar upgrade | 1 / 2 / 3 / 4 / 5 ou clique |
| Abrir inventário / equipamentos | I |
| Abrir status do personagem | C |

---

## Configurações, save e persistência

| Arquivo | Conteúdo |
|---|---|
| `settings.json` | Vídeo, áudio, controles, gameplay, acessibilidade |
| `save_v2.json` | Progresso global: ouro, talentos, unlocks, estatísticas |
| `run_slot_1~3.json` | Estado completo de cada slot de run |

Seções das configurações:

- **Vídeo**: resolução (dinâmica), tela cheia, VSync, limite de FPS, mostrar FPS.
- **Audio**: volume de música, volume de efeitos, mudo.
- **Controles**: remapeamento de teclas.
- **Gameplay**: auto-aplicar recompensa de baú, indicadores de inimigos fora de tela.
- **Acessibilidade**: opções extras de visualização.

---

## Resolução e compatibilidade

A lista de resoluções é detectada automaticamente via `pygame.display.list_modes()` ao abrir as configurações. Nenhum valor está fixo no código.

Exemplo de resoluções detectadas (variam por monitor):

```
1280x720  1366x768  1600x900  1920x1080  2560x1440  3840x2160
```

Comportamento de fallback:

- Se a resolução salva não couber no monitor atual → usa resolução nativa.
- Se o monitor não reportar lista de modos → usa lista padrão até 4K.
- Se `pygame.display.set_mode` falhar com as flags escolhidas → abre em janela simples com double buffering.

---

## Debug e benchmark de performance

### Overlay in-game (F3)

- FPS e tempo médio de frame.
- Contagem de inimigos, projéteis e partículas em tela.
- Consultas espaciais por frame e taxa de cache hit do A*.
- Backend ativo: Cython ON / Numba ON / NumPy fallback.

### Benchmark offline

```bash
python benchmark_spatial.py
```

---

## Estrutura de pastas

```text
underworld-hero-survivor/
├── jogo_final.py            # Loop principal e estados de jogo
├── balance.py               # Fórmulas de balanceamento e progressão
├── characters.py            # Personagens jogáveis
├── enemies.py               # Inimigos, IA e animações
├── hud.py                   # HUD e interface in-game
├── upgrades.py              # Upgrades, sinergia e evoluções
├── drops.py                 # Gemas e drops
├── forest_biome.py          # Bioma floresta (tilemap + decorações animadas)
├── dungeon_biome.py         # Bioma dungeon (decorações de chão)
├── volcano_biome.py         # Bioma vulcão (rochas, geiseres, colisões)
├── moon_biome.py            # Bioma lua (decorações lunares)
├── spatial_index.py         # Indexação espacial e pathfinding
├── hot_kernels.py           # Kernels NumPy / Numba / Cython
├── hot_kernels_cy.pyx       # Extensão Cython (opcional)
├── benchmark_spatial.py     # Benchmark de performance
├── build_cython.py          # Script de build Cython
├── build_dist.py            # Script de empacotamento PyInstaller
├── build_nuitka.py          # Script de compilação Nuitka (binário nativo)
├── combat/
│   └── projectiles.py       # Projéteis e explosões
├── assets/
│   ├── audio/               # Músicas e efeitos (.mp3)
│   ├── backgrounds/         # Fundos dos biomas
│   ├── characters/          # Sprites dos personagens
│   ├── effects/             # Auras, explosões, slashes, orbes
│   ├── enemies/             # Sprites de inimigos e chefes
│   ├── fonts/               # Fontes medievais
│   ├── icons/               # Ícones de upgrades e talentos
│   ├── items/               # Gemas e itens coletáveis
│   ├── sprite/
│   │   └── monster/         # Spritesheets direcionais de monstros
│   └── ui/
│       ├── buttons/         # Barras ornamentadas, skills.png, config.png
│       ├── chao/            # Decorações de chão (dungeon)
│       ├── menu_icons/      # Ícones do menu principal
│       ├── panels/          # Painéis de seleção de personagem
│       ├── tiles/           # Tiles de bioma (estáticos e animados)
│       └── newItens/        # Ícones de armaduras (capacete/, armor/, calças/, botas/)
├── settings.json            # Configurações salvas
├── save_v2.json             # Progresso global
├── requirements.txt         # Dependências runtime (pygame-ce, numpy, numba)
└── requirements-dev.txt     # Dependências de build (Cython, PyInstaller)
```

---

## Troubleshooting

### "ModuleNotFoundError: No module named 'pygame'" ou "pygame-ce"

**Causa:** O ambiente não está ativado ou pygame-ce não foi instalado.

**Solução:**

```bash
# Ativar venv
.\venv\Scripts\Activate.ps1  # Windows
source venv/bin/activate        # Linux/macOS

# Reinstalar pygame-ce
pip uninstall pygame pygame-ce -y
pip install pygame-ce==2.5.7
```

### "pygame.error: video system not initialized"

**Causa:** Pygame não conseguiu acessar o driver de vídeo (Linux headless, WSL sem display).

**Solução:**

```bash
# Linux: instalar SDL2
sudo apt-get install libsdl2-2.0-0 libsdl2-dev

# Verificar instalação
python -c "import pygame; pygame.init(); print('OK')"
```

### FPS baixo ou stutter mesmo com Pygame-CE e hardware bom

**Otimizações:**

1. **Reduzir resolução** em Configurações > Vídeo (tente 1280x720).
2. **Desabilitar VSync** se o jogo ficar travado inconsistentemente.
3. **Compilar Cython** para kernels de IA mais rápidos:
   ```bash
   python build_cython.py build_ext --inplace
   ```
4. **Verificar Numba ativo** (`NUMBA_ACTIVE = True`):
   ```bash
   python -c "import hot_kernels; print(hot_kernels.NUMBA_ACTIVE)"
   ```
5. **Fechar aplicações em background** (Discord, Chrome, etc).

### Erro ao compilar Cython no Windows

**Causa:** Compilador C não encontrado.

**Solução rápida (recomendada) — WinLibs GCC ~255 MB:**

```powershell
winget install BrechtSanders.WinLibs.POSIX.UCRT
# Abra um novo terminal após instalar para o PATH ser atualizado
python build_cython.py build_ext --inplace
```

**Solução alternativa — Visual C++ Build Tools ~5 GB:**

Instale **Visual C++ Build Tools 2019+** do site oficial da Microsoft e tente novamente:

```bash
python build_cython.py build_ext --inplace
```

**Verificar se GCC está no PATH:**

```bash
gcc --version
```

---

## Roadmap

- [ ] Novos biomas com mecânicas exclusivas.
- [x] Boss Agis — invocação por selo, ataque à distância e magia em área.
- [ ] Novos chefes com fases e ataques adicionais.
- [ ] Sistema de conquistas com recompensas visuais.
- [x] Sistema de balanceamento contínuo de progressão e economia (`balance.py`).
- [x] Build distribuível para Windows (.exe) via PyInstaller (`build_dist.py`) e Nuitka (`build_nuitka.py`).
- [x] Suporte a controle gamepad.
- [x] Migrar para Pygame-CE (concluído com sucesso).
- [x] Aba ARMADURAS na loja com 46 itens em 4 categorias (capacetes, armaduras, calças, botas).
- [x] Sistema de resistência a dano por armaduras equipadas.
- [x] Drag-and-drop para todos os slots de equipamento (arma, escudo, capacete, armadura, calças, botas).
- [x] Painel de status (C) e Sala do Herói alinhados às zonas das imagens de UI.
- [x] Árvore de talentos com painel expandido para acomodar todos os talentos por caminho.
- [x] 218 upgrades divididos em 8 categorias com sistema de sinergia.
- [x] Seleção de 5 upgrades por nível (teclas 1–5).
- [x] Novas mecânicas de run: lifesteal, multiplicador de ouro, bônus de XP.
- [x] Numba JIT no kernel de separação de inimigos (`hot_kernels.py`).
- [x] Double buffering (`pygame.DOUBLEBUF`) para reduzir tearing.
- [x] Cache de chão — tilemap pré-renderizado (~54 blits/frame → 1 blit/frame).
- [x] Frame time smoothing — média móvel de 6 frames elimina micro-stutters.
- [x] Bioma Vulcão com decorações, geiseres e inimigos exclusivos.
- [x] Bioma Lua com decorações temáticas.
- [ ] SDL3 quando Pygame-CE lançar (GPU acceleration e melhor performance).
- [ ] Multiplayer local (co-op para 2 jogadores).

---

## Contribuição

1. Abra uma issue descrevendo o bug, melhoria ou proposta.
2. Crie uma branch a partir de `beta`.
3. Envie um Pull Request com descrição do que foi alterado e como testar.

Diretrizes: [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)

---

## Licença

Licença proprietária com codigo disponivel (source-available).
O codigo esta disponivel apenas para visualizacao e fins educacionais.
Compilacao, redistribuicao e venda do codigo-fonte ou binario sao proibidas.
Todos os direitos de exploracao comercial sao reservados ao autor.
Consulte [LICENSE](LICENSE).

---

## Gameplay

<p align="center">
  <img src="screenshots/gameplay_readme.gif" alt="Gameplay do UnderWorld Hero" width="900">
</p>
