"""
GUIA DE INTEGRAÇÃO - Otimizações de Desempenho e Layout Responsivo

Este arquivo contém exemplos de código mostrando como integrar os novos sistemas
de otimização no seu jogo.

═════════════════════════════════════════════════════════════════════════════════
1. OBJECT POOLING PARA PROJÉTEIS
═════════════════════════════════════════════════════════════════════════════════

No início do jogo (main()), após inicializar pygame:

    from projectile_pool import ProjectilePool, MeleeSlashPool, init_pools
    from combat.projectiles import Projectile, MeleeSlash
    
    # Inicializa os pools
    init_pools()
    projectile_pool.set_projectile_class(Projectile)
    melee_slash_pool.set_melee_class(MeleeSlash)
    projectile_pool.set_group(projectiles_group)
    melee_slash_pool.set_group(projectiles_group)

Quando criar projéteis (substitua o código antigo):

    ❌ ANTES (cria novo objeto a cada vez):
    projectile = CoreProjectile(pos, vel, dmg, frames, pierce, ricochet)
    projectiles_group.add(projectile)
    
    ✅ DEPOIS (reutiliza do pool):
    from projectile_pool import projectile_pool
    projectile = projectile_pool.spawn(pos, vel, dmg, frames, pierce, ricochet)

Mesma coisa para golpes melee:

    ❌ ANTES:
    melee_slash = CoreMeleeSlash(player, target_dir, dmg, frames)
    projectiles_group.add(melee_slash)
    
    ✅ DEPOIS:
    from projectile_pool import melee_slash_pool
    melee_slash = melee_slash_pool.spawn(player, target_dir, dmg, frames)

═════════════════════════════════════════════════════════════════════════════════
2. PERFORMANCE PROFILER - IDENTIFICAR GARGALOS
═════════════════════════════════════════════════════════════════════════════════

No loop principal, meça seções críticas:

    from performance import frame_profiler, profile_section
    
    while running:
        dt = clock.tick(FPS) / 1000.0
        
        # Opção 1: Usar context manager (recomendado)
        with profile_section(frame_profiler, "player_update"):
            player.update(dt)
        
        with profile_section(frame_profiler, "enemies_update"):
            for enemy in enemies_group:
                enemy.update(dt)
        
        with profile_section(frame_profiler, "projectile_collision"):
            check_projectile_collisions()
        
        with profile_section(frame_profiler, "render"):
            screen.fill((0, 0, 0))
            # ... draw all entities
            pygame.display.flip()
        
        frame_profiler.new_frame()
        
        # Imprimir relatório a cada 300 frames
        if frame_count % 300 == 0:
            frame_profiler.print_report()

Ou manualmente (sem context manager):

    frame_profiler.start_section("pathfinding")
    # ... código pesado
    frame_profiler.end_section("pathfinding")

═════════════════════════════════════════════════════════════════════════════════
3. OTIMIZAÇÕES DO LOOP PRINCIPAL
═════════════════════════════════════════════════════════════════════════════════

A. Throttle para cálculos de IA/Pathfinding (executar a cada N frames):

    ai_update_interval = 0.1  # Atualizar IA a cada 100ms
    ai_timer = 0.0
    
    while running:
        dt = clock.tick(FPS) / 1000.0
        ai_timer += dt
        
        # Atualiza IA apenas periodicamente
        if ai_timer >= ai_update_interval:
            with profile_section(frame_profiler, "enemy_ai"):
                for enemy in enemies_group:
                    if should_update_ai(enemy):
                        enemy.update_pathfinding(dt)
            ai_timer -= ai_update_interval

B. Separação de inimigos em frames alternados:

    sep_frame = 0
    
    while running:
        dt = clock.tick(FPS) / 1000.0
        
        # Separação de inimigos (throttle)
        if sep_frame % 2 == 0:  # Executa a cada 2 frames
            with profile_section(frame_profiler, "enemy_separation"):
                apply_enemy_separation(enemies_group)
        
        sep_frame += 1

C. Lazy-update para sprites fora da câmera:

    # No update de cada enemy:
    def update_enemy(self, dt, cam, screen_bounds):
        # Verifica se está na câmera
        if screen_bounds.colliderect(self.rect.move(cam)):
            # Atualiza normalmente
            self.update_logic(dt)
        else:
            # Fora da câmera: update mínimo
            self.update_minimal(dt)

═════════════════════════════════════════════════════════════════════════════════
4. UI RESPONSIVA - POSICIONAMENTO DINÂMICO
═════════════════════════════════════════════════════════════════════════════════

No main(), após inicializar a resolução:

    from ui_scaler import init_ui_scaler, Anchor
    
    # Inicializa o scaler com a resolução base do design (1920x1080)
    # e a resolução atual (pode ser diferente)
    ui_scaler = init_ui_scaler(
        base_res=(1920, 1080),
        current_res=(SCREEN_W, SCREEN_H)
    )

Exemplo: Posicionar barra de vida no canto superior esquerdo:

    from ui_scaler import ui_scaler, Anchor
    
    # Cálculo único (salve como atributo da classe)
    class Player:
        def __init__(self):
            self.hp_bar_rect = ui_scaler.get_ui_rect(
                normalized_x=0.05,      # 5% da direita
                normalized_y=0.05,      # 5% do topo
                width=200,              # 200px
                height=40,              # 40px
                anchor=Anchor.TOP_LEFT
            )
    
    # No render:
    def render_ui(screen):
        pygame.draw.rect(screen, (200, 0, 0), player.hp_bar_rect)

Exemplo: Posicionar botão no canto inferior direito (responsivo):

    button_rect = ui_scaler.get_ui_rect(
        normalized_x=1.0,           # Canto direito
        normalized_y=1.0,           # Canto inferior
        width=150,
        height=50,
        anchor=Anchor.BOTTOM_RIGHT  # Âncora no canto inferior direito do botão
    )

Exemplo: Escalar tamanho de fonte dinamicamente:

    from ui_scaler import ui_scaler
    
    # Fonte base de 32px, escalada proporcionalmente
    font_size = ui_scaler.scale_size(32)
    font = pygame.font.Font(None, font_size)
    text = font.render("Score: 1000", True, (255, 255, 255))

Quando a resolução muda (evento de redimensionamento):

    if event.type == pygame.VIDEORESIZE:
        new_w, new_h = event.size
        ui_scaler.update_resolution((new_w, new_h))
        
        # Repositornar todos os botões
        player.hp_bar_rect = ui_scaler.get_ui_rect(
            0.05, 0.05, 200, 40, Anchor.TOP_LEFT
        )
        button_rect = ui_scaler.get_ui_rect(
            1.0, 1.0, 150, 50, Anchor.BOTTOM_RIGHT
        )

Helper para repositornar múltiplos elementos:

    from ui_scaler import UIElementHelper
    
    ui_helper = UIElementHelper(ui_scaler)
    
    # Registra elementos uma vez
    ui_helper.register_element(
        "hp_bar",
        normalized_pos=(0.05, 0.05),
        anchor=Anchor.TOP_LEFT,
        dimensions=(200, 40)
    )
    ui_helper.register_element(
        "inventory_btn",
        normalized_pos=(0.95, 0.05),
        anchor=Anchor.TOP_RIGHT,
        dimensions=(100, 50)
    )
    
    # Atualiza todas as posições quando resolução muda
    if resolution_changed:
        ui_helper.update_all_positions({
            "hp_bar": player.hp_bar,
            "inventory_btn": inventory_button
        })

═════════════════════════════════════════════════════════════════════════════════
5. EXEMPLO COMPLETO - INTEGRAÇÃO NO LOOP PRINCIPAL
═════════════════════════════════════════════════════════════════════════════════

def main():
    pygame.init()
    
    # Setup inicial
    from ui_scaler import init_ui_scaler
    from projectile_pool import init_pools, projectile_pool, melee_slash_pool
    from performance import frame_profiler
    
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    clock = pygame.time.Clock()
    
    # Inicializa sistemas de otimização
    init_ui_scaler(base_res=(1920, 1080), current_res=(SCREEN_W, SCREEN_H))
    init_pools()
    projectile_pool.set_projectile_class(Projectile)
    melee_slash_pool.set_melee_class(MeleeSlash)
    projectile_pool.set_group(projectiles_group)
    melee_slash_pool.set_group(projectiles_group)
    
    # Loop principal
    frame_count = 0
    ai_timer = 0.0
    sep_frame = 0
    
    while running:
        dt = clock.tick(FPS) / 1000.0
        frame_count += 1
        
        # Handle events
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.VIDEORESIZE:
                SCREEN_W, SCREEN_H = event.size
                ui_scaler.update_resolution((SCREEN_W, SCREEN_H))
        
        # Atualizar com profiling
        with profile_section(frame_profiler, "player_update"):
            player.update(dt)
        
        # AI com throttle
        ai_timer += dt
        if ai_timer >= 0.1:
            with profile_section(frame_profiler, "enemy_ai"):
                for enemy in enemies:
                    enemy.update_ai()
            ai_timer -= 0.1
        
        # Separação de inimigos (frames alternados)
        if sep_frame % 2 == 0:
            with profile_section(frame_profiler, "enemy_separation"):
                apply_enemy_separation(enemies)
        
        with profile_section(frame_profiler, "enemies_update"):
            for enemy in enemies:
                enemy.update(dt)
        
        with profile_section(frame_profiler, "projectile_collision"):
            check_projectile_collisions()
        
        # Render
        with profile_section(frame_profiler, "render"):
            screen.fill((0, 0, 0))
            # ... draw everything
            pygame.display.flip()
        
        frame_profiler.new_frame()
        sep_frame += 1
        
        # Print perfil a cada 5 segundos
        if frame_count % 300 == 0:
            frame_profiler.print_report()

═════════════════════════════════════════════════════════════════════════════════
6. DICAS DE OTIMIZAÇÃO ADICIONAIS
═════════════════════════════════════════════════════════════════════════════════

✓ Use profiler para encontrar gargalos ANTES de otimizar
✓ Object pooling é mais importante para objetos criados frequentemente
✓ Throttle IA/pathfinding: nem todo frame precisa rodar
✓ Culling: não atualize sprites fora da câmera
✓ Cache de desenho: reutilize surfaces quando possível
✓ Batching: agrupe draw calls similares
✓ Use NumPy arrays para cálculos em batch (já está em spatial_index.py)
✓ Monitore FPS continuamente com debug overlay

═════════════════════════════════════════════════════════════════════════════════
"""

# Arquivo de referência apenas - não execute
