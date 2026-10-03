"""HTML report engine service for TrustLayers (T²).

Enforces:
- R-SEC-07: The HTML report escapes all artifact-derived text.
- RPT-001: Self-contained HTML report generated via Jinja2 from case state.
"""

from pathlib import Path
from typing import Optional
from jinja2 import Environment, FileSystemLoader, select_autoescape

from models.schemas import Case
from core.config import BASE_DIR

TEMPLATES_DIR = BASE_DIR / "templates"


def _get_jinja_env() -> Environment:
    """Create Jinja2 environment with strict autoescaping enabled (R-SEC-07)."""
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
    )


def generate_report_html(case: Case) -> str:
    """Render self-contained HTML report for a case session.

    Args:
        case: Case schema instance.

    Returns:
        Rendered HTML string.
    """
    env = _get_jinja_env()
    template = env.get_template("report.html.j2")
    return template.render(case=case)


def save_report_html(case: Case, output_dir: Path) -> Path:
    """Render and save HTML report file to session derived directory.

    Args:
        case: Case schema instance.
        output_dir: Directory where report.html should be saved.

    Returns:
        Path to saved HTML file.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / f"report_{case.id}.html"
    html_content = generate_report_html(case)

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    return report_path
