"""Sistema de personagens do UnderWorld Hero.

Este módulo existe para tirar a responsabilidade de personagens de dentro do
arquivo principal do jogo. A ideia é simples:

1. O arquivo principal continua sendo o dono do loop do jogo, dos sprites
   globais, dos assets e das regras gerais da run.
2. Cada personagem passa a encapsular sua própria identidade: ataque básico,
   dash, ultimate, nomes exibidos na HUD e efeitos especiais.
3. O acoplamento com o restante do projeto é feito por injeção de dependências,
   evitando import circular com jogo_final.py.

Com essa separação, editar um personagem fica muito mais barato: quase sempre a
mudança ficará concentrada neste arquivo, sem exigir vários if/else no loop
principal.
"""

import math
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass

import pygame


@dataclass
class CharacterDependencies:
    """Agrupa tudo o que o módulo de personagens precisa receber do jogo.

    Em vez de importar classes e funções do arquivo principal, recebemos essas
    referências prontas. Isso mantém o módulo independente e reduz o risco de
    dependências circulares.
    """

    char_data_map: dict
    control_reader: object
    particle_cls: object
    damage_text_cls: object
    projectile_cls: object
    melee_slash_cls: object
    gem_cls: object
    dash_speed: float
    dash_duration: float
    dash_cooldown: float
    ultimate_max_charge: int
    screen_size_getter: object


@dataclass
class CharacterCombatContext:
    """Carrega o estado dinâmico usado pelos personagens em combate.

    Este contexto é remontado pelo arquivo principal sempre que necessário,
    porque os valores mudam o tempo todo durante a run: upgrades, grupos de
    sprites, dano atual, speed de projétil e assim por diante.
    """

    enemies: object = None
    projectiles: object = None
    particles: object = None
    damage_texts: object = None
    gems: object = None
    projectile_frames_raw: object = None
    slash_frames_raw: object = None
    loader: object = None
    projectile_speed: float = 0.0
    projectile_damage: float = 0.0
    projectile_count: int = 1
    fury_multiplier: float = 1.0
    bazooka_active: bool = False
    dt: float = 0.016
    blood_rain_cls: object = None


@dataclass
class CharacterActionFeedback:
    """Resposta padronizada para ações de personagem.

    O loop principal usa esse retorno para tocar sons, alimentar o log lateral
    e disparar pequenos efeitos de interface sem precisar conhecer os detalhes
    de implementação da habilidade.
    """

    activated: bool = False
    sound_name: str = ""
    log_text: str = ""
    log_color: tuple = (220, 220, 220)
    kills_gained: int = 0


class Player(ABC, pygame.sprite.Sprite):
    """Classe base abstrata com o comportamento comum a todo personagem.

    Esta classe concentra apenas o que realmente é compartilhado:

    - carregamento de animação
    - movimentação e colisão
    - timers de dash
    - carga/tempo de ultimate
    - hooks para as subclasses personalizarem ataque e skills

    O objetivo não é ter uma classe “genérica demais”, mas sim um esqueleto bem
    estável sobre o qual cada herói pode construir sua própria identidade.
    """

    def __init__(self, loader, char_id, dependencies):
        super().__init__()
        self.deps = dependencies
        self.char_id = char_id
        self.data = dependencies.char_data_map[char_id]
        self.name = self.data.get("name", f"CHAR_{char_id}")

        # Cada personagem pode informar seu próprio tamanho e quantidade de
        # frames diretamente no CHAR_DATA, sem hardcode espalhado no jogo.
        char_size = self.data.get("size", (180, 180))
        anim_frames_count = self.data.get("anim_frames", 11)
        spritesheet_path = self.data.get("spritesheet")
        self.anim_frames = None
        if spritesheet_path and hasattr(loader, "load_spritesheet"):
            self.anim_frames = loader.load_spritesheet(
                spritesheet_path,
                self.data.get("spritesheet_frame_w", 64),
                self.data.get("spritesheet_frame_h", 64),
                anim_frames_count,
                char_size,
                frame_indices=self.data.get("spritesheet_frame_indices"),
            )
        if not self.anim_frames:
            self.anim_frames = loader.load_animation(f"char{char_id}", anim_frames_count, char_size)
        self.flipped_frames = [pygame.transform.flip(frame, True, False) for frame in self.anim_frames]

        # Animação idle (parado) — opcional. Se não existir usa o primeiro frame do walk.
        idle_path = self.data.get("spritesheet_idle")
        idle_count = self.data.get("idle_anim_frames", anim_frames_count)
        self.idle_frames = None
        if idle_path and hasattr(loader, "load_spritesheet"):
            self.idle_frames = loader.load_spritesheet(
                idle_path,
                self.data.get("spritesheet_idle_frame_w", self.data.get("spritesheet_frame_w", 64)),
                self.data.get("spritesheet_idle_frame_h", self.data.get("spritesheet_frame_h", 64)),
                idle_count,
                char_size,
                frame_indices=self.data.get("spritesheet_idle_frame_indices"),
            )
        if not self.idle_frames:
            self.idle_frames = self.anim_frames
        self.idle_flipped_frames = [pygame.transform.flip(f, True, False) for f in self.idle_frames]

        # Attack animation (opcional — só carregado se o personagem tiver a config)
        atk_path = self.data.get("spritesheet_attack")
        atk_count = self.data.get("attack_anim_frames", 0)
        self.attack_frames = None
        if atk_path and atk_count > 0 and hasattr(loader, "load_spritesheet"):
            self.attack_frames = loader.load_spritesheet(
                atk_path,
                self.data.get("spritesheet_attack_frame_w", self.data.get("spritesheet_frame_w", 64)),
                self.data.get("spritesheet_attack_frame_h", self.data.get("spritesheet_frame_h", 64)),
                atk_count,
                char_size,
                frame_indices=self.data.get("spritesheet_attack_frame_indices"),
            )
        self.attack_flipped_frames = (
            [pygame.transform.flip(f, True, False) for f in self.attack_frames]
            if self.attack_frames else None
        )
        self._atk_anim_active = False
        self._atk_frame_idx = 0
        self._atk_anim_timer = 0.0
        self._atk_anim_speed = self.data.get("attack_anim_speed", 0.07)

        self.frame_idx = 0
        self.anim_timer = 0.0
        self.anim_speed = self.data.get("anim_speed", 0.08)
        self.idle_frame_idx = 0
        self.idle_anim_timer = 0.0
        self.idle_anim_speed = self.data.get("idle_anim_speed", self.data.get("anim_speed", 0.12))

        # Projétil customizado por personagem (opcional — fallback nos frames globais)
        proj_sheet = self.data.get("projectile_spritesheet")
        self.char_projectile_frames = None
        if proj_sheet and hasattr(loader, "load_spritesheet"):
            self.char_projectile_frames = loader.load_spritesheet(
                proj_sheet,
                self.data.get("projectile_frame_w", 32),
                self.data.get("projectile_frame_h", 32),
                self.data.get("projectile_frame_count", 4),
                self.data.get("projectile_display_size"),
                frame_indices=self.data.get("projectile_frame_indices"),
            )
            if self.char_projectile_frames and self.data.get("projectile_flip_x"):
                self.char_projectile_frames = [
                    pygame.transform.flip(f, True, False)
                    for f in self.char_projectile_frames
                ]
        # Suporte a lista de frames individuais (ex: Typhoon_Frame_01..12)
        proj_frames_list = self.data.get("projectile_frames_list")
        if proj_frames_list and hasattr(loader, "load_image"):
            disp_size = self.data.get("projectile_display_size")
            _pfl = []
            for _pf_path in proj_frames_list:
                _pf_img = loader.load_image(_pf_path, disp_size, ((100, 150, 255), (50, 100, 200)))
                if _pf_img:
                    _pfl.append(_pf_img)
            if _pfl:
                self.char_projectile_frames = _pfl
        self.facing_right = True
        self._facing_dir = "down"   # up/down/left/right — usado por subclasses com 4 direções
        # Dicts de frames direcionais (populados por subclasses como Vampire).
        # Quando vazios, o sistema cai no comportamento padrão de flip horizontal.
        self._dir_walk_frames   = {}
        self._dir_idle_frames   = {}
        self._dir_attack_frames = {}
        self.image = self.anim_frames[0]
        self.rect = self.image.get_rect()
        self.pos = pygame.Vector2(0, 0)
        self.vel = pygame.Vector2(0, 0)

        # Os atributos base também vêm do CHAR_DATA. Isso facilita balancear um
        # personagem sem tocar na lógica do loop principal.
        self.base_hp = self.data.get("hp", 5)
        self.base_speed = self.data.get("speed", 280)
        self.base_damage = self.data.get("damage", 2)
        self.dash_speed = self.data.get("dash_speed", dependencies.dash_speed)
        self.dash_duration = self.data.get("dash_duration", dependencies.dash_duration)
        self.dash_cooldown = self.data.get("dash_cooldown", dependencies.dash_cooldown)

        self.dash_active = False
        self.dash_timer = 0.0
        self.dash_cooldown_timer = 0.0

        self.ult_charge = 0
        self.ult_max = dependencies.ultimate_max_charge
        self.ult_active_timer = 0.0
        self.ult_active = False

        self.hp = self.base_hp
        self.iframes = 0.0

    def get_attack_name(self):
        """Nome curto do ataque básico exibido na HUD."""
        return "Disparo Rúnico"

    def get_dash_name(self):
        """Nome curto do dash exibido na HUD e no feed lateral."""
        return "Deslocamento"

    def get_ultimate_name(self):
        """Nome curto do ultimate exibido na HUD e no feed lateral."""
        return "Poder Supremo"

    def get_skill_cards(self):
        """Retorna as três skills principais mostradas na interface.

        O formato foi mantido simples para o arquivo principal só se preocupar
        com renderização.
        """

        return [
            ("Ataque", self.get_attack_name()),
            ("Dash", self.get_dash_name()),
            ("Ultimate", self.get_ultimate_name()),
        ]

    def should_draw_tornado_effect(self):
        """Permite efeitos visuais persistentes específicos de uma ultimate."""
        return False

    def get_attack_sound(self):
        """Cada personagem pode tocar um som diferente no ataque básico."""
        return "shoot"

    def get_projectile_damage_multiplier(self):
        """Multiplicador simples para personalizar dano de personagens ranged."""
        return 1.0

    def on_dash_start(self, particles_group):
        """Hook chamado no momento exato em que o dash é iniciado."""
        return

    def on_dash_update(self, dt, combat_context):
        """Hook executado enquanto o dash permanece ativo."""
        return

    def update_ultimate_effects(self, combat_context):
        """Processa efeitos contínuos de ultimate.

        A maioria dos personagens não precisa de processamento por frame, então o
        comportamento padrão simplesmente não faz nada.
        """

        return CharacterActionFeedback()

    def _build_action_feedback(self, sound_name="", log_text="", log_color=(220, 220, 220)):
        """Pequeno helper para padronizar retornos de ações do personagem."""

        return CharacterActionFeedback(True, sound_name, log_text, log_color)

    def _attack_vectors(self, base_direction, projectile_count):
        """Gera os vetores usados em ataques com múltiplos projéteis.

        O leque de disparo fica centralizado no alvo principal, mantendo o mesmo
        comportamento que o jogo já possuía antes da refatoração.
        """

        for index in range(projectile_count):
            angle = -(15 * (projectile_count - 1)) / 2 + (index * 15)
            yield base_direction.rotate(angle)

    def start_dash(self, particles_group):
        """Ativa o dash respeitando cooldown e i-frames.

        Em vez de retornar apenas True/False, devolvemos um objeto de feedback
        para a HUD e o sistema de sons reagirem sem lógica duplicada.
        """

        if self.dash_cooldown_timer > 0:
            return CharacterActionFeedback()

        self.dash_active = True
        self.dash_timer = self.dash_duration
        self.dash_cooldown_timer = self.dash_cooldown
        self.iframes = self.dash_duration + 0.1
        self.on_dash_start(particles_group)
        return self._build_action_feedback(
            sound_name="dash",
            log_text=f"Skill: {self.get_dash_name()}",
            log_color=(80, 180, 255),
        )

    def update(self, dt, keys, obstacles, particles_group, biome_type="normal", combat_context=None):
        """Atualiza movimentação, colisão, animação e timers comuns.

        A lógica central ficou aqui porque é igual para todos os personagens.
        O que muda por personagem entra pelos hooks de dash e ultimate.
        """

        self.vel = pygame.Vector2(0, 0)

        if self.dash_active:
            self.dash_timer -= dt
            if random.random() < 0.5:
                particles_group.add(self.deps.particle_cls(self.pos, (200, 200, 200), 5, 50, 0.3))
            self.on_dash_update(dt, combat_context)
            if self.dash_timer <= 0:
                self.dash_active = False

        if self.dash_cooldown_timer > 0:
            self.dash_cooldown_timer -= dt

        if self.ult_active_timer > 0:
            self.ult_active_timer -= dt
            if self.ult_active_timer <= 0:
                self.ult_active = False

        movement = pygame.Vector2(0, 0)
        if self.deps.control_reader(keys, "up"):
            movement.y -= 1
        if self.deps.control_reader(keys, "down"):
            movement.y += 1
        if self.deps.control_reader(keys, "left"):
            movement.x -= 1
        if self.deps.control_reader(keys, "right"):
            movement.x += 1

        if movement.length_squared() > 0:
            current_speed = self.dash_speed if self.dash_active else self.base_speed
            self.vel = movement.normalize() * current_speed

            if movement.x > 0:
                self.facing_right = True
                self._facing_dir = "right"
            elif movement.x < 0:
                self.facing_right = False
                self._facing_dir = "left"
            elif movement.y > 0:
                self._facing_dir = "down"
            elif movement.y < 0:
                self._facing_dir = "up"

            move = self.vel * dt
            self.pos.x += move.x
            for obstacle in obstacles:
                if obstacle.hitbox.collidepoint(self.pos):
                    self.pos.x -= move.x

            self.pos.y += move.y
            for obstacle in obstacles:
                if obstacle.hitbox.collidepoint(self.pos):
                    self.pos.y -= move.y

            self.anim_timer += dt
            if self.anim_timer > self.anim_speed:
                self.anim_timer = 0
                self.frame_idx = (self.frame_idx + 1) % len(self.anim_frames)
            # Reinicia idle para começar do frame 0 quando voltar a andar
            self.idle_frame_idx = 0
            self.idle_anim_timer = 0.0
        else:
            self.frame_idx = 0
            self.idle_anim_timer += dt
            if self.idle_anim_timer > self.idle_anim_speed:
                self.idle_anim_timer = 0
                self.idle_frame_idx = (self.idle_frame_idx + 1) % len(self.idle_frames)

        is_moving = movement.length_squared() > 0
        if is_moving:
            if self._dir_walk_frames:
                dir_frames = self._dir_walk_frames.get(self._facing_dir) or next(iter(self._dir_walk_frames.values()))
                self.image = dir_frames[self.frame_idx % len(dir_frames)]
            else:
                frame_set = self.anim_frames if self.facing_right else self.flipped_frames
                self.image = frame_set[self.frame_idx]
        else:
            if self._dir_idle_frames:
                dir_frames = self._dir_idle_frames.get(self._facing_dir) or next(iter(self._dir_idle_frames.values()))
                self.image = dir_frames[self.idle_frame_idx % len(dir_frames)]
            else:
                frame_set = self.idle_frames if self.facing_right else self.idle_flipped_frames
                self.image = frame_set[self.idle_frame_idx]

        # Animação de ataque sobrescreve walk/idle enquanto estiver ativa
        if self._atk_anim_active and self.attack_frames:
            self._atk_anim_timer += dt
            if self._atk_anim_timer >= self._atk_anim_speed:
                self._atk_anim_timer = 0.0
                self._atk_frame_idx += 1
                if self._atk_frame_idx >= len(self.attack_frames):
                    self._atk_anim_active = False
                    self._atk_frame_idx = 0
            if self._atk_anim_active:
                if self._dir_attack_frames:
                    dir_frames = self._dir_attack_frames.get(self._facing_dir) or next(iter(self._dir_attack_frames.values()))
                    self.image = dir_frames[self._atk_frame_idx % len(dir_frames)]
                else:
                    atk_set = self.attack_frames if self.facing_right else self.attack_flipped_frames
                    self.image = atk_set[self._atk_frame_idx]

        self.iframes = max(0, self.iframes - dt)

        screen_w, screen_h = self.deps.screen_size_getter()
        self.rect.center = (screen_w // 2, screen_h // 2)

    def trigger_attack_anim(self):
        """Reinicia a animação de ataque se o personagem tiver frames de ataque."""
        if self.attack_frames:
            self._atk_anim_active = True
            self._atk_frame_idx = 0
            self._atk_anim_timer = 0.0

    def atacar(self, target, combat_context):
        """Executa o ataque básico padrão para personagens ranged.

        O loop principal não precisa mais saber se o personagem é corpo a corpo
        ou à distância. Ele apenas chama `atacar()` e deixa a subclasse decidir
        como materializar esse ataque.
        """

        if target is None:
            return CharacterActionFeedback()

        base_direction = target.pos - self.pos
        if base_direction.length_squared() <= 0:
            return CharacterActionFeedback()

        base_direction = base_direction.normalize()
        base_proj_frames = self.char_projectile_frames or combat_context.projectile_frames_raw
        for direction in self._attack_vectors(base_direction, combat_context.projectile_count):
            shoot_angle = math.degrees(math.atan2(-direction.y, direction.x))
            rotated_frames = [
                pygame.transform.rotate(frame, shoot_angle)
                for frame in base_proj_frames
            ]
            if combat_context.bazooka_active:
                projectile_damage = combat_context.projectile_damage * 3
            else:
                projectile_damage = combat_context.projectile_damage

            projectile_damage *= self.get_projectile_damage_multiplier()
            projectile_damage = int(projectile_damage * combat_context.fury_multiplier)
            projectile = self.deps.projectile_cls(
                self.pos,
                direction * combat_context.projectile_speed,
                projectile_damage,
                rotated_frames,
            )
            combat_context.projectiles.add(projectile)

        self.trigger_attack_anim()
        return self._build_action_feedback(sound_name=self.get_attack_sound())

    @abstractmethod
    def use_ultimate(self, combat_context):
        """Ativa a ultimate específica de cada personagem."""


class Warrior(Player):
    """Personagem corpo a corpo focado em pressão próxima e área persistente."""

    # Mesma ordem de linhas do Vampire: baixo=0, cima=1, esquerda=2, direita=3
    _SPRITE_DIR_ROWS = {"down": 0, "up": 1, "left": 2, "right": 3}

    def __init__(self, loader, char_id, dependencies):
        super().__init__(loader, char_id, dependencies)
        data = dependencies.char_data_map[char_id]
        char_size = data.get("size", (200, 200))

        fw = data.get("spritesheet_frame_w", 64)
        fh = data.get("spritesheet_frame_h", 64)

        # Walk direcional — guerreiro_run.png 4 rows × 8 frames
        walk_sheet = data.get("spritesheet")
        walk_n = data.get("anim_frames", 8)
        for dir_name, row in self._SPRITE_DIR_ROWS.items():
            indices = list(range(row * walk_n, (row + 1) * walk_n))
            frames = loader.load_spritesheet(walk_sheet, fw, fh, walk_n, char_size, frame_indices=indices)
            if frames:
                self._dir_walk_frames[dir_name] = frames

        # Idle direcional — guerreiro_idle.png 4 rows × 4 frames
        idle_sheet = data.get("spritesheet_idle")
        idle_n = data.get("idle_anim_frames", 4)
        idle_fw = data.get("spritesheet_idle_frame_w", fw)
        idle_fh = data.get("spritesheet_idle_frame_h", fh)
        for dir_name, row in self._SPRITE_DIR_ROWS.items():
            indices = list(range(row * idle_n, (row + 1) * idle_n))
            frames = loader.load_spritesheet(idle_sheet, idle_fw, idle_fh, idle_n, char_size, frame_indices=indices)
            if frames:
                self._dir_idle_frames[dir_name] = frames

        # Ataque direcional — guerreiro_ataque.png 4 rows × 8 frames
        atk_sheet = data.get("spritesheet_attack")
        atk_n = data.get("attack_anim_frames", 8)
        atk_fw = data.get("spritesheet_attack_frame_w", fw)
        atk_fh = data.get("spritesheet_attack_frame_h", fh)
        if atk_sheet:
            for dir_name, row in self._SPRITE_DIR_ROWS.items():
                indices = list(range(row * atk_n, (row + 1) * atk_n))
                frames = loader.load_spritesheet(atk_sheet, atk_fw, atk_fh, atk_n, char_size, frame_indices=indices)
                if frames:
                    self._dir_attack_frames[dir_name] = frames
            if self._dir_attack_frames and not self.attack_frames:
                self.attack_frames = next(iter(self._dir_attack_frames.values()))

        # Efeito de ataque mid-range — efeito_guerreiro.png 4 rows × 4 frames de 64x128
        # Row "right" (linha 3) está vazia no sprite — usa flip horizontal da direção "left"
        eff_sheet = data.get("slash_effect_spritesheet")
        eff_n     = data.get("slash_effect_frames", 4)
        eff_fw    = data.get("slash_effect_frame_w", 64)
        eff_fh    = data.get("slash_effect_frame_h", 128)
        eff_size  = (int(char_size[0] * 1.5), int(char_size[1] * 1.5))
        self._slash_dir_frames = {}
        if eff_sheet:
            for dir_name, row in self._SPRITE_DIR_ROWS.items():
                if dir_name == "right":
                    continue  # gerado por flip abaixo
                indices = list(range(row * eff_n, (row + 1) * eff_n))
                frames = loader.load_spritesheet(eff_sheet, eff_fw, eff_fh, eff_n, eff_size, frame_indices=indices)
                if frames:
                    self._slash_dir_frames[dir_name] = frames
            # "right" = flip horizontal de "left"
            if "left" in self._slash_dir_frames:
                self._slash_dir_frames["right"] = [
                    pygame.transform.flip(f, True, False) for f in self._slash_dir_frames["left"]
                ]

        # Ultimate — ultimate_guerreiro.png 256x640, animação linear:
        # 2 colunas × 4 linhas = 8 frames, lidos esq→dir, linha por linha (não direcional)
        ult_sheet = data.get("ultimate_spritesheet")
        ult_fw    = data.get("ultimate_frame_w", 128)
        ult_fh    = data.get("ultimate_frame_h", 160)
        ult_n     = data.get("ultimate_frames_per_row", 2)
        ult_rows  = data.get("ultimate_rows", 4)
        # Tamanho de exibição: 4× o frame natural, mantendo proporção
        ult_size  = (ult_fw * 4, ult_fh * 4)
        self._ult_display_frames = []
        if ult_sheet and hasattr(loader, "load_spritesheet"):
            for row in range(ult_rows):
                indices = list(range(row * ult_n, (row + 1) * ult_n))
                frames = loader.load_spritesheet(
                    ult_sheet, ult_fw, ult_fh, ult_n, ult_size, frame_indices=indices
                )
                if frames:
                    self._ult_display_frames.extend(frames)
        self._ult_frame_idx   = 0
        self._ult_frame_timer = 0.0
        self._ult_frame_speed = 0.10   # segundos por frame — faz loop enquanto ult ativa

    def get_attack_name(self):
        return "Corte Direcional"

    def get_dash_name(self):
        return "Investida Guardiã"

    def get_ultimate_name(self):
        return "Fúria do Guerreiro"

    def get_attack_sound(self):
        return "slash"

    def should_draw_tornado_effect(self):
        return False

    def get_ult_anim_frame(self):
        """Retorna o frame atual da animação linear da ultimate, ou None."""
        if not self._ult_display_frames:
            return None
        idx = self._ult_frame_idx % len(self._ult_display_frames)
        return self._ult_display_frames[idx]

    def atacar(self, target, combat_context):
        """Ataque mid-range usando efeito_guerreiro.png como projétil de curto alcance."""

        if target is None:
            return CharacterActionFeedback()

        base_direction = target.pos - self.pos
        if base_direction.length_squared() <= 0:
            return CharacterActionFeedback()

        base_direction = base_direction.normalize()

        # Seleciona frames do efeito de acordo com a direção atual
        eff_frames = (
            self._slash_dir_frames.get(self._facing_dir)
            or (next(iter(self._slash_dir_frames.values())) if self._slash_dir_frames else None)
        )

        for direction in self._attack_vectors(base_direction, combat_context.projectile_count):
            melee_damage = int((combat_context.projectile_damage + 2) * combat_context.fury_multiplier)

            if eff_frames:
                # Mid-range: projétil com alcance limitado usando efeito direcional
                shoot_angle = math.degrees(math.atan2(-direction.y, direction.x))
                rotated = [pygame.transform.rotate(f, shoot_angle) for f in eff_frames]
                proj = self.deps.projectile_cls(
                    self.pos,
                    direction * 480,
                    melee_damage,
                    rotated,
                )
                proj.max_range  = 220
                proj._spawn_pos = pygame.Vector2(self.pos)
                proj.pierce     = 2
                combat_context.projectiles.add(proj)
            else:
                slash = self.deps.melee_slash_cls(self, direction, melee_damage, combat_context.slash_frames_raw)
                slash.distance = 180
                slash.pos = self.pos + direction * 180
                combat_context.projectiles.add(slash)

        self.trigger_attack_anim()
        return self._build_action_feedback(sound_name=self.get_attack_sound())

    def use_ultimate(self, combat_context):
        if self.ult_charge < self.ult_max:
            return CharacterActionFeedback()

        self.ult_charge = 0
        self.ult_active = True
        self.ult_active_timer = 3.0
        self._ult_frame_idx   = 0
        self._ult_frame_timer = 0.0
        return self._build_action_feedback(
            log_text=f"Ultimate: {self.get_ultimate_name()}",
            log_color=(255, 90, 90),
        )

    def update_ultimate_effects(self, combat_context):
        """Avança a animação da ultimate e aplica dano em área enquanto ativa."""

        if not self.ult_active:
            return CharacterActionFeedback()

        # Avança frame da animação linear em loop enquanto a ultimate estiver ativa
        self._ult_frame_timer += combat_context.dt
        if self._ult_frame_timer >= self._ult_frame_speed:
            self._ult_frame_timer = 0.0
            if self._ult_display_frames:
                self._ult_frame_idx = (self._ult_frame_idx + 1) % len(self._ult_display_frames)

        if random.random() < 0.8:
            combat_context.particles.add(
                self.deps.particle_cls(
                    self.pos + pygame.Vector2(random.randint(-120, 120), random.randint(-120, 120)),
                    (255, 180, 60),
                    6, 220, 0.4,
                )
            )

        kills_gained = 0
        for enemy in combat_context.enemies:
            if self.pos.distance_to(enemy.pos) < 250:
                enemy.hp -= 2
                if random.random() < 0.2:
                    combat_context.damage_texts.add(
                        self.deps.damage_text_cls(enemy.pos, 2, False, (255, 200, 0))
                    )
                if enemy.hp <= 0:
                    if self.ult_charge < self.ult_max:
                        self.ult_charge += 1
                    combat_context.gems.add(self.deps.gem_cls(enemy.pos, combat_context.loader))
                    enemy.kill()
                    kills_gained += 1

        return CharacterActionFeedback(kills_gained=kills_gained)


class Assassin(Player):
    """Personagem móvel e agressivo, com dash ofensivo e chuva de flechas de fogo."""

    def __init__(self, loader, char_id, dependencies):
        super().__init__(loader, char_id, dependencies)
        self._dash_hit_targets = set()

        # Projétil exclusivo da ultimate: flechafire.png
        data = dependencies.char_data_map[char_id]
        ult_sheet = data.get("ultimate_projectile_spritesheet")
        self._ult_projectile_frames = None
        if ult_sheet and hasattr(loader, "load_spritesheet"):
            self._ult_projectile_frames = loader.load_spritesheet(
                ult_sheet,
                data.get("ultimate_projectile_frame_w", 30),
                data.get("ultimate_projectile_frame_h", 5),
                data.get("ultimate_projectile_frame_count", 1),
                data.get("ultimate_projectile_display_size", (55, 9)),
            )

    def get_attack_name(self):
        return "Rajada Precisa"

    def get_dash_name(self):
        return "Passo Sombrio"

    def get_ultimate_name(self):
        return "Chuva de Flechas"

    def on_dash_start(self, particles_group):
        self._dash_hit_targets.clear()

    def on_dash_update(self, dt, combat_context):
        """Durante o dash, o assassino corta inimigos atravessados pela corrida."""

        if combat_context is None or not combat_context.enemies:
            return

        dash_damage = int(self.base_damage * 2 + 2)
        for enemy in combat_context.enemies:
            if enemy in self._dash_hit_targets:
                continue
            if self.pos.distance_to(enemy.pos) <= 110:
                enemy.hp -= dash_damage
                self._dash_hit_targets.add(enemy)
                if combat_context.damage_texts is not None:
                    combat_context.damage_texts.add(
                        self.deps.damage_text_cls(enemy.pos, dash_damage, False, (255, 120, 120))
                    )

    def get_projectile_damage_multiplier(self):
        return 1.1

    def use_ultimate(self, combat_context):
        if self.ult_charge < self.ult_max:
            return CharacterActionFeedback()

        self.ult_charge = 0
        # Usa flechafire para a ultimate, com fallback para o projétil padrão do personagem
        base_frames = self._ult_projectile_frames or self.char_projectile_frames or combat_context.projectile_frames_raw
        for index in range(36):
            angle = index * 10
            direction = pygame.Vector2(1, 0).rotate(angle)
            shoot_angle = math.degrees(math.atan2(-direction.y, direction.x))
            rotated_frames = [
                pygame.transform.rotate(frame, shoot_angle)
                for frame in base_frames
            ]
            projectile = self.deps.projectile_cls(
                self.pos,
                direction * combat_context.projectile_speed,
                int(combat_context.projectile_damage * 3 * self.get_projectile_damage_multiplier()),
                rotated_frames,
            )
            projectile.pierce = 5
            combat_context.projectiles.add(projectile)

        return self._build_action_feedback(
            log_text=f"Ultimate: {self.get_ultimate_name()}",
            log_color=(255, 170, 80),
        )


class Mage(Player):
    """Personagem de controle, com foco em utilidade e congelamento de massa."""

    def get_attack_name(self):
        return "Orbe Arcano"

    def get_dash_name(self):
        return "Passo Arcano"

    def get_ultimate_name(self):
        return "Congelamento Temporal"

    def use_ultimate(self, combat_context):
        if self.ult_charge < self.ult_max:
            return CharacterActionFeedback()

        self.ult_charge = 0
        for enemy in combat_context.enemies:
            enemy.frozen_timer = 5.0

        return self._build_action_feedback(
            log_text=f"Ultimate: {self.get_ultimate_name()}",
            log_color=(120, 220, 255),
        )


class Vampire(Player):
    """Personagem sombrio de média distância, com projéteis sombrios e drenar de vida."""

    # Ordem das linhas no spritesheet do Vampire: baixo=0, cima=1, esquerda=2, direita=3
    _SPRITE_DIR_ROWS = {"down": 0, "up": 1, "left": 2, "right": 3}

    def __init__(self, loader, char_id, dependencies):
        super().__init__(loader, char_id, dependencies)
        data = dependencies.char_data_map[char_id]
        char_size = data.get("size", (150, 150))

        fw = data.get("spritesheet_frame_w", 64)
        fh = data.get("spritesheet_frame_h", 64)
        walk_sheet = data.get("spritesheet")
        walk_n = data.get("anim_frames", 8)
        for dir_name, row in self._SPRITE_DIR_ROWS.items():
            indices = list(range(row * walk_n, (row + 1) * walk_n))
            frames = loader.load_spritesheet(walk_sheet, fw, fh, walk_n, char_size, frame_indices=indices)
            if frames:
                self._dir_walk_frames[dir_name] = frames

        idle_fw = data.get("spritesheet_idle_frame_w", fw)
        idle_fh = data.get("spritesheet_idle_frame_h", fh)
        idle_sheet = data.get("spritesheet_idle")
        idle_n = data.get("idle_anim_frames", 4)
        for dir_name, row in self._SPRITE_DIR_ROWS.items():
            indices = list(range(row * idle_n, (row + 1) * idle_n))
            frames = loader.load_spritesheet(idle_sheet, idle_fw, idle_fh, idle_n, char_size, frame_indices=indices)
            if frames:
                self._dir_idle_frames[dir_name] = frames

        atk_fw = data.get("spritesheet_attack_frame_w", fw)
        atk_fh = data.get("spritesheet_attack_frame_h", fh)
        atk_sheet = data.get("spritesheet_attack")
        atk_n = data.get("attack_anim_frames", 12)
        if atk_sheet and atk_n:
            for dir_name, row in self._SPRITE_DIR_ROWS.items():
                indices = list(range(row * atk_n, (row + 1) * atk_n))
                frames = loader.load_spritesheet(atk_sheet, atk_fw, atk_fh, atk_n, char_size, frame_indices=indices)
                if frames:
                    self._dir_attack_frames[dir_name] = frames
            # Garante que attack_frames (usado como flag de habilitação) está preenchido
            if self._dir_attack_frames and not self.attack_frames:
                self.attack_frames = next(iter(self._dir_attack_frames.values()))

    def get_attack_name(self):
        return "Lança Sombria"

    def get_dash_name(self):
        return "Voo Sombrio"

    def get_ultimate_name(self):
        return "Tempestade Sombria"

    def get_projectile_damage_multiplier(self):
        return 1.2

    def use_ultimate(self, combat_context):
        if self.ult_charge < self.ult_max:
            return CharacterActionFeedback()

        self.ult_charge = 0
        base_frames = self.char_projectile_frames or combat_context.projectile_frames_raw
        # Dispara 8 projéteis em todas as direções
        for i in range(8):
            angle = i * 45
            direction = pygame.Vector2(1, 0).rotate(angle)
            shoot_angle = math.degrees(math.atan2(-direction.y, direction.x))
            rotated_frames = [
                pygame.transform.rotate(frame, shoot_angle)
                for frame in base_frames
            ]
            projectile = self.deps.projectile_cls(
                self.pos,
                direction * combat_context.projectile_speed * 1.4,
                int(combat_context.projectile_damage * 4 * self.get_projectile_damage_multiplier()),
                rotated_frames,
            )
            projectile.pierce = 3
            combat_context.projectiles.add(projectile)

        return self._build_action_feedback(
            log_text=f"Ultimate: {self.get_ultimate_name()}",
            log_color=(180, 0, 255),
        )


class Demon(Player):
    """Personagem de alta ofensiva: projéteis de fogo e rajada infernal em todas as direções."""

    # Mesma ordem de linhas que Vampire/Warrior: baixo=0, cima=1, esquerda=2, direita=3
    _SPRITE_DIR_ROWS = {"down": 0, "up": 1, "left": 2, "right": 3}

    def __init__(self, loader, char_id, dependencies):
        super().__init__(loader, char_id, dependencies)
        data = dependencies.char_data_map[char_id]
        char_size = data.get("size", (200, 200))

        fw = data.get("spritesheet_frame_w", 128)
        fh = data.get("spritesheet_frame_h", 128)

        # Walk direcional — demon_run.png 4 rows × 8 frames de 128×128
        walk_sheet = data.get("spritesheet")
        walk_n = data.get("anim_frames", 8)
        for dir_name, row in self._SPRITE_DIR_ROWS.items():
            indices = list(range(row * walk_n, (row + 1) * walk_n))
            frames = loader.load_spritesheet(walk_sheet, fw, fh, walk_n, char_size, frame_indices=indices)
            if frames:
                self._dir_walk_frames[dir_name] = frames

        # Idle direcional — demon_idle.png 4 rows × 4 frames de 128×128
        idle_sheet = data.get("spritesheet_idle")
        idle_n = data.get("idle_anim_frames", 4)
        idle_fw = data.get("spritesheet_idle_frame_w", fw)
        idle_fh = data.get("spritesheet_idle_frame_h", fh)
        for dir_name, row in self._SPRITE_DIR_ROWS.items():
            indices = list(range(row * idle_n, (row + 1) * idle_n))
            frames = loader.load_spritesheet(idle_sheet, idle_fw, idle_fh, idle_n, char_size, frame_indices=indices)
            if frames:
                self._dir_idle_frames[dir_name] = frames

        # Ataque direcional — demon_ataque.png 4 rows × 10 frames de 128×128
        # Sequência invertida: sprite foi desenhado da direita para a esquerda
        atk_sheet = data.get("spritesheet_attack")
        atk_n = data.get("attack_anim_frames", 10)
        atk_fw = data.get("spritesheet_attack_frame_w", fw)
        atk_fh = data.get("spritesheet_attack_frame_h", fh)
        if atk_sheet:
            for dir_name, row in self._SPRITE_DIR_ROWS.items():
                indices = list(range(row * atk_n, (row + 1) * atk_n))[::-1]
                frames = loader.load_spritesheet(atk_sheet, atk_fw, atk_fh, atk_n, char_size, frame_indices=indices)
                if frames:
                    self._dir_attack_frames[dir_name] = frames
            if self._dir_attack_frames and not self.attack_frames:
                self.attack_frames = next(iter(self._dir_attack_frames.values()))

    def get_attack_name(self):
        return "Fogo Infernal"

    def get_dash_name(self):
        return "Teletransporte"

    def get_ultimate_name(self):
        return "Chama Infernal"

    def get_attack_sound(self):
        return "shoot"

    def get_projectile_damage_multiplier(self):
        return 1.25

    def use_ultimate(self, combat_context):
        """Dispara 6 projéteis de fogo em todas as direções (60° cada), igual ao Vampire mas menor."""
        if self.ult_charge < self.ult_max:
            return CharacterActionFeedback()

        self.ult_charge = 0
        base_frames = self.char_projectile_frames or combat_context.projectile_frames_raw
        # 6 projéteis a cada 60° — Vampire usa 8 a cada 45°; Demônio é "um pouco menor"
        for i in range(6):
            angle = i * 60
            direction = pygame.Vector2(1, 0).rotate(angle)
            shoot_angle = math.degrees(math.atan2(-direction.y, direction.x))
            rotated_frames = [pygame.transform.rotate(frame, shoot_angle) for frame in base_frames]
            proj = self.deps.projectile_cls(
                self.pos,
                direction * combat_context.projectile_speed,
                int(combat_context.projectile_damage * 3.5 * self.get_projectile_damage_multiplier()),
                rotated_frames,
            )
            proj.pierce = 3
            combat_context.projectiles.add(proj)

        return self._build_action_feedback(
            log_text=f"Ultimate: {self.get_ultimate_name()}",
            log_color=(255, 80, 0),
        )


class Golem(Player):
    """Herói tanque corpo a corpo — alto HP, soco de pedra e terremoto em área."""

    # Mesma ordem que Vampire/Warrior: baixo=0, cima=1, esquerda=2, direita=3
    _SPRITE_DIR_ROWS = {"down": 0, "up": 1, "left": 2, "right": 3}

    def __init__(self, loader, char_id, dependencies):
        super().__init__(loader, char_id, dependencies)
        data = dependencies.char_data_map[char_id]
        char_size = data.get("size", (220, 220))

        fw = data.get("spritesheet_frame_w", 128)
        fh = data.get("spritesheet_frame_h", 128)

        # Walk direcional — golem_run.png: 1024×512, 4 rows × 8 frames de 128×128
        walk_sheet = data.get("spritesheet")
        walk_n = data.get("anim_frames", 8)
        for dir_name, row in self._SPRITE_DIR_ROWS.items():
            indices = list(range(row * walk_n, (row + 1) * walk_n))
            frames = loader.load_spritesheet(walk_sheet, fw, fh, walk_n, char_size, frame_indices=indices)
            if frames:
                self._dir_walk_frames[dir_name] = frames

        # Idle direcional — golem_idle.png: 512×512, 4 rows × 4 frames de 128×128
        idle_sheet = data.get("spritesheet_idle")
        idle_n = data.get("idle_anim_frames", 4)
        idle_fw = data.get("spritesheet_idle_frame_w", fw)
        idle_fh = data.get("spritesheet_idle_frame_h", fh)
        for dir_name, row in self._SPRITE_DIR_ROWS.items():
            indices = list(range(row * idle_n, (row + 1) * idle_n))
            frames = loader.load_spritesheet(idle_sheet, idle_fw, idle_fh, idle_n, char_size, frame_indices=indices)
            if frames:
                self._dir_idle_frames[dir_name] = frames

    def get_attack_name(self):
        return "Soco de Pedra"

    def get_dash_name(self):
        return "Investida Granítica"

    def get_ultimate_name(self):
        return "Golpe da Terra"

    def get_attack_sound(self):
        return "slash"

    def get_projectile_damage_multiplier(self):
        return 1.3

    def atacar(self, target, combat_context):
        """Ataque melee corpo a corpo: usa efeito basic_golem.png como slash de impacto."""
        if target is None:
            return CharacterActionFeedback()

        base_direction = target.pos - self.pos
        if base_direction.length_squared() <= 0:
            return CharacterActionFeedback()

        base_direction = base_direction.normalize()
        melee_frames = self.char_projectile_frames or combat_context.slash_frames_raw

        for direction in self._attack_vectors(base_direction, combat_context.projectile_count):
            melee_damage = int(
                (combat_context.projectile_damage + 3)
                * self.get_projectile_damage_multiplier()
                * combat_context.fury_multiplier
            )
            slash = self.deps.melee_slash_cls(self, direction, melee_damage, melee_frames)
            slash.distance = 110
            combat_context.projectiles.add(slash)

        self.trigger_attack_anim()
        return self._build_action_feedback(sound_name=self.get_attack_sound())

    def use_ultimate(self, combat_context):
        """Golpe da Terra: estouro de slashes em todas as direções ao redor do Golem."""
        if self.ult_charge < self.ult_max:
            return CharacterActionFeedback()

        self.ult_charge = 0
        melee_frames = self.char_projectile_frames or combat_context.slash_frames_raw
        ult_damage = int(
            (combat_context.projectile_damage + 5)
            * self.get_projectile_damage_multiplier()
            * 2.5
            * combat_context.fury_multiplier
        )

        # 8 slashes em todas as direções (a cada 45°) — dois anéis de distância
        for ring_dist in (100, 190):
            for i in range(8):
                angle = i * 45
                direction = pygame.Vector2(1, 0).rotate(angle)
                slash = self.deps.melee_slash_cls(self, direction, ult_damage, melee_frames)
                slash.distance = ring_dist
                combat_context.projectiles.add(slash)

        # Partículas de impacto
        for _ in range(24):
            angle = random.uniform(0, math.pi * 2)
            offset = pygame.Vector2(math.cos(angle), math.sin(angle)) * random.uniform(60, 200)
            combat_context.particles.add(
                self.deps.particle_cls(
                    self.pos + offset,
                    random.choice([(220, 140, 50), (255, 80, 30), (200, 60, 20)]),
                    random.randint(5, 9), random.randint(150, 280), 0.45,
                )
            )

        return self._build_action_feedback(
            log_text=f"Ultimate: {self.get_ultimate_name()}",
            log_color=(200, 130, 50),
        )


class Skeleton(Player):
    """Herói melee ágil — HP médio, golpes rápidos com esguicho de sangue e frenesi ultimate."""

    _SPRITE_DIR_ROWS = {"down": 0, "up": 1, "left": 2, "right": 3}

    # Cores de sangue usadas nos efeitos de partícula do ataque
    _BLOOD_COLORS = [
        (200, 0, 0), (180, 10, 10), (220, 20, 20),
        (150, 0, 0), (255, 30, 30), (140, 0, 0),
    ]

    def __init__(self, loader, char_id, dependencies):
        super().__init__(loader, char_id, dependencies)
        data = dependencies.char_data_map[char_id]
        char_size = data.get("size", (200, 200))

        fw = data.get("spritesheet_frame_w", 64)
        fh = data.get("spritesheet_frame_h", 64)

        # Walk direcional — Skeleton3_Run_with_shadow.png: 512×256, 4 rows × 8 frames de 64×64
        walk_sheet = data.get("spritesheet")
        walk_n = data.get("anim_frames", 8)
        for dir_name, row in self._SPRITE_DIR_ROWS.items():
            indices = list(range(row * walk_n, (row + 1) * walk_n))
            frames = loader.load_spritesheet(walk_sheet, fw, fh, walk_n, char_size, frame_indices=indices)
            if frames:
                self._dir_walk_frames[dir_name] = frames

        # Idle direcional — Skeleton3_Idle_with_shadow.png: 256×256, 4 rows × 4 frames de 64×64
        idle_sheet = data.get("spritesheet_idle")
        idle_n = data.get("idle_anim_frames", 4)
        idle_fw = data.get("spritesheet_idle_frame_w", fw)
        idle_fh = data.get("spritesheet_idle_frame_h", fh)
        for dir_name, row in self._SPRITE_DIR_ROWS.items():
            indices = list(range(row * idle_n, (row + 1) * idle_n))
            frames = loader.load_spritesheet(idle_sheet, idle_fw, idle_fh, idle_n, char_size, frame_indices=indices)
            if frames:
                self._dir_idle_frames[dir_name] = frames

        # Attack direcional — Skeleton3_Attack_with_shadow.png: 576×256, 4 rows × 9 frames de 64×64
        atk_sheet = data.get("spritesheet_attack")
        atk_n = data.get("attack_anim_frames", 9)
        atk_fw = data.get("spritesheet_attack_frame_w", fw)
        atk_fh = data.get("spritesheet_attack_frame_h", fh)
        for dir_name, row in self._SPRITE_DIR_ROWS.items():
            indices = list(range(row * atk_n, (row + 1) * atk_n))
            frames = loader.load_spritesheet(atk_sheet, atk_fw, atk_fh, atk_n, char_size, frame_indices=indices)
            if frames:
                self._dir_attack_frames[dir_name] = frames

    def get_attack_name(self):
        return "Golpe Cadavérico"

    def get_dash_name(self):
        return "Avanço Sombrio"

    def get_ultimate_name(self):
        return "Frenesi Sanguinário"

    def get_attack_sound(self):
        return "slash"

    def get_projectile_damage_multiplier(self):
        return 1.2

    def atacar(self, target, combat_context):
        """Ataque melee com gotículas de sangue — efeito grande estilo splash."""
        if target is None:
            return CharacterActionFeedback()

        base_direction = target.pos - self.pos
        if base_direction.length_squared() <= 0:
            return CharacterActionFeedback()

        base_direction = base_direction.normalize()
        melee_frames = self.char_projectile_frames or combat_context.slash_frames_raw

        for direction in self._attack_vectors(base_direction, combat_context.projectile_count):
            melee_damage = int(
                (combat_context.projectile_damage + 2)
                * self.get_projectile_damage_multiplier()
                * combat_context.fury_multiplier
            )
            slash = self.deps.melee_slash_cls(self, direction, melee_damage, melee_frames)
            slash.distance = 100
            combat_context.projectiles.add(slash)

        # Ponto de impacto estimado
        hit_pos = self.pos + base_direction * 100

        # Blobs grandes (efeito de splash estilo tela de carregamento)
        for _ in range(6):
            p = self.deps.particle_cls(
                hit_pos,
                random.choice(self._BLOOD_COLORS[:3]),
                random.randint(18, 32),
                random.randint(35, 85),
                random.uniform(0.35, 0.65),
            )
            p.vel.x += base_direction.x * 65
            p.vel.y += base_direction.y * 65
            combat_context.particles.add(p)

        # Gotículas médias
        for _ in range(10):
            p = self.deps.particle_cls(
                hit_pos,
                random.choice(self._BLOOD_COLORS),
                random.randint(6, 13),
                random.randint(75, 170),
                random.uniform(0.22, 0.48),
            )
            p.vel.x += base_direction.x * 90
            p.vel.y += base_direction.y * 90
            combat_context.particles.add(p)

        # Spray fino em cone
        for _ in range(8):
            spread_dir = base_direction.rotate(random.uniform(-40, 40))
            spray_pos = self.pos + spread_dir * random.randint(55, 135)
            p = self.deps.particle_cls(
                spray_pos,
                random.choice(self._BLOOD_COLORS[2:]),
                random.randint(3, 7),
                random.randint(110, 210),
                random.uniform(0.18, 0.38),
            )
            combat_context.particles.add(p)

        self.trigger_attack_anim()
        return self._build_action_feedback(sound_name=self.get_attack_sound())

    def use_ultimate(self, combat_context):
        """Frenesi Sanguinário: chuva de sangue massiva caindo do céu em área enorme."""
        if self.ult_charge < self.ult_max:
            return CharacterActionFeedback()

        self.ult_charge = 0
        rain_cls = combat_context.blood_rain_cls
        if rain_cls is None:
            return CharacterActionFeedback()

        # Chuva centrada no próprio Esqueleto, abrangendo toda a área ao redor
        rain_radius = 340
        n_drops = 40
        ult_dmg = max(1, int(
            (combat_context.projectile_damage + 4)
            * self.get_projectile_damage_multiplier()
            * 0.55   # dano moderado por gota — área compensa
            * combat_context.fury_multiplier
        ))

        for _ in range(n_drops):
            angle = random.uniform(0, math.pi * 2)
            r = rain_radius * math.sqrt(random.random())
            drop_pos = self.pos + pygame.Vector2(math.cos(angle), math.sin(angle)) * r
            combat_context.projectiles.add(rain_cls(drop_pos, ult_dmg))

        # Explosão de partículas de sangue junto com a chuva
        for _ in range(28):
            angle = random.uniform(0, math.pi * 2)
            dist = random.uniform(40, 180)
            offset = pygame.Vector2(math.cos(angle), math.sin(angle)) * dist
            p = self.deps.particle_cls(
                self.pos + offset,
                random.choice(self._BLOOD_COLORS),
                random.randint(10, 28),
                random.randint(20, 100),
                random.uniform(0.4, 0.85),
            )
            p.vel.x += math.cos(angle) * 100
            p.vel.y += math.sin(angle) * 100
            combat_context.particles.add(p)

        return self._build_action_feedback(
            log_text=f"Ultimate: {self.get_ultimate_name()}",
            log_color=(180, 0, 0),
        )


class Hurricane(Player):
    """Herói ranged — projéteis de furacão e vórtice de tempestade em área."""

    _SPRITE_DIR_ROWS = {"down": 0, "up": 1, "left": 2, "right": 3}
    _WIND_COLORS = [
        (100, 200, 255), (140, 220, 255), (180, 240, 255),
        (60, 160, 220), (200, 230, 255), (120, 180, 220),
    ]

    def __init__(self, loader, char_id, dependencies):
        super().__init__(loader, char_id, dependencies)
        data = dependencies.char_data_map[char_id]
        char_size = data.get("size", (200, 200))

        fw = data.get("spritesheet_frame_w", 64)
        fh = data.get("spritesheet_frame_h", 64)

        # Walk direcional — Lich3_Run_with_shadow.png 384×256, 4 rows × 6 frames de 64×64
        walk_sheet = data.get("spritesheet")
        walk_n = data.get("anim_frames", 6)
        for dir_name, row in self._SPRITE_DIR_ROWS.items():
            indices = list(range(row * walk_n, (row + 1) * walk_n))
            frames = loader.load_spritesheet(walk_sheet, fw, fh, walk_n, char_size, frame_indices=indices)
            if frames:
                self._dir_walk_frames[dir_name] = frames

        # Idle direcional — Lich3_Idle_with_shadow.png 256×256, 4 rows × 4 frames de 64×64
        idle_sheet = data.get("spritesheet_idle")
        idle_n = data.get("idle_anim_frames", 4)
        idle_fw = data.get("spritesheet_idle_frame_w", fw)
        idle_fh = data.get("spritesheet_idle_frame_h", fh)
        for dir_name, row in self._SPRITE_DIR_ROWS.items():
            indices = list(range(row * idle_n, (row + 1) * idle_n))
            frames = loader.load_spritesheet(idle_sheet, idle_fw, idle_fh, idle_n, char_size, frame_indices=indices)
            if frames:
                self._dir_idle_frames[dir_name] = frames

        # Ataque direcional — Lich3_Attack_with_shadow.png 512×256, 4 rows × 8 frames de 64×64
        atk_sheet = data.get("spritesheet_attack")
        atk_n = data.get("attack_anim_frames", 8)
        atk_fw = data.get("spritesheet_attack_frame_w", fw)
        atk_fh = data.get("spritesheet_attack_frame_h", fh)
        if atk_sheet:
            for dir_name, row in self._SPRITE_DIR_ROWS.items():
                indices = list(range(row * atk_n, (row + 1) * atk_n))
                frames = loader.load_spritesheet(atk_sheet, atk_fw, atk_fh, atk_n, char_size, frame_indices=indices)
                if frames:
                    self._dir_attack_frames[dir_name] = frames
            if self._dir_attack_frames and not self.attack_frames:
                self.attack_frames = next(iter(self._dir_attack_frames.values()))

    def get_attack_name(self):
        return "Rajada de Furacão"

    def get_dash_name(self):
        return "Impulso do Vento"

    def get_ultimate_name(self):
        return "Vórtice da Tempestade"

    def get_attack_sound(self):
        return "shoot"

    def get_projectile_damage_multiplier(self):
        return 1.15

    def atacar(self, target, combat_context):
        """Projétil de furacão — vórtice não rotaciona com a direção de disparo."""
        if target is None:
            return CharacterActionFeedback()
        base_direction = target.pos - self.pos
        if base_direction.length_squared() <= 0:
            return CharacterActionFeedback()
        base_direction = base_direction.normalize()
        base_proj_frames = self.char_projectile_frames or combat_context.projectile_frames_raw
        for direction in self._attack_vectors(base_direction, combat_context.projectile_count):
            if combat_context.bazooka_active:
                projectile_damage = combat_context.projectile_damage * 3
            else:
                projectile_damage = combat_context.projectile_damage
            projectile_damage = int(
                projectile_damage * self.get_projectile_damage_multiplier() * combat_context.fury_multiplier
            )
            proj = self.deps.projectile_cls(
                self.pos,
                direction * combat_context.projectile_speed,
                projectile_damage,
                base_proj_frames,
            )
            combat_context.projectiles.add(proj)
        self.trigger_attack_anim()
        return self._build_action_feedback(sound_name=self.get_attack_sound())

    def use_ultimate(self, combat_context):
        """Vórtice da Tempestade: 12 projéteis de furacão em círculo + rajada de vento."""
        if self.ult_charge < self.ult_max:
            return CharacterActionFeedback()

        self.ult_charge = 0
        base_frames = self.char_projectile_frames or combat_context.projectile_frames_raw

        n_proj = 12
        ult_dmg = int(
            combat_context.projectile_damage
            * self.get_projectile_damage_multiplier()
            * 2.2
            * combat_context.fury_multiplier
        )
        for i in range(n_proj):
            angle = i * (360 / n_proj)
            direction = pygame.Vector2(1, 0).rotate(angle)
            proj = self.deps.projectile_cls(
                self.pos,
                direction * combat_context.projectile_speed * 1.2,
                ult_dmg,
                base_frames,
            )
            proj.pierce = 3
            combat_context.projectiles.add(proj)

        for _ in range(32):
            angle = random.uniform(0, math.pi * 2)
            dist = random.uniform(30, 180)
            offset = pygame.Vector2(math.cos(angle), math.sin(angle)) * dist
            p = self.deps.particle_cls(
                self.pos + offset,
                random.choice(self._WIND_COLORS),
                random.randint(8, 22),
                random.randint(25, 110),
                random.uniform(0.3, 0.75),
            )
            p.vel.x += math.cos(angle) * 130
            p.vel.y += math.sin(angle) * 130
            combat_context.particles.add(p)

        return self._build_action_feedback(
            log_text=f"Ultimate: {self.get_ultimate_name()}",
            log_color=(100, 200, 255),
        )


PLAYER_CLASS_FACTORY = {
    0: Warrior,
    1: Assassin,
    2: Mage,
    3: Vampire,
    4: Demon,
    5: Golem,
    6: Skeleton,
    7: Hurricane,
}


def create_player(loader, char_id, dependencies):
    """Factory central para construir o personagem correto a partir do char_id."""

    safe_char_id = char_id if char_id in dependencies.char_data_map else 0
    player_cls = PLAYER_CLASS_FACTORY.get(safe_char_id, Warrior)
    return player_cls(loader, safe_char_id, dependencies)
