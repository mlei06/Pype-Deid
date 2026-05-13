#!/usr/bin/env bash
# =============================================================================
# NeuroNER Environment Setup Script
#
# Sets up a Python 3.7.12 environment via pyenv for running NeuroNER LSTM-CRF
# models (inference and training). This is required because NeuroNER depends on
# TensorFlow 1.x which only supports Python <=3.7.
#
# Directory layout (all data/output at project root, neuroner-cspmc is engine only):
#   neuroner-cspmc/          # Library code + venv (no data, no output)
#   data/word_vectors/       # GloVe embeddings
#   data/neuroner_deploy/    # Bootstrap deploy folder for inference pipe
#   models/neuroner/         # Pretrained model checkpoints
#   output/neuroner/         # Training and inference output
#
# Prerequisites:
#   - Linux or WSL
#   - pyenv installed (https://github.com/pyenv/pyenv#installation)
#   - Build dependencies for Python 3.7:
#       sudo apt install -y build-essential libssl-dev zlib1g-dev \
#         libbz2-dev libreadline-dev libsqlite3-dev libffi-dev \
#         liblzma-dev libncurses-dev tk-dev
#   - gdown (pip install gdown) for downloading from Google Drive
#
# Usage:
#   chmod +x scripts/setup_neuroner.sh
#   ./scripts/setup_neuroner.sh
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
NEURONER_ROOT="$PROJECT_ROOT/neuroner-cspmc"
VENV_DIR="$NEURONER_ROOT/venv"
MODELS_DIR="$PROJECT_ROOT/models/neuroner"
DATA_DIR="$PROJECT_ROOT/data"
OUTPUT_DIR="$PROJECT_ROOT/output/neuroner"

PYTHON_VERSION="3.7.12"

# Google Drive IDs
PRETRAINED_MODELS_FOLDER_URL="https://drive.google.com/drive/folders/1qKK4eTQgF2RWOfmBo_MvayUm0oY6uxOZ"
GLOVE_EMBEDDINGS_FILE_ID="1_Dx5-S8GMivdWM4AXqE2PyUD_00DRpFY"

# ── Helpers ──────────────────────────────────────────────────────────────────

info()  { echo -e "\033[1;34m[INFO]\033[0m  $*"; }
ok()    { echo -e "\033[1;32m[OK]\033[0m    $*"; }
warn()  { echo -e "\033[1;33m[WARN]\033[0m  $*"; }
error() { echo -e "\033[1;31m[ERROR]\033[0m $*"; exit 1; }

check_command() {
    command -v "$1" &>/dev/null || error "'$1' is not installed. $2"
}

# ── Step 0: Validate prerequisites ──────────────────────────────────────────

info "Checking prerequisites..."

check_command pyenv "Install pyenv: https://github.com/pyenv/pyenv#installation"

if ! command -v gdown &>/dev/null; then
    warn "'gdown' not found. Installing via pip..."
    pip install --quiet gdown
fi

if [ ! -d "$NEURONER_ROOT" ]; then
    error "neuroner-cspmc directory not found at $NEURONER_ROOT"
fi

ok "Prerequisites satisfied"

# ── Step 1: Install Python 3.7.12 via pyenv ────────────────────────────────

info "Setting up Python $PYTHON_VERSION via pyenv..."

if pyenv versions --bare | grep -qx "$PYTHON_VERSION"; then
    ok "Python $PYTHON_VERSION already installed"
else
    info "Installing Python $PYTHON_VERSION (this may take a few minutes)..."
    pyenv install "$PYTHON_VERSION"
    ok "Python $PYTHON_VERSION installed"
fi

# ── Step 2: Create virtualenv ──────────────────────────────────────────────

info "Creating virtualenv at $VENV_DIR..."

if [ -d "$VENV_DIR" ] && [ -x "$VENV_DIR/bin/python" ]; then
    EXISTING_VERSION=$("$VENV_DIR/bin/python" --version 2>&1 | awk '{print $2}')
    if [ "$EXISTING_VERSION" = "$PYTHON_VERSION" ]; then
        ok "Virtualenv already exists with Python $PYTHON_VERSION"
    else
        warn "Existing venv has Python $EXISTING_VERSION, recreating..."
        rm -rf "$VENV_DIR"
        "$(pyenv prefix "$PYTHON_VERSION")/bin/python" -m venv "$VENV_DIR"
        ok "Virtualenv recreated"
    fi
else
    "$(pyenv prefix "$PYTHON_VERSION")/bin/python" -m venv "$VENV_DIR"
    ok "Virtualenv created"
fi

PYTHON="$VENV_DIR/bin/python"
PIP="$VENV_DIR/bin/pip"

# Upgrade pip to latest version that supports Python 3.7
"$PYTHON" -m pip install --quiet --upgrade "pip<24"
ok "pip upgraded"

# ── Step 3: Install dependencies ───────────────────────────────────────────

info "Installing NeuroNER dependencies..."

REQUIREMENTS="$NEURONER_ROOT/requirements.txt"
CONSTRAINTS="$NEURONER_ROOT/constraints.txt"

if [ ! -f "$REQUIREMENTS" ]; then
    error "requirements.txt not found at $REQUIREMENTS"
fi

if [ -f "$CONSTRAINTS" ]; then
    "$PIP" install --quiet -c "$CONSTRAINTS" -r "$REQUIREMENTS"
else
    "$PIP" install --quiet -r "$REQUIREMENTS"
fi
ok "Dependencies installed"

# ── Step 4: Download spaCy English model ───────────────────────────────────

info "Downloading spaCy English model..."

if "$PYTHON" -c "import spacy; spacy.load('en')" 2>/dev/null; then
    ok "spaCy 'en' model already installed"
else
    "$PYTHON" -m spacy download en
    ok "spaCy 'en' model installed"
fi

# ── Step 5: Download pretrained models from Google Drive ───────────────────

info "Downloading pretrained NeuroNER models..."

mkdir -p "$MODELS_DIR"

EXPECTED_MODELS=(
    "conll_2003_en"
    "i2b2_2014_glove_spacy_bioes"
    "i2b2_2014_glove_stanford_bioes"
    "mimic_glove_spacy_bioes"
    "mimic_glove_stanford_bioes"
)

ALL_PRESENT=true
for model in "${EXPECTED_MODELS[@]}"; do
    if [ ! -d "$MODELS_DIR/$model" ] || [ ! -f "$MODELS_DIR/$model/dataset.pickle" ]; then
        ALL_PRESENT=false
        break
    fi
done

if $ALL_PRESENT; then
    ok "All pretrained models already present in $MODELS_DIR"
else
    info "Downloading models folder from Google Drive (this may take a while)..."
    TEMP_DL=$(mktemp -d)
    gdown --folder "$PRETRAINED_MODELS_FOLDER_URL" -O "$TEMP_DL" --quiet || {
        rm -rf "$TEMP_DL"
        error "Failed to download pretrained models. Try manually:\n  gdown --folder '$PRETRAINED_MODELS_FOLDER_URL' -O '$MODELS_DIR'"
    }
    for model_dir in "$TEMP_DL"/*/; do
        model_name=$(basename "$model_dir")
        if [ -d "$MODELS_DIR/$model_name" ]; then
            warn "Model '$model_name' already exists, skipping"
        else
            mv "$model_dir" "$MODELS_DIR/"
            info "  Installed model: $model_name"
        fi
    done
    rm -rf "$TEMP_DL"
    ok "Pretrained models installed to $MODELS_DIR"
fi

# ── Step 6: Download GloVe word embeddings ─────────────────────────────────

info "Downloading GloVe word embeddings..."

EMBED_DIR="$DATA_DIR/word_vectors"
GLOVE_FILE="$EMBED_DIR/glove.6B.100d.txt"

mkdir -p "$EMBED_DIR"

if [ -f "$GLOVE_FILE" ]; then
    ok "GloVe embeddings already present at $GLOVE_FILE"
else
    info "Downloading glove.6B.zip from Google Drive..."
    GLOVE_ZIP="$EMBED_DIR/glove.6B.zip"
    gdown "$GLOVE_EMBEDDINGS_FILE_ID" -O "$GLOVE_ZIP" --quiet || {
        rm -f "$GLOVE_ZIP"
        error "Failed to download GloVe embeddings. Try manually:\n  gdown '$GLOVE_EMBEDDINGS_FILE_ID' -O '$GLOVE_ZIP'"
    }
    info "Extracting GloVe embeddings..."
    unzip -o "$GLOVE_ZIP" -d "$EMBED_DIR"
    rm -f "$GLOVE_ZIP"
    ok "GloVe embeddings extracted to $EMBED_DIR"
fi

# ── Step 7: Create bootstrap deploy folder ─────────────────────────────────

DEPLOY_DIR="$DATA_DIR/neuroner_deploy/deploy"
if [ ! -d "$DEPLOY_DIR" ]; then
    info "Creating bootstrap deploy directory..."
    mkdir -p "$DEPLOY_DIR"
    cat > "$DEPLOY_DIR/example.txt" <<'SAMPLE'
Patient John Smith, age 72, was seen at Mount Sinai Hospital on 01/15/2024.
His medical record number is 123-45-6789. Dr. Jane Doe reviewed his chart.
Contact: (555) 123-4567 or john.smith@email.com. Address: 123 Main St, New York, NY 10001.
SAMPLE
    ok "Created deploy bootstrap at $DEPLOY_DIR"
fi

# ── Step 8: Create output directory ────────────────────────────────────────

mkdir -p "$OUTPUT_DIR"

# ── Done ───────────────────────────────────────────────────────────────────

echo ""
echo "=========================================="
echo "  NeuroNER setup complete!"
echo "=========================================="
echo ""
echo "Virtualenv:  $VENV_DIR"
echo "Python:      $("$PYTHON" --version 2>&1)"
echo "Models:      $MODELS_DIR"
echo "Embeddings:  $GLOVE_FILE"
echo "Output:      $OUTPUT_DIR"
echo ""
echo "── Quick start (standalone) ──"
echo ""
echo "  source $VENV_DIR/bin/activate"
echo "  cd $NEURONER_ROOT"
echo ""
echo "  # Inference"
echo "  neuroner --train_model=False \\"
echo "           --use_pretrained_model=True \\"
echo "           --pretrained_model_folder=$MODELS_DIR/i2b2_2014_glove_spacy_bioes \\"
echo "           --dataset_text_folder=$DATA_DIR/neuroner_deploy \\"
echo "           --token_pretrained_embedding_filepath=$DATA_DIR/word_vectors/glove.6B.100d.txt \\"
echo "           --output_folder=$OUTPUT_DIR"
echo ""
echo "  # Fine-tune"
echo "  neuroner --train_model=True \\"
echo "           --use_pretrained_model=True \\"
echo "           --pretrained_model_folder=$MODELS_DIR/i2b2_2014_glove_spacy_bioes \\"
echo "           --dataset_text_folder=$DATA_DIR/<your_dataset> \\"
echo "           --token_pretrained_embedding_filepath=$DATA_DIR/word_vectors/glove.6B.100d.txt \\"
echo "           --output_folder=$OUTPUT_DIR"
echo ""
echo "── Quick start (pipeline pipe) ──"
echo ""
echo "  # From project root — the neuroner_ner pipe auto-launches the Py3.7 subprocess"
echo "  cd $PROJECT_ROOT"
echo "  pypedeid run --config pipeline_with_neuroner.json"
echo ""
