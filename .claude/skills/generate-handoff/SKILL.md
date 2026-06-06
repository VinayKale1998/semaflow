---
name: generate-handoff
description: Generate a handoff document for continuing in a new chat
---

Generate a handoff document capturing the current SemaFlow build state:
1. Read CLAUDE.md for project context
2. Check which files exist and their completion status in app/sql/
3. Note any failing tests or open TODOs
4. List locked decisions that must not be reopened
5. State the next concrete action for the new session
6. Write the handoff to /semaflow/docs/handoff_latest.md
