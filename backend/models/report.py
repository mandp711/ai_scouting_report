from dataclasses import dataclass, asdict, field
from typing import Dict, List, Optional
from datetime import datetime
import hashlib


@dataclass
class Report:
    opponent_name: str
    sport: str
    statistics: Dict
    structured_analysis: Dict
    final_report: str
    video_insights: Optional[Dict] = None
    report_id: Optional[str] = None
    created_at: Optional[str] = None
    metadata: Dict = field(default_factory=dict)

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now().isoformat()
        if self.report_id is None:
            self.report_id = self._generate_report_id()

    def _generate_report_id(self) -> str:
        hash_input = f"{self.opponent_name}_{self.sport}_{self.created_at}"
        return hashlib.md5(hash_input.encode()).hexdigest()[:12]

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> 'Report':
        return cls(**data)

    def get_executive_summary(self) -> str:
        if "EXECUTIVE SUMMARY" in self.final_report:
            parts = self.final_report.split("# TEAM STRENGTHS")
            if len(parts) > 0:
                return parts[0].replace("# EXECUTIVE SUMMARY", "").strip()
        sentences = self.final_report.split('.')[:3]
        return '. '.join(sentences) + '.'

    def get_key_strengths(self) -> List[str]:
        return [s.get("strength", "") for s in self.structured_analysis.get("key_strengths", [])]

    def get_key_weaknesses(self) -> List[str]:
        return [w.get("weakness", "") for w in self.structured_analysis.get("key_weaknesses", [])]

    def get_recommendations(self) -> List[str]:
        return [r.get("recommendation", "") for r in self.structured_analysis.get("recommendations", [])]
