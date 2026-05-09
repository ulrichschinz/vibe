import re

from models import AiSettings, AiProvider


class AiDraftError(Exception):
    """Raised when generating proposal drafts from a planning chat fails."""


PROPOSAL_DRAFTS_SYSTEM = (
    "Du bist Texter für Agentic Reach (KI-Beratung). Aus dem folgenden "
    "Planungs-Chat erstellst du jetzt einen Angebots-Entwurf mit GENAU "
    "folgender Struktur (Trennzeichen exakt einhalten):\n\n"
    "===INTRO===\n"
    "<3-4 Sätze persönliches Anschreiben für ein B2B-Angebot. Fließtext, "
    "kein 'Sehr geehrte', keine Überschrift, kein Betreff.>\n"
    "===STRATEGY_DESCRIPTION===\n"
    "<2-3 Sätze: was Agentic Reach im Bereich Strategie & Consulting für "
    "diesen Kunden konkret macht. Wenn aus dem Chat nicht relevant: kurze "
    "generische Beschreibung des Bereichs.>\n"
    "===STRATEGY_DELIVERABLES===\n"
    "<3-5 Stichpunkte, eine pro Zeile, OHNE Bulletzeichen oder Bindestriche>\n"
    "===CHANGE_DESCRIPTION===\n<analog>\n"
    "===CHANGE_DELIVERABLES===\n<analog>\n"
    "===TECH_DESCRIPTION===\n<analog>\n"
    "===TECH_DELIVERABLES===\n<analog>\n\n"
    "Halte dich strikt an dieses Format. Keine zusätzlichen Sections, "
    "keine ===-Marker im Text. Schreib auf Deutsch."
)


SYSTEM_PROMPTS = {
    "intro_text": (
        "Du bist Texter für Agentic Reach, ein KI-Beratungsunternehmen. "
        "Schreibe einen professionellen, persönlichen Einleitungstext für ein Angebot. "
        "Ton: vertrauensvoll, kompetent, nicht zu formell. "
        "Nur Fließtext, keine Überschrift. Ca. 3–4 Sätze. Kein Betreff, kein 'Sehr geehrte/r'."
    ),
    "service_description": (
        "Du bist Texter für Agentic Reach, ein KI-Beratungsunternehmen. "
        "Schreibe eine prägnante Beschreibung (2–3 Sätze) für den angegebenen Leistungsbereich "
        "in einem B2B-Angebot. Klar, nutzenorientiert, kein Fachjargon."
    ),
    "service_deliverables": (
        "Du bist Texter für Agentic Reach. "
        "Formuliere Deliverables für den angegebenen Leistungsbereich als knappe, klare Stichpunkte. "
        "Eine pro Zeile, ohne Bulletzeichen oder Bindestriche. Maximal 4 Punkte."
    ),
    "payment_terms": (
        "Formuliere Zahlungsmodalitäten für ein B2B-Beratungsangebot professionell und knapp. "
        "Nur den Text, keine Einleitung, kein Satzanfang wie 'Die Zahlungsmodalitäten lauten:'."
    ),
}


def generate_text(field: str, notes: str, context: dict, settings: AiSettings) -> str:
    system = SYSTEM_PROMPTS.get(field, SYSTEM_PROMPTS["intro_text"])

    parts = []
    if context.get("lead_name") or context.get("lead_company"):
        client_info = " / ".join(filter(None, [context.get("lead_name"), context.get("lead_company")]))
        parts.append(f"Kunde: {client_info}")
    if context.get("proposal_title"):
        parts.append(f"Angebots-Titel: {context['proposal_title']}")
    if context.get("service_title"):
        parts.append(f"Leistungsbereich: {context['service_title']}")
    if notes.strip():
        parts.append(f"Stichpunkte / Kontext:\n{notes.strip()}")

    user_content = "\n".join(parts)

    if settings.provider == AiProvider.anthropic:
        return _call_anthropic(system, user_content, settings)

    raise ValueError(f"Unbekannter Provider: {settings.provider}")


def _call_anthropic(system: str, user_content: str, settings: AiSettings) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=settings.api_key)
    message = client.messages.create(
        model=settings.model,
        max_tokens=1024,
        system=system,
        messages=[{"role": "user", "content": user_content}],
    )
    return message.content[0].text


def chat_with_context(messages: list, system: str, settings: AiSettings) -> str:
    """Multi-turn chat. messages = [{"role": "user"|"assistant", "content": str}]"""
    import anthropic
    client = anthropic.Anthropic(api_key=settings.api_key)
    resp = client.messages.create(
        model=settings.model,
        max_tokens=2048,
        system=system,
        messages=messages,
    )
    return resp.content[0].text


def _parse_proposal_drafts(text: str) -> dict:
    """Parse the trennzeichen-formatted LLM output into intro + 3 service blocks.

    Missing sections fall back to empty defaults so a partial answer never
    collapses the UI.
    """
    sections: dict[str, str] = {}
    for m in re.finditer(r"===(\w+)===\s*\n(.*?)(?=\n===\w+===|\Z)", text, re.DOTALL):
        sections[m.group(1).lower()] = m.group(2).strip()

    def to_list(s: str) -> list[str]:
        return [ln.strip() for ln in s.splitlines() if ln.strip()]

    return {
        "intro": sections.get("intro", ""),
        "services": [
            {"id": "strategy",
             "description": sections.get("strategy_description", ""),
             "deliverables": to_list(sections.get("strategy_deliverables", ""))},
            {"id": "change",
             "description": sections.get("change_description", ""),
             "deliverables": to_list(sections.get("change_deliverables", ""))},
            {"id": "tech",
             "description": sections.get("tech_description", ""),
             "deliverables": to_list(sections.get("tech_deliverables", ""))},
        ],
    }


def generate_proposal_drafts(lead, planning_messages, settings: AiSettings) -> dict:
    """Single Anthropic call → parsed dict {intro, services:[3 blocks]}.

    Raises AiDraftError when there is no chat to draw from.
    """
    if not planning_messages:
        raise AiDraftError("Kein Chat-Verlauf vorhanden.")
    messages = [{"role": m.role, "content": m.content} for m in planning_messages]
    messages.append({"role": "user", "content": (
        "Erstelle jetzt den Angebots-Entwurf wie im System-Prompt vorgegeben. "
        f"Kunde: {lead.name or '—'} / {lead.company or '—'}."
    )})
    text = chat_with_context(messages, PROPOSAL_DRAFTS_SYSTEM, settings)
    return _parse_proposal_drafts(text)
