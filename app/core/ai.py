"""app.core.ai — Anthropic adapter + prompt registry (placeholder).

Soll (Schritt 6): the Anthropic client, model selection from `AiSettings`,
the hardcoded system prompts and the fragile `===MARKER===` parsing move
here **verbatim** from `services/ai.py` — no robustness fix in that step
(separate later item; see ARCHITECTURE.md Struktur-Schuld 6). AI is a
*capability*, not a domain: orchestration (draft-merge, planning) stays in
the owning domain's service (proposals, leads); only the adapter lives
here. Empty by design in Schritt 2.
"""
