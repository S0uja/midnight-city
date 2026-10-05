"""Family relationship interaction policy for Midnight City.

This module contains only the family-role guard used by the interaction
handler. It returns a response dictionary when an interaction is blocked,
otherwise None so the normal interaction flow can continue.
"""


BLOCKED_FAMILY_INTERACTIONS = {'flirt', 'hug', 'kiss', 'intimacy', 'date'}


def check_family_role_interaction(rel, engine_type, target_name, sim_minutes):
    """Block romantic/intimate interaction types for family relationships."""
    family_role = str((rel or {}).get('family_role') or '')
    if not family_role or engine_type not in BLOCKED_FAMILY_INTERACTIONS:
        return None

    return {
        'ok': True,
        'accepted': False,
        'interaction': engine_type,
        'target_name': target_name,
        'message': f'{target_name}: Это неуместно между нами.',
        'dialogue': 'Давай без этого. Мы семья — я отношусь к тебе по-семейному.',
        'speaker': target_name,
        'sim_minutes': sim_minutes,
    }
