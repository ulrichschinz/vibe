"""app.core.ai — Anthropic adapter + prompt registry (Scaling-roadmap Schritt 6).

The Anthropic client, model selection from ``AiSettings``, the hardcoded
system prompts and the two fragile response parsers (the ``===MARKER===``
proposal-draft format and the LinkedIn ``<json>`` block) are moved here
**verbatim** from ``services/ai.py`` + ``services/linkedin_import.py`` — no
robustness fix in this step (separate later item; see ARCHITECTURE.md
Struktur-Schuld 6). "Keine Verhaltensänderung" — prompts and parsing are
byte-for-byte the originals.

AI is a *capability*, not a domain: orchestration (draft-merge, planning,
LinkedIn-import flow) stays in the owning domain's service
(``app.domains.proposals.service`` / ``app.domains.leads.service``); only the
adapter lives here. Contract-conformant: imports ``app.core.*`` only — never
``app.domains.*`` / ``app.interfaces.*`` (core knows no domain).

The legacy module ``services/linkedin_import.py`` remains as a thin
re-export shim so the frozen Schritt-0.5 characterization tests
(``monkeypatch.setattr(services.linkedin_import, "extract_lead_from_pdf",
…)``) keep intercepting through the same module object until they retire
(T7-C lifecycle). ``services/ai.py`` died in T7-B (ADR-015).
"""

from __future__ import annotations

import base64
import json
import re

from app.core.ai_settings import AiProvider, AiSettings


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
        client_info = " / ".join(
            filter(None, [context.get("lead_name"), context.get("lead_company")])
        )
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
    return message.content[0].text  # type: ignore[union-attr,no-any-return]


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
    return resp.content[0].text  # type: ignore[union-attr,no-any-return]


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
            {
                "id": "strategy",
                "description": sections.get("strategy_description", ""),
                "deliverables": to_list(sections.get("strategy_deliverables", "")),
            },
            {
                "id": "change",
                "description": sections.get("change_description", ""),
                "deliverables": to_list(sections.get("change_deliverables", "")),
            },
            {
                "id": "tech",
                "description": sections.get("tech_description", ""),
                "deliverables": to_list(sections.get("tech_deliverables", "")),
            },
        ],
    }


# ── LinkedIn-PDF → Lead extraction (adapter; orchestration in leads.service) ──


class LinkedInImportError(Exception):
    """Raised when extracting lead data from a LinkedIn PDF fails."""


SYSTEM_PROMPT = (
    "Du bist ein erfahrener B2B-Sales-Researcher für Agentic Reach, eine "
    "deutsche KI-Beratung (Strategie, Change-Management, Tech-Implementierung). "
    "Du bekommst ein LinkedIn-Profil als PDF und erstellst eine "
    "Account-Bewertung für den Vertrieb — vor dem Erstkontakt.\n\n"
    "WICHTIG: Wir suchen Käufer, keine Kandidaten. Die zentrale Frage lautet: "
    "Ist diese Firma ein guter potenzieller Kunde — und ist diese Person der "
    "richtige Hebel (Decision-Maker, Influencer, Champion)?\n\n"
    "Antworte AUSSCHLIESSLICH mit einem einzigen <json>...</json>-Block. "
    "Kein Text davor, kein Text danach, keine Markdown-Codefence.\n\n"
    "Format:\n"
    "<json>\n"
    "{\n"
    '  "name": "Vorname Nachname",\n'
    '  "company": "Aktuelle Firma",\n'
    '  "salutation": "Frau" oder "Herr" oder "",\n'
    '  "email": "" (LinkedIn-PDFs enthalten i. d. R. keine E-Mail),\n'
    '  "phone": "" (analog),\n'
    '  "company_summary": "1-2 Sätze: Branche, Größe (falls erkennbar), Phase (Wachstum/Konsolidierung/Restrukturierung), Geo. Faktisch, kein Marketing.",\n'
    '  "buying_signals": "3-5 Bullets als String mit \\n getrennt: konkrete Hinweise auf Kauf-/Beratungsbedarf — frische Rolle (Kaufzeitfenster!), Internationalisierung, M&A, Wachstum, regulatorischer Druck, sichtbare Pain-Indikatoren. Spekulative Punkte mit \\"evtl.\\" kennzeichnen.",\n'
    '  "decision_role": "1 Satz: Decision-Maker / Influencer / Champion / Gatekeeper? Begründet aus Titel und Karriereverlauf.",\n'
    '  "agentic_reach_fit": "1-2 Sätze: Welche Agentic-Reach-Leistung (Strategie / Change / Tech) passt warum? Konkreter Aufhänger fürs Erstgespräch.",\n'
    '  "ai_readiness_level": "high" oder "medium" oder "low",\n'
    '  "ai_readiness_reason": "1 Satz: Worauf basiert die Einstufung? Bezogen auf die FIRMA, nicht die Person.",\n'
    '  "bant_authority": "yes" oder "open" oder "no",\n'
    '  "bant_need": "yes" oder "open" oder "no" oder "",\n'
    '  "career_highlights": "3-5 Bullets als String mit \\n getrennt, Format: Firma · Rolle · Zeitraum. Knapp, kein Roman.",\n'
    '  "pain_points": "1-2 Sätze: konkreter Sales-Aufhänger fürs Erstgespräch. Hypothese OK, mit \\"vermutlich\\"/\\"evtl.\\" kennzeichnen wenn spekulativ."\n'
    "}\n"
    "</json>\n\n"
    "Mapping-Regeln:\n"
    '- bant_authority: CEO/CFO/CIO/CTO/Inhaber/Geschäftsführer → "yes". '
    'Direktor/Bereichsleiter/Head of/VP → "open". Manager/Senior/Junior/Praktikant → "no".\n'
    '- bant_need: "yes" nur wenn Profil aktive Initiativen, klare Pain-Indikatoren oder explizites KI-/Digital-Engagement zeigt. '
    '"open" wenn plausibel aber nicht belegt. "no" wenn Branche/Rolle KI-fern. "" wenn unklar.\n'
    '- ai_readiness_level: bezogen auf die FIRMA. "high" = Tech/Daten-getrieben mit etablierter Digitalkultur. '
    '"medium" = Mittelstand mit punktuellen Digital-Initiativen. "low" = klassisches Gewerbe ohne sichtbare Digital-Spur.\n'
    '- Wenn ein Feld nicht erkennbar ist: leerer String "". Niemals null.\n'
    "- Anrede nur setzen, wenn aus Vornamen eindeutig.\n"
    "- Bullet-Strings (buying_signals, career_highlights): einzelner JSON-String mit \\n als Trenner, ohne führende Bulletzeichen."
)


_JSON_BLOCK_RE = re.compile(r"<json>\s*(\{.*?\})\s*</json>", re.DOTALL)
_EXPECTED_KEYS = (
    "name",
    "company",
    "salutation",
    "email",
    "phone",
    "company_summary",
    "buying_signals",
    "decision_role",
    "agentic_reach_fit",
    "ai_readiness_level",
    "ai_readiness_reason",
    "bant_authority",
    "bant_need",
    "career_highlights",
    "pain_points",
)


def extract_lead_from_pdf(pdf_bytes: bytes, why_good: str, settings: AiSettings) -> dict:
    """Send PDF to Claude, parse and return extracted fields as a flat dict."""
    if not pdf_bytes:
        raise LinkedInImportError("Leeres PDF.")
    if settings.provider != AiProvider.anthropic:
        raise LinkedInImportError(f"Unbekannter Provider: {settings.provider}")

    user_text = (
        "Hier ist das LinkedIn-Profil als PDF. Erstelle die Account-Bewertung "
        "wie im System-Prompt beschrieben."
    )
    if why_good.strip():
        user_text += (
            "\n\nKontext vom Vertrieb (warum dieser Lead interessant ist):\n"
            f"{why_good.strip()}\n\n"
            "Beziehe diesen Kontext bei buying_signals, agentic_reach_fit und "
            "pain_points mit ein, falls passend."
        )

    import anthropic

    client = anthropic.Anthropic(api_key=settings.api_key)

    try:
        message = client.messages.create(
            model=settings.model,
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "document",
                            "source": {
                                "type": "base64",
                                "media_type": "application/pdf",
                                "data": base64.b64encode(pdf_bytes).decode("ascii"),
                            },
                        },
                        {"type": "text", "text": user_text},
                    ],
                }
            ],
        )
    except anthropic.APIError as e:
        raise LinkedInImportError(f"KI-Anfrage fehlgeschlagen: {e}") from e

    text_parts = [
        b.text  # type: ignore[union-attr]
        for b in message.content
        if getattr(b, "type", None) == "text"
    ]
    return _parse_json_block("\n".join(text_parts))


def _parse_json_block(text: str) -> dict:
    m = _JSON_BLOCK_RE.search(text)
    if not m:
        raise LinkedInImportError("KI-Antwort enthält keinen <json>-Block.")
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError as e:
        raise LinkedInImportError(f"KI-Antwort ist kein gültiges JSON: {e}") from e
    if not isinstance(data, dict):
        raise LinkedInImportError("KI-Antwort ist kein JSON-Objekt.")
    return {k: str(data.get(k) or "").strip() for k in _EXPECTED_KEYS}
