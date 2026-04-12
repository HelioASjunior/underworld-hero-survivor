"""
build_cython.py – Compila hot_kernels_cy.pyx para extensão nativa.

Uso:
    python build_cython.py build_ext --inplace

Requisitos (Windows):
    pip install -r requirements-dev.txt
    Visual C++ Build Tools 2019+ instalado

Verificar backend após build:
    python -c "import hot_kernels; print('Cython:', hot_kernels.CYTHON_ACTIVE)"
"""

from setuptools import Extension, setup
from Cython.Build import cythonize
import numpy as np

# Diretivas de compilação: desliga verificações de segurança para máxima velocidade
CYTHON_DIRECTIVES = {
    "language_level":  "3",
    "boundscheck":     False,   # sem checagem de índice (já garantido pelo código)
    "wraparound":      False,   # sem suporte a índices negativos
    "cdivision":       True,    # divisão C pura (sem checagem de divisão por zero)
    "nonecheck":       False,   # sem checagem de None em objetos tipados
    "initializedcheck": False,  # sem checagem de memoryview inicializado
}

import sys, os

def _compile_args():
    """Detecta compilador e retorna flags de otimização corretas."""
    compiler = os.environ.get("CC", "")
    # MinGW/GCC: usa -O3; MSVC (cl.exe): usa /O2
    if "gcc" in compiler.lower() or "mingw" in compiler.lower():
        return ["-O3"]
    if sys.platform == "win32" and "gcc" not in compiler.lower():
        # Verifica se o compilador padrão do Python é MSVC
        import sysconfig
        cc = sysconfig.get_config_var("CC") or ""
        if "gcc" in cc.lower():
            return ["-O3"]
        return []   # Deixa setuptools escolher as flags corretas para o compilador ativo
    return ["-O3", "-march=native"]

extensions = [
    Extension(
        name="hot_kernels_cy",
        sources=["hot_kernels_cy.pyx"],
        include_dirs=[np.get_include()],
        extra_compile_args=_compile_args(),
    )
]

setup(
    name="underworldhero-hot-kernels",
    ext_modules=cythonize(
        extensions,
        compiler_directives=CYTHON_DIRECTIVES,
        annotate=False,   # True gera .html com anotações de performance (útil para debug)
    ),
)
