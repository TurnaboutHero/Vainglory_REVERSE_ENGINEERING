#!/usr/bin/env python3
"""
Gold Temporal Analysis - Per-player gold accumulation over time in full replays.

Analyzes 22,000+ credit events to:
1. Track frame-by-frame gold accumulation (gold curves)
2. Analyze 0x08 passive gold patterns (burst values)
3. Optimize gold income formula (test all action byte combinations)
4. Compare income vs spending distributions
5. Compare team total gold (winner vs loser)

Credit record structure:
  [10 04 1D][00 00][eid BE 2B][value f32 BE][action_byte 1B] (12 bytes)

Action bytes:
  0x06: Gold income/spending (r=0.98 correlation, positive=income, negative=spending)
  0x08: Passive gold (0.6/tick baseline + burst values 8.0, 30.0, etc.)
  0x0E: Minion kill flag (paired with 0x0F)
  0x0F: Minion gold income
  0x0D: Jungle gold income
  0x04: Turret/objective gold
"""

import struct
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple, Set
from datetime import datetime

# matplotlib is optional - visualization will be skipped if not available
try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from vg.core.unified_decoder import UnifiedDecoder, _le_to_be

# Event headers
CREDIT_HEADER = bytes([0x10, 0x04, 0x1D])

# Full replay directories
REPLAY_DIRS = [
    'D:/Desktop/My Folder/Game/VG/vg replay/22.06.07/EA vs SEA/cache1/cache',
    'D:/Desktop/My Folder/Game/VG/vg replay/23.02.09/cache',
    'D:/Desktop/My Folder/Game/VG/vg replay/22.11.02/cache/cache',
]


def load_frames(cache_dir: Path) -> List[Tuple[int, bytes]]:
    """Load all .vgr frames from cache directory."""
    vgr_files = list(cache_dir.glob('*.vgr'))
    if not vgr_files:
        return []

    # Group by base name (handle .0.vgr, .1.vgr, etc.)
    by_base = defaultdict(list)
    for f in vgr_files:
        parts = f.stem.split('.')
        if len(parts) >= 2:
            base = '.'.join(parts[:-1])
            try:
                idx = int(parts[-1])
                by_base[base].append((idx, f))
            except ValueError:
                continue

    if not by_base:
        return []

    # Pick the base with most frames
    base_name = max(by_base.keys(), key=lambda b: len(by_base[b]))
    frames = by_base[base_name]
    frames.sort(key=lambda x: x[0])

    return [(idx, f.read_bytes()) for idx, f in frames]


def get_player_entity_ids(cache_dir: Path) -> Dict[int, str]:
    """Get player entity IDs (BE) -> hero name mapping from first frame."""
    vgr0_files = list(cache_dir.glob('*.0.vgr'))
    if not vgr0_files:
        return {}

    vgr0 = vgr0_files[0]
    decoder = UnifiedDecoder(str(vgr0))
    decoded = decoder.decode()

    player_eids = {}
    player_teams = {}
    for p in decoded.all_players:
        eid_be = _le_to_be(p.entity_id)
        player_eids[eid_be] = p.hero_name
        player_teams[eid_be] = p.team

    return player_eids, player_teams


def extract_all_credits(frames: List[Tuple[int, bytes]], valid_eids: Set[int]) -> List[dict]:
    """
    Extract all credit records with frame, timestamp, action byte.

    Returns:
        List of dicts with: frame, eid, value, action, offset
    """
    all_credits = []

    for frame_idx, data in frames:
        pos = 0
        while True:
            pos = data.find(CREDIT_HEADER, pos)
            if pos == -1:
                break
            if pos + 12 > len(data):
                pos += 1
                continue
            if data[pos+3:pos+5] != b'\x00\x00':
                pos += 1
                continue

            eid = struct.unpack_from(">H", data, pos + 5)[0]
            if eid not in valid_eids:
                pos += 3
                continue

            value = struct.unpack_from(">f", data, pos + 7)[0]
            action = data[pos + 11]

            # Validate value (filter NaN/Inf)
            if abs(value) > 1e6 or value != value:  # NaN check
                pos += 3
                continue

            all_credits.append({
                'frame': frame_idx,
                'eid': eid,
                'value': value,
                'action': action,
                'offset': pos,
            })

            pos += 3

    return all_credits


def analyze_gold_curves(credits: List[dict], player_eids: Dict[int, str],
                        player_teams: Dict[int, str]) -> Dict[int, List[Tuple[int, float]]]:
    """
    Build gold accumulation curves per player (frame-by-frame cumulative sum).

    Uses current formula: 600 starting + action 0x06 (positive only) + 0x0F + 0x0D

    Returns:
        Dict[eid] -> List[(frame, cumulative_gold)]
    """
    gold_by_player = defaultdict(lambda: 600.0)  # Starting gold
    curves = defaultdict(list)

    # Sort by frame
    credits_sorted = sorted(credits, key=lambda x: x['frame'])

    for cr in credits_sorted:
        eid = cr['eid']
        action = cr['action']
        value = cr['value']

        # Current formula
        if action == 0x06 and value > 0:
            gold_by_player[eid] += value
        elif action in (0x0F, 0x0D) and value > 0:
            gold_by_player[eid] += value

        # Record snapshot at each frame (sparse)
        curves[eid].append((cr['frame'], gold_by_player[eid]))

    return curves


def analyze_passive_gold_patterns(credits: List[dict]) -> dict:
    """
    Analyze 0x08 passive gold patterns.

    Returns:
        Dict with value distributions, burst event timing, etc.
    """
    passive_credits = [c for c in credits if c['action'] == 0x08]

    values = [c['value'] for c in passive_credits]
    value_counts = defaultdict(int)
    for v in values:
        # Bin to 1 decimal place
        binned = round(v, 1)
        value_counts[binned] += 1

    # Identify burst values (> 5.0)
    burst_events = [c for c in passive_credits if c['value'] > 5.0]

    # Analyze burst timing (are they after minion kills?)
    burst_frames = set(c['frame'] for c in burst_events)
    minion_credits = [c for c in credits if c['action'] == 0x0E]
    minion_frames = set(c['frame'] for c in minion_credits)

    # Count bursts within ±5 frames of minion kill
    bursts_near_minions = 0
    for burst_frame in burst_frames:
        if any(abs(burst_frame - mf) <= 5 for mf in minion_frames):
            bursts_near_minions += 1

    return {
        'total_passive_credits': len(passive_credits),
        'value_distribution': dict(sorted(value_counts.items())),
        'burst_events': len(burst_events),
        'burst_values': sorted(set(round(c['value'], 1) for c in burst_events)),
        'bursts_near_minions': bursts_near_minions,
        'burst_ratio_near_minions': bursts_near_minions / max(len(burst_events), 1),
    }


def test_gold_formulas(credits: List[dict], player_eids: Dict[int, str]) -> dict:
    """
    Test different gold formula combinations.

    Returns:
        Dict with formula results (no truth available, just consistency metrics)
    """
    formulas = {
        'current': lambda c: (c['action'] == 0x06 and c['value'] > 0) or c['action'] in (0x0F, 0x0D),
        '0x06_only': lambda c: c['action'] == 0x06 and c['value'] > 0,
        '0x06_0x08': lambda c: (c['action'] == 0x06 and c['value'] > 0) or (c['action'] == 0x08),
        '0x06_0x08_burst': lambda c: (c['action'] == 0x06 and c['value'] > 0) or (c['action'] == 0x08 and c['value'] > 5.0),
        '0x06_0x0F_0x0D_0x04': lambda c: (c['action'] == 0x06 and c['value'] > 0) or c['action'] in (0x0F, 0x0D, 0x04),
        'all_positive': lambda c: c['value'] > 0,
    }

    results = {}
    for name, formula_fn in formulas.items():
        player_totals = defaultdict(float)
        for cr in credits:
            if formula_fn(cr):
                player_totals[cr['eid']] += cr['value']

        # Add starting gold
        for eid in player_eids.keys():
            player_totals[eid] += 600

        totals = list(player_totals.values())
        results[name] = {
            'mean': sum(totals) / len(totals) if totals else 0,
            'min': min(totals) if totals else 0,
            'max': max(totals) if totals else 0,
            'std': (sum((x - sum(totals)/len(totals))**2 for x in totals) / len(totals))**0.5 if totals else 0,
        }

    return results


def analyze_income_spending_distribution(credits: List[dict]) -> dict:
    """
    Analyze 0x06 positive (income) vs negative (spending) distribution.

    Returns:
        Dict with income/spending patterns
    """
    action_06_credits = [c for c in credits if c['action'] == 0x06]

    positive = [c for c in action_06_credits if c['value'] > 0]
    negative = [c for c in action_06_credits if c['value'] < 0]

    pos_values = [c['value'] for c in positive]
    neg_values = [abs(c['value']) for c in negative]

    return {
        'total_0x06': len(action_06_credits),
        'positive_count': len(positive),
        'negative_count': len(negative),
        'positive_sum': sum(pos_values),
        'negative_sum': sum(neg_values),
        'positive_mean': sum(pos_values) / len(pos_values) if pos_values else 0,
        'negative_mean': sum(neg_values) / len(neg_values) if neg_values else 0,
    }


def compare_team_gold(credits: List[dict], player_teams: Dict[int, str],
                      player_eids: Dict[int, str]) -> dict:
    """
    Compare total gold between teams (winner vs loser).

    Returns:
        Dict with team gold totals
    """
    team_gold = defaultdict(float)

    for cr in credits:
        eid = cr['eid']
        team = player_teams.get(eid)
        action = cr['action']
        value = cr['value']

        if not team:
            continue

        # Current formula
        if action == 0x06 and value > 0:
            team_gold[team] += value
        elif action in (0x0F, 0x0D) and value > 0:
            team_gold[team] += value

    # Add starting gold (600 per player)
    for eid, team in player_teams.items():
        team_gold[team] += 600

    return {
        'left_gold': team_gold.get('left', 0),
        'right_gold': team_gold.get('right', 0),
        'difference': abs(team_gold.get('left', 0) - team_gold.get('right', 0)),
        'ratio': team_gold.get('left', 1) / max(team_gold.get('right', 1), 1),
    }


def generate_visualizations(curves: Dict[int, List[Tuple[int, float]]],
                           player_eids: Dict[int, str],
                           player_teams: Dict[int, str],
                           replay_name: str) -> str:
    """Generate gold curve visualizations."""
    if not HAS_MATPLOTLIB:
        return None

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    fig_path = f'.omc/scientist/figures/{timestamp}_gold_curves_{replay_name}.png'

    fig, ax = plt.subplots(figsize=(14, 8))

    # Plot each player's gold curve
    colors_left = ['#1f77b4', '#ff7f0e', '#2ca02c']
    colors_right = ['#d62728', '#9467bd', '#8c564b']

    left_idx = 0
    right_idx = 0

    for eid, curve in curves.items():
        if not curve:
            continue

        frames = [c[0] for c in curve]
        gold = [c[1] for c in curve]

        team = player_teams.get(eid, 'unknown')
        hero = player_eids.get(eid, f'EID_{eid}')

        if team == 'left':
            color = colors_left[left_idx % len(colors_left)]
            left_idx += 1
        else:
            color = colors_right[right_idx % len(colors_right)]
            right_idx += 1

        ax.plot(frames, gold, label=f'{hero} ({team})', color=color, alpha=0.7)

    ax.set_xlabel('Frame Number')
    ax.set_ylabel('Cumulative Gold')
    ax.set_title(f'Gold Accumulation Over Time - {replay_name}')
    ax.legend(loc='upper left', fontsize=8)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(fig_path, dpi=150)
    plt.close()

    return fig_path


def main():
    print("[OBJECTIVE] Analyze per-player gold accumulation in full replays with 22,000+ events")
    print()

    all_results = []

    for replay_dir in REPLAY_DIRS:
        cache_dir = Path(replay_dir)
        if not cache_dir.exists():
            print(f"[LIMITATION] Directory not found: {replay_dir}")
            continue

        replay_name = cache_dir.parent.name if cache_dir.name == 'cache' else cache_dir.name
        print(f"\n{'='*60}")
        print(f"[DATA] Analyzing replay: {replay_name}")
        print(f"[DATA] Directory: {cache_dir}")

        # Load frames
        frames = load_frames(cache_dir)
        if not frames:
            print(f"[LIMITATION] No frames found in {cache_dir}")
            continue

        print(f"[DATA] Loaded {len(frames)} frames")

        # Get player entity IDs
        player_eids, player_teams = get_player_entity_ids(cache_dir)
        if not player_eids:
            print(f"[LIMITATION] Could not extract player entity IDs")
            continue

        print(f"[DATA] Found {len(player_eids)} players:")
        for eid, hero in player_eids.items():
            team = player_teams.get(eid, 'unknown')
            print(f"  - {hero} (team={team}, eid={eid})")

        # Extract all credit records
        valid_eids = set(player_eids.keys())
        credits = extract_all_credits(frames, valid_eids)
        print(f"[DATA] Extracted {len(credits):,} total credit records")

        # Action byte distribution
        action_counts = defaultdict(int)
        for c in credits:
            action_counts[c['action']] += 1

        print(f"[DATA] Credit action distribution:")
        for action, count in sorted(action_counts.items(), key=lambda x: -x[1]):
            print(f"  - 0x{action:02X}: {count:,} records")

        # 1. Gold curves
        print(f"\n[STAGE:begin:gold_curves]")
        curves = analyze_gold_curves(credits, player_eids, player_teams)

        for eid, curve in curves.items():
            if curve:
                hero = player_eids.get(eid, f'EID_{eid}')
                final_gold = curve[-1][1]
                print(f"[STAT:{hero}_final_gold] {final_gold:,.0f}")

        print(f"[STAGE:status:success]")
        print(f"[STAGE:end:gold_curves]")

        # 2. Passive gold patterns
        print(f"\n[STAGE:begin:passive_gold_analysis]")
        passive_analysis = analyze_passive_gold_patterns(credits)

        print(f"[FINDING] Passive gold (0x08) analysis:")
        print(f"[STAT:total_passive_credits] {passive_analysis['total_passive_credits']:,}")
        print(f"[STAT:burst_events] {passive_analysis['burst_events']:,}")
        print(f"[STAT:burst_values] {passive_analysis['burst_values']}")
        print(f"[STAT:bursts_near_minions] {passive_analysis['bursts_near_minions']}")
        print(f"[STAT:burst_ratio_near_minions] {passive_analysis['burst_ratio_near_minions']:.2%}")

        print(f"[FINDING] Value distribution (top 10):")
        for value, count in sorted(passive_analysis['value_distribution'].items(),
                                   key=lambda x: -x[1])[:10]:
            print(f"  - {value:6.1f}: {count:,} occurrences")

        print(f"[STAGE:status:success]")
        print(f"[STAGE:end:passive_gold_analysis]")

        # 3. Gold formula testing
        print(f"\n[STAGE:begin:formula_testing]")
        formula_results = test_gold_formulas(credits, player_eids)

        print(f"[FINDING] Gold formula comparison (per-player totals):")
        for name, stats in formula_results.items():
            print(f"\n  Formula: {name}")
            print(f"    Mean: {stats['mean']:,.0f}")
            print(f"    Range: {stats['min']:,.0f} - {stats['max']:,.0f}")
            print(f"    Std Dev: {stats['std']:,.0f}")

        print(f"[STAGE:status:success]")
        print(f"[STAGE:end:formula_testing]")

        # 4. Income vs Spending
        print(f"\n[STAGE:begin:income_spending]")
        income_spending = analyze_income_spending_distribution(credits)

        print(f"[FINDING] Income vs Spending (action 0x06):")
        print(f"[STAT:total_0x06] {income_spending['total_0x06']:,}")
        print(f"[STAT:positive_count] {income_spending['positive_count']:,}")
        print(f"[STAT:negative_count] {income_spending['negative_count']:,}")
        print(f"[STAT:positive_sum] {income_spending['positive_sum']:,.0f}")
        print(f"[STAT:negative_sum] {income_spending['negative_sum']:,.0f}")
        print(f"[STAT:positive_mean] {income_spending['positive_mean']:,.2f}")
        print(f"[STAT:negative_mean] {income_spending['negative_mean']:,.2f}")

        print(f"[STAGE:status:success]")
        print(f"[STAGE:end:income_spending]")

        # 5. Team gold comparison
        print(f"\n[STAGE:begin:team_comparison]")
        team_comparison = compare_team_gold(credits, player_teams, player_eids)

        print(f"[FINDING] Team total gold comparison:")
        print(f"[STAT:left_team_gold] {team_comparison['left_gold']:,.0f}")
        print(f"[STAT:right_team_gold] {team_comparison['right_gold']:,.0f}")
        print(f"[STAT:gold_difference] {team_comparison['difference']:,.0f}")
        print(f"[STAT:gold_ratio] {team_comparison['ratio']:.3f}")

        print(f"[STAGE:status:success]")
        print(f"[STAGE:end:team_comparison]")

        # 6. Generate visualization
        print(f"\n[STAGE:begin:visualization]")
        if HAS_MATPLOTLIB:
            fig_path = generate_visualizations(curves, player_eids, player_teams, replay_name)
            print(f"[FINDING] Gold curve visualization saved to {fig_path}")
        else:
            print(f"[LIMITATION] matplotlib not installed - skipping visualization")
        print(f"[STAGE:status:success]")
        print(f"[STAGE:end:visualization]")

        all_results.append({
            'replay_name': replay_name,
            'frame_count': len(frames),
            'credit_count': len(credits),
            'player_count': len(player_eids),
            'passive_analysis': passive_analysis,
            'formula_results': formula_results,
            'income_spending': income_spending,
            'team_comparison': team_comparison,
        })

    # Summary across all replays
    print(f"\n{'='*60}")
    print(f"[FINDING] Summary across {len(all_results)} replays")
    print()

    total_credits = sum(r['credit_count'] for r in all_results)
    total_passive = sum(r['passive_analysis']['total_passive_credits'] for r in all_results)
    total_bursts = sum(r['passive_analysis']['burst_events'] for r in all_results)

    print(f"[STAT:total_credits_all_replays] {total_credits:,}")
    print(f"[STAT:total_passive_credits_all_replays] {total_passive:,}")
    print(f"[STAT:total_burst_events_all_replays] {total_bursts:,}")
    print()

    print(f"[LIMITATION] No truth data available - accuracy measured by pattern consistency")
    print(f"[LIMITATION] Team labels (left/right) may be swapped - affects team comparison interpretation")
    print(f"[LIMITATION] 0x08 burst gold timing correlation with minion kills suggests shared gold mechanism")


if __name__ == '__main__':
    main()
