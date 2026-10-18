"""ADK root-cause agent. Tools are bound methods of an RcaToolbox (read-only, templated)."""
from __future__ import annotations

import asyncio
import os
import uuid

from google.adk.agents import LlmAgent
from google.adk.runners import InMemoryRunner
from google.genai import types

from .gemini_common import HTTP_OPTIONS

INSTRUCTION = """You are a casting-plant quality engineer investigating a defect spike flagged by an
SPC p-chart. Find the root cause with evidence, then draft an 8D report.

Method:
1. Call get_process_context to learn the defect, the flagged subgroup and suggested windows.
2. Call get_cards for the part to know the expert's rules for this defect.
3. Compare the defect rate before vs after the spike for each process dimension with
   query_events("rate_by_dim", ...). Use first_seen to find lots or moulds that appeared near
   the spike.
4. Check interactions with query_events("rate_by_mould_lot", ...) on the after window.
5. Rank 1-3 hypotheses. Each must name the exact dimension values you blame (for example
   {"mould_id": "MD-04", "material_lot": "LOT-2409C"}) and cite numbers: counts, rates,
   before/after. Prefer the most specific explanation the data supports; say why simpler
   single-factor explanations are weaker if the data shows that.
6. Call draft_8d once with the hypotheses and all eight sections D1_team..D8_recognition.
   Mark it as a draft for the QC engineer; do not claim actions were already taken.
Never invent numbers that a tool did not return."""


def build_agent(toolbox, model: str) -> LlmAgent:
    return LlmAgent(
        name="senpai_rca",
        model=model,
        description="Finds the root cause of a defect spike and drafts an 8D report.",
        instruction=INSTRUCTION,
        tools=[toolbox.query_events, toolbox.get_cards, toolbox.get_process_context, toolbox.draft_8d],
        generate_content_config=types.GenerateContentConfig(http_options=HTTP_OPTIONS),
    )


async def _run(agent: LlmAgent, prompt: str) -> list:
    runner = InMemoryRunner(agent=agent, app_name="senpaiqc")
    session = await runner.session_service.create_session(app_name="senpaiqc", user_id="qc")
    events = []
    msg = types.Content(role="user", parts=[types.Part(text=prompt)])
    async for ev in runner.run_async(user_id="qc", session_id=session.id, new_message=msg):
        events.append(ev)
    return events


def run_investigation(toolbox, model: str, api_key: str, vertex: tuple[str, str] | None = None) -> dict:
    """Run the agent to completion. Returns usage totals; findings land on the toolbox.
    `vertex=(project, location)` runs the agent's model on Vertex AI instead of the API key."""
    if vertex:
        os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "TRUE"
        os.environ["GOOGLE_CLOUD_PROJECT"], os.environ["GOOGLE_CLOUD_LOCATION"] = vertex
    else:
        os.environ.setdefault("GOOGLE_API_KEY", api_key)
    agent = build_agent(toolbox, model)
    prompt = f"Investigate {toolbox.inv['id']}: {toolbox.inv['defect_name']} spike on {toolbox.inv['part_number']}."
    try:
        asyncio.get_running_loop()
        # Already inside an event loop (FastAPI): run in a fresh loop on a worker thread.
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(1) as ex:
            events = ex.submit(asyncio.run, _run(agent, prompt)).result()
    except RuntimeError:
        events = asyncio.run(_run(agent, prompt))
    tin = tout = 0
    for ev in events:
        um = getattr(ev, "usage_metadata", None)
        if um:
            tin += um.prompt_token_count or 0
            tout += (um.candidates_token_count or 0) + (um.thoughts_token_count or 0)
    return {"input_tokens": tin, "output_tokens": tout, "run_id": uuid.uuid4().hex[:8]}
