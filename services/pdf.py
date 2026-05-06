from pathlib import Path
from datetime import timedelta
from jinja2 import Environment, FileSystemLoader
import weasyprint

BASE_DIR = Path(__file__).parent.parent
TEMPLATES_DIR = BASE_DIR / "templates"
BRAND_DIR = BASE_DIR.parent / "brand"
PDF_DIR = BASE_DIR / "generated_pdfs"

PDF_DIR.mkdir(exist_ok=True)


def render_proposal_html(proposal, lead: str = "") -> str:
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))
    template = env.get_template("proposals/document.html")
    return template.render(
        proposal=proposal,
        lead=lead,
        brand_base_url=BRAND_DIR.as_uri(),
        timedelta=timedelta,
    )


def generate_proposal_pdf(proposal, lead) -> Path:
    html_string = render_proposal_html(proposal, lead)
    out_path = PDF_DIR / f"{proposal.number}.pdf"
    weasyprint.HTML(
        string=html_string,
        base_url=str(BRAND_DIR) + "/",
    ).write_pdf(str(out_path))
    return out_path
