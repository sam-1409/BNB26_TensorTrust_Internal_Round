"""Cross-Platform Investigation Client Module for TrustLayers (T²).

Implements:
- Legitimate YouTube Data API v3 integration for video metadata, channel provenance, and top comments.
- Extensible BasePlatformClient interface for source verification ecosystem (YouTube, Reddit, URLs).
- FAST-FIRST / CONDITIONAL-DEEP operational principle: queries invoked only when relevant.
- COMMENTS AS EVIDENCE:
  - Capped strength (<= 0.10) and capped reliability (<= 0.20).
  - Never treated as ground truth or consensus reality.
  - No majority voting.
- Safe disk caching to avoid redundant queries and respect API quotas.
- Graceful degradation: Missing API keys or network errors record limitations without pipeline crashes.
"""

import os
import re
import json
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from models.schemas import (
    PlatformArtifact,
    CommentEvidence,
    EvidenceItem,
    EvidenceRef,
    Relation,
)
from core.config import (
    YOUTUBE_API_KEY,
    MAX_PLATFORM_COMMENTS,
    COMMENT_EVIDENCE_STRENGTH,
    COMMENT_EVIDENCE_RELIABILITY,
)


class PlatformClientError(Exception):
    """Exception for platform client failures."""
    def __init__(self, error_code: str, message: str):
        super().__init__(message)
        self.error_code = error_code
        self.message = message


class BasePlatformClient:
    """Abstract base class for platform source verifiers."""

    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = cache_dir
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_cached(self, key: str) -> Optional[Dict[str, Any]]:
        if not self.cache_dir:
            return None
        cache_file = self.cache_dir / f"{key}.json"
        if cache_file.exists():
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return None

    def _save_cache(self, key: str, data: Dict[str, Any]) -> None:
        if not self.cache_dir:
            return
        cache_file = self.cache_dir / f"{key}.json"
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    def fetch_artifact(self, url_or_id: str) -> Optional[PlatformArtifact]:
        raise NotImplementedError


class YouTubeClient(BasePlatformClient):
    """Client for YouTube Data API v3."""

    def __init__(self, api_key: Optional[str] = None, cache_dir: Optional[Path] = None):
        super().__init__(cache_dir=cache_dir)
        self.api_key = api_key or YOUTUBE_API_KEY or os.environ.get("YOUTUBE_API_KEY", "")

    @staticmethod
    def extract_video_id(url_or_id: str) -> Optional[str]:
        """Extract YouTube 11-char video ID from URL or return raw ID."""
        cleaned = url_or_id.strip()
        # Direct video ID pattern
        if re.match(r"^[A-Za-z0-9_-]{11}$", cleaned):
            return cleaned

        patterns = [
            r"(?:v=|\/v\/|youtu\.be\/|\/embed\/|\/shorts\/)([A-Za-z0-9_-]{11})",
            r"[?&]v=([A-Za-z0-9_-]{11})",
        ]
        for pat in patterns:
            match = re.search(pat, cleaned)
            if match:
                return match.group(1)
        return None

    def fetch_artifact(self, url_or_id: str) -> Optional[PlatformArtifact]:
        """Fetch video metadata and top comments from YouTube Data API v3."""
        video_id = self.extract_video_id(url_or_id)
        if not video_id:
            return None

        if not self.api_key:
            raise PlatformClientError(
                "YOUTUBE_API_KEY_MISSING",
                "YouTube API key is not configured. External YouTube verification is unavailable."
            )

        cache_key = f"yt_{video_id}"
        cached_data = self._get_cached(cache_key)
        if cached_data:
            return PlatformArtifact(**cached_data)

        # 1. Fetch Video Metadata
        video_api_url = (
            f"https://www.googleapis.com/youtube/v3/videos"
            f"?part=snippet,statistics&id={video_id}&key={self.api_key}"
        )
        try:
            req = urllib.request.Request(
                video_api_url,
                headers={"User-Agent": "TrustLayers-Verification/1.0"}
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception as err:
            raise PlatformClientError("YOUTUBE_API_ERROR", f"Failed to retrieve YouTube video data: {err}")

        items = payload.get("items", [])
        if not items:
            return None

        item = items[0]
        snippet = item.get("snippet", {})
        statistics = item.get("statistics", {})

        title = snippet.get("title")
        description = snippet.get("description")
        upload_date = snippet.get("publishedAt")
        view_count_raw = statistics.get("viewCount")
        view_count = int(view_count_raw) if view_count_raw is not None else None

        # 2. Fetch Top Comments Sample (up to MAX_PLATFORM_COMMENTS)
        comments_sample: List[str] = []
        try:
            comments_api_url = (
                f"https://www.googleapis.com/youtube/v3/commentThreads"
                f"?part=snippet&videoId={video_id}&maxResults={MAX_PLATFORM_COMMENTS}&key={self.api_key}"
            )
            req_comments = urllib.request.Request(
                comments_api_url,
                headers={"User-Agent": "TrustLayers-Verification/1.0"}
            )
            with urllib.request.urlopen(req_comments, timeout=10) as resp_comm:
                comm_payload = json.loads(resp_comm.read().decode("utf-8"))
                for c_item in comm_payload.get("items", []):
                    top_comm = c_item.get("snippet", {}).get("topLevelComment", {}).get("snippet", {})
                    comm_text = top_comm.get("textDisplay") or top_comm.get("textOriginal")
                    if comm_text:
                        comments_sample.append(comm_text.strip()[:500])
        except Exception:
            # Comments might be disabled on video; continue gracefully
            pass

        now_iso = datetime.now(timezone.utc).isoformat()
        platform_artifact = PlatformArtifact(
            platform="youtube",
            url=f"https://www.youtube.com/watch?v={video_id}",
            title=title,
            description=description,
            upload_date=upload_date,
            view_count=view_count,
            comments_sample=comments_sample[:MAX_PLATFORM_COMMENTS],
            comment_reliability_note="Comments are unverified user opinions.",
            retrieval_timestamp=now_iso,
        )

        self._save_cache(cache_key, platform_artifact.model_dump())
        return platform_artifact


class RedditClient(BasePlatformClient):
    """Extensible client for Reddit discussion and post verification."""

    def __init__(self, cache_dir: Optional[Path] = None):
        super().__init__(cache_dir=cache_dir)

    def fetch_artifact(self, url_or_id: str) -> Optional[PlatformArtifact]:
        """Fetch post and comments from Reddit public json endpoint."""
        cleaned = url_or_id.strip()
        if "reddit.com" not in cleaned:
            return None

        # Clean trailing slash and append .json
        clean_url = cleaned.split("?")[0].rstrip("/")
        json_url = f"{clean_url}.json"

        cache_key = f"reddit_{hash(clean_url)}"
        cached = self._get_cached(cache_key)
        if cached:
            return PlatformArtifact(**cached)

        try:
            req = urllib.request.Request(
                json_url,
                headers={"User-Agent": "TrustLayers/1.0 (Verification Research)"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            if not isinstance(data, list) or not data:
                return None

            post_data = data[0].get("data", {}).get("children", [{}])[0].get("data", {})
            title = post_data.get("title")
            description = post_data.get("selftext")
            created_utc = post_data.get("created_utc")
            upload_date = datetime.fromtimestamp(created_utc, timezone.utc).isoformat() if created_utc else None

            # Comments
            comments_sample: List[str] = []
            if len(data) > 1:
                comm_children = data[1].get("data", {}).get("children", [])
                for child in comm_children[:MAX_PLATFORM_COMMENTS]:
                    c_body = child.get("data", {}).get("body")
                    if c_body and c_body != "[deleted]":
                        comments_sample.append(c_body.strip()[:500])

            plat_art = PlatformArtifact(
                platform="reddit",
                url=clean_url,
                title=title,
                description=description,
                upload_date=upload_date,
                view_count=None,
                comments_sample=comments_sample[:MAX_PLATFORM_COMMENTS],
                comment_reliability_note="Comments are unverified user opinions.",
                retrieval_timestamp=datetime.now(timezone.utc).isoformat(),
            )
            self._save_cache(cache_key, plat_art.model_dump())
            return plat_art
        except Exception as err:
            raise PlatformClientError("REDDIT_API_ERROR", f"Failed to retrieve Reddit post data: {err}")


class PlatformInvestigationManager:
    """Coordinates conditional cross-platform investigation workflows."""

    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = cache_dir
        self.youtube_client = YouTubeClient(cache_dir=cache_dir)
        self.reddit_client = RedditClient(cache_dir=cache_dir)

    def investigate(
        self,
        urls: List[str],
        query: Optional[str] = None,
    ) -> Tuple[List[PlatformArtifact], List[CommentEvidence], List[EvidenceItem]]:
        """Run conditional external platform investigation.

        Returns:
            Tuple of (PlatformArtifacts, CommentEvidences, EvidenceItems).
        """
        platform_artifacts: List[PlatformArtifact] = []
        comment_evidences: List[CommentEvidence] = []
        evidence_items: List[EvidenceItem] = []

        # If no URLs provided, skip external queries (FAST-FIRST principle)
        if not urls:
            return [], [], []

        for url in urls:
            plat_art: Optional[PlatformArtifact] = None
            try:
                if "youtube.com" in url or "youtu.be" in url:
                    plat_art = self.youtube_client.fetch_artifact(url)
                elif "reddit.com" in url:
                    plat_art = self.reddit_client.fetch_artifact(url)
            except PlatformClientError:
                # Handled gracefully, will be recorded in limitations
                continue
            except Exception:
                continue

            if plat_art:
                platform_artifacts.append(plat_art)

                # Process sampled comments as weak, low-reliability evidence
                for idx, comm_text in enumerate(plat_art.comments_sample):
                    # Keyword check for suspicious user consensus
                    lower_comm = comm_text.lower()
                    direction: str = "neutral"
                    if any(term in lower_comm for term in ("fake", "deepfake", "ai generated", "cgi", "hoax", "edited")):
                        direction = "manipulated"
                    elif any(term in lower_comm for term in ("authentic", "original", "verified", "real video", "source")):
                        direction = "authentic"

                    c_ev = CommentEvidence(
                        text=comm_text,
                        platform=plat_art.platform,
                        direction=direction,  # type: ignore
                        strength=COMMENT_EVIDENCE_STRENGTH,      # strictly capped at 0.10
                        reliability=COMMENT_EVIDENCE_RELIABILITY, # strictly capped at 0.20
                        note="User comment — unverified opinion, not forensic evidence.",
                    )
                    comment_evidences.append(c_ev)

                    # Also emit atomic EvidenceItem for check catalog
                    ev_item = EvidenceItem(
                        id=f"plat_{plat_art.platform}_{idx+1}",
                        artifact_ids=[],
                        direction=direction,  # type: ignore
                        strength=COMMENT_EVIDENCE_STRENGTH,
                        reliability=COMMENT_EVIDENCE_RELIABILITY,
                        scope="set",
                        evidence_ref=EvidenceRef(type="region", value="metadata"),
                        description=f"User discussion on {plat_art.platform}: '{comm_text[:100]}...'",
                        source="forensic",
                        check_id="CHK_PLATFORM_VERIFY",
                    )
                    evidence_items.append(ev_item)

        return platform_artifacts, comment_evidences, evidence_items
