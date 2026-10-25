# termux-agent

Chrome CDP automation agent for **Termux / Linux / WSL**, with a **Maps skills pipeline** (no LLM) for local business listings and a **llama_tui** console.

## What you get

| Piece | Role |
|-------|------|
| `agent/` | Task queue, workers, scheduler, CDP tools |
| `agent/skills/` | Decision → pincodes CSV → Google Maps scrape |
| `agent_bridge.py` | Orchestrator used by TUI + cron |
| `llama_tui.py` | Textual TUI — auto-routes business goals to Maps skills |
| `scripts-library/google-maps/` | Consent, discover, scroll, phone enrich JS |
| `data/pincodes.csv` | India PIN coverage for geo scrapes |
| `handlers/maps_scrape.py` | Cron task type `maps_scrape` |
| `mmcp/` | Optional multi-model / LangGraph extras |

## Install

```bash
bash install.sh
# optional LangGraph/MCP extras:
WITH_MMCP=1 bash install.sh

export PATH="$PWD/bin:$PATH"
export PINCODE_CSV="$PWD/data/pincodes.csv"
```

Termux: `bash install_termux.sh` (same installer).

## Quick start

```bash
python launch-chrome.py          # Chrome with remote debugging
llama-tui                        # or: python llama_tui.py

# In TUI — these hit Maps skills (not Google Search):
#   fetch me list of automation companies in pune
#   give me list of all pharmacy in delhi
#   /agent scrape pharmacies in surat on google maps

bash start_agent.sh              # daemon + dashboard http://localhost:9227/
python run_agent.py submit maps_scrape -p '{"goal":"pharmacies in delhi","dry_run":false}'
```

## Maps skills routing

Business / contact / geo goals skip the LLM and open `google.com/maps/search/...`:

1. **decision** — parse query, city/state, fields  
2. **pincodes** — filter `data/pincodes.csv`  
3. **maps_geo** — run `scripts-library/google-maps/*` over CDP  

Say `dry` in the goal for plan-only; otherwise live when Chrome CDP is up.

## Layout

```
agent/                 core runtime + skills/
agent_bridge.py        orchestrator
llama_tui.py           TUI
handlers/              CDP + maps_scrape plugins
scripts-library/       site JS (google-maps, …)
data/pincodes.csv      bundled PIN database
api/                   monitor dashboard
mmcp/                  optional multi-model protocol
har2api/               HAR → client utilities
install.sh             full bundle installer
```
