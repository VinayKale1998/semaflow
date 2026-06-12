# SemaFlow Stage 5, Piece 2: LangGraph Orchestrator

## Goal
Build `app/orchestrator/graph.py`. A LangGraph StateGraph that takes a 
query, runs the router, then executes the SQL node, RAG retriever, or 
both based on the route. Returns raw results. NO synthesis yet. NO 
reviewer yet.

## First step: inspect what already exists
Before writing any new code, read these files and tell me their public 
interface:
- `app/sql/node.py` (Stage 3 text-to-SQL entry point)
- `app/rag/retriever.py` (Stage 4 hybrid retriever)

Specifically: what function or method do I call, what does it take, 
what does it return? Show me a brief interface summary before building 
anything that depends on them.

## Dependencies
```bash
python -m pip install langgraph langsmith
```

LangSmith is for tracing. Set these env vars in .env if not already there: