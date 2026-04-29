from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from dotenv import load_dotenv
import json
import os
import tempfile
from services.twelvelabs_service import TwelveLabsService
from services.openai_service import OpenAIService
from services.gemini_service import ClaudeService
from services.scraper_service import ScraperService
from models.video import Video
from models.report import Report
import traceback

load_dotenv()

app = Flask(__name__)
CORS(app)

# Initialize services with OpenRouter API key
openrouter_key = os.getenv('OPENROUTER_API_KEY')
twelvelabs_service = TwelveLabsService(os.getenv('TWELVELABS_API_KEY'))
openai_service = OpenAIService(openrouter_key)
claude_service = ClaudeService(openrouter_key)
scraper_service = ScraperService()

_master_scouting_cache = None
_team_stats_cache = None


def load_master_scouting():
    """Load master_scouting_database_cleaned.json once (cached)."""
    global _master_scouting_cache
    if _master_scouting_cache is None:
        path = os.path.join(os.path.dirname(__file__), 'master_scouting_database_cleaned.json')
        if not os.path.isfile(path):
            _master_scouting_cache = {'_missing': True}
        else:
            with open(path, 'r', encoding='utf-8') as f:
                _master_scouting_cache = json.load(f)
    if _master_scouting_cache.get('_missing'):
        return None
    return _master_scouting_cache


def load_team_stats():
    """Load team_stats_database_batch1.json (aggregated NCAA team totals) once (cached)."""
    global _team_stats_cache
    if _team_stats_cache is None:
        path = os.path.join(os.path.dirname(__file__), 'team_stats_database_batch1.json')
        if not os.path.isfile(path):
            _team_stats_cache = {'_missing': True}
        else:
            with open(path, 'r', encoding='utf-8') as f:
                _team_stats_cache = json.load(f)
    if isinstance(_team_stats_cache, dict) and _team_stats_cache.get('_missing'):
        return None
    return _team_stats_cache


def match_display_name_to_school_row(team_query: str, rows: list, school_key: str = 'school'):
    """
    Match an NCAA_UI team display name (e.g. \"Vermont Catamounts\") to a DB row whose
    ``school_key`` equals the longest leading phrase of the query.
    """
    if not rows:
        return None
    qclean = ' '.join(team_query.strip().lower().replace(',', ' ').split())
    qwords = qclean.split()
    if not qwords:
        return None
    best = None
    best_key = (-1, -1)

    for t in rows:
        sch = (t.get(school_key) or '').strip()
        if not sch:
            continue
        sl = sch.lower().strip()
        for n in range(min(len(qwords), 8), 0, -1):
            prefix = ' '.join(qwords[:n])
            if prefix == sl:
                key = (n, len(sch))
                if key > best_key:
                    best_key = key
                    best = t
                break

    return best


def find_master_team_for_display(team_query: str):
    """
    Match an NCAA_UI team display name (e.g. \"Vermont Catamounts\") to a master DB row.
    Picks the longest matching school prefix against the leading words of the query.
    """
    data = load_master_scouting()
    if not data or 'teams' not in data:
        return None
    return match_display_name_to_school_row(team_query, data['teams'], 'school')


def find_team_stats_for_display(team_query: str):
    """Match UI team name to a row from team_stats_database_batch1.json."""
    data = load_team_stats()
    if not data or 'teams' not in data:
        return None
    return match_display_name_to_school_row(team_query, data['teams'], 'school')


# ─── Frontend ────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    """Serve the frontend"""
    return render_template('index.html')


# ─── API Endpoints ───────────────────────────────────────────────────────────

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({"status": "healthy", "message": "AI Scouting Report API is running"}), 200


@app.route('/api/generate-report', methods=['POST'])
def generate_report():
    try:
        # Support both JSON and multipart/form-data (for file upload)
        if request.is_json:
            data = request.json or {}
            opponent_name = data.get('opponent_name')
            sport = data.get('sport', 'soccer')
            date_range = data.get('date_range')
            video_url = data.get('video_url')
            video_file = None
        else:
            opponent_name = request.form.get('opponent_name')
            sport = request.form.get('sport', 'soccer')
            date_range = request.form.get('date_range')
            video_url = request.form.get('video_url') or None
            video_file = request.files.get('video_file')

        if not opponent_name:
            return jsonify({"error": "opponent_name is required"}), 400

        # Step 1: Scrape statistics
        print(f"Scraping statistics for {opponent_name}...")
        team_stats = scraper_service.scrape_team_stats(opponent_name, sport, date_range)

        # Step 2: Analyze video if provided (URL or uploaded file)
        video_insights = None
        if video_file and video_file.filename:
            # Save uploaded file to temp, then analyze
            ext = os.path.splitext(video_file.filename)[1] or '.mp4'
            fd, video_file_path = tempfile.mkstemp(suffix=ext)
            try:
                os.close(fd)
                video_file.save(video_file_path)
                print(f"Analyzing uploaded video: {video_file.filename}...")
                video_insights = twelvelabs_service.analyze_video(sport, video_file_path=video_file_path)
            finally:
                if video_file_path and os.path.exists(video_file_path):
                    os.remove(video_file_path)
        elif video_url:
            print(f"Analyzing video URL: {video_url}...")
            video_insights = twelvelabs_service.analyze_video(sport, video_url=video_url)

        # Step 3: Process data with OpenAI
        print("Processing data with OpenAI...")
        structured_data = openai_service.process_team_data(team_stats, video_insights, sport)

        # Step 4: Generate scouting report
        print("Generating scouting report...")
        scouting_report = claude_service.generate_scouting_report(opponent_name, structured_data, sport)

        # Create report object
        report = Report(
            opponent_name=opponent_name,
            sport=sport,
            statistics=team_stats,
            video_insights=video_insights,
            structured_analysis=structured_data,
            final_report=scouting_report
        )

        return jsonify(report.to_dict()), 200

    except Exception as e:
        print(f"Error generating report: {str(e)}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route('/api/analyze-video', methods=['POST'])
def analyze_video():
    try:
        data = request.json
        video_url = data.get('video_url')
        sport = data.get('sport', 'soccer')

        if not video_url:
            return jsonify({"error": "video_url is required"}), 400

        insights = twelvelabs_service.analyze_video(sport, video_url=video_url)
        return jsonify({"video_url": video_url, "sport": sport, "insights": insights}), 200

    except Exception as e:
        print(f"Error analyzing video: {str(e)}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route('/api/team-stats', methods=['GET'])
def get_team_stats_row():
    """
    Aggregated team totals from team_stats_database_batch1.json.
    Query: ?team=Vermont+Catamounts (full UI name).
    """
    team_q = request.args.get('team', '').strip()
    if not team_q:
        return jsonify({'error': 'team query required'}), 400
    row = find_team_stats_for_display(team_q)
    if not row:
        return jsonify({'error': 'not found'}), 404
    return jsonify(row), 200


@app.route('/api/scouting-master', methods=['GET'])
def get_scouting_master_team():
    """
    JSON slice for one team from master_scouting_database_cleaned.json.
    Query: ?team=Vermont+Catamounts (full UI team name).
    """
    team_q = request.args.get('team', '').strip()
    if not team_q:
        return jsonify({'error': 'team query required'}), 400
    row = find_master_team_for_display(team_q)
    if not row:
        return jsonify({'error': 'not found'}), 404
    return jsonify(row), 200


@app.route('/api/roster/<team_name>', methods=['GET'])
def get_roster(team_name):
    """Get roster data for a team from rosters.json"""
    try:
        rosters_path = os.path.join(os.path.dirname(__file__), '..', 'rosters.json')
        if not os.path.exists(rosters_path):
            return jsonify({"team_name": team_name, "roster": []}), 200
        with open(rosters_path, 'r') as f:
            rosters = json.load(f)
        # Try exact match first, then fuzzy match
        roster = rosters.get(team_name)
        if roster is None:
            for key in rosters:
                if team_name.lower() in key.lower() or key.lower() in team_name.lower():
                    roster = rosters[key]
                    break
        return jsonify({"team_name": team_name, "roster": roster or []}), 200
    except Exception as e:
        print(f"Error loading roster: {str(e)}")
        return jsonify({"team_name": team_name, "roster": []}), 200


@app.route('/api/scrape-stats', methods=['POST'])
def scrape_stats():
    try:
        data = request.json
        team_name = data.get('team_name')
        sport = data.get('sport', 'soccer')
        date_range = data.get('date_range')

        if not team_name:
            return jsonify({"error": "team_name is required"}), 400

        stats = scraper_service.scrape_team_stats(team_name, sport, date_range)
        return jsonify({"team_name": team_name, "sport": sport, "statistics": stats}), 200

    except Exception as e:
        print(f"Error scraping stats: {str(e)}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8000)
