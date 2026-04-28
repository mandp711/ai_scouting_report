import json

# --- 1. ENTER YOUR EXACT FILE NAMES HERE ---
FILE_1 = "rosters_pos_stats_batch1_gemini.json"  # Your V1 successful scrape
FILE_2 = "rosters_pos_stats_batch2_gemini.json"                 # Your V2 table scrape
FILE_3 = "rosters_pos_stats_batch3_gemini.json"          # CHANGE THIS to your 3rd file's name
MASTER_OUTPUT = "master_scouting_database.json"

def merge_databases():
    print("Loading databases...")
    
    # Load all three JSON files
    with open(FILE_1, "r", encoding="utf-8") as f1:
        data1 = json.load(f1)
    with open(FILE_2, "r", encoding="utf-8") as f2:
        data2 = json.load(f2)
    with open(FILE_3, "r", encoding="utf-8") as f3:
        data3 = json.load(f3)

    # Extract the 'teams' arrays from each file
    teams1 = data1.get("teams", [])
    teams2 = data2.get("teams", [])
    teams3 = data3.get("teams", [])

    # Combine all teams into one massive list
    combined_teams = teams1 + teams2 + teams3

    # Create the clean master structure for your frontend
    master_data = {
        "season": "2025",
        "total_teams": len(combined_teams),
        "teams": combined_teams
    }

    # Save it to the final master file
    with open(MASTER_OUTPUT, "w", encoding="utf-8") as out:
        json.dump(master_data, out, indent=2, ensure_ascii=False)

    # Print out a receipt so you know the math matches up
    print("\n" + "="*40)
    print("MERGE COMPLETE!")
    print(f"File 1 Teams: {len(teams1)}")
    print(f"File 2 Teams: {len(teams2)}")
    print(f"File 3 Teams: {len(teams3)}")
    print(f"Total Teams in Master Database: {len(combined_teams)}")
    print(f"Saved to: {MASTER_OUTPUT}")
    print("="*40)

if __name__ == "__main__":
    merge_databases()