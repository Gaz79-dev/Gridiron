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
    "Spotter": 1, "Sniper": 1, "Tank Commander": 1,
    "Rifleman": 99, "Crewman": 99,
}

# The order in which roles should be prioritized when filling squads.
# This ensures essential roles are filled first.
ROLE_PRIORITY = [
    "Officer", "Support", "Medic", "Anti-Tank", "Machine Gunner", "Automatic Rifleman",
    "Engineer", "Assault", "Rifleman", "Tank Commander", "Crewman", "Spotter", "Sniper"
]

# --- AI Helper Functions ---

def _calculate_suitability_score(player_stats: Dict, target_squad_type: str, target_role: str) -> float:
    """
    Calculates a player's suitability for a specific role and squad type.
    This score is a weighted combination of their skill rating and their learned habits.
    """
    # Define the weights for each factor. These can be tuned.
    RATING_WEIGHT = 0.60  # 60% of the score comes from raw skill
    SQUAD_AFFINITY_WEIGHT = 0.15  # 15% from how often they play this squad type
    ROLE_AFFINITY_WEIGHT = 0.25   # 25% from how often they play this specific role

    # 1. Get the player's skill rating (defaults to 50 if not set)
    rating = player_stats.get('rating', 50)

    # 2. Get the player's learned affinities
    affinities = player_stats.get('role_affinities', {})
    squad_counts = affinities.get('squad_types', {})
    role_counts = affinities.get('roles', {})

    # 3. Calculate the affinity scores
    total_squad_placements = sum(squad_counts.values())
    squad_affinity = (squad_counts.get(target_squad_type, 0) / total_squad_placements) if total_squad_placements > 0 else 0

    total_role_placements = sum(role_counts.values())
    role_affinity = (role_counts.get(target_role, 0) / total_role_placements) if total_role_placements > 0 else 0

    # 4. Calculate the final weighted score
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
    else: # 'none' or any other value
        return squad_name

# --- Main AI Drafting Logic ---

async def run_ai_draft(db: Database, event_id: int, request: SquadBuildRequest) -> List[Dict]:
    """
    The core logic for drafting players into squads using the AI-driven
    "Suitability Score" to find the best fit for each slot.
    """
    # 1. SETUP: Clear old squads and get all necessary player data
    await db.delete_squads_for_event(event_id)
    
    signups = await db.get_signups_for_event(event_id)
    player_stats_records = await db.get_all_player_stats_for_admin()
    
    # Create a lookup map for player stats
    player_stats_map = {str(p['user_id']): p for p in player_stats_records}

    # Create the initial pool of available players who have accepted the event
    player_pool = [
        dict(s) for s in signups if s['rsvp_status'] == RsvpStatus.ACCEPTED
    ]

    # 2. SQUAD DEFINITION: Build the list of squads to be filled based on the template
    template = await db.get_squad_template_by_id(request.template_id)
    if not template:
        raise ValueError("Squad template not found.")
    
    squad_counts, squads_to_fill = {}, []
    numeric_group_index = 1
    for definition in template['definitions']:
        squad_name = definition['squad_name']
        convention = definition['naming_convention']
        count = request.squad_counts.get(squad_name, 0)

        group_index_for_naming = numeric_group_index if convention == 'numeric' else 0

        for _ in range(count):
            full_squad_name = get_squad_iteration(squad_name, squad_counts, convention, group_index_for_naming)
            squads_to_fill.append({
                'name': full_squad_name,
                'squad_type': definition['squad_type'],
                'source_pool': definition['source_rsvp_pool'],
                'members': [],
                'class_counts': defaultdict(int)
            })
        
        if convention == 'numeric':
            numeric_group_index += 1

    # 3. DRAFTING PHASE: Fill squads using the AI suitability score
    for squad in squads_to_fill:
        squad_size = 1 if squad['squad_type'] == "Command" else \
                     3 if squad['squad_type'] == "Armour" else \
                     2 if squad['squad_type'] in ["Recon", "Artillery"] else 6

        # Define the roles needed for this squad, in order of priority
        roles_to_fill = [role for role in ROLE_PRIORITY if CLASS_LIMITS.get(role, 0) > 0]

        for role in roles_to_fill:
            if len(squad['members']) >= squad_size:
                break
            if squad['class_counts'][role] >= CLASS_LIMITS.get(role, 99):
                continue

            best_player = None
            highest_score = -1

            # Find the best available player for this specific role
            for player in player_pool:
                player_stats = player_stats_map.get(str(player['user_id']), {})
                score = _calculate_suitability_score(player_stats, squad['squad_type'], role)
                
                if score > highest_score:
                    highest_score = score
                    best_player = player
            
            # If a suitable player was found, draft them
            if best_player:
                squad['members'].append(best_player)
                squad['class_counts'][role] += 1
                player_pool.remove(best_player)

    # 4. CLEANUP: Assign all remaining players to a "Reserves" squad
    reserves_squad = {
        'name': "Reserves",
        'squad_type': "Reserves",
        'members': player_pool,
        'class_counts': defaultdict(int)
    }
    squads_to_fill.append(reserves_squad)

    # 5. FINALIZATION: Write the newly created squads and members to the database
    for squad_data in squads_to_fill:
        squad_id = await db.create_squad(event_id, squad_data['name'], squad_data['squad_type'])
        for member in squad_data['members']:
            # The assigned role is determined by the AI draft, falling back to their sign-up choice
            assigned_role = next((role for role, count in squad_data['class_counts'].items() if any(m['user_id'] == member['user_id'] for m in squad_data['members'])), None)
            assigned_role = assigned_role or member.get('subclass_name') or member.get('role_name', 'Unassigned')
            await db.add_squad_member(squad_id, member['user_id'], assigned_role)

    # Return the final state from the database, which includes display names
    return await db.get_squads_with_members(event_id)
