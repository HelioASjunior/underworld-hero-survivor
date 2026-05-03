import os
import math
import pygame

UI_THEME = {
    "void_black": (26, 26, 26),
    "charcoal": (34, 34, 34),
    "iron": (78, 74, 69),
    "old_gold": (184, 134, 72),
    "faded_gold": (156, 126, 74),
    "blood_red": (139, 0, 0),
    "mana_blue": (70, 110, 160),
    "parchment": (210, 198, 170),
    "mist": (210, 210, 210),
}

# Paleta de raridade de itens
ITEM_COLORS = {
    "normal":     (252, 245, 229),   # #FCF5E5  — branco pergaminho
    "rare":       (255, 215,   0),   # #FFD700  — dourado
    "magic":      (  0, 116, 217),   # #0074D9  — azul arcano
    "danger":     (255,  65,  54),   # #FF4136  — vermelho perigo / identificado
}

_font_cache = {}
_vignette_cache = {}
_stat_sprites = None   # carregado por init_stat_sprites()


def init_stat_sprites(asset_dir):
    """Carrega os sprites de barra do stats.png (HP, MANA, DASH).

    Layout do spritesheet (336x240):
      Fileira 0 (y=3,  h=11): HP   — s0=borda(48px), s1=fill cheio(42px)
      Fileira 1 (y=19, h=11): MANA — s0=borda(48px), s1=fill cheio(42px)
      Fileira 2 (y=35, h=11): DASH — s0=borda(48px), s1=fill cheio(42px)
    """
    global _stat_sprites
    path = os.path.join(asset_dir, "sprite", "stats.png")
    if not os.path.exists(path):
        return
    try:
        sheet = pygame.image.load(path).convert_alpha()
        rows = {"hp": 3, "mana": 19, "dash": 35}
        fh = 11
        _stat_sprites = {}
        for name, y0 in rows.items():
            _stat_sprites[name] = {
                "border": sheet.subsurface((0,  y0, 48, fh)).copy(),
                "fill":   sheet.subsurface((51, y0, 42, fh)).copy(),
            }
    except Exception as e:
        print(f"[HUD] Erro ao carregar stats.png: {e}")
skill_feed = []
upgrade_notifications = []
ui_visual_state = {
    "char_id": None, "hp": None, "mana": None,
    "xp_flash_timer": 0.0, "prev_level": None,
    "hurt_flash_timer": 0.0, "prev_hp": None,
}


def reset_feedback():
    global skill_feed, upgrade_notifications, ui_visual_state
    skill_feed = []
    upgrade_notifications = []
    ui_visual_state = {
        "char_id": None, "hp": None, "mana": None,
        "xp_flash_timer": 0.0, "prev_level": None,
        "hurt_flash_timer": 0.0, "prev_hp": None,
    }


def _load_font_from_candidates(candidates, size, bold, fallback_sys, asset_dir):
    """Tenta cada nome de arquivo em ordem; cai para SysFont se nenhum existir."""
    cache_key = (asset_dir, size, bold, tuple(candidates))
    if cache_key in _font_cache:
        return _font_cache[cache_key]

    font_path = None
    for fname in candidates:
        candidate = os.path.join(asset_dir, "fonts", fname)
        if os.path.exists(candidate):
            font_path = candidate
            break
    try:
        font = pygame.font.Font(font_path, size) if font_path else pygame.font.SysFont(fallback_sys, size)
        font.set_bold(bold)
    except Exception:
        font = pygame.font.SysFont(fallback_sys, size)
        font.set_bold(bold)

    _font_cache[cache_key] = font
    return font


def load_dark_font(size, bold=False, asset_dir="assets"):
    """Fonte temática principal (Catholicon) — títulos legados e HUD."""
    return _load_font_from_candidates(
        ("Catholicon.ttf", "Catholicon.otf", "fonte_dark.ttf"),
        size, bold, "georgia", asset_dir,
    )


def load_title_font(size, bold=False, asset_dir="assets"):
    """Fonte principal do jogo (Runewood) — títulos, cabeçalhos e menus."""
    return _load_font_from_candidates(
        ("Runewood.ttf",),
        size, bold, "georgia", asset_dir,
    )


def load_body_font(size, bold=False, asset_dir="assets"):
    """Fonte principal do jogo (Runewood) — descrições de itens e corpo de texto."""
    return _load_font_from_candidates(
        ("Runewood.ttf",),
        size, bold, "georgia", asset_dir,
    )


def load_number_font(size, bold=False, asset_dir="assets"):
    """Fonte dedicada para números e valores numéricos (Catholicon)."""
    return _load_font_from_candidates(
        ("Catholicon.ttf", "Catholicon.otf", "fonte_dark.ttf"),
        size, bold, "georgia", asset_dir,
    )


def push_skill_feed(text, color=(220, 220, 220), duration=4.0):
    global skill_feed
    if not text:
        return
    skill_feed.insert(0, {"text": text, "color": color, "timer": duration})
    skill_feed = skill_feed[:8]


def push_upgrade_notification(text, color=None, duration=4.5):
    global upgrade_notifications
    if not text:
        return
    upgrade_notifications.insert(0, {
        "text": text,
        "color": color or UI_THEME["faded_gold"],
        "timer": duration,
        "max_timer": duration,
        "slide_x": 400.0,   # Entra da direita → 0
    })
    upgrade_notifications = upgrade_notifications[:5]


def smooth_ui_value(current_value, target_value, dt, speed=8.0):
    if current_value is None:
        return target_value
    blend = min(1.0, speed * dt)
    return current_value + (target_value - current_value) * blend


def update_feedback(dt):
    global skill_feed, upgrade_notifications

    active_entries = []
    for entry in skill_feed:
        entry["timer"] -= dt
        if entry["timer"] > 0:
            active_entries.append(entry)
    skill_feed = active_entries

    active_upgrade_notifications = []
    for entry in upgrade_notifications:
        entry["timer"] -= dt
        slide = entry.get("slide_x", 0.0)
        slide += (0.0 - slide) * min(1.0, 12.0 * dt)
        entry["slide_x"] = slide
        if entry["timer"] > 0:
            active_upgrade_notifications.append(entry)
    upgrade_notifications = active_upgrade_notifications


def draw_dark_panel(screen, rect, alpha=180, border_color=None):
    panel_surface = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
    panel_surface.fill((UI_THEME["void_black"][0], UI_THEME["void_black"][1], UI_THEME["void_black"][2], alpha))
    screen.blit(panel_surface, rect.topleft)
    # Sharp corners (radius=4) for stone/carved-wood medieval aesthetic
    pygame.draw.rect(screen, border_color or UI_THEME["iron"], rect, 2, border_radius=4)
    inner_rect = rect.inflate(-6, -6)
    pygame.draw.rect(screen, UI_THEME["charcoal"], inner_rect, 1, border_radius=2)


def draw_critical_vignette(screen, hp_ratio, screen_w, screen_h):
    """Pulsing red vignette on screen edges when HP < 25%."""
    if hp_ratio >= 0.25:
        return
    intensity = 1.0 - (hp_ratio / 0.25)
    pulse = 0.5 + 0.5 * math.sin(pygame.time.get_ticks() / 350.0)
    alpha_mult = int(min(230, 55 + intensity * 150 + pulse * 25 * intensity))
    key = (screen_w, screen_h)
    if key not in _vignette_cache:
        surf = pygame.Surface((screen_w, screen_h), pygame.SRCALPHA)
        edge = 110
        for i in range(edge):
            a = int(255 * ((edge - i) / edge) ** 2.0)
            c = (180, 12, 12, a)
            pygame.draw.line(surf, c, (0, i), (screen_w - 1, i))
            pygame.draw.line(surf, c, (0, screen_h - 1 - i), (screen_w - 1, screen_h - 1 - i))
            pygame.draw.line(surf, c, (i, 0), (i, screen_h - 1))
            pygame.draw.line(surf, c, (screen_w - 1 - i, 0), (screen_w - 1 - i, screen_h - 1))
        _vignette_cache[key] = surf
    blended = _vignette_cache[key].copy()
    blended.fill((255, 255, 255, alpha_mult), special_flags=pygame.BLEND_RGBA_MULT)
    screen.blit(blended, (0, 0))


def _blit_bar_sprite(screen, rect, sprite, ratio, ghost_ratio=0.0):
    """Blita um sprite de barra escalado e recortado pelo ratio (0.0–1.0)."""
    w, h = rect.width, rect.height
    scaled = pygame.transform.scale(sprite, (w, h))

    # Barra fantasma (lag visual de dano)
    if ghost_ratio > ratio + 0.01:
        ghost_w = int(w * ghost_ratio)
        ghost_surf = pygame.Surface((ghost_w, h), pygame.SRCALPHA)
        ghost_surf.blit(scaled, (0, 0), (0, 0, ghost_w, h))
        ghost_surf.set_alpha(100)
        screen.blit(ghost_surf, rect.topleft)

    # Preenchimento atual
    fill_w = max(0, int(w * ratio))
    if fill_w > 0:
        fill_surf = pygame.Surface((fill_w, h), pygame.SRCALPHA)
        fill_surf.blit(scaled, (0, 0), (0, 0, fill_w, h))
        screen.blit(fill_surf, rect.topleft)


def draw_metallic_bar(screen, rect, display_value, max_value, fill_color, label, font_s, font_m, current_value=None):
    """Barra de status — usa sprites do stats.png se disponíveis, senão fallback procedural."""
    safe_max = max(1.0, max_value)
    cur_val = current_value if current_value is not None else display_value
    disp_r = max(0.0, min(1.0, display_value / safe_max))
    cur_r  = max(0.0, min(1.0, cur_val / safe_max))

    # HP usa sprite "hp"; mana usa sprite "dash" (sprites invertidos intencionalmente)
    stat_key = "hp" if fill_color == UI_THEME["blood_red"] else "dash"

    if _stat_sprites and stat_key in _stat_sprites:
        sprites = _stat_sprites[stat_key]
        outer = pygame.Rect(rect)

        # Sombra
        sh = pygame.Surface((outer.width, outer.height), pygame.SRCALPHA)
        sh.fill((0, 0, 0, 70))
        screen.blit(sh, (outer.x + 3, outer.y + 4))

        # Fundo escuro (track)
        bg = pygame.Surface((outer.width, outer.height), pygame.SRCALPHA)
        bg.fill((12, 10, 8, 200))
        screen.blit(bg, outer.topleft)

        # Fill + ghost
        _blit_bar_sprite(screen, outer, sprites["fill"], cur_r, ghost_ratio=disp_r)

        # Borda por cima
        border_scaled = pygame.transform.scale(sprites["border"], (outer.width, outer.height))
        screen.blit(border_scaled, outer.topleft)

        # Textos centralizados
        cur_int = int(max(0, cur_val))
        value_str = f"{label}  {cur_int} / {int(safe_max)}"
        txt_surf = font_s.render(value_str, True, UI_THEME["parchment"])
        _sh = (0, 0, 0)
        tx = outer.centerx - txt_surf.get_width() // 2
        ty = outer.centery - txt_surf.get_height() // 2
        screen.blit(font_s.render(value_str, True, _sh), (tx + 1, ty + 1))
        screen.blit(txt_surf, (tx, ty))
        return

    # ── Fallback procedural ──────────────────────────────────────────────────
    outer = pygame.Rect(rect)
    shadow_surf = pygame.Surface((outer.width, outer.height), pygame.SRCALPHA)
    shadow_surf.fill((0, 0, 0, 80))
    screen.blit(shadow_surf, (outer.x + 3, outer.y + 3))
    bg_surf = pygame.Surface((outer.width, outer.height), pygame.SRCALPHA)
    bg_surf.fill((18, 16, 14, 215))
    screen.blit(bg_surf, outer.topleft)
    pygame.draw.rect(screen, UI_THEME["old_gold"], outer, 2, border_radius=6)
    pygame.draw.rect(screen, (60, 48, 30), outer.inflate(-4, -4), 1, border_radius=4)
    fill_area = outer.inflate(-12, -12)
    fill_area.height = max(8, fill_area.height)
    track_color = (50, 15, 15) if fill_color == UI_THEME["blood_red"] else (15, 22, 40)
    pygame.draw.rect(screen, track_color, fill_area, border_radius=5)
    if disp_r > cur_r + 0.01:
        gw = max(4, int(fill_area.width * disp_r))
        ghost = fill_area.copy(); ghost.width = gw
        pygame.draw.rect(screen, tuple(max(0, c - 60) for c in fill_color), ghost, border_radius=5)
    fill_w = max(0, int(fill_area.width * cur_r))
    if fill_w > 0:
        fr = fill_area.copy(); fr.width = fill_w
        pygame.draw.rect(screen, fill_color, fr, border_radius=5)
        shine_h = max(3, fill_area.height // 3)
        shine = pygame.Surface((fill_w, shine_h), pygame.SRCALPHA)
        for row in range(shine_h):
            shine.fill((255, 255, 255, int(48 * (1.0 - row / shine_h))), (0, row, fill_w, 1))
        screen.blit(shine, fr.topleft)
    cur_int = int(max(0, cur_val))
    value_str = f"{cur_int} / {int(safe_max)}"
    lbl_surf = font_s.render(label, True, UI_THEME["parchment"])
    val_surf = font_s.render(value_str, True, UI_THEME["mist"])
    fa = outer.inflate(-12, -12)
    lbl_x = fa.x + 6; lbl_y = fa.y + (fa.height - lbl_surf.get_height()) // 2
    val_x = fa.right - val_surf.get_width() - 6
    _sh = (0, 0, 0)
    screen.blit(font_s.render(label, True, _sh), (lbl_x + 1, lbl_y + 1))
    screen.blit(lbl_surf, (lbl_x, lbl_y))
    screen.blit(font_s.render(value_str, True, _sh), (val_x + 1, lbl_y + 1))
    screen.blit(val_surf, (val_x, lbl_y))


def draw_dash_indicator(screen, rect, dash_ratio, font_s):
    """Barra de cooldown do Dash — usa sprite se disponível, fallback procedural."""
    ready = dash_ratio >= 1.0
    outer = pygame.Rect(rect)
    ratio = max(0.0, min(1.0, dash_ratio))

    if _stat_sprites and "mana" in _stat_sprites:
        sprites = _stat_sprites["mana"]

        # Sombra
        sh = pygame.Surface((outer.width, outer.height), pygame.SRCALPHA)
        sh.fill((0, 0, 0, 70))
        screen.blit(sh, (outer.x + 3, outer.y + 4))

        # Fundo
        bg = pygame.Surface((outer.width, outer.height), pygame.SRCALPHA)
        bg.fill((12, 10, 8, 200))
        screen.blit(bg, outer.topleft)

        # Fill
        _blit_bar_sprite(screen, outer, sprites["fill"], ratio)

        # Pulso quando pronto (BLEND_ADD sobre o sprite)
        if ready:
            pulse = 0.5 + 0.5 * math.sin(pygame.time.get_ticks() / 280.0)
            glow = pygame.Surface((outer.width, outer.height), pygame.SRCALPHA)
            glow.fill((255, 220, 50, int(25 + 20 * pulse)))
            screen.blit(glow, outer.topleft, special_flags=pygame.BLEND_RGBA_ADD)

        # Borda
        border_scaled = pygame.transform.scale(sprites["border"], (outer.width, outer.height))
        screen.blit(border_scaled, outer.topleft)

        # Label
        label_txt = "DASH  PRONTO" if ready else f"DASH  {int(ratio * 100)}%"
        lbl_color = (255, 240, 80) if ready else (200, 170, 60)
        lbl_surf = font_s.render(label_txt, True, lbl_color)
        _sh = (0, 0, 0)
        tx = outer.centerx - lbl_surf.get_width() // 2
        ty = outer.centery - lbl_surf.get_height() // 2
        screen.blit(font_s.render(label_txt, True, _sh), (tx + 1, ty + 1))
        screen.blit(lbl_surf, (tx, ty))
        return

    # ── Fallback procedural ──────────────────────────────────────────────────
    shadow_surf = pygame.Surface((outer.width, outer.height), pygame.SRCALPHA)
    shadow_surf.fill((0, 0, 0, 70))
    screen.blit(shadow_surf, (outer.x + 3, outer.y + 3))
    bg_surf = pygame.Surface((outer.width, outer.height), pygame.SRCALPHA)
    bg_surf.fill((18, 16, 14, 200))
    screen.blit(bg_surf, outer.topleft)
    border_color = (255, 210, 50) if ready else UI_THEME["iron"]
    pygame.draw.rect(screen, border_color, outer, 2, border_radius=6)
    pygame.draw.rect(screen, (40, 40, 50), outer.inflate(-4, -4), 1, border_radius=4)
    fill_area = outer.inflate(-12, -12)
    fill_area.height = max(6, fill_area.height)
    pygame.draw.rect(screen, (30, 25, 10), fill_area, border_radius=4)
    fill_w = max(0, int(fill_area.width * ratio))
    if fill_w > 0:
        fill_color = (255, 210, 50) if ready else (160, 130, 20)
        fill_rect = fill_area.copy(); fill_rect.width = fill_w
        pygame.draw.rect(screen, fill_color, fill_rect, border_radius=4)
        if ready:
            pulse = 0.5 + 0.5 * math.sin(pygame.time.get_ticks() / 280.0)
            glow_surf = pygame.Surface((outer.width, outer.height), pygame.SRCALPHA)
            glow_surf.fill((255, 200, 50, int(30 + 25 * pulse)))
            screen.blit(glow_surf, outer.topleft, special_flags=pygame.BLEND_RGBA_ADD)
    lbl_color = (255, 240, 80) if ready else (180, 150, 40)
    label_txt = "DASH  PRONTO" if ready else f"DASH  {int(ratio * 100)}%"
    lbl_surf = font_s.render(label_txt, True, lbl_color)
    screen.blit(font_s.render(label_txt, True, (0, 0, 0)), (outer.x + 15, outer.centery - lbl_surf.get_height() // 2 + 1))
    screen.blit(lbl_surf, lbl_surf.get_rect(midleft=(outer.x + 14, outer.centery)))


def _draw_last_upgrades_panel(screen, player_upgrades, font_s, x, y, width):
    """Painel 'Últimos Upgrades' redesenhado — cada upgrade em linha própria.

    Visual inspirado em jogos indie premium: fundo escuro, borda dourada,
    título separado por linha e até 5 upgrades recentes com ícone de estrela.
    """
    if not player_upgrades:
        return

    recent = list(reversed(player_upgrades))[:5]   # últimos 5, mais recente primeiro
    PAD_X = 14
    PAD_Y = 10
    ROW_H = 26                                       # altura por linha de upgrade
    TITLE_H = 28                                     # altura do bloco de título
    SEP_GAP = 6                                      # gap acima/abaixo do separador
    panel_h = PAD_Y + TITLE_H + SEP_GAP + len(recent) * ROW_H + PAD_Y

    panel_rect = pygame.Rect(x, y, width, panel_h)

    # Sombra
    sh = pygame.Surface((width, panel_h), pygame.SRCALPHA)
    sh.fill((0, 0, 0, 70))
    screen.blit(sh, (x + 3, y + 3))

    # Fundo
    bg = pygame.Surface((width, panel_h), pygame.SRCALPHA)
    bg.fill((16, 13, 10, 210))
    screen.blit(bg, (x, y))

    # Borda e gravura interna
    pygame.draw.rect(screen, UI_THEME["faded_gold"], panel_rect, 2, border_radius=6)
    pygame.draw.rect(screen, (55, 42, 20), panel_rect.inflate(-4, -4), 1, border_radius=4)

    # Destaque sutil no topo do painel (toque metálico)
    top_hl = pygame.Surface((width - 8, 2), pygame.SRCALPHA)
    top_hl.fill((220, 170, 80, 50))
    screen.blit(top_hl, (x + 4, y + 4))

    # Título
    title_surf = font_s.render("ÚLTIMOS UPGRADES", True, UI_THEME["old_gold"])
    title_shadow = font_s.render("ÚLTIMOS UPGRADES", True, (0, 0, 0))
    title_y = y + PAD_Y
    screen.blit(title_shadow, (x + PAD_X + 1, title_y + 1))
    screen.blit(title_surf, (x + PAD_X, title_y))

    # Separador dourado
    sep_y = title_y + TITLE_H
    pygame.draw.line(screen, UI_THEME["faded_gold"],
                     (x + PAD_X, sep_y),
                     (x + width - PAD_X, sep_y), 1)

    # Linhas de upgrade
    cursor_y = sep_y + SEP_GAP + 2
    for i, upg_name in enumerate(recent):
        # Fundo alternado leve para leitura
        if i % 2 == 0:
            row_bg = pygame.Surface((width - 8, ROW_H - 2), pygame.SRCALPHA)
            row_bg.fill((255, 255, 255, 8))
            screen.blit(row_bg, (x + 4, cursor_y))

        # Ícone estrela — dourado para o mais recente, desbotado para os demais
        star_color = UI_THEME["old_gold"] if i == 0 else UI_THEME["faded_gold"]
        star_surf = font_s.render("\u2605", True, star_color)
        screen.blit(star_surf, (x + PAD_X, cursor_y + (ROW_H - star_surf.get_height()) // 2))

        # Nome do upgrade
        name_color = UI_THEME["parchment"] if i == 0 else (160, 148, 130)
        name_shadow = font_s.render(upg_name, True, (0, 0, 0))
        name_surf = font_s.render(upg_name, True, name_color)
        nx = x + PAD_X + star_surf.get_width() + 6
        ny = cursor_y + (ROW_H - name_surf.get_height()) // 2
        screen.blit(name_shadow, (nx + 1, ny + 1))
        screen.blit(name_surf, (nx, ny))

        cursor_y += ROW_H


def draw_skill_feed_panel(screen, player, font_s, hud_scale, high_contrast, screen_w, screen_h=720):
    if not player:
        return

    # Layout dinâmico do grimório:
    #
    # 1) medimos a largura de todas as linhas relevantes;
    # 2) aplicamos padding para construir uma moldura que não corte texto;
    # 3) usamos line_spacing fixo para impedir sobreposição.
    pad_x = 20
    pad_y = 14
    line_spacing = max(24, int(30 * hud_scale))
    section_gap = max(12, int(14 * hud_scale))
    anchor_offset = 10

    title_text = "GRIMORIO DE BATALHA"
    recent_title_text = "MAGIAS RECENTES"
    skill_lines = [f"{label.upper()}: {value}" for label, value in player.get_skill_cards()]
    recent_lines = [entry["text"] for entry in skill_feed[:4]]

    measured_lines = [title_text, recent_title_text] + skill_lines + recent_lines
    longest_width = 0
    for line in measured_lines:
        line_surface = font_s.render(line, True, UI_THEME["mist"])
        longest_width = max(longest_width, line_surface.get_width())

    panel_w = longest_width + pad_x * 2
    skill_block_h = line_spacing * max(1, len(skill_lines))
    recent_block_h = line_spacing * max(1, len(recent_lines))
    panel_h = (
        pad_y
        + line_spacing
        + 6
        + section_gap
        + skill_block_h
        + section_gap
        + line_spacing
        + 6
        + section_gap
        + recent_block_h
        + pad_y
    )

    # Âncora: canto inferior esquerdo com margem fixa de 20px.
    panel_x = 20
    panel_y = screen_h - panel_h - 20
    panel_rect = pygame.Rect(panel_x, panel_y, panel_w, panel_h)
    border_color = UI_THEME["old_gold"] if not high_contrast else (255, 255, 255)
    title_color = UI_THEME["old_gold"] if not high_contrast else (255, 255, 0)
    text_color = UI_THEME["mist"] if not high_contrast else (255, 255, 255)

    draw_dark_panel(screen, panel_rect, alpha=180, border_color=border_color)

    cursor_y = panel_rect.y + pad_y

    # Título principal + separador
    title_surf = font_s.render(title_text, True, title_color)
    screen.blit(title_surf, (panel_rect.x + pad_x, cursor_y))
    cursor_y += line_spacing
    pygame.draw.line(
        screen,
        UI_THEME["faded_gold"],
        (panel_rect.x + pad_x, cursor_y - 6),
        (panel_rect.right - pad_x, cursor_y - 6),
        1,
    )
    cursor_y += section_gap

    # Linhas do grimório (todas alinhadas à esquerda)
    for line in skill_lines:
        line_surf = font_s.render(line, True, text_color)
        screen.blit(line_surf, (panel_rect.x + pad_x, cursor_y))
        cursor_y += line_spacing

    cursor_y += section_gap

    # Subtítulo de magias recentes + separador
    recent_title_surf = font_s.render(recent_title_text, True, title_color)
    screen.blit(recent_title_surf, (panel_rect.x + pad_x, cursor_y))
    cursor_y += line_spacing
    pygame.draw.line(
        screen,
        UI_THEME["faded_gold"],
        (panel_rect.x + pad_x, cursor_y - 6),
        (panel_rect.right - pad_x, cursor_y - 6),
        1,
    )
    cursor_y += section_gap

    # Entradas recentes com fade-out e espaçamento constante
    if not recent_lines:
        empty_surf = font_s.render("Sem magias recentes", True, UI_THEME["iron"])
        screen.blit(empty_surf, (panel_rect.x + pad_x, cursor_y))
    else:
        for entry in skill_feed[:4]:
            alpha_ratio = max(0.18, min(1.0, entry["timer"] / 4.0))
            color = tuple(int(channel * alpha_ratio) for channel in entry["color"])
            text_surface = font_s.render(entry["text"], True, color)
            screen.blit(text_surface, (panel_rect.x + pad_x, cursor_y))
            cursor_y += line_spacing


def draw_upgrade_notifications(screen, font_s, screen_w=1920):
    """Notificações de upgrade — flutuam no canto superior direito."""
    start_y = 28
    ROW_H = 38
    for index, entry in enumerate(upgrade_notifications[:5]):
        alpha_ratio = max(0.0, min(1.0, entry["timer"] / max(0.01, entry["max_timer"])))
        bg_alpha = int(180 * alpha_ratio)
        text_alpha = int(255 * alpha_ratio)
        text_surface = font_s.render(entry["text"], True, entry["color"])
        text_surface.set_alpha(text_alpha)

        box_w = text_surface.get_width() + 32
        box_h = 32

        # Slide da direita para dentro (slide_x vai de +400 → 0)
        slide_offset = int(entry.get("slide_x", 0.0))
        box_x = screen_w - box_w - 20 + (-slide_offset)   # slide_x negativo → entra da direita
        box_y = start_y + index * (box_h + 6)

        box_rect = pygame.Rect(box_x, box_y, box_w, box_h)

        # Sombra
        sh = pygame.Surface((box_w, box_h), pygame.SRCALPHA)
        sh.fill((0, 0, 0, int(60 * alpha_ratio)))
        screen.blit(sh, (box_x + 3, box_y + 3))

        # Fundo
        bg_surface = pygame.Surface((box_w, box_h), pygame.SRCALPHA)
        bg_surface.fill((16, 13, 10, bg_alpha))
        screen.blit(bg_surface, box_rect.topleft)

        # Borda e gravura
        border_col = tuple(int(c * alpha_ratio) for c in UI_THEME["faded_gold"])
        pygame.draw.rect(screen, border_col, box_rect, 2, border_radius=6)
        pygame.draw.rect(screen, tuple(int(c * alpha_ratio) for c in (50, 38, 18)),
                         box_rect.inflate(-4, -4), 1, border_radius=4)

        screen.blit(text_surface, (box_rect.x + 14, box_rect.y + (box_h - text_surface.get_height()) // 2))


def draw_ui(screen, player, state, font_s, font_m, font_l, hud_scale, high_contrast, level, xp, current_xp_to_level, game_time, kills, dt, screen_w, screen_h, player_max_hp, game_version, build_type, player_upgrades, dash_ratio=1.0):
    version_str = f"v{game_version} ({build_type})"
    version_shadow = font_s.render(version_str, True, (0, 0, 0))
    version_text = font_s.render(version_str, True, UI_THEME["iron"])
    version_rect = version_text.get_rect(bottomright=(screen_w - 12, screen_h - 10))

    if player and state in ["PLAYING", "UPGRADE", "CHEST_UI", "PAUSED", "GAME_OVER"]:
        if ui_visual_state["char_id"] != player.char_id:
            ui_visual_state["char_id"] = player.char_id
            ui_visual_state["hp"] = float(player.hp)
            ui_visual_state["mana"] = float(player.ult_charge)

        ui_visual_state["hp"] = smooth_ui_value(ui_visual_state["hp"], float(player.hp), dt)
        ui_visual_state["mana"] = smooth_ui_value(ui_visual_state["mana"], float(player.ult_charge), dt)

        # Tamanhos fixos responsivos — independentes de hud_scale para
        # garantir legibilidade em qualquer resolução sem texto cortado.
        BAR_W = max(300, int(screen_w * 0.185))  # ~355px a 1920 | ~260px a 1366
        BAR_H = 54                                # Altura fixa — texto 18px cabe com folga
        BAR_GAP = 10
        DASH_H = 36
        PAD_L = 20
        hp_y = 28
        mana_y = hp_y + BAR_H + BAR_GAP
        dash_y = mana_y + BAR_H + BAR_GAP
        ups_y = dash_y + DASH_H + 16

        hp_rect   = pygame.Rect(PAD_L, hp_y,   BAR_W, BAR_H)
        mana_rect = pygame.Rect(PAD_L, mana_y, BAR_W, BAR_H)
        dash_rect = pygame.Rect(PAD_L, dash_y, BAR_W, DASH_H)

        draw_metallic_bar(screen, hp_rect, ui_visual_state["hp"], player_max_hp, UI_THEME["blood_red"], "HP", font_s, font_m, current_value=player.hp)
        draw_metallic_bar(screen, mana_rect, ui_visual_state["mana"], player.ult_max, UI_THEME["mana_blue"], "MANA", font_s, font_m, current_value=player.ult_charge)
        draw_dash_indicator(screen, dash_rect, dash_ratio, font_s)

        time_m, time_s = divmod(int(game_time), 60)
        top_panel = pygame.Rect(screen_w // 2 - 160, 20, 320, 44)
        draw_dark_panel(screen, top_panel, alpha=180, border_color=UI_THEME["iron"])
        time_text = font_s.render(f"{time_m:02}:{time_s:02}  |  KILLS  {kills}", True, UI_THEME["parchment"])
        screen.blit(time_text, time_text.get_rect(center=top_panel.center))

        # Aviso do Boss Agis abaixo do painel de kills
        _agis_spawn_min = 15
        if time_m < _agis_spawn_min:
            _warn_text = f"O BOSS AGIS IRÁ NASCER NO MINUTO {_agis_spawn_min}, SOBREVIVA ATÉ LÁ"
            _warn_pulse = abs(math.sin(game_time * 1.5))
            _warn_r = int(220 + 35 * _warn_pulse)
            _warn_g = int(80 + 40 * _warn_pulse)
            _warn_surf = font_s.render(_warn_text, True, (_warn_r, _warn_g, 40))
            _warn_bg = pygame.Surface((_warn_surf.get_width() + 16, _warn_surf.get_height() + 6), pygame.SRCALPHA)
            _warn_bg.fill((8, 4, 2, 160))
            _warn_rect = _warn_bg.get_rect(centerx=screen_w // 2, top=top_panel.bottom + 4)
            screen.blit(_warn_bg, _warn_rect)
            screen.blit(_warn_surf, _warn_surf.get_rect(center=_warn_rect.center))

        # XP bar — altura maior (18px) com nível centralizado dentro da barra.
        XP_BAR_H = 18
        if ui_visual_state["prev_level"] is None:
            ui_visual_state["prev_level"] = level
        elif level > ui_visual_state["prev_level"]:
            ui_visual_state["xp_flash_timer"] = 0.8
            ui_visual_state["prev_level"] = level
        ui_visual_state["xp_flash_timer"] = max(0.0, ui_visual_state["xp_flash_timer"] - dt)
        xp_bg = pygame.Surface((screen_w, XP_BAR_H), pygame.SRCALPHA)
        xp_bg.fill((UI_THEME["void_black"][0], UI_THEME["void_black"][1], UI_THEME["void_black"][2], 220))
        screen.blit(xp_bg, (0, 0))
        xp_ratio = 0 if current_xp_to_level <= 0 else max(0.0, min(1.0, xp / current_xp_to_level))
        xp_fill_w = int(screen_w * xp_ratio)
        if xp_fill_w > 0:
            pygame.draw.rect(screen, UI_THEME["faded_gold"], (0, 0, xp_fill_w, XP_BAR_H))
            hl = pygame.Surface((xp_fill_w, XP_BAR_H // 2), pygame.SRCALPHA)
            hl.fill((255, 255, 255, 38))
            screen.blit(hl, (0, 2))
        pygame.draw.rect(screen, UI_THEME["old_gold"], (0, 0, screen_w, XP_BAR_H), 1)
        if ui_visual_state["xp_flash_timer"] > 0:
            flash_a = int(210 * (ui_visual_state["xp_flash_timer"] / 0.8))
            flash_surf = pygame.Surface((screen_w, XP_BAR_H), pygame.SRCALPHA)
            flash_surf.fill((255, 230, 80, flash_a))
            screen.blit(flash_surf, (0, 0))
        # Nível centralizado verticalmente dentro da barra de XP.
        level_text = font_s.render(f"NIVEL {level}", True, UI_THEME["mist"])
        screen.blit(level_text, level_text.get_rect(midright=(screen_w - 10, XP_BAR_H // 2)))

        draw_skill_feed_panel(screen, player, font_s, hud_scale, high_contrast, screen_w, screen_h)

        if player_upgrades:
            _draw_last_upgrades_panel(screen, player_upgrades, font_s, PAD_L, ups_y, BAR_W)

        draw_upgrade_notifications(screen, font_s, screen_w=screen_w)
        draw_critical_vignette(screen, player.hp / max(1.0, player_max_hp), screen_w, screen_h)

        # Flash vermelho na tela ao receber dano — feedback imediato de hit.
        prev_hp = ui_visual_state.get("prev_hp")
        if prev_hp is not None and player.hp < prev_hp:
            ui_visual_state["hurt_flash_timer"] = 0.18
        ui_visual_state["prev_hp"] = float(player.hp)
        ui_visual_state["hurt_flash_timer"] = max(0.0, ui_visual_state.get("hurt_flash_timer", 0.0) - dt)
        if ui_visual_state["hurt_flash_timer"] > 0:
            flash_ratio = ui_visual_state["hurt_flash_timer"] / 0.18
            flash_alpha = int(90 * flash_ratio)
            hurt_surf = pygame.Surface((screen_w, screen_h), pygame.SRCALPHA)
            hurt_surf.fill((200, 10, 10, flash_alpha))
            screen.blit(hurt_surf, (0, 0))

    screen.blit(version_shadow, (version_rect.x + 1, version_rect.y + 1))
    screen.blit(version_text, version_rect)
