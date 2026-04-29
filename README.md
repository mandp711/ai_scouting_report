# ai_scouting_report

NCAA men’s soccer scouting UI with a Flask backend. The scout page mixes AI-generated narratives (when API keys are set) with bundled team/player statistics and roster data so you can explore the UI locally.

## Prerequisites

- **Python 3.11+** (the repo was developed with Python 3.12)
- **`git`** (optional, only if cloning from a remote)

## 1. Get the code

Clone the repository or unpack the archive, then go to the project root:

```bash
cd project_showcase
```

## 2. Create a virtual environment (recommended)

From the **`backend`** directory:

```bash
cd backend
python3 -m venv venv
```

Activate it:

- **macOS / Linux:**
  ```bash
  source venv/bin/activate
  ```

- **Windows (Command Prompt):**
  ```cmd
  venv\Scripts\activate.bat
  ```

## 3. Install dependencies

Still inside **`backend`**, with the venv activated:

```bash
pip install -r requirements.txt
```

## 4. Environment variables

Create a file **`backend/.env`** in the **`backend`** folder (same folder as `app.py`).

Minimal example:

```bash
# Required for generating full AI reports (/api/generate-report) — OpenRouter
OPENROUTER_API_KEY=sk-or-v1-your-key-here

# Optional: video analysis (TwelveLabs). Omit or leave empty to skip video features.
TWELVELABS_API_KEY=

# Optional overrides used by some API clients
APP_NAME=AI_Scouting_Report
APP_URL=http://localhost:8000
```

- **`OPENROUTER_API_KEY`** — Used for structuring team data and writing the scouting report text. Without it, report generation may fail; the Scout page can still fall back to demo text in some flows.
- **`TWELVELABS_API_KEY`** — Only needed if you upload a video or pass a video URL for analysis.

Copy your real secrets into `.env`; do not commit `.env` (it is listed in `.gitignore`).

## 5. Run the app locally

From the **`backend`** directory, with the venv activated:

```bash
python app.py
```

The server binds to **all interfaces** on port **8000** (see `app.py`).

Open a browser to:

**[http://localhost:8000](http://localhost:8000)**

Health check:

**[http://localhost:8000/health](http://localhost:8000/health)**

### Alternative: Flask CLI

```bash
cd backend
source venv/bin/activate   # adjust for Windows as above
export FLASK_APP=app.py
flask run --host 0.0.0.0 --port 8000 --debug
```

## 6. Local data files (already in the repo)

These files power team stats, rosters, and player rows when you select a team:

| File | Role |
|------|------|
| `backend/team_stats_database_batch1.json` | Season team aggregates (win rate, goals, shots, etc.) |
| `backend/master_scouting_database_cleaned.json` | Per-player stats by team |
| `rosters.json` (project root) | Roster names/positions for `/api/roster` |

You do not need to regenerate them unless you are updating data.

### Optional: rebuild `rosters.json`

From the **project root** (one level above `backend`):

```bash
python roster_scraper.py
```

That writes **`rosters.json`** in the current directory; keep the project layout so `rosters.json` stays beside `backend/` as in the repo.

## Troubleshooting

- **Port already in use** — Stop the other process on port `8000`, or change the port in `app.py` (`app.run(..., port=...)`) / your `flask run` command.
- **Module not found** — Ensure the venv is activated and you ran `pip install -r requirements.txt` from **`backend`**.
- **`.env` not loaded** — Start the app from **`backend`** so `python-dotenv` picks up **`backend/.env`**.
