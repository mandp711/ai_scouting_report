from dataclasses import dataclass, asdict
from typing import Dict, Optional
from datetime import datetime


@dataclass
class Video:
    video_url: str
    sport: str
    video_id: Optional[str] = None
    index_id: Optional[str] = None
    status: str = "pending"
    insights: Optional[Dict] = None
    created_at: Optional[str] = None
    processed_at: Optional[str] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now().isoformat()

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> 'Video':
        return cls(**data)

    def update_status(self, status: str):
        self.status = status
        if status == "ready":
            self.processed_at = datetime.now().isoformat()

    def add_insights(self, insights: Dict):
        self.insights = insights
        self.update_status("ready")
