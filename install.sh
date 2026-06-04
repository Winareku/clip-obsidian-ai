#!/usr/bin/env bash
# install.sh — Sets up clip-obsidian-ai on a Linux system.
#
# What it does:
#   1. Installs Python dependencies from requirements.txt
#   2. Copies config defaults to ~/.config/clip-obsidian-ai/
#   3. Creates a launcher script at ~/.local/bin/clip-obsidian-ai
#
# Usage:
#   chmod +x install.sh && ./install.sh

set -euo pipefail

# ── Colors ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

info()    { echo -e "${CYAN}[INFO]${RESET}  $*"; }
success() { echo -e "${GREEN}[OK]${RESET}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
error()   { echo -e "${RED}[ERROR]${RESET} $*" >&2; }

echo -e "\n${BOLD}clip-obsidian-ai — Installer${RESET}\n"

# ── 0. Prerequisites ──────────────────────────────────────────────────────────
command -v python3 >/dev/null 2>&1 || { error "python3 not found."; exit 1; }
command -v pip3    >/dev/null 2>&1 || { error "pip3 not found."; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
info "Project directory: ${SCRIPT_DIR}"

# ── 1. Install Python deps ────────────────────────────────────────────────────
info "Installing Python dependencies…"
pip3 install --user -q -r "${SCRIPT_DIR}/requirements.txt"
success "Python dependencies installed."

# ── 2. Bootstrap user config ──────────────────────────────────────────────────
CONFIG_DIR="${HOME}/.config/clip-obsidian-ai"
mkdir -p "${CONFIG_DIR}"

for file in config.yaml format.md; do
    src="${SCRIPT_DIR}/config/${file}"
    dst="${CONFIG_DIR}/${file}"
    if [[ -f "${src}" && ! -f "${dst}" ]]; then
        cp "${src}" "${dst}"
        success "Created ${dst}"
    elif [[ -f "${dst}" ]]; then
        warn "${dst} already exists — skipping (not overwritten)."
    else
        warn "Source file not found: ${src}"
    fi
done

# ── 3. Create launcher script ─────────────────────────────────────────────────
BIN_DIR="${HOME}/.local/bin"
mkdir -p "${BIN_DIR}"
LAUNCHER="${BIN_DIR}/clip-obsidian-ai"

cat > "${LAUNCHER}" << EOF
#!/usr/bin/env bash
exec python3 "${SCRIPT_DIR}/main.py" "\$@"
EOF

chmod +x "${LAUNCHER}"
success "Launcher created at ${LAUNCHER}"

# ── 4. PATH check ─────────────────────────────────────────────────────────────
if ! echo "${PATH}" | grep -q "${BIN_DIR}"; then
    warn "${BIN_DIR} is not in your PATH."
    echo -e "     Add this to your ~/.bashrc or ~/.zshrc:\n"
    echo -e "     ${YELLOW}export PATH=\"\${HOME}/.local/bin:\${PATH}\"${RESET}\n"
fi

# ── 5. Ollama check ───────────────────────────────────────────────────────────
if ! command -v ollama >/dev/null 2>&1; then
    warn "Ollama not found. Install from https://ollama.com and pull a model:"
    echo  "     ollama pull llama3.2"
else
    success "Ollama found at $(command -v ollama)"
fi

echo -e "\n${BOLD}${GREEN}Installation complete!${RESET}"
echo -e "Run: ${BOLD}clip-obsidian-ai --check${RESET}  to verify system dependencies."
echo -e "Run: ${BOLD}clip-obsidian-ai --help${RESET}   for usage information.\n"
