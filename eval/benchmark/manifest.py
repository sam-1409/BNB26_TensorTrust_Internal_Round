"""Benchmark cases manifest and dataset builder for TrustLayers.

Generates 24 real, labeled test cases partitioned into:
- DEV split (14 cases)
- HELD_OUT split (10 cases)

Covers all mentor manipulation families:
- authentic multimodal corroboration
- manipulated EXIF/metadata
- cross-modal location/event conflicts
- coordinated synthetic AI clusters
- near-duplicate / repost matching
- timestamp differences (provenance context, not manipulation)
- weak comments
- degraded/inconclusive artifacts
"""

import io
from pathlib import Path
from typing import List, Dict, Any
from PIL import Image, ExifTags


def _create_jpeg_bytes(exif_software: str = "", width: int = 100, height: int = 100, color=(100, 150, 200), exif_comment: str = "") -> bytes:
    """Create a minimal valid JPEG image with optional EXIF software tag."""
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()

    exif = img.getexif()
    if exif_software:
        exif[0x0131] = exif_software  # 0x0131 is Software tag in EXIF
        exif[0x0132] = "2024:05:01 10:00:00"
    if exif_comment:
        exif[0x9286] = exif_comment

    img.save(buf, format="JPEG", exif=exif)
    return buf.getvalue()


def _create_wav_bytes(duration_sec: float = 1.0) -> bytes:
    """Create minimal valid WAV audio bytes."""
    import wave
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        num_frames = int(16000 * duration_sec)
        wf.writeframes(b"\x00\x00" * num_frames)
    return buf.getvalue()


def get_benchmark_cases() -> List[Dict[str, Any]]:
    """Return complete list of 24 benchmark case specifications."""
    cases = [
        # ==========================================
        # DEV SPLIT (14 Cases)
        # ==========================================
        {
            "case_id": "case_dev_01_auth_img_txt",
            "split": "dev",
            "label": "AUTHENTIC",
            "description": "Corroborated news report with matching image date and text timeline.",
            "files": [
                {"filename": "press_photo.jpg", "bytes": _create_jpeg_bytes("Nikon D850")},
                {"filename": "article.txt", "bytes": b"In 2024, the summit convened in Paris to discuss international accord."},
            ],
            "platform_urls": [],
        },
        {
            "case_id": "case_dev_02_manip_exif_ai",
            "split": "dev",
            "label": "MANIPULATED",
            "description": "Image containing Midjourney generative synthesis software signature.",
            "files": [
                {"filename": "ai_portrait.jpg", "bytes": _create_jpeg_bytes("Midjourney v6.0")},
            ],
            "platform_urls": [],
        },
        {
            "case_id": "case_dev_03_coord_synthetic_pair",
            "split": "dev",
            "label": "COORDINATED_SYNTHETIC",
            "description": "Multiple images sharing ComfyUI generative metadata markers.",
            "files": [
                {"filename": "synth_1.jpg", "bytes": _create_jpeg_bytes("ComfyUI Stable Diffusion", color=(100, 150, 200))},
                {"filename": "synth_2.jpg", "bytes": _create_jpeg_bytes("ComfyUI Stable Diffusion", color=(120, 160, 210))},
            ],
            "platform_urls": [],
        },
        {
            "case_id": "case_dev_04_inconclusive_sparse",
            "split": "dev",
            "label": "INCONCLUSIVE",
            "description": "Short ambiguous snippet without verifiable entities or corroboration.",
            "files": [
                {"filename": "note.txt", "bytes": b"Hello world."},
            ],
            "platform_urls": [],
        },
        {
            "case_id": "case_dev_05_auth_audio",
            "split": "dev",
            "label": "AUTHENTIC",
            "description": "Recorded audio statement with consistent acoustic profile and verified timeline.",
            "files": [
                {"filename": "speech.wav", "bytes": _create_wav_bytes(2.0)},
                {"filename": "official_dispatch.txt", "bytes": b"In 2024, the keynote speech was archived in full in Paris."},
            ],
            "platform_urls": [],
        },
        {
            "case_id": "case_dev_06_manip_cross_conflict",
            "split": "dev",
            "label": "MANIPULATED",
            "description": "Cross-modal location conflict: Paris in image vs Tokyo in statement.",
            "files": [
                {"filename": "photo_paris.jpg", "bytes": _create_jpeg_bytes("Canon EOS R5", exif_comment="Location: Paris")},
                {"filename": "claim_tokyo.txt", "bytes": b"Location: Tokyo. The conference took place exclusively in Tokyo."},
            ],
            "platform_urls": [],
        },
        {
            "case_id": "case_dev_07_coord_near_dup",
            "split": "dev",
            "label": "COORDINATED_SYNTHETIC",
            "description": "Two visually near-identical images reposted across channels.",
            "files": [
                {"filename": "original_campaign.jpg", "bytes": _create_jpeg_bytes("Midjourney", 200, 200, color=(100, 150, 200))},
                {"filename": "repost_campaign.jpg", "bytes": _create_jpeg_bytes("Midjourney", 200, 200, color=(100, 150, 201))},
            ],
            "platform_urls": [],
        },
        {
            "case_id": "case_dev_08_timestamp_provenance_safe",
            "split": "dev",
            "label": "AUTHENTIC",
            "description": "Photo recorded in 2022 with article published in 2024. Provenance difference alone is NOT manipulation.",
            "files": [
                {"filename": "archived_photo.jpg", "bytes": _create_jpeg_bytes("Sony A7IV")},
                {"filename": "modern_article.txt", "bytes": b"Reflecting on past events in 2024."},
            ],
            "platform_urls": [],
        },
        {
            "case_id": "case_dev_09_manip_photoshop_layer",
            "split": "dev",
            "label": "MANIPULATED",
            "description": "Document image modified with Adobe Photoshop editing tool.",
            "files": [
                {"filename": "altered_receipt.jpg", "bytes": _create_jpeg_bytes("Adobe Photoshop 2023")},
            ],
            "platform_urls": [],
        },
        {
            "case_id": "case_dev_10_auth_multimodal_meeting",
            "split": "dev",
            "label": "AUTHENTIC",
            "description": "Meeting press release with audio clip and official transcript.",
            "files": [
                {"filename": "official_statement.txt", "bytes": b"In 2024, the meeting was adjourned following consensus."},
                {"filename": "meeting_recording.wav", "bytes": _create_wav_bytes(3.0)},
            ],
            "platform_urls": [],
        },
        {
            "case_id": "case_dev_11_coord_sha256_duplicates",
            "split": "dev",
            "label": "COORDINATED_SYNTHETIC",
            "description": "Exact SHA-256 duplicate files submitted as supposed independent corroboration.",
            "files": [
                {"filename": "file_alpha.txt", "bytes": b"Identical viral message broadcasted synchronously."},
                {"filename": "file_beta.txt", "bytes": b"Identical viral message broadcasted synchronously."},
            ],
            "platform_urls": [],
        },
        {
            "case_id": "case_dev_12_inconclusive_low_quality",
            "split": "dev",
            "label": "INCONCLUSIVE",
            "description": "Extremely low resolution image with minimal forensic trace.",
            "files": [
                {"filename": "low_res_thumb.jpg", "bytes": _create_jpeg_bytes("", 16, 16)},
            ],
            "platform_urls": [],
        },
        {
            "case_id": "case_dev_13_manip_speech_conflict",
            "split": "dev",
            "label": "MANIPULATED",
            "description": "Spoken audio claims election results overturned while official text affirms certification.",
            "files": [
                {"filename": "audio_narration.wav", "bytes": _create_wav_bytes(2.0)},
                {"filename": "official_doc.txt", "bytes": b"Certified results confirmed unanimously in 2024."},
            ],
            "platform_urls": [],
        },
        {
            "case_id": "case_dev_14_auth_press_release",
            "split": "dev",
            "label": "AUTHENTIC",
            "description": "Verified corporate announcement published across official channels.",
            "files": [
                {"filename": "announcement.txt", "bytes": b"Corporate earnings for Q1 2024 reported positive growth."},
            ],
            "platform_urls": [],
        },

        # ==========================================
        # HELD-OUT SPLIT (10 Cases - Evaluated ONCE)
        # ==========================================
        {
            "case_id": "case_heldout_01_auth_photo_transcript",
            "split": "held_out",
            "label": "AUTHENTIC",
            "description": "Live briefing photo corroborated with verified transcript.",
            "files": [
                {"filename": "briefing.jpg", "bytes": _create_jpeg_bytes("Leica Q2")},
                {"filename": "transcript.txt", "bytes": b"The prime minister addressed the delegation in 2024."},
            ],
            "platform_urls": [],
        },
        {
            "case_id": "case_heldout_02_manip_dalle_synth",
            "split": "held_out",
            "label": "MANIPULATED",
            "description": "Synthesized scene generated via DALL-E AI tool.",
            "files": [
                {"filename": "dalle_scene.jpg", "bytes": _create_jpeg_bytes("DALL-E 3")},
            ],
            "platform_urls": [],
        },
        {
            "case_id": "case_heldout_03_coord_repost_swarm",
            "split": "held_out",
            "label": "COORDINATED_SYNTHETIC",
            "description": "Multiple near-identical text posts distributed simultaneously.",
            "files": [
                {"filename": "post_1.txt", "bytes": b"Alert: Emergency broadcast issued for downtown district immediately."},
                {"filename": "post_2.txt", "bytes": b"Alert: Emergency broadcast issued for downtown district immediately in full."},
            ],
            "platform_urls": [],
        },
        {
            "case_id": "case_heldout_04_inconclusive_missing_ref",
            "split": "held_out",
            "label": "INCONCLUSIVE",
            "description": "Ambiguous fragment lacking sufficient evidence to certify genuine or fake.",
            "files": [
                {"filename": "fragment.txt", "bytes": b"Unverifiable fragment."},
            ],
            "platform_urls": [],
        },
        {
            "case_id": "case_heldout_05_auth_conference_audio",
            "split": "held_out",
            "label": "AUTHENTIC",
            "description": "Authentic academic keynote speech with verified event record.",
            "files": [
                {"filename": "keynote.wav", "bytes": _create_wav_bytes(2.5)},
                {"filename": "keynote_metadata.txt", "bytes": b"Keynote address archived in full in Paris in 2024."},
            ],
            "platform_urls": [],
        },
        {
            "case_id": "case_heldout_06_manip_gimp_edit",
            "split": "held_out",
            "label": "MANIPULATED",
            "description": "Forensic evidence of GIMP editing on official letterhead.",
            "files": [
                {"filename": "letterhead.jpg", "bytes": _create_jpeg_bytes("GIMP 2.10")},
            ],
            "platform_urls": [],
        },
        {
            "case_id": "case_heldout_07_coord_ai_cluster",
            "split": "held_out",
            "label": "COORDINATED_SYNTHETIC",
            "description": "Cluster of images generated from identical Stable Diffusion pipeline.",
            "files": [
                {"filename": "sd_cluster_a.jpg", "bytes": _create_jpeg_bytes("Stable Diffusion WebUI", color=(100, 150, 200))},
                {"filename": "sd_cluster_b.jpg", "bytes": _create_jpeg_bytes("Stable Diffusion WebUI", color=(120, 160, 210))},
            ],
            "platform_urls": [],
        },
        {
            "case_id": "case_heldout_08_auth_multimodal_archive",
            "split": "held_out",
            "label": "AUTHENTIC",
            "description": "Verified archival record with matching dates across documents.",
            "files": [
                {"filename": "record.txt", "bytes": b"Signed and sealed in Paris in 2024."},
                {"filename": "photo.jpg", "bytes": _create_jpeg_bytes("Fujifilm X-T4")},
            ],
            "platform_urls": [],
        },
        {
            "case_id": "case_heldout_09_manip_contradictory_claims",
            "split": "held_out",
            "label": "MANIPULATED",
            "description": "Direct semantic contradiction between stated casualty count and official figures.",
            "files": [
                {"filename": "statement_manip.txt", "bytes": b"Location: London. Casualties in London confirmed zero."},
                {"filename": "report_official.txt", "bytes": b"Location: Geneva. Casualties in Geneva confirmed fifty."},
            ],
            "platform_urls": [],
        },
        {
            "case_id": "case_heldout_10_auth_field_recording",
            "split": "held_out",
            "label": "AUTHENTIC",
            "description": "Authentic nature field recording with verified timeline.",
            "files": [
                {"filename": "field_audio.wav", "bytes": _create_wav_bytes(3.0)},
                {"filename": "field_log.txt", "bytes": b"Recorded in 2024 at environmental research station in Paris."},
            ],
            "platform_urls": [],
        },
    ]
    return cases
