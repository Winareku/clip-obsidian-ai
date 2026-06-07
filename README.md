# clip-obsidian-ai

> Automatización de apuntes para Obsidian potenciada por LLM local (Ollama).

Procesa texto del portapapeles o documentos completos de un directorio y los transforma en notas estructuradas en Markdown, listas para pegar en tu vault de Obsidian, todo sin salir de tu máquina.

---

## Características

| Feature | Detalle |
|---|---|
| **Modo clip** | Lee el portapapeles, muestra una preview interactiva (wofi/rofi/zenity), envía el texto a Ollama y devuelve el resultado formateado al portapapeles |
| **Modo dir** | Escanea un directorio, extrae texto de todos los `.pdf`, `.pptx`, `.docx`, `.txt`, `.md`, los consolida y genera `notas_generadas.md` |
| **Hot-reload** | Edita `format.md` en cualquier momento; se carga fresco en cada llamada al LLM sin reiniciar nada |
| **Zero cloud** | Ollama corre localmente; tus documentos nunca salen de tu máquina |
| **Arquitectura limpia** | SOLID + Adapter Pattern + Factory + type hints completos |

---

## Requisitos del sistema

### Ollama (obligatorio)
```bash
# Instala Ollama desde https://ollama.com
ollama pull llama3.2          # o gemma2, mistral, etc.
ollama serve                   # debe estar corriendo
```

### Portapapeles (uno de los dos)
```bash
# Wayland (recomendado)
sudo pacman -S wl-clipboard    # Arch
sudo apt install wl-clipboard  # Ubuntu

# X11
sudo pacman -S xclip
sudo apt install xclip
```

### UI de confirmación (opcional, uno de los tres)
```bash
sudo pacman -S wofi            # Wayland launcher (recomendado)
sudo pacman -S rofi            # X11/Wayland launcher
sudo pacman -S zenity          # GTK dialog
```

### Notificaciones (opcional)
```bash
sudo pacman -S libnotify       # notify-send
sudo apt install libnotify-bin
```

---

## Instalación

Para instalar la aplicación de forma permanente e independiente en tu sistema:

```bash
git clone https://github.com/winareku/clip-obsidian-ai
cd clip-obsidian-ai

# Ejecutar el instalador guiado interactivo
python install.py

# Verificar que todo esté listo
clip-obsidian-ai --check
```

### ¿Qué hace el instalador?
1. Copia de forma aislada los archivos del proyecto a `~/.local/share/clip-obsidian-ai/`.
2. Genera un entorno virtual Python (`venv`) en dicho directorio de infraestructura e instala de manera silenciosa las dependencias necesarias.
3. Crea un script ejecutable en `~/.local/bin/clip-obsidian-ai` que enlaza al `venv` de la aplicación.
4. Lanza un **Asistente de Configuración Guiado** interactivo para configurar el proveedor de IA (Ollama, Gemini, auto o mock), solicitando de forma segura tu API Key de Google AI Studio y sugiriendo modelos por defecto.

La instalación copia los archivos de configuración por defecto a:
```
~/.config/clip-obsidian-ai/
├── config.yaml     ← configuración general
└── format.md       ← instrucciones del sistema para el LLM
```

---

## Uso

### Modo clip — Portapapeles

```bash
# Copia texto en cualquier aplicación, luego:
clip-obsidian-ai --mode clip

# Aparecerá un diálogo (wofi/rofi/zenity) para confirmar.
# El texto formateado regresa al portapapeles listo para pegar.
```

**Flujo completo:**
```
Portapapeles (texto crudo)
        ↓
  Diálogo de confirmación (wofi/rofi/zenity)
        ↓  [usuario confirma]
  Ollama + format.md como system prompt
        ↓
  Portapapeles (Markdown estructurado)
        ↓
  Notificación de escritorio ✅
```

### Modo dir — Directorio completo

```bash
# Procesar el directorio actual
cd ~/Documents/apuntes-curso
clip-obsidian-ai --mode dir

# Procesar un directorio específico
clip-obsidian-ai --mode dir --dir ~/Downloads/papers

# El resultado se guarda en notas_generadas.md
```

**Salida de ejemplo:**
```
────────────────────────────────────────────────────────────
  clip-obsidian-ai  │  dir mode  │  /home/user/apuntes
────────────────────────────────────────────────────────────

Archivos encontrados: 4

  ✔ [ 1/ 4] introduccion.pdf                      12,450 chars
  ✔ [ 2/ 4] slides_semana1.pptx                    8,230 chars
  ✔ [ 3/ 4] resumen.docx                            3,100 chars
  ✔ [ 4/ 4] notas_manuales.txt                      1,200 chars
············································

Texto total extraído: 24,980 caracteres

⏳ Enviando al LLM (llama3.2)…

✅ Notas generadas:
   /home/user/apuntes/notas_generadas.md
```

### Opciones adicionales

```bash
# Usar un modelo específico (override del config)
clip-obsidian-ai --mode clip --model gemma2
clip-obsidian-ai --mode dir  --model mistral

# Editar la configuración
clip-obsidian-ai --edit-config    # abre config.yaml en $EDITOR
clip-obsidian-ai --edit-format    # abre format.md en $EDITOR

# Verificar dependencias del sistema
clip-obsidian-ai --check

# Aumentar verbosidad para debug
clip-obsidian-ai --mode clip --log-level DEBUG
```

---

## Configuración

### `~/.config/clip-obsidian-ai/config.yaml`

```yaml
llm:
  model: "llama3.2"        # Cambia al modelo que tengas en Ollama
  max_input_chars: 12000   # Ajusta según el context window del modelo

clipboard:
  backend: "auto"          # auto | wl-clipboard | xclip

ui:
  backend: "auto"          # auto | wofi | rofi | zenity | none
  preview_chars: 300       # Caracteres de preview en el diálogo

dir_mode:
  recursive: false         # true para escanear subdirectorios
  output_filename: "notas_generadas.md"
```

### `~/.config/clip-obsidian-ai/format.md`

Este archivo es el **system prompt** que recibe el LLM. Puedes editarlo en caliente para cambiar el formato de salida sin reiniciar nada:

```bash
clip-obsidian-ai --edit-format
# o directamente:
$EDITOR ~/.config/clip-obsidian-ai/format.md
```

El formato por defecto genera:
- 📌 Resumen ejecutivo
- 🔑 Conceptos clave
- 📋 Puntos principales
- 💡 Insights y observaciones
- 🔗 Referencias y términos técnicos
- 🏷️ Tags sugeridos para Obsidian

---

## Arquitectura

```
clip-obsidian-ai/
├── main.py                    ← Entry point (argparse, routing)
├── config_manager.py          ← Bootstrap + carga de config
│
├── extractors/
│   └── __init__.py            ← BaseExtractor (ABC) + PDFExtractor,
│                                 PPTXExtractor, DocxExtractor, TXTExtractor,
│                                 ExtractorFactory
│
├── adapters/
│   └── __init__.py            ← ClipboardAdapter, UIAdapter, NotifierAdapter,
│                                 LLMAdapter (ABC) + implementaciones concretas
│                                 + AdapterFactory (auto-detección)
│
├── modes/
│   ├── __init__.py
│   ├── clip_mode.py           ← Orquestador modo portapapeles
│   └── dir_mode.py            ← Orquestador modo directorio
│
├── config/                    ← Defaults shipped con el repo
│   ├── config.yaml
│   └── format.md
│
├── tests/
│   └── test_all.py            ← 38 tests unitarios (pytest)
│
├── requirements.txt
└── install.sh
```

### Principios aplicados

**SOLID:**
- **S** — Cada clase tiene una responsabilidad: `PDFExtractor` sólo extrae PDF, `OllamaAdapter` sólo habla con Ollama, `DirMode` sólo orquesta el flujo dir.
- **O** — `ExtractorFactory.register()` permite añadir formatos sin tocar código existente.
- **L** — Cualquier `ClipboardAdapter` concreto puede sustituirse por otro sin romper el resto.
- **I** — Interfaces finas: `ClipboardAdapter` tiene sólo `read/write`, no métodos que los backends no necesiten.
- **D** — `ClipMode` y `DirMode` reciben sus dependencias inyectadas; nunca las instancian directamente.

**Adapter Pattern:**
- Los backends de sistema (wl-clipboard, rofi, notify-send, Ollama) están todos detrás de interfaces Python. Cambiar de Wayland a X11 o de rofi a wofi es cuestión de editar una línea del config.

---

## Añadir soporte para nuevos formatos de archivo

```python
# 1. Define tu extractor (en extractors/__init__.py o en un archivo separado)
class RTFExtractor(BaseExtractor):
    def extract_text(self, file_path: str) -> str:
        # tu lógica aquí
        ...

# 2. Regístralo en la factory (una línea, en tiempo de ejecución)
ExtractorFactory.register(".rtf", RTFExtractor)
```

## Tests

```bash
pip install pytest
python -m pytest tests/ -v

# 38 tests — ConfigManager, Extractors, Adapters, ClipMode, DirMode
```

---

## Integración con atajos de teclado (sway / i3 / hyprland)

```
# ~/.config/sway/config
bindsym $mod+shift+c exec clip-obsidian-ai --mode clip
bindsym $mod+shift+d exec clip-obsidian-ai --mode dir
```

```ini
# ~/.config/hypr/hyprland.conf
bind = $mainMod SHIFT, C, exec, clip-obsidian-ai --mode clip
bind = $mainMod SHIFT, D, exec, clip-obsidian-ai --mode dir
```

---

## Licencia

MIT
