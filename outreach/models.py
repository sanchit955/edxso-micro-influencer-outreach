"""Shared data model for one influencer record as it flows through the pipeline.

Data-integrity rule: a field that could not be obtained from a real public
page is stored as the literal string "Not Found" / "Unavailable" (or None for
numeric fields before formatting). Nothing is ever guessed or filled in.
"""

from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class Influencer:
    # Identity (from discovery / enrichment)
    channel_id: str = ""
    name: str = "Not Found"
    platform: str = "YouTube"
    profile_url: str = "Not Found"
    source_url: str = ""  # the exact public page this record was fetched from

    # Enrichment
    subscribers: Optional[int] = None          # None -> "Unavailable"
    description: str = ""
    email: str = "Not Found"                   # only if literally in description
    recent_videos: list = field(default_factory=list)   # [{title, views}]
    avg_views: Optional[float] = None
    engagement_rate: Optional[float] = None    # avg_views / subscribers * 100
    themes: list = field(default_factory=list)          # content themes detected
    social_links: list = field(default_factory=list)

    # Filtering
    status: str = "Pending"                    # Passed / Failed
    filter_reason: str = ""

    # Personalization (filled only for Passed records)
    email_subject: str = ""
    email_pitch: str = ""
    dm_text: str = ""
    collab_angle: str = ""

    def followers_display(self) -> str:
        return str(self.subscribers) if self.subscribers is not None else "Unavailable"

    def engagement_display(self) -> str:
        if self.engagement_rate is None:
            return "Unavailable"
        return f"{self.engagement_rate:.2f}%"

    def to_dataset_row(self) -> dict:
        return {
            "Name": self.name,
            "Platform": self.platform,
            "Followers": self.followers_display(),
            "Engagement": self.engagement_display(),
            "Niche": "Fitness",
            "Email": self.email,
            "Profile URL": self.profile_url,
            "Content Themes": "; ".join(self.themes) if self.themes else "Not Found",
            "Status": self.status,
            "Filter Reason": self.filter_reason,
            "Source URL": self.source_url,
        }

    def to_dict(self) -> dict:
        return asdict(self)
