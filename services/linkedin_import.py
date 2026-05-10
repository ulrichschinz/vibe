"""Extract a B2B-sales-oriented account assessment from a LinkedIn profile PDF.

The PDF is forwarded as an Anthropic document content block — no local text
extraction. Claude returns a single ``<json>...</json>`` block which we parse
into a flat dict of strings. Missing keys default to ``""``.

The Lead is treated as a *buyer*, not a candidate: the goal is to assess the
company's fit for Agentic Reach (AI consulting) and the person's role as a
decision-maker / influencer. The route handler composes the human-readable
notes block from these structured fields.
"""

import base64
import json
import re

from models import AiSettings, AiProvider


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
    "- bant_authority: CEO/CFO/CIO/CTO/Inhaber/Geschäftsführer → \"yes\". "
    "Direktor/Bereichsleiter/Head of/VP → \"open\". Manager/Senior/Junior/Praktikant → \"no\".\n"
    "- bant_need: \"yes\" nur wenn Profil aktive Initiativen, klare Pain-Indikatoren oder explizites KI-/Digital-Engagement zeigt. "
    "\"open\" wenn plausibel aber nicht belegt. \"no\" wenn Branche/Rolle KI-fern. \"\" wenn unklar.\n"
    "- ai_readiness_level: bezogen auf die FIRMA. \"high\" = Tech/Daten-getrieben mit etablierter Digitalkultur. "
    "\"medium\" = Mittelstand mit punktuellen Digital-Initiativen. \"low\" = klassisches Gewerbe ohne sichtbare Digital-Spur.\n"
    "- Wenn ein Feld nicht erkennbar ist: leerer String \"\". Niemals null.\n"
    "- Anrede nur setzen, wenn aus Vornamen eindeutig.\n"
    "- Bullet-Strings (buying_signals, career_highlights): einzelner JSON-String mit \\n als Trenner, ohne führende Bulletzeichen."
)


_JSON_BLOCK_RE = re.compile(r"<json>\s*(\{.*?\})\s*</json>", re.DOTALL)
_EXPECTED_KEYS = (
    "name", "company", "salutation", "email", "phone",
    "company_summary", "buying_signals", "decision_role", "agentic_reach_fit",
    "ai_readiness_level", "ai_readiness_reason",
    "bant_authority", "bant_need",
    "career_highlights", "pain_points",
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
            messages=[{
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
            }],
        )
    except anthropic.APIError as e:
        raise LinkedInImportError(f"KI-Anfrage fehlgeschlagen: {e}") from e

    text_parts = [b.text for b in message.content if getattr(b, "type", None) == "text"]
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
