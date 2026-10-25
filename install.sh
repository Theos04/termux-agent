#!/usr/bin/env bash
# termux-agent installer — Linux / WSL / Termux
# Bundles: agent + Maps skills + llama_tui + CDP scripts + pincode CSV
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

IS_TERMUX=0
if [[ "${PREFIX:-}" == *"com.termux"* ]] || [[ -d /data/data/com.termux ]]; then
  IS_TERMUX=1
fi

echo "=== termux-agent install ==="
echo "Root: $ROOT"
echo "Termux: $IS_TERMUX"

# ── system packages ──────────────────────────────────────────────
if [[ "$IS_TERMUX" -eq 1 ]]; then
  pkg update -y || true
  pkg install -y python python-pip git openssh termux-api 2>/dev/null || true
elif command -v apt-get >/dev/null 2>&1; then
  sudo apt-get update -y >/dev/null 2>&1 || true
  sudo apt-get install -y python3 python3-pip python3-venv git curl >/dev/null 2>&1 || true
fi

# ── python ───────────────────────────────────────────────────────
if command -v python3 >/dev/null 2>&1; then
  PYTHON=python3
else
  PYTHON=python
fi

VENV="$ROOT/.venv"
mkdir -p "$ROOT/bin" "$ROOT/data" "$ROOT/agent_runs" "$ROOT/logs"

if [[ "$IS_TERMUX" -eq 1 ]]; then
  "$PYTHON" -m pip install --upgrade pip setuptools wheel
  "$PYTHON" -m pip install -r "$ROOT/requirements.txt"
  if [[ "${WITH_MMCP:-0}" == "1" ]]; then
    "$PYTHON" -m pip install -r "$ROOT/requirements-mmcp.txt"
  fi
  PY_RUN="$PYTHON"
else
  if [[ ! -d "$VENV" ]]; then
    "$PYTHON" -m venv "$VENV"
  fi
  # shellcheck disable=SC1091
  source "$VENV/bin/activate"
  pip install --upgrade pip setuptools wheel
  pip install -r "$ROOT/requirements.txt"
  if [[ "${WITH_MMCP:-0}" == "1" ]]; then
    pip install -r "$ROOT/requirements-mmcp.txt"
  fi
  PY_RUN="$VENV/bin/python"
fi

# ── data ─────────────────────────────────────────────────────────
if [[ ! -f "$ROOT/data/pincodes.csv" ]]; then
  echo "WARN: data/pincodes.csv missing — Maps geo coverage needs it."
  echo "      Place CSV at data/pincodes.csv or set PINCODE_CSV=/path/to.csv"
else
  echo "OK: pincodes.csv ($(wc -l < "$ROOT/data/pincodes.csv") rows)"
fi

cat > "$ROOT/.env.example" <<'EOF'
PINCODE_CSV=./data/pincodes.csv
AGENT_LIVE=1
# CDP_PORT=9222
# LLAMA_BIN=llama-cli
# LLAMA_MODEL=/path/to/model.gguf
EOF

# ── CLI wrappers ─────────────────────────────────────────────────
cat > "$ROOT/bin/termux-agent" <<EOF
#!/usr/bin/env bash
ROOT="$ROOT"
cd "\$ROOT"
[[ -f "\$ROOT/.venv/bin/activate" ]] && source "\$ROOT/.venv/bin/activate"
export PINCODE_CSV="\${PINCODE_CSV:-\$ROOT/data/pincodes.csv}"
exec python "\$ROOT/run_agent.py" "\$@"
EOF

cat > "$ROOT/bin/llama-tui" <<EOF
#!/usr/bin/env bash
ROOT="$ROOT"
cd "\$ROOT"
[[ -f "\$ROOT/.venv/bin/activate" ]] && source "\$ROOT/.venv/bin/activate"
export PINCODE_CSV="\${PINCODE_CSV:-\$ROOT/data/pincodes.csv}"
exec python "\$ROOT/llama_tui.py" "\$@"
EOF

chmod +x "$ROOT/bin/termux-agent" "$ROOT/bin/llama-tui"
chmod +x "$ROOT/install.sh" "$ROOT/start_agent.sh" "$ROOT/install_termux.sh" 2>/dev/null || true

# ── smoke ────────────────────────────────────────────────────────
echo ""
echo "=== smoke checks ==="
export PINCODE_CSV="$ROOT/data/pincodes.csv"
"$PY_RUN" - <<'PY'
import sys
sys.path.insert(0, ".")
from agent.skills.decision import DecisionBuilderSkill
g = "fetch me list of automation companies in pune"
d = DecisionBuilderSkill()
assert d.can_handle(g), "skills gate failed"
dec = d.build(g, dry_run=True)
assert dec.search_urls and "maps" in dec.search_urls[0], dec.search_urls
print("skills OK:", dec.query, "→", dec.search_urls[0][:64], "...")
import fetch_page2  # noqa: F401
import agent_bridge  # noqa: F401
print("imports OK")
PY

echo ""
echo "=== install complete ==="
echo "  export PATH=\"$ROOT/bin:\$PATH\""
echo "  python launch-chrome.py          # CDP Chrome"
echo "  llama-tui                        # TUI → Maps skills for business lists"
echo "  bash start_agent.sh              # daemon + dashboard :9227"
echo "  WITH_MMCP=1 bash install.sh      # optional LangGraph/MCP extras"
echo "  PINCODE_CSV=$ROOT/data/pincodes.csv"
