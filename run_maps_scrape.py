#!/usr/bin/env python3
"""Standalone maps scrape runner — no timeout, DB persistence enabled."""
import sys, json, os, time, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

GOAL = "fetch phone numbers for bars and bistro in pune live"

print(f"[{time.strftime('%H:%M:%S')}] Starting: {GOAL!r}", flush=True)
print("─" * 60, flush=True)

from agent_bridge import PageFetcher, HarManager, OrchestratorAgent, create_mmcp_llm_fn
from agent.database import Database
from agent.config import AgentConfig

fetcher = PageFetcher()
har = HarManager()
llm_fn = create_mmcp_llm_fn() or (lambda p: "")

db = Database(AgentConfig().db_path)

def on_event(evt, data):
    if evt == "task_progress":
        label = data.get("label","")
        phase = data.get("phase","")
        cards = data.get("cards",0)
        phones = data.get("phones",0)
        step  = data.get("step",0)
        total = data.get("total",0)
        print(f"[{time.strftime('%H:%M:%S')}] {label} | {phase} | {step}/{total} | cards={cards} phones={phones}", flush=True)
    elif evt in ("agent_started", "agent_done", "step_observation"):
        print(f"[{time.strftime('%H:%M:%S')}] [{evt}] {str(data)[:120]}", flush=True)

agent = OrchestratorAgent(
    llm_fn=llm_fn,
    page_fetcher=fetcher,
    har_manager=har,
    ui_callback=on_event,
)

t0 = time.time()
result = agent.run_goal(GOAL, max_steps=60)
elapsed = time.time() - t0

print("\n" + "─" * 60, flush=True)
print(f"[{time.strftime('%H:%M:%S')}] Done in {elapsed:.1f}s", flush=True)
print(result[:3000], flush=True)

# Final DB snapshot
c = db.count_places()
print(f"\n✓ DB places: total={c['total']}  with_phone={c['with_phone']}", flush=True)

rows = db.get_places(with_phone=True, limit=15)
print("\nSample (with phone):")
for r in rows:
    print(f"  {r['name'][:42]:<42} {r['phone']:<14} {(r['category'] or '')[:20]}")
