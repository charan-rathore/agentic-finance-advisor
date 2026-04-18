# Archive: Historical Design Documents

This folder contains the evolution of the multi-agent finance advisor's planning documents. These files are preserved for historical reference and to help understand design decisions, but **the canonical architecture documentation is now [`../ARCHITECTURE.md`](../ARCHITECTURE.md)**.

## Contents

| File | Date | Description | Status |
|------|------|-------------|---------|
| [`multi-agent-finance-cursor-plan-v2.md`](multi-agent-finance-cursor-plan-v2.md) | 2026-04-11 | 67 KB execution plan, v1→v2 refactor | Superseded |
| [`multi-agent-finance-cursor-plan-v3.md`](multi-agent-finance-cursor-plan-v3.md) | 2026-04-11 | 82 KB execution plan, v2→v3 LLM Wiki | **Reference** |
| [`deep-research-report.md`](deep-research-report.md) | 2026-04-11 | 27 KB research summary | Superseded |

**Total:** 175 KB of design history

## What Changed

The **v3** plan document (`multi-agent-finance-cursor-plan-v3.md`) was the final execution guide and contains the most complete architectural thinking. However, it was optimized for step-by-step Cursor execution (2200+ lines with detailed checklists) rather than ongoing reference.

**`docs/ARCHITECTURE.md`** distills the key decisions from v3 into a 5-page reference format:
- System overview diagram  
- Three-agent pipeline responsibilities
- LLM Wiki vs. RAG rationale
- Data flow (raw → wiki → SQLite → UI)
- Operational excellence (health monitoring, error handling)
- Scaling considerations

## Migration Notes

If you're reading the archived plans to understand why something was built a certain way:

1. **Architecture decisions** → See `../ARCHITECTURE.md` first
2. **Implementation details** → `multi-agent-finance-cursor-plan-v3.md` has the full context
3. **Historical alternatives** → `multi-agent-finance-cursor-plan-v2.md` shows the pre-LLM-Wiki approach

The live system as of 2026-04-18 matches the v3 plan with all P0–P2 items complete.