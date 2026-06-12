"""Probe: does Streamlit's script thread have a running event loop?

If it does, the orchestrator's asyncio.run(run_sql_pipeline(...)) inside
_run_sql will raise "asyncio.run() cannot be called from a running event
loop". Run headless:

    .venv/bin/python -m streamlit run scripts/probes/streamlit_async_check.py \
        --server.headless true --server.port 8599

Watch the terminal: it prints the verdict on first script run, then you can
ctrl-c. Nothing here imports the heavy orchestrator; it only reproduces the
asyncio.run pattern.
"""
import asyncio

import streamlit as st


async def _trivial() -> str:
    await asyncio.sleep(0)
    return "coroutine ran"


# Is a loop already running on this (script) thread?
try:
    running = asyncio.get_running_loop()
    loop_state = f"RUNNING LOOP PRESENT: {running!r}"
except RuntimeError:
    loop_state = "no running loop on this thread"

# Does the orchestrator's exact pattern work here?
try:
    result = asyncio.run(_trivial())
    run_state = f"asyncio.run OK -> {result}"
except RuntimeError as exc:
    run_state = f"asyncio.run FAILED -> {exc}"

print("=== STREAMLIT ASYNC PROBE ===")
print(loop_state)
print(run_state)
print("=== END PROBE ===")

st.write(loop_state)
st.write(run_state)
