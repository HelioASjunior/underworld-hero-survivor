"""
build_nuitka_linux.py — Roda DENTRO do container Docker para gerar o binario Linux.
Nao execute diretamente no Windows. E invocado por build_nuitka.py via docker run.
Variavel de ambiente LINUX_ONEFILE=1 ativa modo --onefile.
"""

import os
import sys
import subprocess

BASE_DIR = "/game"
OUT_DIR  = "/game/dist-nuitka/udw-linux"
onefile  = os.environ.get("LINUX_ONEFILE", "0") == "1"

cmd = [
    sys.executable, "-m", "nuitka",
    "--output-dir=" + OUT_DIR,
    "--output-filename=UnderWorld Hero",
    "--follow-imports",
    "--noinclude-numba-mode=nofollow",
    "--module-parameter=numba-disable-jit=yes",
    "--onefile" if onefile else "--standalone",
    f"--include-data-dir={BASE_DIR}/assets=assets",
    f"--include-data-file={BASE_DIR}/settings.json=settings.json",
]

# run_slot_1.json se existir
slot = f"{BASE_DIR}/run_slot_1.json"
if os.path.isfile(slot):
    cmd.append(f"--include-data-file={slot}=run_slot_1.json")

for mod in ("spatial_index", "hot_kernels", "balance", "characters",
            "enemies", "drops", "upgrades", "hud", "hub_room",
            "forest_biome", "dungeon_biome", "volcano_biome", "moon_biome",
            "combat.projectiles"):
    cmd.append(f"--include-module={mod}")

cmd.append(f"{BASE_DIR}/jogo_final.py")

print("\n>>> " + " ".join(cmd) + "\n")
result = subprocess.run(cmd, cwd=BASE_DIR)
sys.exit(result.returncode)
