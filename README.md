# UnderWorld Hero

![Python](https://img.shields.io/badge/Python-3.12-blue?style=for-the-badge&logo=python)
![Pygame-CE](https://img.shields.io/badge/Pygame--CE-2.5.7-green?style=for-the-badge)
![NumPy](https://img.shields.io/badge/NumPy-2.4.4-013243?style=for-the-badge&logo=numpy)
![Status](https://img.shields.io/badge/Status-Em_Desenvolvimento-yellow?style=for-the-badge)

Jogo de sobrevivencia estilo bullet hell desenvolvido em Python com Pygame-CE, com foco em combate rapido, progressao por upgrades, multiplos personagens, sistema de pactos e pipeline de performance baseado em indexacao espacial (NumPy + Cython opcional).

English version: [README.en.md](README.en.md)

## Sumario

- [Visao geral](#visao-geral)
- [Personagens](#personagens)
- [Inimigos e Chefes](#inimigos-e-chefes)
- [Sistemas de jogo](#sistemas-de-jogo)
- [Interface e UI medieval](#interface-e-ui-medieval)
- [Arquitetura do projeto](#arquitetura-do-projeto)
- [Requisitos](#requisitos)
- [Instalacao e execucao](#instalacao-e-execucao)
- [Build opcional com Cython](#build-opcional-com-cython)
- [Controles](#controles)
- [Configuracoes, save e persistencia](#configuracoes-save-e-persistencia)
- [Resolucao e compatibilidade](#resolucao-e-compatibilidade)
- [Debug e benchmark de performance](#debug-e-benchmark-de-performance)
- [Estrutura de pastas](#estrutura-de-pastas)
- [Roadmap](#roadmap)
- [Contribuicao](#contribuicao)
- [Licenca](#licenca)

---

## Visao geral

UnderWorld Hero e um survivor roguelike onde o jogador enfrenta ondas crescentes de inimigos, escolhe upgrades a cada nivel e tenta sobreviver o maior tempo possivel. A cada run e possivel escolher personagem, dificuldade, pacto e bioma, gerando combinacoes distintas de desafio e estilo.

Destaques gerais:

- Combate em tempo real com alto volume de inimigos em tela.
- Progressao por nivel com selecao de upgrades e evolucoes sinergicas.
- 3 personagens jogaveis com estilos e ultimates proprios.
- 4 niveis de dificuldade e 4 pactos com modificadores de risco/recompensa.
- Missoes diarias, meta-progresso e arvore de talentos permanente.
- 3 slots de run independentes com estado completo salvo.
- Interface 100% tematica medieval com sprites ornamentados.

---

## Personagens

| Personagem | HP | Estilo | Ultimate |
|---|---|---|---|
| Guerreiro | 8 | Corpo a corpo + projeteis | Furia: aumenta cadencia e dano |
| Cacador | 5 | Projeteis rapidos, alta critico | Rajada: disparo em cone |
| Mago | 6 | Aura + orbes magicos | Tornado: dano em area continuo |

Cada personagem possui spritesheets direcionais (cima/baixo/esquerda/direita) com animacoes de andar e atacar carregadas via `characters.py`.

---

## Inimigos e Chefes

| Tipo | Descricao |
|---|---|
| Slime | Inimigo basico, baixo HP, rapido |
| Robo | Inimigo padrao equilibrado |
| Shooter | Atira projeteis a distancia |
| Tank | Alto HP e dano corpo a corpo |
| Bat | Morcego rapido com movimento senoidal |
| Orc | Grande (168px), tanque corpo a corpo com barra de vida visivel |
| Elite | Versao reforcada dos comuns com drop de ouro garantido |
| Mini Boss | Inimigo intermediario com barra de vida propria |
| Chefe | Multi-fase com ataques especiais, aparece a cada 5 minutos |

Hordas sao processadas em fila assincrona (6 inimigos/frame) eliminando travamentos de CPU. Obstaculos surgem gradualmente desde o inicio da run — nao em massa durante hordas.

---

## Sistemas de jogo

### Upgrades e Evolucoes

- Pool de upgrades com 4 raridades: Comum, Raro, Epico, Lendario.
- Sinergia: upgrades anteriores influenciam as opcoes oferecidas.
- Evolucoes desbloqueiam versoes aprimoradas ao atingir nivel maximo.
- `TREVO SORTE` aumenta a raridade das proximas ofertas.
- Notificacoes visuais com fade-out ao aplicar upgrades.

### Pactos

Modificadores opcionais escolhidos antes da run:

| Pacto | Efeito | Bonus |
|---|---|---|
| Sem Pacto | Nenhum modificador | — |
| Pacto da Pressa | Inimigos 50% mais rapidos | +50% Ouro |
| Pacto Fragil | -2 HP maximo | +30% XP |
| Pacto da Sombra | Inimigos invisiveis | +80% Ouro |

### Dificuldades

| Dificuldade | HP inimigos | Velocidade | Dano | Ouro |
|---|---|---|---|---|
| Facil | 0.7x | 0.8x | 0.5x | 0.8x |
| Medio | 1.0x | 1.0x | 1.0x | 1.0x |
| Dificil | 1.5x | 1.15x | 1.5x | 1.4x |
| Hardcore | 2.5x | 1.3x | 2.0x | 2.0x |

Dificil e Hardcore sao desbloqueados por missoes especificas.

### Biomas

- **Dungeon**: fundo de pedra com decoracoes de chao animadas (pentagrama, dinossauro).
- **Floresta**: tilemap composto com tiles animados (fogueira, bandeira).
- **Gelo** e **Vulcao**: fundos estaticos tematicos com trilha propria.

### Missoes e Talentos

- Missoes com recompensas em ouro.
- Arvore de talentos permanente aplicada no inicio de cada run.
- Unlocks de personagens, dificuldades e cosmeticos por conquistas.

---

## Interface e UI medieval

Toda a interface usa sprites ornamentados medievais com fundo transparente (Photoroom). O texto e sempre renderizado dinamicamente por cima — nenhum texto fica gravado na imagem.

| Elemento | Sprite |
|---|---|
| Botoes de todos os menus | `Barras de interface medieval ornamentada-Photoroom.png` (7 barras) |
| Cartas de selecao de skill (level-up) | `skills.png` (3 cartas) |
| Titulo e secao de configuracoes | `config.png` (barra grande + barra pequena) |
| Paineis de selecao de personagem | `painelguerreiro.png`, `painelcacador.png`, `painelmago.png` |
| Tela de selecao de dificuldade | `selecionar_dificuldade.png` |

O `AssetLoader` usa cache recursivo (`_build_cache`): arquivos podem estar em qualquer subpasta de `assets/` e sao encontrados pelo nome sem alterar nenhuma chamada de codigo.

---

## Arquitetura do projeto

### Modulos principais

| Arquivo | Responsabilidade |
|---|---|
| `jogo_final.py` | Loop principal, estados de jogo, UI, constantes de balanceamento |
| `characters.py` | Classes de personagem, habilidades e ultimates |
| `enemies.py` | Inimigos, IA direcional, spritesheets, projeteis inimigos |
| `hud.py` | HUD in-game, tema visual, notificacoes de upgrade |
| `upgrades.py` | Pool de upgrades, sinergia, evolucoes |
| `drops.py` | Gemas, itens e logica de coleta |
| `combat/projectiles.py` | Projeteis, slashes e explosoes com cache de frames |
| `forest_biome.py` | Tilemap de floresta, decoracoes animadas |
| `dungeon_biome.py` | Decoracoes de chao do dungeon |
| `spatial_index.py` | Indices espaciais, pathfinding A* em grid, metricas |
| `hot_kernels.py` | Kernels NumPy com deteccao automatica de backend Cython |
| `hot_kernels_cy.pyx` | Implementacao acelerada opcional em Cython |

### Decisoes tecnicas

- **Fila de spawn de hordas**: producer/consumer (6 inimigos/frame) — elimina picos de CPU.
- **Cache de explosoes**: indexado por `(id(raw_frames), size)` — evita reescalonamento repetido.
- **AssetLoader recursivo**: `os.walk` em `assets/` mapeia stem → path completo; mover arquivos nao quebra o codigo.
- **Resolucao dinamica**: `pygame.display.list_modes()` detecta modos do monitor em tempo real.
- **Spawn gradual de obstaculos**: timer decrescente desde o inicio da run em vez de bulk em hordas.
- **Fallback em camadas**: Cython opcional, sprites com fallback procedural, resolucao com fallback para nativa.

---

## Requisitos

- Python 3.12+
- Windows, Linux ou macOS
- Dependencias runtime:
  - `pygame-ce` 2.5.7+ (Community Edition com SDL 2.32.10 ou superior)
  - `numpy` 2.4.4+

> **Atencao:** O projeto usa **pygame-ce** (Community Edition), nao o pygame original. Instalar ambos simultaneamente causa conflito — desinstale `pygame` antes de instalar `pygame-ce`.

### Por que Pygame-CE?

O projeto migrou para **Pygame Community Edition** (Pygame-CE) pelos seguintes beneficios:

1. **Drop-in replacement** — API 100% compativel com pygame original, sem refatory necessaria.
2. **Melhor performance** — Otimizacoes em drivers SDL2, reducao de overhead em renderizacao e eventos.
3. **Suporte SDL3 (futuro)** — Aceleracao GPU via SDL3: melhor FPS em cenas complexas com muitos sprites.
4. **Manutencao ativa** — Comunidade open-source mantendo e atualizando regularmente.
5. **Recursos extras** — Suporte aprimorado a spritesheets, efeitos de blending e transformacoes.

No contexto deste jogo (survivor com 100+ inimigos + UI animada), o Pygame-CE proporciona FPS mais consistente, especialmente em modos dificeis com muitas particulas e projeteis.

---

## Instalacao e execucao

### 1) Clonar repositorio

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

### 3) Instalar dependencias

```bash
pip install -r requirements.txt
```

Isso instala:
- `pygame-ce` 2.5.7 (Community Edition)
- `numpy` 2.4.4 (processamento rapido de arrays para IA espacial)

> Se ja tiver `pygame` (original) instalado, remova com `pip uninstall pygame` antes.

### 4) Verificar instalacao

```bash
python -c "import pygame; print(f'Pygame-CE versao: {pygame.version.vernum}')"
python -c "import numpy; print(f'NumPy versao: {numpy.__version__}')"
```

### 5) Executar

```bash
python jogo_final.py
```

Sem ativar o venv (Windows):

```powershell
.\venv\Scripts\python.exe jogo_final.py
```

**Primeira execucao:** O jogo criara `settings.json` e `save_v2.json` na primeira vez — aguarde alguns segundos para o AssetLoader indexar os arquivos de assets.

---

## Otimizacoes e Build opcional com Cython

### Performance base

O jogo ja e otimizado via:
- **Pygame-CE com SDL2** — renderizacao mais eficiente que pygame original.
- **Indexacao espacial NumPy** — buscas O(1) em grid para colisoes e ataques.
- **Fila assincrona de spawn** — 6 inimigos por frame evita travamentos.
- **Cache de frames** — sprites efeito pre-escalados, sem recomputar por frame.

### Build opcional com Cython (avancado)

Para ganho adicional de performance nos kernels de pathfinding e IA, compile a extensao Cython. **Sem ela o jogo funciona normalmente via NumPy puro** — a compilacao e totalmente opcional.

#### Kernels disponíveis

| Kernel | Funcao | Ganho tipico |
|---|---|---|
| `radius_indices` | Inimigos dentro de raio (colisao de projeteis, pick-up range) | 4-6x vs Python puro |
| `nearest_index` | Inimigo mais proximo respeitando mascara de exclusao (targeting) | 4-6x vs Python puro |
| `batch_directions` | Direcao normalizada para N inimigos de uma vez (movimento em batch) | 6-10x vs Python puro |
| `astar_cy` | Pathfinding A* com variaveis C internas, sem overhead de atributo Python | 4-8x vs Python puro |
| `positions_in_rect` | Indices dentro de retangulo para ataques AOE (slash, cone) | 4-6x vs Python puro |

O modulo `hot_kernels.py` detecta automaticamente quais kernels estao compilados e usa fallback NumPy individualmente por funcao — um `.pyd` antigo com menos kernels funciona sem erros.

#### Benchmarks medidos (Intel i5, Python 3.12, GCC 15.2 -O3)

| Teste | Tempo |
|---|---|
| `radius_indices` × 1000 chamadas | ~12.6 ms |
| `batch_directions` × 1000 chamadas | ~14.5 ms |
| `astar_cy` × 500 chamadas | ~59.5 ms |

#### Instalar dependencias de build

```bash
pip install -r requirements-dev.txt
```

#### Opção A: WinLibs GCC (recomendado, ~255 MB)

Alternativa leve ao Visual C++ Build Tools (que exige ~5 GB). Instale via winget:

```powershell
winget install BrechtSanders.WinLibs.POSIX.UCRT
```

Apos instalar, abra um novo terminal (para o PATH ser atualizado) e compile:

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

Saida esperada com todos os kernels compilados:

```
CYTHON_ACTIVE = True
```

Cada kernel e verificado individualmente via `hasattr`. Se apenas alguns estiverem presentes no `.pyd`, os demais usam fallback NumPy automaticamente.

---

## Controles

Reconfiguraveis em **Configuracoes → Controles**:

| Acao | Padrao |
|---|---|
| Movimentacao | W A S D |
| Dash | Space |
| Ultimate | E |
| Pausar / Retomar | P |
| Menu rapido | Esc |
| Overlay de debug | F3 |
| Selecionar upgrade | 1 / 2 / 3 ou clique |

---

## Sobre Pygame-CE (Community Edition)

### Por que Pygame-CE?

Este projeto usa **Pygame-CE (Community Edition)** em vez do Pygame original pelos seguintes beneficios:

| Criterio | Pygame Original | Pygame-CE |
|---|---|---|
| Manutencao | Inativa desde 2009 | Comunitaria, ativa |
| Performance | Baseline | 5-15% mais rapido |
| SDL2 | 2.28 | 2.32+ (otimizacoes) |
| Python 3.12+ | Limitado | Full support |
| GPU acceleration | Nao | SDL3 (roadmap 2025) |
| API | Compativel | 100% drop-in |

### Impacto no jogo

- **FPS consistente** com 100+ inimigos em cena.
- **Menos stutter** em transicoes e efeitos visuais.
- **Melhor SDL2** com renderizacao otimizada para lotes de sprites.

---

## Configuracoes, save e persistencia

| Arquivo | Conteudo |
|---|---|
| `settings.json` | Video, audio, controles, gameplay, acessibilidade |
| `save_v2.json` | Progresso global: ouro, talentos, unlocks, estatisticas |
| `run_slot_1~3.json` | Estado completo de cada slot de run |

Secoes das configuracoes:

- **Video**: resolucao (dinamica), tela cheia, VSync, limite de FPS, mostrar FPS.
- **Audio**: volume de musica, volume de efeitos, mudo.
- **Controles**: remapeamento de teclas.
- **Gameplay**: auto-aplicar recompensa de bau, indicadores de inimigos fora de tela.
- **Acessibilidade**: opcoes extras de visualizacao.

---

## Resolucao e compatibilidade

A lista de resolucoes e detectada automaticamente via `pygame.display.list_modes()` ao abrir as configuracoes. Nenhum valor esta fixo no codigo.

Exemplo de resolucoes detectadas (variam por monitor):

```
1280x720  1366x768  1600x900  1920x1080  2560x1440  3840x2160
```

Comportamento de fallback:

- Se a resolucao salva nao couber no monitor atual → usa resolucao nativa.
- Se o monitor nao reportar lista de modos → usa lista padrao ate 4K.
- Se `pygame.display.set_mode` falhar com as flags escolhidas → abre em janela simples.

---

## Debug e benchmark de performance

### Overlay in-game (F3)

- FPS e tempo medio de frame.
- Contagem de inimigos, projeteis e particulas em tela.
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
├── characters.py            # Personagens jogaveis
├── enemies.py               # Inimigos, IA e animacoes
├── hud.py                   # HUD e interface in-game
├── upgrades.py              # Upgrades, sinergia e evolucoes
├── drops.py                 # Gemas e drops
├── forest_biome.py          # Bioma floresta (tilemap)
├── dungeon_biome.py         # Bioma dungeon (decoracoes)
├── spatial_index.py         # Indexacao espacial e pathfinding
├── hot_kernels.py           # Kernels NumPy / Cython
├── hot_kernels_cy.pyx       # Extensao Cython (opcional)
├── benchmark_spatial.py     # Benchmark de performance
├── build_cython.py          # Script de build Cython
├── combat/
│   └── projectiles.py       # Projeteis e explosoes
├── assets/
│   ├── audio/               # Musicas e efeitos (.mp3)
│   ├── backgrounds/         # Fundos dos biomas
│   ├── characters/          # Sprites dos personagens
│   ├── effects/             # Auras, explosoes, slashes, orbes
│   ├── enemies/             # Sprites de inimigos e chefes
│   ├── fonts/               # Fontes medievais
│   ├── icons/               # Icones de upgrades e talentos
│   ├── items/               # Gemas e itens coletaveis
│   ├── sprite/
│   │   └── monster/         # Spritesheets direcionais de monstros
│   └── ui/
│       ├── buttons/         # Barras ornamentadas, skills.png, config.png
│       ├── chao/            # Decoracoes de chao (dungeon)
│       ├── menu_icons/      # Icones do menu principal
│       ├── panels/          # Paineis de selecao de personagem
│       └── tiles/           # Tiles de bioma (estaticos e animados)
├── settings.json            # Configuracoes salvas
├── save_v2.json             # Progresso global
├── requirements.txt         # Dependencias runtime (pygame-ce, numpy)
└── requirements-dev.txt     # Dependencias de build (Cython)
```

---

## Roadmap

- [ ] Novos biomas com mecanicas exclusivas.
- [ ] Novos chefes com fases e ataques adicionais.
- [ ] Sistema de conquistas com recompensas visuais.
- [ ] Balanceamento continuo de progressao e economia.
- [ ] Build distribuivel para Windows (.exe).
- [x] Suporte a controle gamepad.
- [x] Migrar para Pygame-CE (concluido com sucesso).
- [ ] SDL3 quando Pygame-CE lancar (GPU acceleration e melhor performance).
- [ ] Multiplayer local (co-op para 2 jogadores).

---

## Troubleshooting

### "ModuleNotFoundError: No module named 'pygame'" ou "pygame-ce"

**Causa:** Environment nao esta ativado ou pygame-ce nao foi instalado.

**Solucao:**

```bash
# Ativar venv
.\venv\Scripts\Activate.ps1  # Windows
source venv/bin/activate        # Linux/macOS

# Reinstalar pygame-ce
pip uninstall pygame pygame-ce -y
pip install pygame-ce==2.5.7
```

### "pygame.error: video system not initialized"

**Causa:** Pygame nao conseguiu acessar o driver de video (Linux headless, WSL sem display).

**Solucao:**

```bash
# Linux: instalar SDL2
sudo apt-get install libsdl2-2.0-0 libsdl2-dev

# Verificar instalacao
python -c "import pygame; pygame.init(); print('OK')"
```

### FPS baixo ou stutter mesmo com Pygame-CE e hardware bom

**Otimizacoes:**

1. **Reduzir resolucao** em Configuracoes > Video (tente 1280x720).
2. **Desabilitar VSync** se o jogo ficar travado inconsistentemente.
3. **Compilar Cython** para kernels de IA mais rapidos:
   ```bash
   python build_cython.py build_ext --inplace
   ```
4. **Fechar aplicacoes em background** (Discord, Chrome, etc).

### Erro ao compilar Cython no Windows

**Causa:** Compilador C nao encontrado.

**Solucao rapida (recomendada) — WinLibs GCC ~255 MB:**

```powershell
winget install BrechtSanders.WinLibs.POSIX.UCRT
# Abra um novo terminal apos instalar para o PATH ser atualizado
python build_cython.py build_ext --inplace
```

**Solucao alternativa — Visual C++ Build Tools ~5 GB:**

Instale **Visual C++ Build Tools 2019+** do site oficial da Microsoft e tente novamente:

```bash
python build_cython.py build_ext --inplace
```

**Verificar se GCC esta no PATH:**

```bash
gcc --version
```

Se retornar a versao, o compilador esta configurado corretamente.

---

## Contribuicao

1. Abra uma issue descrevendo o bug, melhoria ou proposta.
2. Crie uma branch a partir de `beta`.
3. Envie um Pull Request com descricao do que foi alterado e como testar.

Diretrizes: [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)

---

## Licenca

Distribuido sob licenca MIT. Consulte [LICENSE](LICENSE)...

---

## Gameplay

<p align="center">
  <img src="screenshots/gameplay_readme.gif" alt="Gameplay do UnderWorld Hero" width="900">
</p>

