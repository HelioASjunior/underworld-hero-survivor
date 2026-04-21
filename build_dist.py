"""
build_dist.py — Empacota UnderWorldHero-Game com PyInstaller.

Uso:
    python build_dist.py              # build normal (pasta dist/UnderWorldHero)
    python build_dist.py --onefile    # executável único (mais lento p/ iniciar)
    python build_dist.py --clean      # apaga build/ e dist/ antes de empacotar

Resultado: dist/UnderWorldHero/UnderWorldHero.exe  (ou .exe sozinho com --onefile)
"""

import os
import sys
import shutil
import subprocess
import argparse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def run(cmd):
    print(f"\n>>> {' '.join(cmd)}\n")
    result = subprocess.run(cmd, cwd=BASE_DIR)
    if result.returncode != 0:
        sys.exit(result.returncode)


def collect_data_dirs():
    """Retorna lista de (src, dest) para --add-data."""
    pairs = []
    for folder in ("assets", "combat"):
        src = os.path.join(BASE_DIR, folder)
        if os.path.isdir(src):
            pairs.append((src, folder))
    return pairs


def collect_binaries():
    """Inclui o .pyd Cython compilado se existir."""
    pairs = []
    for fname in os.listdir(BASE_DIR):
        if fname.startswith("hot_kernels_cy") and fname.endswith(".pyd"):
            pairs.append((os.path.join(BASE_DIR, fname), "."))
    return pairs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--onefile", action="store_true")
    parser.add_argument("--clean", action="store_true")
    args = parser.parse_args()

    if args.clean:
        for d in ("build", "dist"):
            path = os.path.join(BASE_DIR, d)
            if os.path.isdir(path):
                print(f"Removendo {path}…")
                shutil.rmtree(path)
        spec = os.path.join(BASE_DIR, "UnderWorldHero.spec")
        if os.path.isfile(spec):
            os.remove(spec)

    sep = ";" if sys.platform == "win32" else ":"

    icon_path = os.path.join(BASE_DIR, "icone.ico")

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", "UnderWorldHero",
        "--icon", icon_path if os.path.isfile(icon_path) else "NONE",
        "--noconfirm",
    ]

    if args.onefile:
        cmd.append("--onefile")
    else:
        cmd.append("--onedir")

    # Dados: assets e subpacotes Python
    for src, dest in collect_data_dirs():
        cmd += ["--add-data", f"{src}{sep}{dest}"]

    # JSONs de save/settings na raiz
    for fname in ("settings.json", "save_v2.json", "run_slot_1.json"):
        fpath = os.path.join(BASE_DIR, fname)
        if os.path.isfile(fpath):
            cmd += ["--add-data", f"{fpath}{sep}."]

    # Binários Cython
    for src, dest in collect_binaries():
        cmd += ["--add-binary", f"{src}{sep}{dest}"]

    # Módulos que PyInstaller pode não detectar automaticamente
    for mod in ("pygame", "numpy", "numba", "pytmx", "spatial_index",
                "hot_kernels", "hot_kernels_cy", "balance", "characters",
                "enemies", "drops", "upgrades", "hud", "hub_room",
                "forest_biome", "dungeon_biome", "volcano_biome", "moon_biome"):
        cmd += ["--hidden-import", mod]

    cmd.append(os.path.join(BASE_DIR, "jogo_final.py"))

    run(cmd)

    print("\n✓ Build concluído.")
    if args.onefile:
        print(f"  Executável: dist/UnderWorldHero.exe")
    else:
        print(f"  Pasta:      dist/UnderWorldHero/")


if __name__ == "__main__":
    main()
