"""Extract structured Lead fields from a LinkedIn profile PDF via Claude.

The PDF is forwarded as an Anthropic document content block — no local text
extraction. Claude returns a single ``<json>...</json>`` block which we parse
into a flat dict of strings. Missing keys default to ``""``.
"""

import base64
import json
import re

from models import AiSettings, AiProvider


class LinkedInImportError(Exception):
    """Raised when extracting lead data from a LinkedIn PDF fails."""


SYSTEM_PROMPT = (
    "Du bist ein Recherche-Assistent für Agentic Reach, eine deutsche KI-Beratung. "
    "Du bekommst ein LinkedIn-Profil als PDF und extrahierst daraus die wichtigsten "
    "Lead-Informationen.\n\n"
    "Antworte AUSSCHLIESSLICH mit einem einzigen <json>...</json>-Block. "
    "Kein Text davor, kein Text danach, keine Markdown-Codefence.\n\n"
    "Format:\n"
    "<json>\n"
    "{\n"
    '  "name": "Vorname Nachname",\n'
    '  "company": "Aktuelle Firma (z. B. \\"finanzen.net Group\\")",\n'
    '  "salutation": "Frau" oder "Herr" oder "",\n'
    '  "email": "" (LinkedIn-PDFs enthalten i. d. R. keine E-Mail),\n'
    '  "phone": "" (analog),\n'
    '  "pain_points": "1-2 Sätze: für welches Problem könnte Agentic Reach (KI-Beratung, Strategie, Change, Tech) bei dieser Person/Firma konkret relevant sein? Konstruktiv, kein Marketing-Sprech.",\n'
    '  "notes_block": "Markdown-Plain-Text mit:\\n• aktuelle Rolle (eine Zeile)\\n• Karriere-Highlights (3-5 Bullets, Format: Firma · Rolle · Zeitraum)\\n• Ausbildung (1-2 Zeilen)\\n• Sprachen (eine Zeile)\\n• LinkedIn-URL (falls im PDF enthalten)"\n'
    "}\n"
    "</json>\n\n"
    "Regeln:\n"
    "- Wenn ein Feld nicht erkennbar ist: leerer String \"\". Niemals null.\n"
    "- Anrede nur setzen, wenn sie aus dem Vornamen eindeutig ist.\n"
    "- notes_block ist ein einzelner JSON-String mit \\n als Zeilenumbruch."
)


_JSON_BLOCK_RE = re.compile(r"<json>\s*(\{.*?\})\s*</json>", re.DOTALL)
_EXPECTED_KEYS = ("name", "company", "salutation", "email", "phone", "pain_points", "notes_block")


def extract_lead_from_pdf(pdf_bytes: bytes, why_good: str, settings: AiSettings) -> dict:
    """Send PDF to Claude, parse and return extracted fields as a flat dict."""
    if not pdf_bytes:
        raise LinkedInImportError("Leeres PDF.")
    if settings.provider != AiProvider.anthropic:
        raise LinkedInImportError(f"Unbekannter Provider: {settings.provider}")

    user_text = "Hier ist das LinkedIn-Profil als PDF. Extrahiere die Lead-Informationen wie im System-Prompt beschrieben."
    if why_good.strip():
        user_text += (
            "\n\nKontext vom Vertrieb (warum dieser Lead interessant ist):\n"
            f"{why_good.strip()}\n\n"
            "Beziehe diesen Kontext bei pain_points mit ein, falls passend."
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
