import re
import json
from collections import defaultdict
from typing import List, Dict

from bot.utils.database import Database, RsvpStatus
from bot.api.models import SquadBuildRequest

# --- Constants & Configuration ---
CLASS_LIMITS = {
    "Officer": 1, "Medic": 1, "Support": 1, "Anti-Tank": 1,
    "Machine Gunner": 1, "Automatic Rifleman": 1, "Assault": 1, "Engineer": 1,
    "Spotter": 1, "Sniper": 1, "Tank Commander": 1, "Commander": 1,
    "Rifleman": 99, "Crewman": 99,
}

ROLE_PRIORITY = [
    "Officer", "Support", "Medic", "Anti-Tank", "Machine Gunner", "Automatic Rifleman",
    "Engineer", "Assault", "Rifleman", "Tank Commander", "Crewman", "Spotter", "Sniper"
]

# --- AI Helper Functions ---
def _calculate_suitability_score(player_stats: Dict, target_squad_type: str, target_role: str) -> float:
    RATING_WEIGHT = 0.60
    SQUAD_AFFINITY_WEIGHT = 0.15
    ROLE_AFFINITY_WEIGHT = 0.25

    rating = player_stats.get('rating', 50)
    affinities = player_stats.get('role_affinities', {})
    squad_counts = affinities.get('squad_types', {})
    role_counts = affinities.get('roles', {})

    total_squad_placements = sum(squad_counts.values())
    squad_affinity = (squad_counts.get(target_squad_type, 0) / total_squad_placements) if total_squad_placements > 0 else 0

    total_role_placements = sum(role_counts.values())
    role_affinity = (role_counts.get(target_role, 0) / total_role_placements) if total_role_placements > 0 else 0

    suitability_score = (
        (rating * RATING_WEIGHT) +
        (squad_affinity * 100 * SQUAD_AFFINITY_WEIGHT) +
        (role_affinity * 100 * ROLE_AFFINITY_WEIGHT)
    )
    return suitability_score

def get_squad_iteration(base_name: str, existing_names: List[str], convention: str, group_index: int) -> str:
    highest_count = 0
    for name in existing_names:
        if name.startswith(base_name):
            if convention == 'numeric':
                match = re.search(rf'\({group_index}\.(\d+)\)', name)
                if match:
                    highest_count = max(highest_count, int(match.group(1)))
            elif convention == 'alpha':
                match = re.search(r' ([A-Z])$', name)
                if match:
                    num = ord(match.group(1)) - ord('A') + 1
                    highest_count = max(highest_count, num)

    next_count = highest_count + 1
    
    if convention == 'numeric':
        return f"{base_name} ({group_index}.{next_count})"
    elif convention == 'alpha':
        iteration_char = chr(ord('A') + next_count - 1)
        return f"{base_name} {iteration_char}"
    else:
        return base_name

async def run_ai_draft(db: Database, event_id: int, request: SquadBuildRequest) -> List[Dict]:
    current_squads_list = await db.get_squads_with_members(event_id)
    current_squads_map = {s['name']: s for s in current_squads_list}
    
    template = await db.get_squad_template_by_id(request.template_id)
    if not template:
        raise ValueError("Squad template not found.")

    desired_squad_names = []
    squad_definitions_map = {}
    numeric_group_index = 1
    
    for definition in template['definitions']:
        base_name = definition['squad_name']
        convention = definition['naming_convention']
        group_index_for_naming = numeric_group_index if convention == 'numeric' else 0
        squad_definitions_map[base_name] = definition
        
        existing_names_for_type = [name for name in desired_squad_names if name.startswith(base_name)]
        for _ in range(request.squad_counts.get(base_name, 0)):
            new_name = get_squad_iteration(base_name, existing_names_for_type, convention, group_index_for_naming)
            desired_squad_names.append(new_name)
            existing_names_for_type.append(new_name)
        
        if convention == 'numeric':
            numeric_group_index += 1
            
    new_squads_map = {}
    available_players = []

    for squad_name, squad_data in current_squads_map.items():
        if squad_name in desired_squad_names:
            new_squads_map[squad_name] = squad_data['members']
        else:
            available_players.extend(squad_data['members'])

    available_players.sort(key=lambda p: ROLE_PRIORITY.index(p.get('assigned_role_name')) if p.get('assigned_role_name') in ROLE_PRIORITY else 99)

    for squad_name in desired_squad_names:
        if squad_name not in new_squads_map:
            base_name = re.split(r' \(\d', squad_name)[0].strip()
            definition = squad_definitions_map.get(base_name)
            if not definition: continue

            new_squad_members = []
            class_counts = defaultdict(int)
            squad_size = 6 if definition['squad_type'] == "Infantry" else 3 if definition['squad_type'] == "Armour" else 2
            
            remaining_available = []
            while len(new_squad_members) < squad_size and available_players:
                player = available_players.pop(0)
                player_class = player['assigned_role_name']
                if class_counts[player_class] < CLASS_LIMITS.get(player_class, 99):
                    new_squad_members.append(player)
                    class_counts[player_class] += 1
                else:
                    remaining_available.append(player)
            
            available_players = remaining_available + available_players
            new_squads_map[squad_name] = new_squad_members

    await db.delete_squads_for_event(event_id)
    
    for squad_name in desired_squad_names:
        base_name = re.split(r' \(\d', squad_name)[0].strip()
        definition = squad_definitions_map.get(base_name)
        if not definition: continue
        
        squad_id = await db.create_squad(event_id, squad_name, definition['squad_type'])
        for member in new_squads_map.get(squad_name, []):
            await db.add_squad_member(squad_id, int(member['user_id']), member['assigned_role_name'])

    reserves_id = await db.create_squad(event_id, "Reserves", "Reserves")
    for player in available_players:
        await db.add_squad_member(reserves_id, int(player['user_id']), player['assigned_role_name'])

    return await db.get_squads_with_members(event_id)
