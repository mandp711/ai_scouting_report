from openai import OpenAI
from typing import Dict, Optional
from datetime import datetime
import json
import os


class OpenAIService:
    """Service for processing and structuring data using OpenAI via OpenRouter"""

    def __init__(self, api_key: str):
        self.client = OpenAI(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1"
        )
        self.model = "openai/gpt-4o-mini"
        self.app_name = os.getenv('APP_NAME', 'AI_Scouting_Report')
        self.app_url = os.getenv('APP_URL', 'http://localhost:8000')

    def process_team_data(
        self,
        team_stats: Dict,
        video_insights: Optional[Dict],
        sport: str
    ) -> Dict:
        prompt = self._build_analysis_prompt(team_stats, video_insights, sport)

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": f"You are an expert {sport} analyst. Analyze the provided data and identify key patterns, strengths, weaknesses, and tactical insights."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                response_format={"type": "json_object"},
                temperature=0.7,
                extra_headers={
                    "HTTP-Referer": self.app_url,
                    "X-Title": self.app_name
                }
            )

            result = json.loads(response.choices[0].message.content)
            return result

        except Exception as e:
            print(f"Error processing data with OpenAI: {str(e)}")
            return {
                "error": str(e),
                "key_strengths": [],
                "key_weaknesses": [],
                "tactical_patterns": [],
                "recommendations": []
            }

    def _build_analysis_prompt(
        self,
        team_stats: Dict,
        video_insights: Optional[Dict],
        sport: str
    ) -> str:
        current_year = datetime.now().year
        prompt = f"""Analyze the following {sport} team data and provide a structured analysis for the {current_year} season.

TEAM STATISTICS:
{json.dumps(team_stats, indent=2)}
"""

        if video_insights:
            prompt += f"""

VIDEO ANALYSIS INSIGHTS:
{json.dumps(video_insights, indent=2)}
"""

        prompt += """

Please provide a JSON response with the following structure:
{
    "key_strengths": [
        {
            "category": "offense/defense/special teams/pitching/hitting/fielding",
            "strength": "description",
            "supporting_data": "specific stats or observations"
        }
    ],
    "key_weaknesses": [
        {
            "category": "offense/defense/special teams/pitching/hitting/fielding",
            "weakness": "description",
            "supporting_data": "specific stats or observations",
            "exploitable": true/false
        }
    ],
    "tactical_patterns": [
        {
            "pattern": "description of tactical pattern",
            "frequency": "how often it occurs",
            "situations": "when it typically happens"
        }
    ],
    "player_analysis": [
        {
            "player": "player name or position",
            "strengths": ["strength 1", "strength 2"],
            "weaknesses": ["weakness 1", "weakness 2"],
            "tendencies": ["tendency 1", "tendency 2"]
        }
    ],
    "recommendations": [
        {
            "category": "game planning category",
            "recommendation": "specific actionable recommendation",
            "rationale": "why this will be effective"
        }
    ]
}
"""
        return prompt

    def extract_key_stats(self, raw_stats: str, sport: str) -> Dict:
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": f"Extract key {sport} statistics from the provided text and structure them in JSON format."
                    },
                    {
                        "role": "user",
                        "content": f"Extract statistics from this text:\n\n{raw_stats}"
                    }
                ],
                response_format={"type": "json_object"},
                temperature=0.3,
                extra_headers={
                    "HTTP-Referer": self.app_url,
                    "X-Title": self.app_name
                }
            )

            return json.loads(response.choices[0].message.content)

        except Exception as e:
            print(f"Error extracting stats: {str(e)}")
            return {"raw_stats": raw_stats}
