"""Text and PDF document adapter for TrustLayers (T²).

Extracts plain text, PDF page layout, PDF metadata forensics,
and page-referenced evidence items.
"""

from pathlib import Path
from typing import Tuple, List, Dict, Any, Optional

try:
    import fitz  # PyMuPDF
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False

from models.schemas import Artifact, EvidenceItem, EvidenceRef
from core.reliability import compute_reliability_score
from ingest.limits import validate_pdf_pages
from core.config import STRENGTH_CLASS_WEIGHTS


def analyze_text_file(artifact: Artifact, file_path: Path) -> Tuple[Artifact, List[EvidenceItem]]:
    """Analyze plain text artifact."""
    evidence_list: List[EvidenceItem] = []
    metadata = dict(artifact.metadata)

    try:
        text_content = file_path.read_text(encoding="utf-8", errors="replace")
        char_count = len(text_content)
        metadata["char_count"] = char_count
        metadata["text_content"] = text_content[:5000]  # Store preview in metadata

        # Quality profiling for text (longer clean text = higher reliability score)
        norm_len = min(1.0, char_count / 1000.0)
        reliability = compute_reliability_score(
            resolution=round(norm_len, 4),
            compression=1.0,
            noise=1.0,
        )

        art_dict = artifact.model_dump()
        art_dict["status"] = "ok"
        art_dict["metadata"] = metadata
        art_dict["reliability"] = reliability
        art_dict["evidence"] = evidence_list
        return Artifact(**art_dict), evidence_list

    except Exception as err:
        art_dict = artifact.model_dump()
        art_dict["status"] = "degraded"
        art_dict["error_code"] = "PREPROCESS_FAILED"
        art_dict["metadata"]["error"] = str(err)
        return Artifact(**art_dict), []


def analyze_pdf_document(artifact: Artifact, file_path: Path) -> Tuple[Artifact, List[EvidenceItem]]:
    """Analyze PDF document artifact using PyMuPDF."""
    if not HAS_PYMUPDF:
        art_dict = artifact.model_dump()
        art_dict["status"] = "degraded"
        art_dict["error_code"] = "DETECTOR_UNAVAILABLE"
        art_dict["metadata"]["error"] = "PyMuPDF package (fitz) is not installed."
        return Artifact(**art_dict), []

    evidence_list: List[EvidenceItem] = []
    metadata = dict(artifact.metadata)

    try:
        doc = fitz.open(file_path)
        page_count = len(doc)
        validate_pdf_pages(page_count, artifact.display_name)

        metadata["page_count"] = page_count

        # Extract PDF metadata properties (Producer, Creator, Title)
        pdf_meta = doc.metadata or {}
        metadata["pdf_metadata"] = pdf_meta

        creator = str(pdf_meta.get("creator", "")).lower()
        producer = str(pdf_meta.get("producer", "")).lower()

        if any(tool in creator or tool in producer for tool in ("canva", "photoshop", "illustrator", "inkscape")):
            ev = EvidenceItem(
                id=f"ev_pdf_creator_{artifact.id}",
                artifact_ids=[artifact.id],
                direction="manipulated",
                strength=STRENGTH_CLASS_WEIGHTS["weak"],  # Provenance anomaly (R-ML-05)
                reliability=0.8,
                scope="artifact",
                evidence_ref=EvidenceRef(type="page", value="metadata"),
                description=f"PDF metadata indicates creation by graphic design software: {pdf_meta.get('producer') or pdf_meta.get('creator')}",
                source="forensic",
                check_id="CHK_TXT_PDF_PROVENANCE",
            )
            evidence_list.append(ev)

        # Extract page texts
        pages_text: List[Dict[str, Any]] = []
        full_text_list: List[str] = []
        for page_num in range(page_count):
            page = doc[page_num]
            text = page.get_text("text")
            full_text_list.append(text)
            pages_text.append({"page": page_num + 1, "text": text})

        metadata["pages_text"] = pages_text
        metadata["text_content"] = "\n\n".join(full_text_list)[:10000]

        doc.close()

        # Reliability profiling for PDF
        reliability = compute_reliability_score(
            resolution=1.0 if page_count > 0 else 0.2,
            compression=0.9,
            noise=0.9,
        )

        art_dict = artifact.model_dump()
        art_dict["status"] = "ok"
        art_dict["metadata"] = metadata
        art_dict["reliability"] = reliability
        art_dict["evidence"] = evidence_list
        return Artifact(**art_dict), evidence_list

    except Exception as err:
        art_dict = artifact.model_dump()
        art_dict["status"] = "degraded"
        art_dict["error_code"] = "PREPROCESS_FAILED"
        art_dict["metadata"]["error"] = str(err)
        return Artifact(**art_dict), []
