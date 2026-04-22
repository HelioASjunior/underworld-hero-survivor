"""
build_nuitka.py — Compila UnderWorldHero-Game para Windows e Linux com Nuitka.

Windows: compila diretamente com MSVC/GCC instalado na maquina.
Linux:   compila dentro de um container Docker (requer Docker Desktop rodando).

Pre-requisito Windows:
    pip install nuitka
    Visual C++ Build Tools 2019+ OU WinLibs GCC no PATH

Pre-requisito Linux:
    Docker Desktop rodando

Uso:
    python build_nuitka.py              # Windows + Linux
    python build_nuitka.py --no-linux   # so Windows
    python build_nuitka.py --clean      # apaga dist-nuitka/ antes de compilar

Resultado:
    dist-nuitka/jogo_final.dist/UnderWorld Hero.exe   (Windows)
    dist-nuitka/udw-linux/jogo_final.dist/            (Linux)
    dist-nuitka/leiame.txt                            (instrucoes Linux)
"""

import os
import sys
import shutil
import subprocess
import argparse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EXE_NAME = "UnderWorld Hero"
DOCKER_IMAGE = "underworldhero-linux-env"


def run(cmd):
    print(f"\n>>> {' '.join(str(c) for c in cmd)}\n")
    result = subprocess.run(cmd, cwd=BASE_DIR)
    if result.returncode != 0:
        sys.exit(result.returncode)


def collect_data_dirs():
    pairs = []
    for folder in ("assets",):
        src = os.path.join(BASE_DIR, folder)
        if os.path.isdir(src):
            pairs.append((src, folder))
    return pairs


def collect_data_files():
    files = []
    for fname in ("settings.json", "run_slot_1.json"):  # save_v2.json excluido intencionalmente
        fpath = os.path.join(BASE_DIR, fname)
        if os.path.isfile(fpath):
            files.append(fpath)
    return files


def build_windows(out_dir, onefile=False):
    print("\n=== BUILD WINDOWS ===")
    icon_path = os.path.join(BASE_DIR, "icone.ico")

    cmd = [
        sys.executable, "-m", "nuitka",
        "--output-dir=" + out_dir,
        f"--output-filename={EXE_NAME}",
        "--assume-yes-for-downloads",
        "--follow-imports",
        "--noinclude-numba-mode=nofollow",
        "--module-parameter=numba-disable-jit=yes",
    ]

    if os.path.isfile(icon_path):
        cmd.append(f"--windows-icon-from-ico={icon_path}")

    cmd += [
        "--windows-console-mode=disable",
        "--windows-product-name=UnderWorld Hero",
        "--windows-file-description=UnderWorld Hero",
        "--windows-product-version=1.0.0.0",
        "--windows-file-version=1.0.0.0",
    ]

    cmd.append("--onefile" if onefile else "--standalone")

    for src, dest in collect_data_dirs():
        cmd.append(f"--include-data-dir={src}={dest}")

    for fpath in collect_data_files():
        cmd.append(f"--include-data-file={fpath}={os.path.basename(fpath)}")

    for fname in os.listdir(BASE_DIR):
        if fname.startswith("hot_kernels_cy") and fname.endswith(".pyd"):
            src = os.path.join(BASE_DIR, fname)
            cmd.append(f"--include-data-file={src}={fname}")

    for mod in ("spatial_index", "hot_kernels", "balance", "characters",
                "enemies", "drops", "upgrades", "hud", "hub_room",
                "forest_biome", "dungeon_biome", "volcano_biome", "moon_biome",
                "combat.projectiles"):
        cmd.append(f"--include-module={mod}")

    cmd.append(os.path.join(BASE_DIR, "jogo_final.py"))
    run(cmd)

    if onefile:
        print(f"\nOK Windows: {out_dir}/{EXE_NAME}.exe")
    else:
        print(f"\nOK Windows: {out_dir}/jogo_final.dist/{EXE_NAME}.exe")


def docker_available():
    try:
        r = subprocess.run(["docker", "ps"], capture_output=True, timeout=5)
        return r.returncode == 0
    except Exception:
        return False


def build_linux_docker(out_dir, onefile=False):
    print("\n=== BUILD LINUX (Docker) ===")

    dockerfile = os.path.join(BASE_DIR, "Dockerfile.linux")
    if not os.path.isfile(dockerfile):
        print("AVISO: Dockerfile.linux nao encontrado, pulando build Linux.")
        return

    linux_out = os.path.join(out_dir, "udw-linux")
    os.makedirs(linux_out, exist_ok=True)

    # Constroi imagem base (cache automatico do Docker — so rebuilda se mudar)
    print(f"Construindo imagem Docker '{DOCKER_IMAGE}'...")
    run(["docker", "build", "-f", dockerfile, "-t", DOCKER_IMAGE, BASE_DIR])

    # Converte caminho Windows para formato Docker (usa / e troca drive)
    if sys.platform == "win32":
        drive, rest = os.path.splitdrive(BASE_DIR)
        docker_mount = "/" + drive[0].lower() + rest.replace("\\", "/")
    else:
        docker_mount = BASE_DIR

    env_flag = ["-e", "LINUX_ONEFILE=1"] if onefile else []

    # Roda o build Nuitka dentro do container com o projeto montado
    run([
        "docker", "run", "--rm",
        "-v", f"{docker_mount}:/game",
        *env_flag,
        DOCKER_IMAGE,
        "python", "/game/build_nuitka_linux.py"
    ])

    mode = "onefile" if onefile else "jogo_final.dist/"
    print(f"\nOK Linux: {linux_out}/{mode}")


def write_leiame(out_dir):
    path = os.path.join(out_dir, "leiame.txt")
    content = """\
UNDERWORLD HERO — INSTALACAO NO LINUX
======================================

CONTEUDO DESTA PASTA
--------------------
  jogo_final.dist/UnderWorld Hero   Executavel do jogo (binario nativo Linux)
  jogo_final.dist/                  Bibliotecas e assets necessarios
  leiame.txt                        Este arquivo


COMO INSTALAR E RODAR
---------------------

1. Extraia a pasta udw-linux para onde quiser, por exemplo:
     ~/jogos/UnderWorldHero/

2. Instale as dependencias do sistema (SDL2):

   Ubuntu / Debian / Mint:
     sudo apt install libsdl2-2.0-0 libsdl2-image-2.0-0 \\
                      libsdl2-mixer-2.0-0 libsdl2-ttf-2.0-0

   Fedora / RHEL:
     sudo dnf install SDL2 SDL2_image SDL2_mixer SDL2_ttf

   Arch Linux:
     sudo pacman -S sdl2 sdl2_image sdl2_mixer sdl2_ttf

3. Dê permissao de execucao ao binario:
     chmod +x "jogo_final.dist/UnderWorld Hero"

4. Execute o jogo:
     cd jogo_final.dist
     ./"UnderWorld Hero"

   Ou com duplo clique no gerenciador de arquivos (se configurado).


OBSERVACOES
-----------
- O save do jogo e criado automaticamente na primeira execucao.
- Nao mova ou delete arquivos dentro da pasta jogo_final.dist/.
- Testado em Ubuntu 22.04+ e Debian 12+.
- Se o jogo nao abrir, verifique se todas as libs SDL2 estao instaladas.
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"OK leiame.txt gerado em {path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--onefile",    action="store_true", help="Windows onefile")
    parser.add_argument("--clean",      action="store_true", help="Apaga dist-nuitka antes de compilar")
    parser.add_argument("--clean-only", action="store_true", help="Apenas apaga dist-nuitka, sem compilar")
    parser.add_argument("--linux",      action="store_true", help="Windows + Linux via Docker")
    parser.add_argument("--linux-only", action="store_true", help="Apenas Linux via Docker (sem Windows)")
    parser.add_argument("--linux-onefile", action="store_true", help="Linux em modo onefile (binario unico)")
    args = parser.parse_args()

    out_dir = os.path.join(BASE_DIR, "dist-nuitka")

    if (args.clean or args.clean_only) and os.path.isdir(out_dir):
        print(f"Removendo {out_dir}...")
        shutil.rmtree(out_dir)

    if args.clean_only:
        print("Limpeza concluida.")
        return

    os.makedirs(out_dir, exist_ok=True)

    do_linux = args.linux or args.linux_only
    linux_onefile = args.linux_onefile

    # --- Windows (pulado se --linux-only) ---
    if not args.linux_only:
        build_windows(out_dir, onefile=args.onefile)

    # --- Linux via Docker (opt-in) ---
    if do_linux:
        if docker_available():
            build_linux_docker(out_dir, onefile=linux_onefile)
        else:
            print("\nAVISO: Docker nao disponivel — inicie o Docker Desktop e tente novamente.")

    # --- leiame.txt ---
    linux_out = os.path.join(out_dir, "udw-linux")
    if os.path.isdir(linux_out):
        write_leiame(linux_out)

    print("\n=== BUILD CONCLUIDO ===")
    if not args.linux_only:
        print(f"  Windows: {out_dir}/jogo_final.dist/{EXE_NAME}.exe")
    if do_linux:
        result_path = "UnderWorld Hero" if linux_onefile else "jogo_final.dist/"
        print(f"  Linux:   {out_dir}/udw-linux/{result_path}")
        print(f"  Leiame:  {out_dir}/udw-linux/leiame.txt")


if __name__ == "__main__":
    main()
