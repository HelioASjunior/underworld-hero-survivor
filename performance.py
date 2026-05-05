"""
Sistema expandido de Performance Profiling para identificar gargalos.

Uso:
    from performance import FrameProfiler, profile_section
    
    profiler = FrameProfiler()
    profiler.start_section("player_update")
    # ... código a medir
    profiler.end_section("player_update")
    
    # Ou como context manager:
    with profile_section(profiler, "enemy_update"):
        # ... código a medir
        pass
    
    # Imprimir relatório
    profiler.print_report()
"""

import time
from collections import defaultdict, deque
from contextlib import contextmanager


class FrameProfiler:
    """Perfil granular de seções do código por frame."""

    def __init__(self, history_frames: int = 60):
        self.history_frames = history_frames
        self.sections: dict[str, deque] = defaultdict(lambda: deque(maxlen=history_frames))
        self._section_starts: dict[str, float] = {}
        self._frame_count: int = 0

    def start_section(self, name: str):
        """Inicia a medição de uma seção."""
        self._section_starts[name] = time.perf_counter()

    def end_section(self, name: str):
        """Termina a medição de uma seção e registra o tempo."""
        if name not in self._section_starts:
            return
        elapsed_ms = (time.perf_counter() - self._section_starts[name]) * 1000.0
        self.sections[name].append(elapsed_ms)
        del self._section_starts[name]

    def new_frame(self):
        """Marca o fim de um frame. Deve ser chamado uma vez por frame."""
        self._frame_count += 1

    def get_average(self, section_name: str) -> float:
        """Retorna o tempo médio (em ms) de uma seção."""
        if section_name not in self.sections or not self.sections[section_name]:
            return 0.0
        return sum(self.sections[section_name]) / len(self.sections[section_name])

    def get_max(self, section_name: str) -> float:
        """Retorna o tempo máximo (em ms) de uma seção."""
        if section_name not in self.sections or not self.sections[section_name]:
            return 0.0
        return max(self.sections[section_name])

    def get_min(self, section_name: str) -> float:
        """Retorna o tempo mínimo (em ms) de uma seção."""
        if section_name not in self.sections or not self.sections[section_name]:
            return 0.0
        return min(self.sections[section_name])

    def print_report(self):
        """Imprime um relatório formatado de todas as seções medidas."""
        if not self.sections:
            print("[Profiler] Nenhuma seção foi medida ainda.")
            return

        print("\n" + "=" * 70)
        print("PERFORMANCE PROFILER REPORT")
        print("=" * 70)

        # Ordena por tempo médio (descendente)
        sorted_sections = sorted(
            self.sections.items(),
            key=lambda x: sum(x[1]) / len(x[1]) if x[1] else 0,
            reverse=True
        )

        print(f"{'Seção':<30} {'Médio':<10} {'Min':<10} {'Max':<10}")
        print("-" * 70)

        total_ms = 0.0
        for section_name, times in sorted_sections:
            if not times:
                continue
            avg_ms = sum(times) / len(times)
            min_ms = min(times)
            max_ms = max(times)
            total_ms += avg_ms

            print(f"{section_name:<30} {avg_ms:>8.2f}ms {min_ms:>8.2f}ms {max_ms:>8.2f}ms")

        print("-" * 70)
        print(f"{'TOTAL':<30} {total_ms:>8.2f}ms")
        print("=" * 70 + "\n")

    def reset(self):
        """Limpa todas as medições."""
        self.sections.clear()
        self._section_starts.clear()
        self._frame_count = 0


# Instância global
frame_profiler = FrameProfiler()


@contextmanager
def profile_section(profiler: FrameProfiler, section_name: str):
    """Context manager para medir uma seção de código automaticamente.
    
    Uso:
        with profile_section(frame_profiler, "my_section"):
            # código a medir
            pass
    """
    profiler.start_section(section_name)
    try:
        yield
    finally:
        profiler.end_section(section_name)
