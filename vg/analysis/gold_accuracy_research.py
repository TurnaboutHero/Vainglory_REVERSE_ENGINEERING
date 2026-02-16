#!/usr/bin/env python3
"""
Gold Accuracy Research - Systematic exploration of gold detection improvement.

Current baseline: action=0x06 positive credits → 91.9% within ±10%, 42.4% within ±5%

Research questions:
1. Which action bytes contribute to gold income?
2. What's the optimal combination of action bytes?
3. Is the error systematic (under/over) or random?
4. Can we reach ±5% > 80% accuracy target?

Action byte mapping (known from credit records):
- 0x06: gold income (CURRENT, r=0.98 correlation)
- 0x08: passive gold (periodic trickle)
- 0x0E: minion kill credit (value=1.0)
- 0x0F: minion gold
- 0x0D: jungle kill
- 0x04: turret/objective bounty
"""

import json
import struct
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Set, Tuple

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from vg.core.unified_decoder import UnifiedDecoder, _le_to_be

# Credit header
CREDIT_HEADER = bytes([0x10, 0x04, 0x1D])


def load_truth_data(truth_path: str) -> Dict:
    """Load tournament truth JSON."""
    with open(truth_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_all_frames(replay_path: str) -> bytes:
    """Load all frame files concatenated."""
    replay_file = Path(replay_path)
    frame_dir = replay_file.parent
    frame_name = replay_file.stem.rsplit('.', 1)[0]

    frame_files = list(frame_dir.glob(f"{frame_name}.*.vgr"))
    if not frame_files:
        return b""

    def _idx(p: Path) -> int:
        try:
            return int(p.stem.split('.')[-1])
        except ValueError:
            return 0

    frame_files.sort(key=_idx)
    return b"".join(f.read_bytes() for f in frame_files)


def extract_gold_by_action(
    all_data: bytes,
    valid_eids: Set[int],
) -> Dict[int, Dict[int, float]]:
    """
    Extract gold credits grouped by action byte.

    Returns:
        {eid: {action_byte: total_gold}}
    """
    gold_by_action: Dict[int, Dict[int, float]] = defaultdict(lambda: defaultdict(float))

    pos = 0
    while True:
        pos = all_data.find(CREDIT_HEADER, pos)
        if pos == -1:
            break
        if pos + 12 > len(all_data):
            pos += 1
            continue
        if all_data[pos + 3:pos + 5] != b'\x00\x00':
            pos += 1
            continue

        eid = struct.unpack_from(">H", all_data, pos + 5)[0]
        if eid not in valid_eids:
            pos += 3
            continue

        value = struct.unpack_from(">f", all_data, pos + 7)[0]
        action = all_data[pos + 11]

        # Only count positive values (earned gold, not spent)
        if value > 0 and value < 50000:  # Sanity check
            gold_by_action[eid][action] += value

        pos += 3

    return gold_by_action


def compute_accuracy(
    detected_gold: float,
    truth_gold: int,
) -> Tuple[float, float, float]:
    """
    Compute error metrics.

    Returns:
        (error_abs, error_pct, within_5pct)
    """
    if truth_gold == 0:
        return 0.0, 0.0, False

    error_abs = detected_gold - truth_gold
    error_pct = abs(error_abs) / truth_gold * 100
    within_5 = error_pct <= 5.0
    within_10 = error_pct <= 10.0

    return error_abs, error_pct, within_5, within_10


def evaluate_formula(
    match_player_data: List[Dict],
    action_combo: List[int],
    formula_name: str,
) -> Dict:
    """
    Evaluate a gold formula (combination of action bytes).

    Args:
        match_player_data: List of {player, gold_by_action, truth_gold}
        action_combo: List of action bytes to sum
        formula_name: Human-readable name

    Returns:
        Stats dict with accuracy metrics
    """
    errors = []
    within_5 = 0
    within_10 = 0
    total_players = len(match_player_data)

    for player_data in match_player_data:
        truth_gold = player_data['truth_gold']
        detected = sum(
            player_data['gold_by_action'].get(action, 0.0)
            for action in action_combo
        )

        err_abs, err_pct, w5, w10 = compute_accuracy(detected, truth_gold)
        errors.append({
            'match': player_data['match'],
            'player': player_data['player'],
            'detected': round(detected),
            'truth': truth_gold,
            'error_abs': round(err_abs),
            'error_pct': round(err_pct, 2),
        })
        if w5:
            within_5 += 1
        if w10:
            within_10 += 1

    # Compute aggregate stats
    avg_error = sum(e['error_abs'] for e in errors) / len(errors)
    avg_error_pct = sum(e['error_pct'] for e in errors) / len(errors)

    return {
        'formula': formula_name,
        'actions': action_combo,
        'total_players': total_players,
        'within_5pct': within_5,
        'within_10pct': within_10,
        'accuracy_5pct': round(within_5 / total_players * 100, 1),
        'accuracy_10pct': round(within_10 / total_players * 100, 1),
        'avg_error_abs': round(avg_error),
        'avg_error_pct': round(avg_error_pct, 2),
        'errors': errors,
    }


def main():
    print("[OBJECTIVE] Systematic gold detection improvement research\n")

    # Paths
    truth_path = Path(__file__).parent.parent / "output" / "tournament_truth.json"
    replay_base = Path(r"D:\Desktop\My Folder\Game\VG\vg replay\Tournament_Replays")

    # Load truth
    truth_data = load_truth_data(str(truth_path))
    print(f"[DATA] Loaded {len(truth_data['matches'])} matches from truth data")

    # Collect per-match data (entity IDs are unique per match!)
    # Structure: {match_idx: {player_name: {detected_gold_by_action, truth_gold}}}
    match_player_data: List[Dict] = []

    print("\n[STAGE:begin:data_collection]")
    processed = 0
    for match_data in truth_data['matches']:
        replay_file = match_data['replay_file']
        if not Path(replay_file).exists():
            print(f"  Skipping missing replay: {replay_file}")
            continue

        # Decode to get entity IDs
        decoder = UnifiedDecoder(replay_file)
        decoded = decoder.decode()

        # Build eid map
        eid_map = {}
        for player in decoded.all_players:
            eid_be = _le_to_be(player.entity_id)
            eid_map[eid_be] = player.name

        # Load frames
        all_data = load_all_frames(replay_file)
        if not all_data:
            print(f"  No frames for {decoded.replay_name}")
            continue

        # Extract gold by action for this match
        gold_by_action = extract_gold_by_action(all_data, set(eid_map.keys()))

        # Build per-player data for this match
        truth_players = match_data.get('players', {})
        for eid, player_name in eid_map.items():
            tp = truth_players.get(player_name, {})
            if 'gold' in tp:
                match_player_data.append({
                    'match': decoded.replay_name,
                    'player': player_name,
                    'gold_by_action': dict(gold_by_action.get(eid, {})),
                    'truth_gold': tp['gold'],
                })

        processed += 1
        print(f"  [{processed}/{len(truth_data['matches'])}] Processed {decoded.replay_name}")

    print(f"[STAGE:status:success]")
    print(f"[STAGE:end:data_collection]")
    print(f"\n[DATA] Collected gold data for {len(match_player_data)} players across {processed} matches")

    # Discover which action bytes are present
    print("\n[STAGE:begin:action_byte_discovery]")
    all_actions = set()
    for player_data in match_player_data:
        all_actions.update(player_data['gold_by_action'].keys())

    print(f"[FINDING] Action bytes present in data: {sorted(all_actions)}")

    # Show action byte contribution statistics
    print("\n[FINDING] Gold contribution by action byte:")
    action_totals = defaultdict(float)
    for player_data in match_player_data:
        for action, value in player_data['gold_by_action'].items():
            action_totals[action] += value

    for action in sorted(action_totals.keys()):
        total = action_totals[action]
        avg = total / len(match_player_data)
        print(f"  [STAT:action_{action:02X}_total] {round(total):,}")
        print(f"  [STAT:action_{action:02X}_avg_per_player] {round(avg)}")

    print(f"[STAGE:status:success]")
    print(f"[STAGE:end:action_byte_discovery]")

    # Test different formulas
    print("\n[STAGE:begin:formula_testing]")

    formulas = [
        ([0x06], "Current (0x06 only)"),
        ([0x06, 0x08], "0x06 + 0x08 (income + passive)"),
        ([0x06, 0x0F], "0x06 + 0x0F (income + minion gold)"),
        ([0x06, 0x0D], "0x06 + 0x0D (income + jungle)"),
        ([0x06, 0x04], "0x06 + 0x04 (income + objective)"),
        ([0x06, 0x08, 0x0F], "0x06 + 0x08 + 0x0F (income + passive + minion)"),
        ([0x06, 0x08, 0x0D], "0x06 + 0x08 + 0x0D (income + passive + jungle)"),
        ([0x06, 0x08, 0x04], "0x06 + 0x08 + 0x04 (income + passive + objective)"),
        ([0x06, 0x0F, 0x0D], "0x06 + 0x0F + 0x0D (income + minion + jungle)"),
        ([0x06, 0x08, 0x0F, 0x0D], "0x06 + 0x08 + 0x0F + 0x0D (all non-objective)"),
        ([0x06, 0x08, 0x0F, 0x0D, 0x04], "All action bytes"),
    ]

    results = []
    for actions, name in formulas:
        result = evaluate_formula(match_player_data, actions, name)
        results.append(result)

        print(f"\n[FINDING] {name}")
        print(f"  [STAT:accuracy_5pct] {result['accuracy_5pct']}% ({result['within_5pct']}/{result['total_players']})")
        print(f"  [STAT:accuracy_10pct] {result['accuracy_10pct']}% ({result['within_10pct']}/{result['total_players']})")
        print(f"  [STAT:avg_error] {result['avg_error_abs']} gold ({result['avg_error_pct']}%)")

    print(f"\n[STAGE:status:success]")
    print(f"[STAGE:end:formula_testing]")

    # Find best formula
    print("\n[STAGE:begin:best_formula_selection]")
    best_5 = max(results, key=lambda r: r['accuracy_5pct'])
    best_10 = max(results, key=lambda r: r['accuracy_10pct'])

    print(f"[FINDING] Best formula for ±5% accuracy: {best_5['formula']}")
    print(f"  [STAT:best_5pct_accuracy] {best_5['accuracy_5pct']}%")
    print(f"  Actions: {[f'0x{a:02X}' for a in best_5['actions']]}")

    print(f"\n[FINDING] Best formula for ±10% accuracy: {best_10['formula']}")
    print(f"  [STAT:best_10pct_accuracy] {best_10['accuracy_10pct']}%")
    print(f"  Actions: {[f'0x{a:02X}' for a in best_10['actions']]}")

    # Error pattern analysis
    print(f"\n[FINDING] Error pattern analysis for best formula ({best_5['formula']}):")
    errors = best_5['errors']
    positive_errors = [e for e in errors if e['error_abs'] > 0]
    negative_errors = [e for e in errors if e['error_abs'] < 0]

    print(f"  [STAT:overestimations] {len(positive_errors)} players (detected > truth)")
    print(f"  [STAT:underestimations] {len(negative_errors)} players (detected < truth)")

    if positive_errors:
        avg_over = sum(e['error_abs'] for e in positive_errors) / len(positive_errors)
        print(f"  [STAT:avg_overestimation] {round(avg_over)} gold")

    if negative_errors:
        avg_under = sum(abs(e['error_abs']) for e in negative_errors) / len(negative_errors)
        print(f"  [STAT:avg_underestimation] {round(avg_under)} gold")

    print(f"\n[STAGE:status:success]")
    print(f"[STAGE:end:best_formula_selection]")

    # Save detailed results
    output_path = Path(__file__).parent.parent / "output" / "gold_accuracy_research.json"
    output_data = {
        'summary': {
            'total_players': len(match_player_data),
            'action_bytes_found': sorted(all_actions),
            'best_formula_5pct': {
                'name': best_5['formula'],
                'actions': [f'0x{a:02X}' for a in best_5['actions']],
                'accuracy_5pct': best_5['accuracy_5pct'],
                'accuracy_10pct': best_5['accuracy_10pct'],
            },
            'best_formula_10pct': {
                'name': best_10['formula'],
                'actions': [f'0x{a:02X}' for a in best_10['actions']],
                'accuracy_5pct': best_10['accuracy_5pct'],
                'accuracy_10pct': best_10['accuracy_10pct'],
            },
        },
        'all_formulas': results,
    }

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2)

    print(f"\n[FINDING] Detailed results saved to {output_path}")

    # Final recommendations
    print("\n" + "="*60)
    print("RECOMMENDATIONS")
    print("="*60)

    if best_5['accuracy_5pct'] >= 80:
        print(f"[+] TARGET ACHIEVED: {best_5['accuracy_5pct']}% ±5% accuracy")
        print(f"  Formula: {best_5['formula']}")
        print(f"  Action bytes: {[f'0x{a:02X}' for a in best_5['actions']]}")
    else:
        print(f"[-] TARGET NOT MET: {best_5['accuracy_5pct']}% ±5% accuracy (target: 80%)")
        print(f"  Best formula: {best_5['formula']}")
        print(f"  Gap: {80 - best_5['accuracy_5pct']:.1f} percentage points")
        print(f"\n[LIMITATION] Current action byte combinations cannot reach 80% ±5% target")
        print(f"[LIMITATION] Missing gold sources likely NOT in credit records")
        print(f"[LIMITATION] May need to explore other event types or accept ~{best_5['accuracy_5pct']}% ceiling")

    print("\n" + "="*60)


if __name__ == '__main__':
    main()
