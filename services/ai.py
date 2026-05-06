from models import AiSettings, AiProvider

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
