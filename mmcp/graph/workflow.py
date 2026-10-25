"""
LangGraph multi-model orchestration with a pure-Python fallback.

Graph:
  route → plan → (vision?) → act → synthesize → END
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Dict, List, Optional

from mmcp.graph.state import AgentGraphState
from mmcp.models.router import ModelRouter, get_router

logger = logging.getLogger(__name__)

_HAS_LANGGRAPH = False
try:
    from langgraph.graph import END, StateGraph  # type: ignore

    _HAS_LANGGRAPH = True
except Exception:
    StateGraph = None  # type: ignore
    END = None  # type: ignore


ToolFn = Callable[[str, Dict[str, Any]], Dict[str, Any]]


class MultiModelWorkflow:
    """
    Production multi-model context protocol runner.

    Uses LangGraph when installed; otherwise runs an equivalent sequential graph.
    """

    def __init__(
        self,
        router: Optional[ModelRouter] = None,
        tool_executor: Optional[ToolFn] = None,
        use_langgraph: bool = True,
    ):
        self.router = router or get_router()
        self.tool_executor = tool_executor
        self.use_langgraph = use_langgraph and _HAS_LANGGRAPH
        self._compiled = None
        if self.use_langgraph:
            self._compiled = self._build_langgraph()

    @property
    def backend(self) -> str:
        return "langgraph" if self._compiled is not None else "fallback"

    # ----- nodes -----

    def node_route(self, state: AgentGraphState) -> AgentGraphState:
        goal = (state.get("goal") or "").lower()
        role = "chat"
        if any(k in goal for k in ("detect", "screenshot", "vision", "ocr", "bbox")):
            role = "vision"
        elif any(k in goal for k in ("plan", "break down", "steps", "strategy")):
            role = "plan"
        elif any(k in goal for k in ("extract", "parse", "json", "har")):
            role = "extract"
        state["role"] = role
        state["step"] = int(state.get("step") or 0)
        state["max_steps"] = int(state.get("max_steps") or 6)
        state.setdefault("observations", [])
        state.setdefault("tool_calls", [])
        state["done"] = False
        return state

    def node_plan(self, state: AgentGraphState) -> AgentGraphState:
        system = (
            "You are a planning node in a multi-model agent. "
            "Return a short numbered plan (max 5 steps). "
            "Prefer concrete browser/HAR/vision actions."
        )
        prompt = (
            f"GOAL: {state.get('goal')}\n"
            f"HAR: {state.get('har_summary') or '(none)'}\n"
            "Write the plan."
        )
        resp = self.router.complete(prompt, role="plan", system=system)
        state["plan"] = resp.text if resp.ok else f"(plan failed: {resp.error})"
        state["model_used"] = resp.model or state.get("model_used") or ""
        state.setdefault("observations", []).append(f"plan@{resp.provider}: {state['plan'][:200]}")
        return state

    def node_vision(self, state: AgentGraphState) -> AgentGraphState:
        if state.get("role") != "vision":
            return state
        image = None
        # Allow image path embedded as IMAGE:/path in goal
        goal = state.get("goal") or ""
        if "IMAGE:" in goal:
            image = goal.split("IMAGE:", 1)[1].strip().split()[0]
        resp = self.router.complete(
            f"Analyze for goal: {goal}",
            role="vision",
            image_path=image,
            system="You are a vision node. Describe detections relevant to the goal.",
        )
        structured = resp.structured or {"text": resp.text, "error": resp.error}
        state["vision_result"] = structured
        state.setdefault("observations", []).append(
            f"vision@{resp.provider}: {(resp.text or resp.error or '')[:200]}"
        )
        if resp.model:
            state["model_used"] = resp.model
        return state

    def node_act(self, state: AgentGraphState) -> AgentGraphState:
        state["step"] = int(state.get("step") or 0) + 1
        if not self.tool_executor:
            state.setdefault("observations", []).append("act: no tool_executor bound")
            return state

        system = (
            "You choose ONE tool call as JSON: "
            '{"tool":"<name>","args":{...}} '
            "Available conceptual tools: browser_navigate, browser_get_content, "
            "har_start, har_stop, har_save, har_analyze, har_apis, finish. "
            "If done, use tool=finish with args.answer."
        )
        obs = "\n".join((state.get("observations") or [])[-6:])
        prompt = (
            f"GOAL: {state.get('goal')}\nPLAN:\n{state.get('plan')}\n"
            f"OBS:\n{obs}\n"
            f"STEP {state.get('step')}/{state.get('max_steps')}\n"
            "Reply with JSON only."
        )
        resp = self.router.complete(prompt, role="chat", system=system)
        tool_name = "finish"
        args: Dict[str, Any] = {"answer": resp.text}
        raw = (resp.text or "").strip()
        try:
            # extract first JSON object
            start = raw.find("{")
            end = raw.rfind("}")
            if start >= 0 and end > start:
                parsed = json.loads(raw[start : end + 1])
                tool_name = parsed.get("tool") or tool_name
                args = parsed.get("args") or args
        except Exception:
            pass

        result = self.tool_executor(tool_name, args)
        state.setdefault("tool_calls", []).append(
            {"tool": tool_name, "args": args, "result": result}
        )
        state.setdefault("observations", []).append(
            f"tool {tool_name}: {str(result)[:240]}"
        )
        if tool_name == "finish" or result.get("done"):
            state["done"] = True
            state["answer"] = (
                args.get("answer")
                or result.get("answer")
                or result.get("summary")
                or raw
            )
        return state

    def node_synthesize(self, state: AgentGraphState) -> AgentGraphState:
        if state.get("answer"):
            return state
        system = "Synthesize a concise final answer for the user from observations."
        obs = "\n".join((state.get("observations") or [])[-10:])
        prompt = f"GOAL: {state.get('goal')}\nOBS:\n{obs}\nAnswer:"
        resp = self.router.complete(prompt, role="extract", system=system)
        state["answer"] = resp.text if resp.ok else (resp.error or "no answer")
        if resp.model:
            state["model_used"] = resp.model
        state["done"] = True
        return state

    def _should_continue(self, state: AgentGraphState) -> str:
        if state.get("done"):
            return "synthesize"
        if int(state.get("step") or 0) >= int(state.get("max_steps") or 6):
            return "synthesize"
        return "act"

    def _build_langgraph(self):
        assert StateGraph is not None
        g = StateGraph(dict)
        g.add_node("route", self.node_route)
        g.add_node("plan", self.node_plan)
        g.add_node("vision", self.node_vision)
        g.add_node("act", self.node_act)
        g.add_node("synthesize", self.node_synthesize)
        g.set_entry_point("route")
        g.add_edge("route", "plan")
        g.add_edge("plan", "vision")
        g.add_conditional_edges(
            "vision",
            self._should_continue,
            {"act": "act", "synthesize": "synthesize"},
        )
        g.add_conditional_edges(
            "act",
            self._should_continue,
            {"act": "act", "synthesize": "synthesize"},
        )
        g.add_edge("synthesize", END)
        return g.compile()

    def run(
        self,
        goal: str,
        *,
        har_summary: str = "",
        max_steps: int = 6,
        initial: Optional[Dict[str, Any]] = None,
    ) -> AgentGraphState:
        state: AgentGraphState = {
            "goal": goal,
            "har_summary": har_summary,
            "observations": [],
            "tool_calls": [],
            "step": 0,
            "max_steps": max_steps,
            "done": False,
        }
        if initial:
            state.update(initial)  # type: ignore[arg-type]

        if self._compiled is not None:
            try:
                out = self._compiled.invoke(state)
                return out  # type: ignore[return-value]
            except Exception:
                logger.exception("LangGraph invoke failed; using fallback")

        return self._run_fallback(state)

    def _run_fallback(self, state: AgentGraphState) -> AgentGraphState:
        state = self.node_route(state)
        state = self.node_plan(state)
        state = self.node_vision(state)
        while not state.get("done") and int(state.get("step") or 0) < int(
            state.get("max_steps") or 6
        ):
            nxt = self._should_continue(state)
            if nxt == "synthesize":
                break
            state = self.node_act(state)
        state = self.node_synthesize(state)
        return state


def langgraph_available() -> bool:
    return _HAS_LANGGRAPH
