#!/usr/bin/env python3
"""
Action Pattern Analyzer - Compare action code patterns between players with different death counts

Strategy: Players don't disappear when dead, but their ACTION CODE PATTERNS should change.
Compare players with 0 deaths (Phinn) vs players with multiple deaths (Yates=4, Caine=4, Amael=3)
to identify death-related action codes.

Truth Data:
- Phinn: 0 deaths (control group)
- Yates: 4 deaths
- Caine: 4 deaths
- Amael: 3 deaths
- Petal: 2 deaths
- Baron: 2 deaths
"""

import sys
import json
from pathlib import Path
from collections import Counter, defaultdict
from typing import Dict, List, Any

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

EVENT_SIZE = 37

PLAYER_ENTITIES = {
    56325: "Phinn",    # 0 deaths - CONTROL
    56581: "Yates",    # 4 deaths
    56837: "Caine",    # 4 deaths
    57093: "Petal",    # 2 deaths
    57349: "Amael",    # 3 deaths
    57605: "Baron"     # 2 deaths
}

DEATH_COUNTS = {
    "Phinn": 0,  # CONTROL
    "Yates": 4,
    "Caine": 4,
    "Petal": 2,
    "Amael": 3,
    "Baron": 2
}

def parse_events_from_frame(frame_data: bytes) -> List[Dict[str, Any]]:
    """Parse all events from a frame."""
    events = []
    offset = 0

    while offset + EVENT_SIZE <= len(frame_data):
        entity_id = int.from_bytes(frame_data[offset:offset+2], 'little')
        action_code = frame_data[offset+4]

        events.append({
            'entity_id': entity_id,
            'action_code': action_code
        })

        offset += EVENT_SIZE

    return events

def load_all_frames(replay_dir: Path, replay_name: str) -> Dict[int, bytes]:
    """Load all frames."""
    frames = {}
    for i in range(200):
        frame_path = replay_dir / f"{replay_name}.{i}.vgr"
        if not frame_path.exists():
            break
        frames[i] = frame_path.read_bytes()
    return frames

def analyze_player_actions(all_frames: Dict[int, bytes], entity_id: int) -> Counter:
    """Count all action codes for a specific player across all frames."""
    action_counts = Counter()

    for frame_data in all_frames.values():
        events = parse_events_from_frame(frame_data)
        for event in events:
            if event['entity_id'] == entity_id:
                action_counts[event['action_code']] += 1

    return action_counts

def find_death_correlated_actions(
    player_actions: Dict[str, Counter],
    death_counts: Dict[str, int]
) -> List[Dict[str, Any]]:
    """
    Find action codes that correlate with death count.

    Hypothesis: If an action code appears N times for a player with N deaths,
    it's likely a death marker.
    """
    candidates = []

    for player, actions in player_actions.items():
        player_deaths = death_counts[player]

        for action_code, count in actions.items():
            # Check if count matches death count (±1 tolerance)
            if player_deaths > 0 and abs(count - player_deaths) <= 1:
                candidates.append({
                    'player': player,
                    'entity_id': [k for k, v in PLAYER_ENTITIES.items() if v == player][0],
                    'action_code': f"0x{action_code:02X}",
                    'count': count,
                    'deaths': player_deaths,
                    'match': 'exact' if count == player_deaths else 'close'
                })

    return candidates

def compare_action_frequencies(
    control_actions: Counter,
    death_actions: Dict[str, Counter],
    min_deaths: int = 2
) -> List[Dict[str, Any]]:
    """
    Compare action frequencies between control (0 deaths) and players with deaths.

    Find actions that appear in death players but NOT in control.
    """
    # Get players with at least min_deaths
    high_death_players = {
        player: actions
        for player, actions in death_actions.items()
        if DEATH_COUNTS[player] >= min_deaths
    }

    # Actions that appear in control
    control_action_set = set(control_actions.keys())

    unique_to_death = []

    for player, actions in high_death_players.items():
        for action_code, count in actions.items():
            # Skip if this action also appears in control (especially high frequency)
            if action_code in control_action_set and control_actions[action_code] > 10:
                continue

            # Action appears in death player but not (or rarely) in control
            control_count = control_actions.get(action_code, 0)

            if count >= 2 and control_count <= 1:
                unique_to_death.append({
                    'action_code': f"0x{action_code:02X}",
                    'player': player,
                    'player_deaths': DEATH_COUNTS[player],
                    'count_in_player': count,
                    'count_in_control': control_count
                })

    return unique_to_death

def analyze_action_ratio(
    player_actions: Dict[str, Counter]
) -> List[Dict[str, Any]]:
    """
    Find action codes where count/deaths ratio is consistent across multiple players.

    If multiple players have action_count ≈ death_count, it's likely a death marker.
    """
    action_death_ratios = defaultdict(list)

    for player, actions in player_actions.items():
        deaths = DEATH_COUNTS[player]
        if deaths == 0:
            continue

        for action_code, count in actions.items():
            ratio = count / deaths
            action_death_ratios[action_code].append({
                'player': player,
                'deaths': deaths,
                'count': count,
                'ratio': ratio
            })

    # Find actions with consistent ratios across players
    consistent_actions = []

    for action_code, ratios in action_death_ratios.items():
        if len(ratios) < 2:
            continue

        # Calculate mean and std of ratios
        ratio_values = [r['ratio'] for r in ratios]
        mean_ratio = sum(ratio_values) / len(ratio_values)

        # Check if ratio is close to 1.0 (count ≈ deaths) or 2.0 (count ≈ 2*deaths)
        if 0.8 <= mean_ratio <= 1.2 or 1.8 <= mean_ratio <= 2.2:
            consistent_actions.append({
                'action_code': f"0x{action_code:02X}",
                'mean_ratio': mean_ratio,
                'players': len(ratios),
                'details': ratios
            })

    return sorted(consistent_actions, key=lambda x: abs(x['mean_ratio'] - 1.0))

def main():
    print("[STAGE:begin:data_loading]")

    replay_dir = Path("D:/Desktop/My Folder/Game/VG/vg replay/21.11.04/cache/")
    replay_name = "8fc12404-6151-11eb-afe2-061b3d1d141d-9de666b6-299f-4503-bf4b-4c7b351847f4"

    all_frames = load_all_frames(replay_dir, replay_name)
    print(f"[DATA] Loaded {len(all_frames)} frames")

    print("[STAGE:status:success]")
    print("[STAGE:end:data_loading]")

    print("\n[STAGE:begin:action_counting]")

    # Analyze action patterns for each player
    player_actions = {}

    for entity_id, player_name in sorted(PLAYER_ENTITIES.items()):
        actions = analyze_player_actions(all_frames, entity_id)
        player_actions[player_name] = actions

        total_events = sum(actions.values())
        unique_actions = len(actions)

        print(f"[DATA] {player_name} ({entity_id}): {total_events} events, {unique_actions} unique actions, {DEATH_COUNTS[player_name]} deaths")

    print("[STAGE:status:success]")
    print("[STAGE:end:action_counting]")

    print("\n[STAGE:begin:death_correlation]")

    # Find actions that match death counts
    death_matches = find_death_correlated_actions(player_actions, DEATH_COUNTS)

    print(f"[FINDING] Found {len(death_matches)} action codes with counts matching death counts:")

    for match in sorted(death_matches, key=lambda x: (x['deaths'], x['player'])):
        print(f"  {match['player']}: {match['action_code']} count={match['count']} deaths={match['deaths']} [{match['match']}]")

    print("[STAGE:status:success]")
    print("[STAGE:end:death_correlation]")

    print("\n[STAGE:begin:control_comparison]")

    # Compare to control (Phinn with 0 deaths)
    control_actions = player_actions["Phinn"]
    death_player_actions = {k: v for k, v in player_actions.items() if k != "Phinn"}

    unique_death_actions = compare_action_frequencies(control_actions, death_player_actions, min_deaths=2)

    print(f"[FINDING] Found {len(unique_death_actions)} actions unique to death players (absent in Phinn):")

    for action in sorted(unique_death_actions, key=lambda x: x['count_in_player'], reverse=True):
        print(f"  {action['action_code']}: {action['player']} (deaths={action['player_deaths']}) "
              f"count={action['count_in_player']}, control={action['count_in_control']}")

    print("[STAGE:status:success]")
    print("[STAGE:end:control_comparison]")

    print("\n[STAGE:begin:ratio_analysis]")

    # Analyze count/deaths ratios
    consistent_ratios = analyze_action_ratio(player_actions)

    print(f"[FINDING] Found {len(consistent_ratios)} actions with consistent count/death ratios:")

    for action in consistent_ratios[:10]:
        print(f"  {action['action_code']}: mean_ratio={action['mean_ratio']:.2f} across {action['players']} players")
        for detail in action['details']:
            print(f"    {detail['player']}: {detail['count']} events / {detail['deaths']} deaths = {detail['ratio']:.2f}")

    print("[STAGE:status:success]")
    print("[STAGE:end:ratio_analysis]")

    print("\n[STAGE:begin:output_generation]")

    output = {
        'player_action_summary': {
            player: {
                'total_events': sum(actions.values()),
                'unique_actions': len(actions),
                'deaths': DEATH_COUNTS[player],
                'top_actions': [
                    {'action': f"0x{code:02X}", 'count': count}
                    for code, count in actions.most_common(20)
                ]
            }
            for player, actions in player_actions.items()
        },
        'death_count_matches': death_matches,
        'unique_to_death_players': unique_death_actions,
        'consistent_ratios': consistent_ratios
    }

    output_path = Path("vg/output/action_pattern_analysis.json")
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"[FINDING] Results saved to {output_path}")

    print("[STAGE:status:success]")
    print("[STAGE:end:output_generation]")

    print("\n" + "="*80)
    print("ACTION PATTERN ANALYSIS COMPLETE")
    print("="*80)
    print(f"Death count matches: {len(death_matches)}")
    print(f"Unique to death players: {len(unique_death_actions)}")
    print(f"Consistent ratios: {len(consistent_ratios)}")
    print("="*80)

if __name__ == '__main__':
    main()
