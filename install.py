#!/usr/bin/env python3
import os
import sys
import shutil
import subprocess
import getpass
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────
PROJECT_DIR = Path(__file__).parent.resolve()
SHARE_DIR = Path.home() / ".local" / "share" / "clip-obsidian-ai"
BIN_DIR = Path.home() / ".local" / "bin"
CONFIG_DIR = Path.home() / ".config" / "clip-obsidian-ai"
CONFIG_FILE = CONFIG_DIR / "config.yaml"
FORMAT_FILE = CONFIG_DIR / "format.md"

def info(msg: str):
    print(f"\033[96m[INFO]\033[0m  {msg}")

def success(msg: str):
    print(f"\033[92m[OK]\033[0m    {msg}")

def warn(msg: str):
    print(f"\033[93m[WARN]\033[0m  {msg}")

def error(msg: str):
    print(f"\033[91m[ERROR]\033[0m {msg}", file=sys.stderr)

def copy_project_files():
    info("Copiando archivos del proyecto a la ruta global de infraestructura...")
    SHARE_DIR.mkdir(parents=True, exist_ok=True)
    
    # Directories to copy
    dirs_to_copy = ["adapters", "extractors", "modes", "config"]
    for d in dirs_to_copy:
        src_path = PROJECT_DIR / d
        dest_path = SHARE_DIR / d
        if src_path.exists():
            if dest_path.exists():
                shutil.rmtree(dest_path)
            shutil.copytree(src_path, dest_path)
            
    # Files to copy
    files_to_copy = ["main.py", "config_manager.py", "requirements.txt"]
    for f in files_to_copy:
        src_path = PROJECT_DIR / f
        dest_path = SHARE_DIR / f
        if src_path.exists():
            shutil.copy2(src_path, dest_path)
            
    success(f"Archivos copiados a {SHARE_DIR}")

def create_venv():
    info("Creando entorno virtual aislado (venv) e instalando dependencias...")
    venv_dir = SHARE_DIR / "venv"
    
    try:
        # Create virtual env
        subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)
        
        # Install requirements
        pip_path = venv_dir / "bin" / "pip"
        subprocess.run(
            [str(pip_path), "install", "-q", "-r", str(SHARE_DIR / "requirements.txt")],
            check=True
        )
        success("Entorno virtual y dependencias instalados correctamente.")
    except subprocess.CalledProcessError as exc:
        error(f"Error al crear el venv o instalar dependencias: {exc}")
        sys.exit(1)

def create_launcher():
    info("Creando script lanzador en ~/.local/bin/clip-obsidian-ai...")
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    launcher_path = BIN_DIR / "clip-obsidian-ai"
    
    launcher_content = f"""#!/bin/sh
exec "{SHARE_DIR}/venv/bin/python" "{SHARE_DIR}/main.py" "$@"
"""
    try:
        with open(launcher_path, "w", encoding="utf-8") as f:
            f.write(launcher_content)
        os.chmod(launcher_path, 0o755)
        success(f"Lanzador creado con permisos ejecutables en {launcher_path}")
    except Exception as exc:
        error(f"Error al crear el lanzador: {exc}")
        sys.exit(1)

def load_simple_config(config_path: Path):
    if not config_path.exists():
        return None
    config = {"provider": "auto", "model": "gemini-1.5-flash", "api_key": ""}
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        in_llm = False
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped.startswith("llm:"):
                in_llm = True
                continue
            if in_llm:
                if line.startswith(" ") or line.startswith("\t"):
                    if ":" in stripped:
                        k, v = stripped.split(":", 1)
                        k = k.strip()
                        v = v.strip().strip('"').strip("'")
                        if "#" in v:
                            v = v.split("#", 1)[0].strip().strip('"').strip("'")
                        if k in config:
                            config[k] = v
                else:
                    in_llm = False
    except Exception:
        pass
    return config

def write_simple_config(config_path: Path, provider: str, model: str, api_key: str):
    # Generates a standard default config template with updated LLM values
    default_template = f"""# clip-obsidian-ai Configuration File
# Located at: ~/.config/clip-obsidian-ai/config.yaml

# ─────────────────────────────────────────────
# LLM Configuration
# ─────────────────────────────────────────────
llm:
  provider: "{provider}"
  model: "{model}"
  api_key: "{api_key}"
  host: "http://localhost:11434"
  timeout: 120
  max_input_chars: 12000

# ─────────────────────────────────────────────
# Clipboard Configuration
# ─────────────────────────────────────────────
clipboard:
  backend: "auto"

# ─────────────────────────────────────────────
# UI / Prompt Configuration
# ─────────────────────────────────────────────
ui:
  backend: "auto"
  prompt_message: "¿Procesar este texto con IA?"
  confirm_label: "✅ Sí, procesar"
  cancel_label: "❌ Cancelar"
  preview_chars: 300

# ─────────────────────────────────────────────
# Notification Configuration
# ─────────────────────────────────────────────
notifications:
  enabled: true
  backend: "notify-send"
  app_name: "clip-obsidian-ai"
  timeout_ms: 4000

# ─────────────────────────────────────────────
# Dir Mode Configuration
# ─────────────────────────────────────────────
dir_mode:
  output_filename: "notas_generadas.md"
  supported_extensions:
    - ".pdf"
    - ".pptx"
    - ".docx"
    - ".txt"
    - ".md"
  recursive: false
  file_separator: "\\n\\n---\\n\\n"

# ─────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────
logging:
  level: "INFO"
  show_timestamps: false
"""
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        f.write(default_template)

def update_yaml_config(config_path: Path, provider: str, model: str, api_key: str):
    if not config_path.exists():
        src_default = PROJECT_DIR / "config" / "config.yaml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        if src_default.exists():
            shutil.copy2(src_default, config_path)
        else:
            write_simple_config(config_path, provider, model, api_key)
            return

    with open(config_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    
    new_lines = []
    in_llm = False
    provider_updated = False
    model_updated = False
    api_key_updated = False
    
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("llm:"):
            in_llm = True
            new_lines.append(line)
            continue
        
        if in_llm:
            if line.startswith(" ") or line.startswith("\t"):
                if ":" in stripped:
                    k_part = stripped.split(":", 1)[0].strip()
                    if k_part == "provider":
                        new_lines.append(f"  provider: \"{provider}\"\n")
                        provider_updated = True
                    elif k_part == "model":
                        new_lines.append(f"  model: \"{model}\"\n")
                        model_updated = True
                    elif k_part == "api_key":
                        new_lines.append(f"  api_key: \"{api_key}\"\n")
                        api_key_updated = True
                    else:
                        new_lines.append(line)
                else:
                    new_lines.append(line)
            else:
                in_llm = False
                new_lines.append(line)
        else:
            new_lines.append(line)
            
    with open(config_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

def run_config_wizard():
    print("\n\033[1m⚙️  Asistente de Configuración de clip-obsidian-ai\033[0m\n")
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    
    # Copy default format.md if not exists
    if not FORMAT_FILE.exists():
        src_format = PROJECT_DIR / "config" / "format.md"
        if src_format.exists():
            shutil.copy2(src_format, FORMAT_FILE)
            success("Archivo de plantilla format.md copiado a ~/.config/clip-obsidian-ai/")

    existing = load_simple_config(CONFIG_FILE)
    if existing:
        print(f"Se detectó una configuración existente en {CONFIG_FILE}:")
        print(f"  - Proveedor actual: {existing.get('provider')}")
        print(f"  - Modelo actual: {existing.get('model')}")
        
        choice = input("\n¿Deseas conservar esta configuración? (S/n): ").strip().lower()
        if choice in ("", "s", "si", "yes", "y"):
            success("Configuración actual conservada.")
            return
            
    # Ask configuration questions
    while True:
        provider = input("¿Qué proveedor de IA deseas usar por defecto? (auto / ollama / gemini / mock) [auto]: ").strip().lower()
        if not provider:
            provider = "auto"
        if provider in ("auto", "ollama", "gemini", "mock"):
            break
        print("Opción no válida. Por favor elige entre auto, ollama, gemini o mock.")
        
    api_key = ""
    if provider in ("gemini", "auto"):
        while True:
            api_key = getpass.getpass("Ingresa tu Token/API Key de Google AI Studio (Gemini): ").strip()
            if api_key:
                break
            warn("La clave API no puede estar vacía para Gemini/Auto.")
            
    suggested_model = "gemini-1.5-flash" if provider in ("gemini", "auto") else ("llama3.2" if provider == "ollama" else "mock")
    model = input(f"Selecciona el modelo por defecto [{suggested_model}]: ").strip()
    if not model:
        model = suggested_model
        
    update_yaml_config(CONFIG_FILE, provider, model, api_key)
    success(f"Configuración guardada exitosamente en {CONFIG_FILE}")

def check_path():
    path_env = os.environ.get("PATH", "")
    bin_str = str(BIN_DIR)
    if bin_str not in path_env and bin_str.replace(str(Path.home()), "~") not in path_env:
        print("\n\033[93m" + "!" * 60 + "\033[0m")
        warn(f"'{BIN_DIR}' no está actualmente en tu variable de entorno PATH.")
        print("Para poder ejecutar 'clip-obsidian-ai' globalmente, añade la siguiente línea a tu ~/.bashrc o ~/.zshrc:")
        print(f"  \033[1mexport PATH=\"$HOME/.local/bin:$PATH\"\033[0m")
        print("\033[93m" + "!" * 60 + "\033[0m\n")

def main():
    print("\n\033[1m🚀 Instalador Global de clip-obsidian-ai\033[0m\n")
    copy_project_files()
    create_venv()
    create_launcher()
    run_config_wizard()
    check_path()
    success("\033[1m¡Instalación completada con éxito!\033[0m")
    print("Ya puedes usar el comando 'clip-obsidian-ai' desde cualquier terminal.\n")

if __name__ == "__main__":
    main()
