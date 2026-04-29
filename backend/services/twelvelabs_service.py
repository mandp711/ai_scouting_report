import requests
import time
import os
import tempfile
import re
from typing import Dict, Optional


class TwelveLabsService:
    """Service for analyzing videos using TwelveLabs API"""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.twelvelabs.io/v1.3"
        self.headers = {
            "x-api-key": api_key or "",
            "Content-Type": "application/json"
        }

    def analyze_video(self, sport: str, video_url: Optional[str] = None, video_file_path: Optional[str] = None) -> Dict:
        """Analyze video from URL or local file path. Provide either video_url or video_file_path."""
        downloaded_file = None
        try:
            index_id = self._get_or_create_index(sport)

            if video_file_path and os.path.exists(video_file_path):
                print(f"Analyzing uploaded file: {video_file_path}")
                video_id = self._upload_video_file(index_id, video_file_path)
            elif video_url and self._is_youtube_url(video_url):
                print("Detected YouTube URL. Downloading video...")
                downloaded_file = self._download_youtube_video(video_url)
                print(f"Downloaded to: {downloaded_file}")
                video_id = self._upload_video_file(index_id, downloaded_file)
            elif video_url:
                video_id = self._upload_video_url(index_id, video_url)
            else:
                raise ValueError("Either video_url or video_file_path must be provided")

            print(f"Video uploaded. Task ID: {video_id}. Waiting for processing...")
            self._wait_for_video_processing(index_id, video_id)
            print("Video processing complete. Generating insights...")
            insights = self._generate_insights(index_id, video_id, sport)
            return insights
        except Exception as e:
            print(f"Error in TwelveLabs video analysis: {str(e)}")
            return {
                "error": str(e),
                "player_movements": [],
                "tactical_patterns": [],
                "key_actions": []
            }
        finally:
            if downloaded_file and os.path.exists(downloaded_file):
                os.remove(downloaded_file)
                print(f"Cleaned up temp file: {downloaded_file}")

    def _is_youtube_url(self, url: str) -> bool:
        youtube_patterns = [
            r'(youtube\.com/watch)',
            r'(youtu\.be/)',
            r'(youtube\.com/embed/)',
            r'(youtube\.com/shorts/)',
        ]
        return any(re.search(pattern, url) for pattern in youtube_patterns)

    def _download_youtube_video(self, url: str) -> str:
        try:
            import yt_dlp
        except ImportError:
            raise Exception("yt-dlp is not installed. Run: pip install yt-dlp")

        temp_dir = tempfile.gettempdir()
        output_path = os.path.join(temp_dir, "scouting_video.mp4")

        ydl_opts = {
            'format': 'worst[ext=mp4]',
            'outtmpl': output_path,
            'quiet': True,
            'no_warnings': True,
            'overwrites': True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        if not os.path.exists(output_path):
            raise Exception("Failed to download YouTube video")

        file_size_mb = os.path.getsize(output_path) / (1024 * 1024)
        print(f"Downloaded video: {file_size_mb:.1f} MB")
        return output_path

    def _upload_video_file(self, index_id: str, file_path: str) -> str:
        headers = {"x-api-key": self.api_key or ""}
        with open(file_path, "rb") as video_file:
            files = {
                "index_id": (None, index_id),
                "video_file": ("video.mp4", video_file, "video/mp4")
            }
            response = requests.post(
                f"{self.base_url}/tasks",
                headers=headers,
                files=files
            )
        if response.status_code in [200, 201]:
            return response.json().get('_id')
        else:
            raise Exception(f"Failed to upload video file: {response.text}")

    def _upload_video_url(self, index_id: str, video_url: str) -> str:
        headers = {"x-api-key": self.api_key or ""}
        files = {
            "index_id": (None, index_id),
            "video_url": (None, video_url)
        }
        response = requests.post(
            f"{self.base_url}/tasks",
            headers=headers,
            files=files
        )
        if response.status_code in [200, 201]:
            return response.json().get('_id')
        else:
            raise Exception(f"Failed to upload video: {response.text}")

    def _get_or_create_index(self, sport: str) -> str:
        index_name = f"{sport}_scouting_index"
        try:
            response = requests.get(f"{self.base_url}/indexes", headers=self.headers)
            if response.status_code == 200:
                indexes = response.json().get('data', [])
                for index in indexes:
                    if index.get('index_name') == index_name:
                        return index.get('_id')
        except Exception as e:
            print(f"Error fetching indexes: {str(e)}")

        payload = {
            "index_name": index_name,
            "models": [
                {"model_name": "marengo2.7", "model_options": ["visual", "audio"]}
            ]
        }
        response = requests.post(f"{self.base_url}/indexes", headers=self.headers, json=payload)
        if response.status_code == 201:
            return response.json().get('_id')
        else:
            raise Exception(f"Failed to create index: {response.text}")

    def _wait_for_video_processing(self, index_id: str, video_id: str, timeout: int = 600):
        start_time = time.time()
        while time.time() - start_time < timeout:
            response = requests.get(f"{self.base_url}/tasks/{video_id}", headers=self.headers)
            if response.status_code == 200:
                status = response.json().get('status')
                print(f"  Video processing status: {status}")
                if status == 'ready':
                    return True
                elif status == 'failed':
                    raise Exception("Video processing failed")
            time.sleep(10)
        raise Exception("Video processing timeout")

    def _generate_insights(self, index_id: str, video_id: str, sport: str) -> Dict:
        if sport == "soccer":
            queries = [
                "What formations and tactical patterns does the team use?",
                "Identify defensive weaknesses and vulnerabilities",
                "What are the team's attacking patterns and set piece strategies?",
                "Analyze individual player movements and positioning",
                "What are the team's strengths in transition play?"
            ]
        else:
            queries = [
                "What are the pitcher's tendencies and pitch selection patterns?",
                "Analyze the team's defensive positioning and shifts",
                "What are the hitters' swing patterns and weaknesses?",
                "Identify base running tendencies and strategies",
                "What are the catcher's game-calling patterns?"
            ]

        insights = {
            "player_movements": [],
            "tactical_patterns": [],
            "key_actions": [],
            "weaknesses": [],
            "strengths": []
        }

        for query in queries:
            try:
                search_result = self._search_video(index_id, query)
                insights["tactical_patterns"].append({"query": query, "findings": search_result})
            except Exception as e:
                print(f"Error searching for '{query}': {str(e)}")

        return insights

    def _search_video(self, index_id: str, query: str) -> str:
        payload = {
            "index_id": index_id,
            "query": query,
            "search_options": ["visual"],
            "group_by": "video"
        }
        response = requests.post(f"{self.base_url}/search", headers=self.headers, json=payload)
        if response.status_code == 200:
            data = response.json().get('data', [])
            if data:
                clips = data[0].get('clips', [])
                results = []
                for clip in clips[:3]:
                    results.append({
                        "start": clip.get('start'),
                        "end": clip.get('end'),
                        "score": clip.get('score'),
                        "text": clip.get('metadata', {}).get('text', '')
                    })
                return results
        return []
