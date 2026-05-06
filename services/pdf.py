from pathlib import Path
from datetime import timedelta
from jinja2 import Environment, FileSystemLoader
import weasyprint

BASE_DIR = Path(__file__).parent.parent
TEMPLATES_DIR = BASE_DIR / "templates"
BRAND_DIR = BASE_DIR / "static" / "brand"
PDF_DIR = BASE_DIR / "generated_pdfs"

PDF_DIR.mkdir(exist_ok=True)

_DE_MONTHS = [
    "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember",
]


def _format_date_de(dt):
    if not dt:
        return "—"
    return f"{dt.day:02d}. {_DE_MONTHS[dt.month - 1]} {dt.year}"


def _format_eur(value):
    if value is None:
        return "—"
    try:
        n = int(float(value))
        formatted = f"{n:,}".replace(",", ".")
        return f"{formatted} €"
    except (ValueError, TypeError):
        return "—"


def _make_env() -> Environment:
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))
    env.filters["date_de"] = _format_date_de
    env.filters["eur"] = _format_eur
    return env


def render_proposal_html(proposal, lead, for_print: bool = True) -> str:
    env = _make_env()
    template = env.get_template("proposals/document.html")
    asset_base = BRAND_DIR.as_uri() if for_print else "/static/brand"
    return template.render(
        proposal=proposal,
        lead=lead,
        asset_base=asset_base,
        timedelta=timedelta,
    )


def generate_proposal_pdf(proposal, lead) -> Path:
    html_string = render_proposal_html(proposal, lead, for_print=True)
    out_path = PDF_DIR / f"{proposal.number}.pdf"
    weasyprint.HTML(
        string=html_string,
        base_url=str(BRAND_DIR) + "/",
    ).write_pdf(str(out_path))
    return out_path
