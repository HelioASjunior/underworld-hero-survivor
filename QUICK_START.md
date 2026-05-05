"""
QUICK START - Guia Rápido de Integração

Este arquivo fornece snippets prontos para copiar e colar.

═════════════════════════════════════════════════════════════════════════════════
1. PERFORMANCE PROFILER - COPY & PASTE
═════════════════════════════════════════════════════════════════════════════════

PASSO 1: Adicionar ao topo do seu arquivo:

    from performance import frame_profiler, profile_section

PASSO 2: No loop principal, envolver seções críticas:

    while running:
        dt = clock.tick(FPS) / 1000.0
        
        # Seção 1: Atualizar Jogador
        with profile_section(frame_profiler, "player_update"):
            player.update(dt)
        
        # Seção 2: Atualizar Inimigos
        with profile_section(frame_profiler, "enemies_update"):
            for enemy in enemies_group:
                enemy.update(dt)
        
        # Seção 3: Colisões
        with profile_section(frame_profiler, "collisions"):
            check_projectile_enemy_collision()
            check_player_enemy_collision()
        
        # Seção 4: Renderização
        with profile_section(frame_profiler, "rendering"):
            screen.fill((0, 0, 0))
            draw_world()
            pygame.display.flip()
        
        # Marcar fim do frame
        frame_profiler.new_frame()
        
        # A cada 5 segundos (300 frames em 60 FPS)
        if frame_count % 300 == 0:
            frame_profiler.print_report()
            frame_count = 0
        frame_count += 1

RESULTADO NO CONSOLE:

    ======================================================================
    PERFORMANCE PROFILER REPORT
    ======================================================================
    Seção                       Médio      Min        Max
    ------
    enemies_update               12.45ms    10.20ms    18.50ms
    rendering                     5.32ms     4.80ms     7.20ms
    player_update                 0.95ms     0.80ms     1.20ms
    collisions                    2.15ms     1.90ms     3.50ms
    ------
    TOTAL                        21.27ms
    ======================================================================

═════════════════════════════════════════════════════════════════════════════════
2. UI SCALER - EXEMPLO DE POSICIONAMENTO
═════════════════════════════════════════════════════════════════════════════════

ANTES (Posições Fixas - Quebra em outras resoluções):

    class HUD:
        def __init__(self, screen_w, screen_h):
            self.hp_bar_rect = pygame.Rect(50, 50, 200, 30)
            self.mana_bar_rect = pygame.Rect(50, 90, 200, 30)
            self.combo_text_rect = pygame.Rect(screen_w - 300, 50, 250, 50)
            # ❌ PROBLEMA: Se o jogador muda para 1280x720, fica desalinhado!
        
        def render(self, screen):
            pygame.draw.rect(screen, (100, 0, 0), self.hp_bar_rect)
            pygame.draw.rect(screen, (0, 0, 100), self.mana_bar_rect)

DEPOIS (Com UIScaler - Responsivo):

    from ui_scaler import ui_scaler, Anchor
    
    class HUD:
        def __init__(self):
            # Posições normalizadas - funcionam em qualquer resolução!
            self.hp_bar_rect = ui_scaler.get_ui_rect(
                normalized_x=0.05,      # 5% da esquerda
                normalized_y=0.05,      # 5% do topo
                width=200,
                height=30,
                anchor=Anchor.TOP_LEFT
            )
            
            self.mana_bar_rect = ui_scaler.get_ui_rect(
                normalized_x=0.05,
                normalized_y=0.12,      # Um pouco mais abaixo (5% + 7%)
                width=200,
                height=30,
                anchor=Anchor.TOP_LEFT
            )
            
            # Combo no canto superior direito
            self.combo_text_rect = ui_scaler.get_ui_rect(
                normalized_x=0.95,      # 95% (quase na ponta direita)
                normalized_y=0.05,      # 5% do topo
                width=250,
                height=50,
                anchor=Anchor.TOP_RIGHT
            )
        
        def render(self, screen):
            pygame.draw.rect(screen, (100, 0, 0), self.hp_bar_rect)
            pygame.draw.rect(screen, (0, 0, 100), self.mana_bar_rect)
            # ✅ Funciona em 1280x720, 1920x1080, 2560x1440, etc.
        
        def on_resolution_change(self, new_w, new_h):
            # Chamado quando resolução muda
            ui_scaler.update_resolution((new_w, new_h))
            
            # Recalcular posições
            self.hp_bar_rect = ui_scaler.get_ui_rect(
                0.05, 0.05, 200, 30, Anchor.TOP_LEFT
            )
            self.mana_bar_rect = ui_scaler.get_ui_rect(
                0.05, 0.12, 200, 30, Anchor.TOP_LEFT
            )
            self.combo_text_rect = ui_scaler.get_ui_rect(
                0.95, 0.05, 250, 50, Anchor.TOP_RIGHT
            )

═════════════════════════════════════════════════════════════════════════════════
3. UI SCALER - EXEMPLOS DE ÂNCORAS
═════════════════════════════════════════════════════════════════════════════════

Visual:

    Topo-Esquerda        Topo-Centro          Topo-Direita
    (0, 0)               (0.5, 0)             (1, 0)
      ⬛                    ⬛                    ⬛
    
    Esq-Centro           Centro               Dir-Centro
    (0, 0.5)             (0.5, 0.5)           (1, 0.5)
      ⬛                    ⬛                    ⬛
    
    Base-Esquerda        Base-Centro          Base-Direita
    (0, 1)               (0.5, 1)             (1, 1)
      ⬛                    ⬛                    ⬛


Exemplos de Código:

    from ui_scaler import ui_scaler, Anchor
    
    # Canto superior esquerdo (HUD de vidas)
    hp_rect = ui_scaler.get_ui_rect(
        0.05, 0.05, 200, 50, Anchor.TOP_LEFT
    )
    
    # Canto superior direito (minimap)
    minimap_rect = ui_scaler.get_ui_rect(
        0.95, 0.05, 150, 150, Anchor.TOP_RIGHT
    )
    
    # Centro da tela (pause menu)
    pause_rect = ui_scaler.get_ui_rect(
        0.5, 0.5, 400, 300, Anchor.CENTER
    )
    
    # Base esquerda (status bar)
    status_rect = ui_scaler.get_ui_rect(
        0.05, 0.95, 300, 50, Anchor.BOTTOM_LEFT
    )
    
    # Base direita (botões)
    btn_rect = ui_scaler.get_ui_rect(
        0.95, 0.95, 120, 50, Anchor.BOTTOM_RIGHT
    )

═════════════════════════════════════════════════════════════════════════════════
4. UI SCALER - ESCALAR FONTES
═════════════════════════════════════════════════════════════════════════════════

ANTES:

    # Fonte fixa - fica pequena em 4K, grande em 720p
    font = pygame.font.Font(None, 32)
    title = font.render("PONTUAÇÃO: 1000", True, (255, 255, 255))

DEPOIS:

    from ui_scaler import ui_scaler
    
    # Fonte escalada dinamicamente
    title_size = ui_scaler.scale_size(32)  # Escala 32px conforme resolução
    font = pygame.font.Font(None, title_size)
    title = font.render("PONTUAÇÃO: 1000", True, (255, 255, 255))
    
    # Exemplo de cálculo:
    # Base: 1920x1080, Current: 1280x720
    # Scale = min(1280/1920, 720/1080) = min(0.67, 0.67) = 0.67
    # Font size = int(32 * 0.67) = 21px (fica proporcional)

═════════════════════════════════════════════════════════════════════════════════
5. INTEGRANDO COM BOTÕES EXISTENTES
═════════════════════════════════════════════════════════════════════════════════

Se você tem uma classe Button existente:

    class Button:
        def __init__(self, x_ratio, y_ratio, width, height, text, font):
            self.x_ratio = x_ratio
            self.y_ratio = y_ratio
            self.width = width
            self.height = height
            self.text = text
            self.font = font
            self.update_rect()
        
        def update_rect(self):
            # Usar UIScaler aqui
            from ui_scaler import ui_scaler, Anchor
            self.rect = pygame.Rect(
                int(ui_scaler.current_w * self.x_ratio),
                int(ui_scaler.current_h * self.y_ratio),
                self.width,
                self.height
            )

Ou melhor ainda:

    from ui_scaler import ui_scaler, Anchor
    
    class Button:
        def __init__(self, norm_x, norm_y, width, height, text, font, anchor=Anchor.CENTER):
            self.norm_x = norm_x
            self.norm_y = norm_y
            self.width = width
            self.height = height
            self.text = text
            self.font = font
            self.anchor = anchor
            self.update_rect()
        
        def update_rect(self):
            x, y = ui_scaler.get_ui_position(
                self.norm_x, self.norm_y,
                self.anchor, self.width, self.height
            )
            self.rect = pygame.Rect(x, y, self.width, self.height)

═════════════════════════════════════════════════════════════════════════════════
6. TRATANDO REDIMENSIONAMENTO DE TELA
═════════════════════════════════════════════════════════════════════════════════

No loop de eventos:

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        
        elif event.type == pygame.VIDEORESIZE:
            # Jogador mudou a resolução
            new_w, new_h = event.size
            
            # Atualizar scaler
            ui_scaler.update_resolution((new_w, new_h))
            
            # Atualizar posições de TODOS os botões
            for btn in all_buttons:
                btn.update_rect()  # Chama update_rect() do botão
            
            print(f"Resolução alterada para {new_w}x{new_h}")

═════════════════════════════════════════════════════════════════════════════════
7. VERIFICANDO SE ESTÁ FUNCIONANDO
═════════════════════════════════════════════════════════════════════════════════

Adicione este código em algum lugar para testar:

    # No main(), após inicializar ui_scaler:
    from ui_scaler import ui_scaler, Anchor
    
    print("=== UI Scaler Status ===")
    print(f"Dimensões da tela: {ui_scaler.get_screen_dimensions()}")
    print(f"Fator de escala: {ui_scaler.get_scale_factor():.2f}x")
    print(f"Orientação: {'Portrait' if ui_scaler.is_portrait() else 'Landscape'}")
    
    # Teste de posicionamento
    corner_tl = ui_scaler.get_ui_position(0, 0, Anchor.TOP_LEFT, 100, 50)
    corner_br = ui_scaler.get_ui_position(1, 1, Anchor.BOTTOM_RIGHT, 100, 50)
    center = ui_scaler.get_ui_position(0.5, 0.5, Anchor.CENTER, 100, 50)
    
    print(f"Topo-Esquerda: {corner_tl}")
    print(f"Base-Direita: {corner_br}")
    print(f"Centro: {center}")
    
    # Teste de escala
    scaled_32 = ui_scaler.scale_size(32)
    print(f"Font 32px escalada: {scaled_32}px")

Saída esperada em 1920x1080:
    === UI Scaler Status ===
    Dimensões da tela: (1920, 1080)
    Fator de escala: 1.00x
    Orientação: Landscape
    Topo-Esquerda: (0, 0)
    Base-Direita: (1820, 1030)
    Centro: (1860, 1080)
    Font 32px escalada: 32px

Saída esperada em 1280x720:
    === UI Scaler Status ===
    Dimensões da tela: (1280, 720)
    Fator de escala: 0.67x
    Orientação: Landscape
    Topo-Esquerda: (0, 0)
    Base-Direita: (1180, 670)
    Centro: (1240, 720)
    Font 32px escalada: 21px

═════════════════════════════════════════════════════════════════════════════════
8. TROUBLESHOOTING
═════════════════════════════════════════════════════════════════════════════════

Problema: "AttributeError: module 'ui_scaler' has no attribute 'ui_scaler'"
Solução:  Use `from ui_scaler import ui_scaler` em vez de apenas `import ui_scaler`

Problema: "Elementos UI aparecem fora da tela"
Solução:  Verifique Anchor - pode estar invertido. TOP_RIGHT com x=1, y=0 é canto superior direito.

Problema: "FPS caiu após adicionar profiler"
Solução:  Frame profiler só registra dados, o overhead é mínimo. Se tiver queda, é outro problema.

Problema: "Projéteis não aparecem"
Solução:  Verificar se projectile_pool foi inicializado antes de start_playing()

═════════════════════════════════════════════════════════════════════════════════
"""

# Arquivo de referência - não execute
