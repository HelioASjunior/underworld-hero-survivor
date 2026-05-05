"""
EXEMPLOS PRÁTICOS - Otimizações no UnderWorld Hero Game

Este arquivo demonstra implementações concretas das otimizações nos seus contextos de uso.

═════════════════════════════════════════════════════════════════════════════════
1. EXEMPLO: Object Pooling - Já Implementado Automaticamente
═════════════════════════════════════════════════════════════════════════════════

O sistema de Object Pooling para projéteis foi AUTOMATICAMENTE integrado ao jogo.

Você não precisa mudar NADA em characters.py ou enemies.py!

O que foi feito automaticamente:
✓ build_character_dependencies() agora cria projéteis via projectile_pool.spawn()
✓ Golpes melee (MeleeSlash) também reutilizam via melee_slash_pool.spawn()
✓ Quando projéteis/golpes terminam (kill()), vão para o pool em vez de serem destruídos
✓ Isso reduz drasticamente alocações/GC durante combate

Resultado esperado:
- Menos picos de CPU durante hordas de projéteis
- FPS mais estável no late-game
- Menos picos de garbage collection

═════════════════════════════════════════════════════════════════════════════════
2. EXEMPLO: Performance Profiler - Identificar Gargalos
═════════════════════════════════════════════════════════════════════════════════

Use o profiler para medir seções críticas do código. Exemplo no loop principal:

    while running:
        dt = clock.tick(FPS) / 1000.0
        
        # Medir atualização do jogador
        with profile_section(frame_profiler, "player_update"):
            player.update(dt)
            player.handle_input(keys)
        
        # Medir atualização de inimigos
        with profile_section(frame_profiler, "enemies_update"):
            for enemy in enemies_group:
                enemy.update(dt, cam)
        
        # Medir colisões
        with profile_section(frame_profiler, "collisions"):
            check_collisions()
        
        # Medir renderização
        with profile_section(frame_profiler, "render"):
            screen.fill((0, 0, 0))
            draw_all()
            pygame.display.flip()
        
        frame_profiler.new_frame()
        
        # A cada 300 frames (5 segundos em 60 FPS), imprimir relatório
        if frame_count % 300 == 0:
            print(f"\\n[Frame {frame_count}] Relatório de Performance:")
            frame_profiler.print_report()

Saída esperada:
    ======================================================================
    PERFORMANCE PROFILER REPORT
    ======================================================================
    Seção                       Médio      Min        Max
    ------
    player_update                0.50ms     0.45ms     0.65ms
    enemies_update               8.32ms     7.20ms    12.50ms
    collisions                   1.23ms     1.15ms     2.10ms
    render                       4.15ms     3.80ms     6.50ms
    ------
    TOTAL                       14.20ms
    ======================================================================

═════════════════════════════════════════════════════════════════════════════════
3. EXEMPLO: Throttle de IA (Não executar a cada frame)
═════════════════════════════════════════════════════════════════════════════════

Pathing e IA não precisam rodar a cada frame. Use throttle:

    ai_update_interval = 0.15  # Atualizar IA a cada 150ms
    ai_timer = 0.0
    
    while running:
        dt = clock.tick(FPS) / 1000.0
        ai_timer += dt
        
        # IA apenas a cada 150ms (não a cada frame)
        if ai_timer >= ai_update_interval:
            with profile_section(frame_profiler, "enemy_ai"):
                for enemy in enemies_group:
                    enemy.update_pathfinding()  # Cálculo pesado
                    enemy.select_action()
            ai_timer -= ai_update_interval
        
        # Mas physics/animation SEMPRE roda a cada frame
        with profile_section(frame_profiler, "enemy_physics"):
            for enemy in enemies_group:
                enemy.update_position(dt)
                enemy.update_animation(dt)

Impacto:
- IA roda ~7 vezes menos frequentemente (150ms vs frame)
- Ainda suave porque movement/animation são fluidos
- Economiza ~80-90% do tempo gasto em pathfinding

═════════════════════════════════════════════════════════════════════════════════
4. EXEMPLO: Separação de Inimigos em Frames Alternados
═════════════════════════════════════════════════════════════════════════════════

Separação de inimigos é cara (O(n²) nas piores circunstâncias). Faça a cada 2 frames:

    sep_frame = 0
    
    while running:
        dt = clock.tick(FPS) / 1000.0
        
        # ... outras atualizações ...
        
        # Separação apenas nos frames pares
        if sep_frame % 2 == 0:  # ou % 3 para ser ainda mais agressivo
            with profile_section(frame_profiler, "enemy_separation"):
                for i, e1 in enumerate(enemies_group):
                    for e2 in list(enemies_group)[i+1:]:
                        if distance(e1.pos, e2.pos) < min_sep_dist:
                            push_apart(e1, e2, push_force)
        
        sep_frame += 1

Impacto:
- Economia de ~50% de tempo em separação
- Ainda visualmente fluido (não é perceptível para o jogador)
- Recomendado quando você tem 200+ inimigos

═════════════════════════════════════════════════════════════════════════════════
5. EXEMPLO: UI Responsiva com UI Scaler
═════════════════════════════════════════════════════════════════════════════════

ANTES (posições fixas em pixels):

    # Quebra em resoluções diferentes!
    hp_bar_rect = pygame.Rect(100, 50, 200, 30)
    mana_bar_rect = pygame.Rect(100, 100, 200, 30)
    inventory_btn_rect = pygame.Rect(SCREEN_W - 200, 50, 150, 50)

DEPOIS (com UIScaler - responsivo):

    from ui_scaler import ui_scaler, Anchor
    
    # Posições normalizadas (0.0 a 1.0)
    hp_bar_rect = ui_scaler.get_ui_rect(
        normalized_x=0.05,              # 5% do lado esquerdo
        normalized_y=0.05,              # 5% do topo
        width=200,
        height=30,
        anchor=Anchor.TOP_LEFT
    )
    
    mana_bar_rect = ui_scaler.get_ui_rect(
        normalized_x=0.05,
        normalized_y=0.12,              # Um pouco mais abaixo
        width=200,
        height=30,
        anchor=Anchor.TOP_LEFT
    )
    
    # Botão no canto inferior direito
    inventory_btn_rect = ui_scaler.get_ui_rect(
        normalized_x=0.95,              # 95% (quase na ponta direita)
        normalized_y=0.95,              # 95% (quase na ponta inferior)
        width=150,
        height=50,
        anchor=Anchor.BOTTOM_RIGHT      # Âncora no canto do botão
    )

Benefícios:
✓ Funciona em 1280x720, 1920x1080, 2560x1440, etc.
✓ Elementos mantêm proporções ao redimensionar
✓ Uma única definição de layout funciona em qualquer resolução

═════════════════════════════════════════════════════════════════════════════════
6. EXEMPLO: Escalar Tamanhos Dinamicamente
═════════════════════════════════════════════════════════════════════════════════

Fontes, ícones e sprites podem ser escalados proporcionalmente:

    from ui_scaler import ui_scaler
    
    # Escala fonte de 32px proporcionalmente
    title_font_size = ui_scaler.scale_size(32)
    title_font = pygame.font.Font(None, title_font_size)
    title_text = title_font.render("VOCÊ MORREU", True, (255, 0, 0))
    
    # Escala botão
    btn_width = ui_scaler.scale_size(150)
    btn_height = ui_scaler.scale_size(50)
    btn_rect = pygame.Rect(100, 100, btn_width, btn_height)
    
    # Verificar orientação
    if ui_scaler.is_portrait():
        # Layout vertical
        pass
    elif ui_scaler.is_landscape():
        # Layout horizontal
        pass

═════════════════════════════════════════════════════════════════════════════════
7. EXEMPLO: Atualizar Posições ao Redimensionar a Tela
═════════════════════════════════════════════════════════════════════════════════

Quando o jogador muda a resolução/sai do fullscreen:

    while running:
        for event in pygame.event.get():
            # ... outros eventos ...
            
            if event.type == pygame.VIDEORESIZE:
                new_w, new_h = event.size
                # Atualizar scaler
                ui_scaler.update_resolution((new_w, new_h))
                
                # Recalcular TODAS as posições de UI
                hp_bar_rect = ui_scaler.get_ui_rect(
                    0.05, 0.05, 200, 30, Anchor.TOP_LEFT
                )
                mana_bar_rect = ui_scaler.get_ui_rect(
                    0.05, 0.12, 200, 30, Anchor.TOP_LEFT
                )
                inventory_btn_rect = ui_scaler.get_ui_rect(
                    0.95, 0.95, 150, 50, Anchor.BOTTOM_RIGHT
                )
                
                # ... atualizar outras posições ...
                
                print(f"Resolução atualizada: {new_w}x{new_h}")

═════════════════════════════════════════════════════════════════════════════════
8. DICAS FINAIS DE OTIMIZAÇÃO
═════════════════════════════════════════════════════════════════════════════════

✓ PROFILE PRIMEIRO: Use frame_profiler para encontrar gargalos REAIS
✓ POOLING: Use para objetos criados frequentemente (já está implementado)
✓ THROTTLE: IA, pathfinding não precisam rodar a cada frame
✓ CULL: Não renderize/atualize sprites muito fora da câmera
✓ BATCH: Agrupe draw calls similares
✓ CACHE: Reutilize surfaces/imagens quando possível
✓ MEASURE: Sempre monitore FPS com debug overlay

Ordem de impacto (maior para menor):
1. Object Pooling (reduz GC) ✓ JÁ IMPLEMENTADO
2. Throttle IA/Pathfinding (reduz cálculos) ← COMECE AQUI
3. Culling (reduz renders) ← PRÓXIMA PRIORIDADE
4. Otimizações menores

═════════════════════════════════════════════════════════════════════════════════
"""

# Arquivo de referência e documentação - não execute como código
