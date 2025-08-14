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

import re # Add this import at the top of your file

def get_squad_iteration(base_name: str, existing_names: List[str], convention: str, group_index: int) -> str:
    """Gets the next available name for a squad, avoiding collisions."""
    # Find the highest existing count for this base name and group index
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
                    # Convert letter back to a number (A=1, B=2)
                    num = ord(match.group(1)) - ord('A') + 1
                    highest_count = max(highest_count, num)

    next_count = highest_count + 1
    
    if convention == 'numeric':
        return f"{base_name} ({group_index}.{next_count})"
    elif convention == 'alpha':
        iteration_char = chr(ord('A') + next_count - 1)
        return f"{base_name} {iteration_char}"
    else: # 'none'
        return base_name

async def run_ai_draft(db: Database, event_id: int, request: SquadBuildRequest) -> List[Dict]:
    """
    Incrementally rebuilds squads using a reconciliation approach that respects template order,
    player RSVP pools, and HLL class limits.
    """
    # 1. GET CURRENT & DESIRED STATE
    current_squads_list = await db.get_squads_with_members(event_id)
    current_squads_map = {s['name']: s for s in current_squads_list}
    player_stats_records = await db.get_all_players_for_admin_panel()
    player_stats_map = {str(p['user_id']): p for p in player_stats_records}
    
    template = await db.get_squad_template_by_id(request.template_id)
    if not template:
        raise ValueError("Squad template not found.")

    # 2. CALCULATE THE DESIRED SQUAD LAYOUT IN THE CORRECT ORDER
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
            
    # 3. RECONCILE: Preserve existing squads and create a pool of available players
    new_squads_map = {}
    available_players = []

    for squad_name, squad_data in current_squads_map.items():
        if squad_name in desired_squad_names:
            new_squads_map[squad_name] = squad_data['members']
        else:
            available_players.extend(squad_data['members'])

    # Re-sort available players into their RSVP pools
    available_player_pools = defaultdict(list)
    for player in available_players:
        # We need the full signup record for the role_name, so we fetch it again
        # This is inefficient, but necessary with the current data structure
        signup_record = await db.get_signup(event_id, int(player['user_id']))
        if signup_record:
            pool_key = signup_record.get('role_name') or "Unassigned"
            # Combine the signup data with the member data
            full_player_data = {**player, **signup_record}
            available_player_pools[pool_key].append(full_player_data)

    # 4. FILL NEWLY CREATED SQUADS using a squad-centric approach
    for squad_name in desired_squad_names:
        if squad_name not in new_squads_map:
            base_name = re.split(r' \(\d', squad_name)[0].strip()
            definition = squad_definitions_map.get(base_name)
            if not definition: continue

            new_squad_members = []
            class_counts = defaultdict(int)
            squad_size = 6 if definition['squad_type'] == "Infantry" else 3 if definition['squad_type'] == "Armour" else 2
            
            # Get the correct pool of players for this squad
            eligible_players = available_player_pools[definition['source_rsvp_pool']]
            
            roles_to_fill = ROLE_PRIORITY
            if definition['squad_type'] == "Armour":
                roles_to_fill = ["Tank Commander", "Crewman"]
            elif definition['squad_type'] == "Recon":
                roles_to_fill = ["Spotter", "Sniper"]
            
            # Fill the squad role-by-role using AI score
            for role in roles_to_fill:
                if len(new_squad_members) >= squad_size: break
                if class_counts[role] >= CLASS_LIMITS.get(role, 99): continue

                best_player = None
                highest_score = -1
                for player in eligible_players:
                    player_stats = player_stats_map.get(str(player['user_id']), {})
                    score = _calculate_suitability_score(player_stats, definition['squad_type'], role)
                    if score > highest_score:
                        highest_score = score
                        best_player = player
                
                if best_player:
                    new_squad_members.append(best_player)
                    class_counts[role] += 1
                    eligible_players.remove(best_player)
            
            new_squads_map[squad_name] = new_squad_members

    # 5. COMMIT CHANGES TO DATABASE
    await db.delete_squads_for_event(event_id)
    
    for squad_name in desired_squad_names:
        base_name = re.split(r' \(\d', squad_name)[0].strip()
        definition = squad_definitions_map.get(base_name)
        if not definition: continue
        
        squad_id = await db.create_squad(event_id, squad_name, definition['squad_type'])
        for member in new_squads_map.get(squad_name, []):
            # The member object could be from get_squads_with_members OR get_signups_for_roster_page
            assigned_role = member.get('assigned_role_name') or member.get('subclass_name') or 'Unassigned'
            await db.add_squad_member(squad_id, int(member['user_id']), assigned_role)

    # Add any leftover players to a new Reserves squad
    reserves_id = await db.create_squad(event_id, "Reserves", "Reserves")
    remaining_players = [p for pool in available_player_pools.values() for p in pool]
    for player in remaining_players:
        assigned_role = player.get('assigned_role_name') or player.get('subclass_name') or 'Unassigned'
        await db.add_squad_member(reserves_id, int(player['user_id']), assigned_role)

    return await db.get_squads_with_members(event_id)
