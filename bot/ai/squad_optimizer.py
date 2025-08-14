from collections import defaultdict
from typing import List, Dict, Optional
import json

# Use absolute imports from the 'bot' package root
from bot.utils.database import Database, RsvpStatus
from bot.api.models import SquadBuildRequest

# --- Constants & Configuration ---

# Hell Let Loose class limits per squad
CLASS_LIMITS = {
    "Officer": 1, "Medic": 1, "Support": 1, "Anti-Tank": 1,
    "Machine Gunner": 1, "Automatic Rifleman": 1, "Assault": 1, "Engineer": 1,
    "Spotter": 1, "Sniper": 1, "Tank Commander": 1, "Commander": 1,
    "Rifleman": 99, "Crewman": 99,
}

# The order in which roles should be prioritized when filling squads.
ROLE_PRIORITY = [
    "Officer", "Support", "Medic", "Anti-Tank", "Machine Gunner", "Automatic Rifleman",
    "Engineer", "Assault", "Rifleman", "Tank Commander", "Crewman", "Spotter", "Sniper"
]

# --- AI Helper Functions ---

def _calculate_suitability_score(player_stats: Dict, target_squad_type: str, target_role: str) -> float:
    """
    Calculates a player's suitability for a specific role and squad type.
    """
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

def get_squad_iteration(squad_name: str, counts: Dict, convention: str, group_index: int) -> str:
    """Gets the next iteration for a squad name based on the convention."""
    counts[squad_name] = counts.get(squad_name, 0) + 1
    count = counts[squad_name]
    
    if convention == 'numeric':
        return f"{squad_name} ({group_index}.{count})"
    elif convention == 'alpha':
        iteration_char = chr(ord('A') + count - 1) if count <= 26 else f"Z{count - 26}"
        return f"{squad_name} {iteration_char}"
    else:
        return squad_name

# --- Main AI Drafting Logic ---

async def run_ai_draft(db: Database, event_id: int, request: SquadBuildRequest) -> List[Dict]:
    """
    Incrementally adjusts squads based on new counts, rather than doing a full rebuild.
    """
    # 1. GET CURRENT & DESIRED STATE
    current_squads = await db.get_squads_with_members(event_id)
    template = await db.get_squad_template_by_id(request.template_id)
    if not template:
        raise ValueError("Squad template not found.")

    # Ensure a reserves squad exists, as it's critical for moves
    reserves_squad = await db.get_reserves_squad(event_id)
    if not reserves_squad:
        reserves_id = await db.create_squad(event_id, "Reserves", "Reserves")
        reserves_squad = {'squad_id': reserves_id}

    # 2. PROCESS EACH SQUAD TYPE (INFANTRY, ARMOUR, ETC.)
    squad_name_definitions = {definition['squad_name']: definition for definition in template['definitions']}

    for base_name, definition in squad_name_definitions.items():
        current_squads_of_type = sorted(
            [s for s in current_squads if s['name'].startswith(base_name)],
            key=lambda s: s['name']
        )
        current_count = len(current_squads_of_type)
        new_count = request.squad_counts.get(base_name, 0)

        # --- HANDLE SQUAD REMOVAL ---
        if new_count < current_count:
            num_to_remove = current_count - new_count
            squads_to_remove = current_squads_of_type[-num_to_remove:] # Get the last N squads
            
            for squad in squads_to_remove:
                members_to_move = await db.get_squad_members(squad['squad_id'])
                for member in members_to_move:
                    await db.move_squad_member(member['squad_member_id'], reserves_squad['squad_id'])
                await db.delete_squad(squad['squad_id'])
            print(f"Removed {num_to_remove} squad(s) of type {base_name} and moved players to reserves.")

        # --- HANDLE SQUAD ADDITION ---
        elif new_count > current_count:
            num_to_add = new_count - current_count
            reserves_members = [m for s in current_squads if s['name'] == 'Reserves' for m in s['members']]
            
            # Prioritize players who signed up for the correct role
            reserves_members.sort(key=lambda p: ROLE_PRIORITY.index(p.get('assigned_role_name')) if p.get('assigned_role_name') in ROLE_PRIORITY else 99)

            squad_name_counts = {base_name: current_count}
            
            for i in range(num_to_add):
                new_squad_name = get_squad_iteration(base_name, squad_name_counts, definition['naming_convention'], 0)
                new_squad_id = await db.create_squad(event_id, new_squad_name, definition['squad_type'])
                
                # Fill the new squad from reserves
                squad_size = 6 if definition['squad_type'] == "Infantry" else 3 if definition['squad_type'] == "Armour" else 2
                class_counts = defaultdict(int)
                
                players_for_new_squad = []
                temp_reserves = []

                while len(players_for_new_squad) < squad_size and reserves_members:
                    player = reserves_members.pop(0)
                    player_class = player['assigned_role_name']
                    
                    if class_counts[player_class] < CLASS_LIMITS.get(player_class, 99):
                        await db.move_squad_member(player['squad_member_id'], new_squad_id)
                        class_counts[player_class] += 1
                        players_for_new_squad.append(player)
                    else:
                        temp_reserves.append(player)
                
                reserves_members = temp_reserves + reserves_members # Add unplaced players back to the pool
            print(f"Added {num_to_add} squad(s) of type {base_name}, filled from reserves.")

    return await db.get_squads_with_members(event_id)
