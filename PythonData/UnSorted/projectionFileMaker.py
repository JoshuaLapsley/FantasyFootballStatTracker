import json

# Load the two projection files
with open("fantasypros_projections.json", "r") as f:
    standard_proj = json.load(f)

with open("fantasypros_projections_ppr.json", "r") as f:
    ppr_proj = json.load(f)

# Sum the projections
final_proj = {}

for player in set(list(standard_proj.keys()) + list(ppr_proj.keys())):
    final_proj[player] = {}
    weeks = set()
    if player in standard_proj:
        weeks.update(standard_proj[player].keys())
    if player in ppr_proj:
        weeks.update(ppr_proj[player].keys())
    
    for week in weeks:
        pts_standard = float(standard_proj.get(player, {}).get(week, 0.0))
        pts_ppr = float(ppr_proj.get(player, {}).get(week, 0.0))
        final_proj[player][week] = pts_standard + pts_ppr

# Save the final summed projections
with open("fantasypros_projFinal.json", "w") as f:
    json.dump(final_proj, f, indent=4)

print("Saved → fantasypros_projFinal.json")
