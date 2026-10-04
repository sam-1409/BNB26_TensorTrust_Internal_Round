"""Unit tests for Phase 7: Cross-platform investigation (services/platform_client.py)."""

from unittest.mock import patch, MagicMock
import io
import json
from services.platform_client import (
    YouTubeClient,
    RedditClient,
    PlatformInvestigationManager,
    PlatformClientError,
)
from core.config import COMMENT_EVIDENCE_STRENGTH, COMMENT_EVIDENCE_RELIABILITY


def test_youtube_video_id_extraction():
    urls = [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/embed/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ]
    for url, expected_id in urls:
        assert YouTubeClient.extract_video_id(url) == expected_id

    assert YouTubeClient.extract_video_id("https://google.com") is None


def test_youtube_missing_api_key():
    client = YouTubeClient(api_key="")
    # When api key is missing, raises PlatformClientError rather than crashing
    try:
        client.fetch_artifact("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        assert False, "Should have raised PlatformClientError"
    except PlatformClientError as err:
        assert err.error_code == "YOUTUBE_API_KEY_MISSING"


def test_youtube_fetch_mocked():
    client = YouTubeClient(api_key="mock_key")

    mock_video_response = {
        "items": [
            {
                "snippet": {
                    "title": "Press Conference Live",
                    "description": "Official broadcast",
                    "publishedAt": "2024-05-10T12:00:00Z",
                },
                "statistics": {
                    "viewCount": "125000",
                }
            }
        ]
    }

    mock_comments_response = {
        "items": [
            {
                "snippet": {
                    "topLevelComment": {
                        "snippet": {
                            "textDisplay": "This video looks totally fake and AI generated."
                        }
                    }
                }
            }
        ]
    }

    def fake_urlopen(req, timeout=10):
        url = req.full_url
        if "videos" in url:
            data = json.dumps(mock_video_response).encode("utf-8")
        else:
            data = json.dumps(mock_comments_response).encode("utf-8")
        return io.BytesIO(data)

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        art = client.fetch_artifact("dQw4w9WgXcQ")
        assert art is not None
        assert art.title == "Press Conference Live"
        assert art.view_count == 125000
        assert len(art.comments_sample) == 1
        assert "totally fake" in art.comments_sample[0]


def test_comment_evidence_capping():
    manager = PlatformInvestigationManager()

    mock_art = MagicMock()
    mock_art.platform = "youtube"
    mock_art.comments_sample = [
        "This looks like deepfake manipulation!",
        "Official authentic recording confirmed.",
    ]

    with patch.object(manager.youtube_client, "fetch_artifact", return_value=mock_art):
        plat_arts, comments, ev_items = manager.investigate(["https://youtu.be/dQw4w9WgXcQ"])

        assert len(comments) == 2
        for c in comments:
            # Strength strictly capped at 0.10
            assert c.strength <= COMMENT_EVIDENCE_STRENGTH
            # Reliability strictly capped at 0.20
            assert c.reliability <= COMMENT_EVIDENCE_RELIABILITY

        # Check directional classification
        assert comments[0].direction == "manipulated"
        assert comments[1].direction == "authentic"


def test_fast_first_skips_when_no_urls():
    manager = PlatformInvestigationManager()
    plat_arts, comments, ev_items = manager.investigate([])
    assert len(plat_arts) == 0
    assert len(comments) == 0
    assert len(ev_items) == 0
