from openai import OpenAI
from typing import Dict
from datetime import datetime
import json
import os


class ClaudeService:
    """Service for generating comprehensive scouting reports via OpenRouter"""

    def __init__(self, api_key: str):
        self.client = OpenAI(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1"
        )
        self.model = "google/gemini-2.0-flash-001"
        self.app_name = os.getenv('APP_NAME', 'AI_Scouting_Report')
        self.app_url = os.getenv('APP_URL', 'http://localhost:8000')

    def generate_scouting_report(self, opponent_name: str, structured_data: Dict, sport: str) -> str:
        prompt = self._build_report_prompt(opponent_name, structured_data, sport)
        system_prompt = self._get_system_prompt(sport)

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                max_tokens=4096,
                temperature=0.7,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                extra_headers={
                    "HTTP-Referer": self.app_url,
                    "X-Title": self.app_name
                }
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"Error generating report: {str(e)}")
            return f"Error generating report: {str(e)}"

    def _get_system_prompt(self, sport: str) -> str:
        return f"""You are an elite {sport} scout and analyst with decades of experience.
Your scouting reports are known for being:
- Data-driven and objective
- Actionable with specific recommendations
- Clear and easy to understand for coaches and players
- Comprehensive but concise
- Focused on exploitable weaknesses and matchup advantages

Write scouting reports that combine statistical analysis with tactical insights.
Use coaching terminology and provide specific game-planning recommendations.
Include real numbers and percentages when available.
Make recommendations concrete and actionable (e.g., "Attack their weak-side defense with outside zone runs"
rather than "They struggle on defense")."""

    def _build_report_prompt(self, opponent_name: str, structured_data: Dict, sport: str) -> str:
        current_year = datetime.now().year
        return f"""Generate a comprehensive scouting report for {opponent_name} ({sport}) for the {current_year} season.

STRUCTURED ANALYSIS DATA:
{json.dumps(structured_data, indent=2)}

Create a detailed scouting report with the following sections:

# EXECUTIVE SUMMARY
A 2-3 paragraph overview of the opponent's identity, style of play, and key matchup considerations.

# TEAM STRENGTHS
List and explain their 3-5 biggest strengths with supporting statistics and specific examples.
For each strength, explain how to respect it or neutralize it.

# EXPLOITABLE WEAKNESSES
List and explain their 3-5 most exploitable weaknesses with supporting data.
For each weakness, provide specific tactical recommendations on how to attack it.

# TACTICAL ANALYSIS
Detailed breakdown of their:
- Offensive/attacking patterns and tendencies
- Defensive schemes and vulnerabilities
- Special situations (set pieces, special teams, etc.)
- Transition play

# PLAYER-BY-PLAYER BREAKDOWN
Key players to watch with their strengths, weaknesses, statistical profile, and tendencies.

# GAME PLAN RECOMMENDATIONS
Specific, actionable recommendations organized by:
1. Offensive game plan (how to attack their defense)
2. Defensive game plan (how to stop their offense)
3. Special situations
4. Key matchups to target

# KEY STATS SUMMARY
Present the most important statistics in an easy-to-read format.

Make the report conversational and coaching-focused. Use specific data points and percentages.
Write as if you're briefing the coaching staff before a game.
"""

    def generate_quick_summary(self, full_report: str) -> str:
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                max_tokens=1024,
                temperature=0.5,
                messages=[
                    {"role": "user", "content": f"""Summarize this scouting report into a 1-page quick reference
that a coach could review 5 minutes before the game. Focus on the most critical
strengths, weaknesses, and recommendations.

FULL REPORT:
{full_report}"""}
                ],
                extra_headers={
                    "HTTP-Referer": self.app_url,
                    "X-Title": self.app_name
                }
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"Error generating summary: {str(e)}")
            return "Error generating summary"
