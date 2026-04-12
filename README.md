# UnderWorld Hero

![Python](https://img.shields.io/badge/Python-3.12-blue?style=for-the-badge&logo=python)
![Pygame-CE](https://img.shields.io/badge/Pygame--CE-2.5.7-green?style=for-the-badge)
![NumPy](https://img.shields.io/badge/NumPy-2.4.4-013243?style=for-the-badge&logo=numpy)
![Status](https://img.shields.io/badge/Status-Em_Desenvolvimento-yellow?style=for-the-badge)

Jogo de sobrevivência estilo bullet hell desenvolvido em Python com Pygame-CE, com foco em combate rápido, progressão por upgrades, múltiplos personagens, sistema de pactos e pipeline de performance baseado em indexação espacial (NumPy + Cython opcional).

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
- [Build opcional com Cython](#build-opcional-com-cython)
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
- 6 personagens jogáveis com estilos e ultimates próprios.
- 4 níveis de dificuldade e 4 pactos com modificadores de risco/recompensa.
- Missões diárias, meta-progresso e árvore de talentos permanente.
- 3 slots de run independentes com estado completo salvo.
- Interface 100% temática medieval com sprites ornamentados.

---

## Personagens

| Personagem | HP | Velocidade | Estilo | Ultimate |
|---|---|---|---|---|
| Guerreiro | 8 | 280 | Corpo a corpo + projéteis | Fúria: aumenta cadência e dano |
| Caçador | 5 | 340 | Projéteis rápidos, alto crítico | Rajada: disparo em cone |
| Mago | 6 | 260 | Aura + orbes mágicos | Congelamento Temporal: congela inimigos em área |
| Vampire | 7 | 300 | Projéteis + regen de vida | Vampirismo |
| Demônio | 6 | 290 | Projéteis múltiplos, burst | Chamas do Abismo |
| Golem | 9 | 240 | Melee puro, alto HP | Golpe da Terra: 16 slashes em área |

Todos os personagens estão desbloqueados por padrão. Cada personagem possui spritesheets direcionais (cima/baixo/esquerda/direita) com animações de andar e atacar carregadas via `characters.py`.

---

## Inimigos e Chefes

### Inimigos — Todas as dificuldades

| Tipo | HP | Vel. | Aparição | Descrição |
|---|---|---|---|---|
| Bat | 1 | 145 | 0s | Morcego com movimento senoidal |
| Runner | 2 | 150 | 0s | Corredor rápido em linha reta |
| Tank | 10 | 65 | 30s | Alto HP, lento, corpo a corpo |
| Shooter | 3 | 90 | 30s | Atira projéteis à distância |
| Goblin | 3 | 160 | 1 min | Rápido com zigzag moderado |
| Beholder | 8 | 85 | 1.5 min | Flutuante, movimento suave |
| Orc | 12 | 75 | 3 min | Grande (168px), corpo a corpo tanque |
| Elite | +50% | base | 30s+ | Versão reforçada com drop de ouro garantido |

### Inimigos — Somente Difícil / Hardcore

| Tipo | HP | Vel. | Aparição | Descrição |
|---|---|---|---|---|
| Slime | 5 | 110 | 30s | Inimigo padrão equilibrado |
| Minotauro | 8 | 130 | 30s | Corpo a corpo, perseguição direta |
| Rat | 6 | 135 | 2 min | Grande (220px), zigzag agressivo |

### Chefes

| Tipo | HP | Aparição | Descrição |
|---|---|---|---|
| Mini Boss | 300+ | ~10s | Barra de vida própria, escala com tempo |
| Chefe | escalável | 5 min (a cada 5 min) | Multi-fase, fica mais forte a cada onda |
| Agis | 800+ | 2 min (selo de invocação) | Boss lento, ataque de orbe à distância + magia em área a cada 5s |

**Agis** é invocado por um selo animado (`doom_agis.png`) que aparece próximo ao herói ~30s antes do spawn. Possui ataque básico de projétil (orbe dupla roxa) e magia em área que dispara 8 orbes em todas as direções. Dropa baú + 15 moedas ao morrer.

Hordas são processadas em fila assíncrona (6 inimigos/frame) eliminando travamentos de CPU. Obstáculos surgem gradualmente desde o início da run — não em massa durante hordas.

---

## Sistemas de jogo

### Upgrades e Evoluções

- Pool de upgrades com 4 raridades: Comum, Raro, Épico, Lendário.
- Sinergia: upgrades anteriores influenciam as opções oferecidas.
- Evoluções desbloqueiam versões aprimoradas ao atingir nível máximo.
- `TREVO SORTE` aumenta a raridade das próximas ofertas.
- Notificações visuais com fade-out ao aplicar upgrades.

### Pactos

Modificadores opcionais escolhidos antes da run:

| Pacto | Efeito | Bônus |
|---|---|---|
| Sem Pacto | Nenhum modificador | — |
| Pacto da Pressa | Inimigos 50% mais rápidos | +50% Ouro |
| Pacto Frágil | -2 HP máximo | +30% XP |
| Pacto da Sombra | Inimigos invisíveis | +80% Ouro |

### Dificuldades

| Dificuldade | HP inimigos | Velocidade | Dano | Ouro |
|---|---|---|---|---|
| Fácil | 0.7x | 0.8x | 0.5x | 0.8x |
| Médio | 1.0x | 1.0x | 1.0x | 1.0x |
| Difícil | 1.5x | 1.15x | 1.5x | 1.4x |
| Hardcore | 2.5x | 1.3x | 2.0x | 2.0x |

Difícil e Hardcore são desbloqueados por missões específicas.

### Biomas

- **Dungeon**: fundo de pedra com decorações de chão animadas (pentagrama, dinossauro).
- **Floresta**: tilemap composto com tiles animados (fogueira, bandeira).
- **Gelo** e **Vulcão**: fundos estáticos temáticos com trilha própria.

### Missões e Talentos

- Missões com recompensas em ouro.
- Árvore de talentos permanente aplicada no início de cada run.
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

O `AssetLoader` usa cache recursivo (`_build_cache`): arquivos podem estar em qualquer subpasta de `assets/` e são encontrados pelo nome sem alterar nenhuma chamada de código.

---

## Arquitetura do projeto

### Módulos principais

| Arquivo | Responsabilidade |
|---|---|
| `jogo_final.py` | Loop principal, estados de jogo, UI, constantes de balanceamento |
| `characters.py` | Classes de personagem, habilidades e ultimates |
| `enemies.py` | Inimigos, IA direcional, spritesheets, projéteis inimigos |
| `hud.py` | HUD in-game, tema visual, notificações de upgrade |
| `upgrades.py` | Pool de upgrades, sinergia, evoluções |
| `drops.py` | Gemas, itens e lógica de coleta |
| `combat/projectiles.py` | Projéteis, slashes e explosões com cache de frames |
| `forest_biome.py` | Tilemap de floresta, decorações animadas |
| `dungeon_biome.py` | Decorações de chão do dungeon |
| `spatial_index.py` | Índices espaciais, pathfinding A* em grid, métricas |
| `hot_kernels.py` | Kernels NumPy com detecção automática de backend Cython |
| `hot_kernels_cy.pyx` | Implementação acelerada opcional em Cython |

### Decisões técnicas

- **Fila de spawn de hordas**: producer/consumer (6 inimigos/frame) — elimina picos de CPU.
- **Cache de explosões**: indexado por `(id(raw_frames), size)` — evita reescalonamento repetido.
- **AssetLoader recursivo**: `os.walk` em `assets/` mapeia stem → path completo; mover arquivos não quebra o código.
- **Resolução dinâmica**: `pygame.display.list_modes()` detecta modos do monitor em tempo real.
- **Spawn gradual de obstáculos**: timer decrescente desde o início da run em vez de bulk em hordas.
- **Fallback em camadas**: Cython opcional, sprites com fallback procedural, resolução com fallback para nativa.

---

## Requisitos

- Python 3.12+
- Windows, Linux ou macOS
- Dependências runtime:
  - `pygame-ce` 2.5.7+ (Community Edition com SDL 2.32.10 ou superior)
  - `numpy` 2.4.4+

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

> Se já tiver `pygame` (original) instalado, remova com `pip uninstall pygame` antes.

### 4) Verificar instalação

```bash
python -c "import pygame; print(f'Pygame-CE versão: {pygame.version.vernum}')"
python -c "import numpy; print(f'NumPy versão: {numpy.__version__}')"
```

### 5) Executar

```bash
python jogo_final.py
```

Sem ativar o venv (Windows):

```powershell
.\venv\Scripts\python.exe jogo_final.py
```

**Primeira execução:** O jogo criará `settings.json` e `save_v2.json` na primeira vez — aguarde alguns segundos para o AssetLoader indexar os arquivos de assets.

---

## Otimizações e Build opcional com Cython

### Performance base

O jogo já é otimizado via:
- **Pygame-CE com SDL2** — renderização mais eficiente que pygame original.
- **Indexação espacial NumPy** — buscas O(1) em grid para colisões e ataques.
- **Fila assíncrona de spawn** — 6 inimigos por frame evita travamentos.
- **Cache de frames** — sprites efeito pre-escalados, sem recomputar por frame.

### Build opcional com Cython (avançado)

Para ganho adicional de performance nos kernels de pathfinding e IA, compile a extensão Cython. **Sem ela o jogo funciona normalmente via NumPy puro** — a compilação é totalmente opcional.

#### Kernels disponíveis

| Kernel | Função | Ganho típico |
|---|---|---|
| `radius_indices` | Inimigos dentro de raio (colisão de projéteis, pick-up range) | 4-6x vs Python puro |
| `nearest_index` | Inimigo mais próximo respeitando máscara de exclusão (targeting) | 4-6x vs Python puro |
| `batch_directions` | Direção normalizada para N inimigos de uma vez (movimento em batch) | 6-10x vs Python puro |
| `astar_cy` | Pathfinding A* com variáveis C internas, sem overhead de atributo Python | 4-8x vs Python puro |
| `positions_in_rect` | Índices dentro de retângulo para ataques AOE (slash, cone) | 4-6x vs Python puro |

O módulo `hot_kernels.py` detecta automaticamente quais kernels estão compilados e usa fallback NumPy individualmente por função — um `.pyd` antigo com menos kernels funciona sem erros.

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

Alternativa leve ao Visual C++ Build Tools (que exige ~5 GB). Instale via winget:

```powershell
winget install BrechtSanders.WinLibs.POSIX.UCRT
```

Após instalar, abra um novo terminal (para o PATH ser atualizado) e compile:

```bash
python build_cython.py build_ext --inplace
```

#### Opção B: Visual C++ Build Tools

Instale o **Visual C++ Build Tools 2019+** do site oficial da Microsoft. Depois:

```bash
python build_cython.py build_ext --inplace
```

#### Verificar backend ativo

```bash
python -c "import hot_kernels; print('CYTHON_ACTIVE =', hot_kernels.CYTHON_ACTIVE)"
```

Saída esperada com todos os kernels compilados:

```
CYTHON_ACTIVE = True
```

Cada kernel é verificado individualmente via `hasattr`. Se apenas alguns estiverem presentes no `.pyd`, os demais usam fallback NumPy automaticamente.

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
| Selecionar upgrade | 1 / 2 / 3 ou clique |

---

## Sobre Pygame-CE (Community Edition)

### Por que Pygame-CE?

Este projeto usa **Pygame-CE (Community Edition)** em vez do Pygame original pelos seguintes benefícios:

| Critério | Pygame Original | Pygame-CE |
|---|---|---|
| Manutenção | Inativa desde 2009 | Comunitária, ativa |
| Performance | Baseline | 5-15% mais rápido |
| SDL2 | 2.28 | 2.32+ (otimizações) |
| Python 3.12+ | Limitado | Full support |
| GPU acceleration | Não | SDL3 (roadmap 2025) |
| API | Compatível | 100% drop-in |

### Impacto no jogo

- **FPS consistente** com 100+ inimigos em cena.
- **Menos stutter** em transições e efeitos visuais.
- **Melhor SDL2** com renderização otimizada para lotes de sprites.

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
- Se `pygame.display.set_mode` falhar com as flags escolhidas → abre em janela simples.

---

## Debug e benchmark de performance

### Overlay in-game (F3)

- FPS e tempo médio de frame.
- Contagem de inimigos, projéteis e partículas em tela.
- Consultas espaciais por frame e taxa de cache hit do A*.
- Backend ativo: Cython ON / NumPy fallback.

### Benchmark offline

```bash
python benchmark_spatial.py
```

---

## Estrutura de pastas

```text
underworld-hero-survivor/
├── jogo_final.py            # Loop principal e estados de jogo
├── characters.py            # Personagens jogáveis
├── enemies.py               # Inimigos, IA e animações
├── hud.py                   # HUD e interface in-game
├── upgrades.py              # Upgrades, sinergia e evoluções
├── drops.py                 # Gemas e drops
├── forest_biome.py          # Bioma floresta (tilemap)
├── dungeon_biome.py         # Bioma dungeon (decorações)
├── spatial_index.py         # Indexação espacial e pathfinding
├── hot_kernels.py           # Kernels NumPy / Cython
├── hot_kernels_cy.pyx       # Extensão Cython (opcional)
├── benchmark_spatial.py     # Benchmark de performance
├── build_cython.py          # Script de build Cython
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
│       └── tiles/           # Tiles de bioma (estáticos e animados)
├── settings.json            # Configurações salvas
├── save_v2.json             # Progresso global
├── requirements.txt         # Dependências runtime (pygame-ce, numpy)
└── requirements-dev.txt     # Dependências de build (Cython)
```

---

## Roadmap

- [ ] Novos biomas com mecânicas exclusivas.
- [x] Boss Agis — invocação por selo, ataque à distância e magia em área.
- [ ] Novos chefes com fases e ataques adicionais.
- [ ] Sistema de conquistas com recompensas visuais.
- [ ] Balanceamento contínuo de progressão e economia.
- [ ] Build distribuível para Windows (.exe).
- [x] Suporte a controle gamepad.
- [x] Migrar para Pygame-CE (concluído com sucesso).
- [ ] SDL3 quando Pygame-CE lançar (GPU acceleration e melhor performance).
- [ ] Multiplayer local (co-op para 2 jogadores).

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
4. **Fechar aplicações em background** (Discord, Chrome, etc).

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

Se retornar a versão, o compilador está configurado corretamente.

---

## Contribuição

1. Abra uma issue descrevendo o bug, melhoria ou proposta.
2. Crie uma branch a partir de `beta`.
3. Envie um Pull Request com descrição do que foi alterado e como testar.

Diretrizes: [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)

---

## Licença

Distribuído sob licença MIT. Consulte [LICENSE](LICENSE)...

---

## Gameplay

<p align="center">
  <img src="screenshots/gameplay_readme.gif" alt="Gameplay do UnderWorld Hero" width="900">
</p>

