#!/usr/bin/env bash
# Instalador para Linux. En Windows usa setup.bat.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
mkdir -p logs
exec > >(tee -a "$ROOT/logs/setup.log") 2>&1

PROFILE="full"
SKIP_ASSETS=0
FORCE=0
for arg in "$@"; do
    case "$arg" in
        --runtime-only) PROFILE="runtime" ;;
        --skip-assets) SKIP_ASSETS=1 ;;
        --force) FORCE=1 ;;
        -h|--help)
            echo "Uso: ./setup.sh [--runtime-only] [--skip-assets] [--force]"
            exit 0
            ;;
        *) echo "Opción desconocida: $arg" >&2; exit 2 ;;
    esac
done

step() { printf '\n==> %s\n' "$*"; }
die() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }

find_python() {
    local candidate
    for candidate in python3.12 python3.13 python3.14 python3.11 python3.10 python3; do
        command -v "$candidate" >/dev/null 2>&1 || continue
        if "$candidate" - <<'PY'
import struct, sys
ok = (3, 10) <= sys.version_info[:2] < (3, 15)
ok = ok and struct.calcsize("P") * 8 == 64
ok = ok and "t" not in getattr(sys, "abiflags", "")
raise SystemExit(0 if ok else 1)
PY
        then
            printf '%s' "$candidate"
            return 0
        fi
    done
    return 1
}

create_venv() {
    local name="$1"
    local venv="$ROOT/.venv-$name"
    local py="$venv/bin/python"
    if [ "$FORCE" -eq 1 ]; then
        step "Eliminando .venv-$name anterior"
        rm -rf "$venv"
    fi
    if [ -x "$py" ] && "$py" -m pip --version >/dev/null 2>&1; then
        echo "Ya existe .venv-$name"
        return 0
    fi
    rm -rf "$venv"
    step "Creando .venv-$name"
    if ! "$PYTHON" -m venv "$venv" >/dev/null 2>&1 || [ ! -x "$py" ] || ! "$py" -m pip --version >/dev/null 2>&1; then
        rm -rf "$venv"
        "$PYTHON" -m venv --without-pip "$venv" || die "No se pudo crear .venv-$name"
        if ! "$py" -m pip --version >/dev/null 2>&1; then
            step "Instalando pip en .venv-$name"
            if ! "$PYTHON" -m pip --python "$py" install --no-cache-dir pip setuptools wheel >/dev/null 2>&1; then
                curl -sS https://bootstrap.pypa.io/get-pip.py | "$py"
            fi
        fi
    fi
    "$py" -m pip --version >/dev/null 2>&1 || die "No se pudo preparar pip en .venv-$name"
}

pip_install() {
    local py="$1"
    shift
    "$py" -m pip install --no-cache-dir --disable-pip-version-check "$@"
}

PYTHON="$(find_python || true)"
[ -n "$PYTHON" ] || die "No se encontró Python 3.10-3.14 de 64 bits. Instala python3 y python3-venv."
step "KittenTTS Local: instalación ($PROFILE)"
echo "Usando $("$PYTHON" -c 'import sys; print(sys.executable, sys.version.split()[0])')"

export PYTHONUTF8=1
export PIP_DISABLE_PIP_VERSION_CHECK=1
create_venv cpp
CPP_PY="$ROOT/.venv-cpp/bin/python"
pip_install "$CPP_PY" --index-url https://download.pytorch.org/whl/cpu torch==2.13.0
pip_install "$CPP_PY" -r "$ROOT/requirements/cpp.txt"

PREP_PY=""
if [ "$PROFILE" = "full" ]; then
    create_venv prep
    PREP_PY="$ROOT/.venv-prep/bin/python"
    pip_install "$PREP_PY" --index-url https://download.pytorch.org/whl/cpu torch==2.11.0 torchaudio==2.11.0
    pip_install "$PREP_PY" -r "$ROOT/requirements/prep.txt"
fi

if [ "$SKIP_ASSETS" -eq 0 ]; then
    step "Descargando assets (puede tardar y ocupar varios GB)"
    if [ -n "$PREP_PY" ]; then
        "$PREP_PY" "$ROOT/setup_assets.py" --profile "$PROFILE"
    else
        "$CPP_PY" "$ROOT/setup_assets.py" --profile "$PROFILE"
    fi
fi

step "Comprobando la instalación"
if [ "$SKIP_ASSETS" -eq 0 ]; then
    "$CPP_PY" "$ROOT/scripts/doctor.py" --load
else
    "$CPP_PY" "$ROOT/scripts/doctor.py"
fi

step "Instalación completada"
echo "Ejecuta: ./run.sh"
echo "Log: $ROOT/logs/setup.log"
