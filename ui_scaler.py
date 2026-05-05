"""
Sistema de UI Scaler Responsivo - Ancoragem e Escalonamento Dinâmico

Este módulo fornece um sistema robusto para posicionar elementos de UI
de forma responsiva, independentemente da resolução da tela.

Conceitos principais:
- Coordenadas normalizadas (0.0 a 1.0) em vez de pixels fixos
- Âncoras para definir pontos de referência (topo-esquerda, centro, topo-direita, etc.)
- Escalonamento baseado na proporção de resolução

Uso:
    from ui_scaler import UIScaler, Anchor
    
    scaler = UIScaler(base_resolution=(1920, 1080), current_resolution=(1920, 1080))
    
    # Posicionar elemento no canto superior direito
    pos = scaler.get_ui_position(
        normalized_x=1.0,
        normalized_y=0.0,
        anchor=Anchor.TOP_RIGHT,
        element_width=200,
        element_height=50
    )
    
    # Escalar tamanho de fonte
    font_size = scaler.scale_size(24)
"""

from enum import Enum
import pygame


class Anchor(Enum):
    """Pontos de ancoragem para elementos de UI."""
    TOP_LEFT = (0, 0)
    TOP_CENTER = (0.5, 0)
    TOP_RIGHT = (1, 0)
    
    CENTER_LEFT = (0, 0.5)
    CENTER = (0.5, 0.5)
    CENTER_RIGHT = (1, 0.5)
    
    BOTTOM_LEFT = (0, 1)
    BOTTOM_CENTER = (0.5, 1)
    BOTTOM_RIGHT = (1, 1)


class UIScaler:
    """Gerencia dimensões de UI de forma responsiva."""

    def __init__(self, base_resolution: tuple = (1920, 1080), 
                 current_resolution: tuple = (1920, 1080)):
        """
        Args:
            base_resolution: Resolução de referência (design baseline)
            current_resolution: Resolução atual da tela
        """
        self.base_w, self.base_h = base_resolution
        self.current_w, self.current_h = current_resolution
        self._update_scale_factors()

    def _update_scale_factors(self):
        """Calcula fatores de escala com base nas resoluções."""
        self.scale_x = self.current_w / self.base_w if self.base_w > 0 else 1.0
        self.scale_y = self.current_h / self.base_h if self.base_h > 0 else 1.0
        # Usa a menor escala para manter aspectos proporcionais
        self.scale_uniform = min(self.scale_x, self.scale_y)

    def update_resolution(self, new_resolution: tuple):
        """Atualiza a resolução atual e recalcula fatores de escala.
        
        Args:
            new_resolution: Tupla (width, height) da nova resolução
        """
        self.current_w, self.current_h = new_resolution
        self._update_scale_factors()

    def scale_size(self, size: float, uniform: bool = True) -> int:
        """Escala um tamanho (e.g., font size) baseado na resolução.
        
        Args:
            size: Tamanho base em pixels
            uniform: Se True, usa escala uniforme; se False, usa escala X
        
        Returns:
            Tamanho escalado em pixels (int)
        """
        scale = self.scale_uniform if uniform else self.scale_x
        return max(1, int(round(size * scale)))

    def get_ui_position(self, normalized_x: float, normalized_y: float,
                       anchor: Anchor = Anchor.TOP_LEFT,
                       element_width: int = 0, element_height: int = 0) -> tuple:
        """Calcula a posição de um elemento de UI baseada em coordenadas normalizadas.
        
        Args:
            normalized_x: Posição X relativa (0.0 = esquerda, 1.0 = direita)
            normalized_y: Posição Y relativa (0.0 = topo, 1.0 = fundo)
            anchor: Ponto de ancoragem do elemento (veja enum Anchor)
            element_width: Largura do elemento em pixels
            element_height: Altura do elemento em pixels
        
        Returns:
            Tupla (x, y) com a posição em pixels da tela
        
        Exemplo:
            # Posicionar elemento no canto superior direito
            x, y = scaler.get_ui_position(
                normalized_x=1.0,
                normalized_y=0.0,
                anchor=Anchor.TOP_RIGHT,
                element_width=200,
                element_height=50
            )
        """
        # Posição base (topo-esquerdo do elemento)
        base_x = normalized_x * self.current_w
        base_y = normalized_y * self.current_h

        # Ajusta pela âncora
        anchor_offset_x, anchor_offset_y = anchor.value
        adjusted_x = base_x - (anchor_offset_x * element_width)
        adjusted_y = base_y - (anchor_offset_y * element_height)

        return (int(round(adjusted_x)), int(round(adjusted_y)))

    def get_ui_rect(self, normalized_x: float, normalized_y: float,
                   width: int, height: int,
                   anchor: Anchor = Anchor.TOP_LEFT) -> pygame.Rect:
        """Retorna um Rect posicionado e dimensionado de forma responsiva.
        
        Args:
            normalized_x: Posição X relativa (0.0 a 1.0)
            normalized_y: Posição Y relativa (0.0 a 1.0)
            width: Largura desejada em pixels
            height: Altura desejada em pixels
            anchor: Ponto de ancoragem
        
        Returns:
            pygame.Rect posicionado corretamente
        """
        x, y = self.get_ui_position(
            normalized_x, normalized_y,
            anchor, width, height
        )
        return pygame.Rect(x, y, width, height)

    def get_screen_dimensions(self) -> tuple:
        """Retorna dimensões atuais da tela (w, h)."""
        return (self.current_w, self.current_h)

    def get_scale_factor(self) -> float:
        """Retorna o fator de escala uniforme (min(scale_x, scale_y))."""
        return self.scale_uniform

    def is_portrait(self) -> bool:
        """Verifica se a orientação é portrait (altura > largura)."""
        return self.current_h > self.current_w

    def is_landscape(self) -> bool:
        """Verifica se a orientação é landscape (largura > altura)."""
        return self.current_w > self.current_h


class UIElementHelper:
    """Helper para repositornar elementos de UI facilmente."""

    def __init__(self, scaler: UIScaler):
        self.scaler = scaler
        self.elements: dict = {}  # Armazena posições antigas dos elementos

    def register_element(self, element_id: str, normalized_pos: tuple,
                        anchor: Anchor, dimensions: tuple):
        """Registra um elemento para fácil repositorcionamento.
        
        Args:
            element_id: ID único do elemento
            normalized_pos: Tupla (x, y) com coordenadas normalizadas
            anchor: Âncora do elemento
            dimensions: Tupla (width, height)
        """
        self.elements[element_id] = {
            "normalized_pos": normalized_pos,
            "anchor": anchor,
            "dimensions": dimensions,
        }

    def update_element_position(self, element_id: str, ui_element):
        """Atualiza a posição de um elemento pygame (rect ou sprite).
        
        Args:
            element_id: ID do elemento registrado
            ui_element: Objeto com atributo 'rect' (pygame sprite ou similar)
        """
        if element_id not in self.elements:
            return

        info = self.elements[element_id]
        x, y = self.scaler.get_ui_position(
            info["normalized_pos"][0],
            info["normalized_pos"][1],
            info["anchor"],
            info["dimensions"][0],
            info["dimensions"][1]
        )
        ui_element.rect.topleft = (x, y)

    def update_all_positions(self, element_dict: dict):
        """Atualiza posições de todos os elementos registrados.
        
        Args:
            element_dict: Dicionário {element_id: ui_element}
        """
        for element_id in self.elements:
            if element_id in element_dict:
                self.update_element_position(element_id, element_dict[element_id])


# Instância global do scaler (inicializada no main)
ui_scaler: UIScaler | None = None


def init_ui_scaler(base_res: tuple = (1920, 1080), current_res: tuple = (1920, 1080)):
    """Inicializa o scaler global. Chamado uma vez no início do jogo."""
    global ui_scaler
    ui_scaler = UIScaler(base_resolution=base_res, current_resolution=current_res)
    return ui_scaler
