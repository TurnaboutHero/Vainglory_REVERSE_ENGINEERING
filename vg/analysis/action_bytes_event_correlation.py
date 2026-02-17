"""
Correlate unknown action bytes with known game events:
- Turret destruction
- Hero kills/deaths
- Objective captures

Hypothesis: These may be turret-related mechanics (damage, shields, buffs)
"""

import sys
from pathlib import Path
from collections import defaultdict
import struct

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from vg.core.unified_decoder import UnifiedDecoder, _le_to_be
from vg.core.kda_detector import KDADetector

REPLAY_DIRS = [
    'D:/Desktop/My Folder/Game/VG/vg replay/22.06.07/EA vs SEA/cache1/cache',
    'D:/Desktop/My Folder/Game/VG/vg replay/23.02.09/cache',
    'D:/Desktop/My Folder/Game/VG/vg replay/22.11.02/cache/cache',
]


def extract_turret_deaths(data: bytes) -> list:
    """Extract turret/objective deaths (eid 1000-2100)."""
    deaths = []
    header = bytes([0x08, 0x04, 0x31])

    i = 0
    while i < len(data) - 11:
        if data[i:i+3] == header and data[i+3:i+5] == b'\x00\x00':
            eid = struct.unpack('>H', data[i+5:i+7])[0]
            timestamp = struct.unpack('>f', data[i+7:i+11])[0]

            if 1000 <= eid < 2100:
                deaths.append({
                    'offset': i,
                    'eid': eid,
                    'timestamp': timestamp,
                })
            i += 11
        else:
            i += 1

    return deaths


def extract_all_credit_records(data: bytes) -> list:
    """Extract ALL credit records."""
    records = []
    header = bytes([0x10, 0x04, 0x1D])

    i = 0
    while i < len(data) - 12:
        if data[i:i+3] == header and data[i+3:i+5] == b'\x00\x00':
            eid = struct.unpack('>H', data[i+5:i+7])[0]
            value = struct.unpack('>f', data[i+7:i+11])[0]
            action = data[i+11]

            records.append({
                'offset': i,
                'eid': eid,
                'value': value,
                'action': action,
            })
            i += 12
        else:
            i += 1

    return records


def correlate_with_turret_deaths(turret_deaths: list, credit_records: list, action: int, time_window: int = 5000) -> dict:
    """Check if action bytes occur near turret deaths."""
    action_recs = [r for r in credit_records if r['action'] == action]

    correlations = []

    for death in turret_deaths:
        # Find action records within offset window
        nearby = [r for r in action_recs
                  if abs(r['offset'] - death['offset']) <= time_window]

        if nearby:
            correlations.append({
                'turret_eid': death['eid'],
                'turret_offset': death['offset'],
                'turret_ts': death['timestamp'],
                'action_count': len(nearby),
                'action_records': nearby[:3],  # Sample
            })

    return {
        'total_turret_deaths': len(turret_deaths),
        'correlations_found': len(correlations),
        'correlation_rate': len(correlations) / len(turret_deaths) if turret_deaths else 0,
        'sample_correlations': correlations[:5],
    }


def analyze_action_0x05_special(records: list) -> dict:
    """
    Special analysis for 0x05 - has negative values and wide range.
    Could be damage or cost-related.
    """
    action_recs = [r for r in records if r['action'] == 0x05]

    positive_vals = [r for r in action_recs if r['value'] > 0]
    negative_vals = [r for r in action_recs if r['value'] < 0]

    # Check for paired positive/negative (like purchases)
    eid_value_map = defaultdict(list)
    for r in action_recs:
        eid_value_map[r['eid']].append(r['value'])

    paired_entities = {}
    for eid, values in eid_value_map.items():
        has_positive = any(v > 0 for v in values)
        has_negative = any(v < 0 for v in values)
        if has_positive and has_negative:
            paired_entities[eid] = {
                'positive_count': sum(1 for v in values if v > 0),
                'negative_count': sum(1 for v in values if v < 0),
                'total_positive': sum(v for v in values if v > 0),
                'total_negative': sum(v for v in values if v < 0),
                'net': sum(values),
            }

    return {
        'total': len(action_recs),
        'positive_count': len(positive_vals),
        'negative_count': len(negative_vals),
        'positive_sum': sum(r['value'] for r in positive_vals),
        'negative_sum': sum(r['value'] for r in negative_vals),
        'net_sum': sum(r['value'] for r in action_recs),
        'paired_entities': paired_entities,
    }


def analyze_value_0_vs_1_pattern(records: list, actions: list) -> dict:
    """
    For binary actions (0x09, 0x0A), analyze when they are 0 vs 1.
    Could be boolean flags (alive/dead, active/inactive, etc.)
    """
    results = {}

    for action in actions:
        action_recs = [r for r in records if r['action'] == action]

        value_0 = [r for r in action_recs if r['value'] == 0.0]
        value_1 = [r for r in action_recs if r['value'] == 1.0]

        # Check entity overlap
        eids_0 = set(r['eid'] for r in value_0)
        eids_1 = set(r['eid'] for r in value_1)

        # Check if same entities toggle between 0 and 1
        toggle_entities = eids_0 & eids_1

        results[f'0x{action:02X}'] = {
            'value_0_count': len(value_0),
            'value_1_count': len(value_1),
            'unique_eids_0': len(eids_0),
            'unique_eids_1': len(eids_1),
            'toggle_entities': len(toggle_entities),
            'toggle_entity_ids': sorted(list(toggle_entities)),
        }

    return results


def analyze_0x0C_fractional_values(records: list) -> dict:
    """
    0x0C has fractional values (0.33, 0.5, 0.25, 1.0).
    Could be:
    - Damage reduction (armor/shield percentage)
    - Capture progress
    - Charge/stack counter (normalized)
    """
    action_recs = [r for r in records if r['action'] == 0x0C]

    value_groups = defaultdict(list)
    for r in action_recs:
        # Round to 2 decimals for grouping
        rounded = round(r['value'], 2)
        value_groups[rounded].append(r)

    # Check if entities progress through values (0 -> 0.33 -> 0.5 -> 1.0)
    entity_value_sequences = defaultdict(list)
    for r in sorted(action_recs, key=lambda x: x['offset']):
        entity_value_sequences[r['eid']].append(round(r['value'], 2))

    progression_entities = {}
    for eid, values in entity_value_sequences.items():
        if len(values) > 1:
            progression_entities[eid] = values

    return {
        'value_distribution': {k: len(v) for k, v in sorted(value_groups.items())},
        'entities_with_progression': len(progression_entities),
        'sample_progressions': dict(list(progression_entities.items())[:10]),
    }


def main():
    print("[STAGE:begin:event_correlation]")

    for replay_dir in REPLAY_DIRS:
        cache_dir = Path(replay_dir)
        if not cache_dir.exists():
            continue

        print(f"\n[DATA] Event correlation: {cache_dir.parent.name}")

        # Get player map
        vgr0_files = list(cache_dir.glob('*.0.vgr'))
        if not vgr0_files:
            continue

        decoder = UnifiedDecoder(str(vgr0_files[0]))
        decoded = decoder.decode()
        player_map = {_le_to_be(p.entity_id): p.hero_name for p in decoded.all_players}

        # Collect all data
        all_turret_deaths = []
        all_records = []

        for vgr_file in sorted(cache_dir.glob('*.vgr')):
            with open(vgr_file, 'rb') as f:
                data = f.read()
                all_turret_deaths.extend(extract_turret_deaths(data))
                all_records.extend(extract_all_credit_records(data))

        print(f"[DATA] Turret/structure deaths: {len(all_turret_deaths)}")
        print(f"[DATA] Total credit records: {len(all_records)}")

        # Correlate with turret deaths
        print("\n[FINDING] Correlation with turret deaths:")
        for action in [0x05, 0x09, 0x0A, 0x0B, 0x0C]:
            corr = correlate_with_turret_deaths(all_turret_deaths, all_records, action, time_window=5000)
            if corr['correlations_found'] > 0:
                print(f"  0x{action:02X}: {corr['correlations_found']}/{corr['total_turret_deaths']} turret deaths ({corr['correlation_rate']:.1%})")

        # Analyze 0x05 special
        print("\n[FINDING] Action 0x05 (has negatives) analysis:")
        analysis_0x05 = analyze_action_0x05_special(all_records)
        print(f"  Total: {analysis_0x05['total']}")
        print(f"  Positive: {analysis_0x05['positive_count']} (sum={analysis_0x05['positive_sum']:.2f})")
        print(f"  Negative: {analysis_0x05['negative_count']} (sum={analysis_0x05['negative_sum']:.2f})")
        print(f"  Net: {analysis_0x05['net_sum']:.2f}")
        print(f"  Entities with both +/-: {len(analysis_0x05['paired_entities'])}")
        if analysis_0x05['paired_entities']:
            print("  Sample paired entity:")
            sample_eid, sample_data = list(analysis_0x05['paired_entities'].items())[0]
            print(f"    eid={sample_eid}: +count={sample_data['positive_count']}, -count={sample_data['negative_count']}, net={sample_data['net']:.2f}")

        # Analyze binary toggle pattern
        print("\n[FINDING] Binary action toggle analysis (0x09, 0x0A):")
        toggle_analysis = analyze_value_0_vs_1_pattern(all_records, [0x09, 0x0A])
        for action_hex, data in toggle_analysis.items():
            print(f"  {action_hex}:")
            print(f"    Value=0: {data['value_0_count']} records, {data['unique_eids_0']} entities")
            print(f"    Value=1: {data['value_1_count']} records, {data['unique_eids_1']} entities")
            print(f"    Entities that toggle: {data['toggle_entities']}")
            if data['toggle_entity_ids']:
                print(f"    Toggle entity IDs: {data['toggle_entity_ids'][:10]}")

        # Analyze 0x0C fractional values
        print("\n[FINDING] Action 0x0C (fractional values) analysis:")
        analysis_0x0C = analyze_0x0C_fractional_values(all_records)
        print(f"  Value distribution: {analysis_0x0C['value_distribution']}")
        print(f"  Entities with value progression: {analysis_0x0C['entities_with_progression']}")
        if analysis_0x0C['sample_progressions']:
            print("  Sample progressions:")
            for eid, values in list(analysis_0x0C['sample_progressions'].items())[:3]:
                print(f"    eid={eid}: {values}")

    print("\n[STAGE:end:event_correlation]")


if __name__ == '__main__':
    main()
