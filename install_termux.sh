#!/data/data/com.termux/files/usr/bin/bash
# Thin Termux entry → full installer
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
exec bash "$ROOT/install.sh" "$@"
