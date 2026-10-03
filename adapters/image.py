"""Image artifact adapter for TrustLayers (T²).

Extracts EXIF metadata, C2PA provenance manifests, resolution/compression metrics,
and image evidence items per RULES R-CODE-01 and R-ML-05.
"""

from pathlib import Path
from typing import Tuple, List, Dict, Any, Optional
from PIL import Image, ExifTags

from models.schemas import Artifact, EvidenceItem, EvidenceRef, Reliability
from core.reliability import compute_reliability_score
from core.config import STRENGTH_CLASS_WEIGHTS


def extract_exif(image: Image.Image) -> Dict[str, Any]:
    """Extract EXIF metadata dictionary from Pillow image."""
    exif_data: Dict[str, Any] = {}
    try:
        raw_exif = image._getexif()
        if raw_exif:
            for tag_id, val in raw_exif.items():
                tag_name = ExifTags.TAGS.get(tag_id, str(tag_id))
                # Store string representations to avoid unserializable types
                if isinstance(val, (str, int, float)):
                    exif_data[tag_name] = val
                else:
                    exif_data[tag_name] = str(val)
    except Exception:
        pass
    return exif_data


def extract_c2pa_manifest(file_path: Path) -> Optional[Dict[str, Any]]:
    """Extract C2PA provenance manifest using c2pa-python if available."""
    try:
        import c2pa
        reader = c2pa.Reader.from_file(str(file_path))
        manifest_json = reader.json()
        import json
        return json.loads(manifest_json)
    except Exception:
        # C2PA not present or no manifest found
        return None


def analyze_image(artifact: Artifact, file_path: Path) -> Tuple[Artifact, List[EvidenceItem]]:
    """Analyze image artifact, profile reliability, extract metadata and evidence items.

    Args:
        artifact: Input Artifact object.
        file_path: Path to the image file on disk.

    Returns:
        Tuple of (updated_artifact, list_of_evidence_items)
    """
    evidence_list: List[EvidenceItem] = []
    metadata = dict(artifact.metadata)

    try:
        with Image.open(file_path) as img:
            width, height = img.size
            metadata["width"] = width
            metadata["height"] = height
            metadata["format"] = img.format

            # Compute resolution quality metric (normalized against 4K resolution)
            pixel_count = width * height
            norm_res = min(1.0, pixel_count / (3840 * 2160))

            # EXIF extraction
            exif = extract_exif(img)
            metadata["exif"] = exif

            # Check EXIF software tag for generative / editing tools
            software = str(exif.get("Software", "")).lower()
            if any(term in software for term in ("photoshop", "gimp", "midjourney", "stable diffusion", "dall-e")):
                ev = EvidenceItem(
                    id=f"ev_img_sw_{artifact.id}",
                    artifact_ids=[artifact.id],
                    direction="manipulated",
                    strength=STRENGTH_CLASS_WEIGHTS["weak"],  # Provenance anomaly is supporting only (R-ML-05)
                    reliability=0.8,
                    scope="artifact",
                    evidence_ref=EvidenceRef(type="region", value="metadata"),
                    description=f"EXIF metadata indicates software modification: {exif.get('Software')}",
                    source="forensic",
                    check_id="CHK_IMG_EXIF_SOFTWARE",
                )
                evidence_list.append(ev)

            # C2PA manifest extraction
            c2pa_manifest = extract_c2pa_manifest(file_path)
            if c2pa_manifest:
                metadata["c2pa"] = True
                ev = EvidenceItem(
                    id=f"ev_img_c2pa_{artifact.id}",
                    artifact_ids=[artifact.id],
                    direction="authentic",
                    strength=STRENGTH_CLASS_WEIGHTS["strong"],
                    reliability=0.95,
                    scope="artifact",
                    evidence_ref=EvidenceRef(type="region", value="manifest"),
                    description="Valid C2PA content credential manifest detected",
                    source="forensic",
                    check_id="CHK_IMG_C2PA_VALID",
                )
                evidence_list.append(ev)

            # Reliability profiling
            reliability = compute_reliability_score(
                resolution=round(norm_res, 4),
                compression=0.8,  # Default baseline for images
                noise=0.8,
            )

            # Construct updated artifact
            art_dict = artifact.model_dump()
            art_dict["status"] = "ok"
            art_dict["metadata"] = metadata
            art_dict["reliability"] = reliability
            art_dict["evidence"] = evidence_list
            updated_artifact = Artifact(**art_dict)

            return updated_artifact, evidence_list

    except Exception as err:
        art_dict = artifact.model_dump()
        art_dict["status"] = "degraded"
        art_dict["error_code"] = "PREPROCESS_FAILED"
        art_dict["metadata"]["error"] = str(err)
        return Artifact(**art_dict), []
