#!/usr/bin/env python3
"""
Minion Gold/XP Sharing Pattern Analysis - Full Replay (1,200+ minion kills)

Analyzes credit record clustering around 0x0E minion kill events to detect:
1. Gold/XP sharing with nearby teammates
2. 0x0F vs 0x0E relationship (gold vs counter)
3. Team distribution patterns
4. Temporal patterns (early vs late game)
5. Jungle (0x0D) vs Lane (0x0E) sharing differences

Credit record structure:
  [10 04 1D][00 00][eid BE 2B][value f32 BE][action_byte 1B] (12 bytes)

Action bytes:
  0x0E: minion kill counter (value=1.0, last-hitter)
  0x0F: minion gold counter (paired with 0x0E)
  0x08: passive gold (0.6/tick + burst values)
  0x06: gold income/expense
  0x02: XP (estimated)
  0x0D: jungle monster credit
"""
import struct
import sys
from collections import defaultdict, Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from vg.core.unified_decoder import UnifiedDecoder, _le_to_be

CREDIT_HEADER = bytes([0x10, 0x04, 0x1D])


@dataclass
class CreditEvent:
    """A single credit record event."""
    eid: int
    value: float
    action_byte: int
    offset: int
    timestamp_approx: Optional[float] = None


@dataclass
class MinionKillCluster:
    """A minion kill event with surrounding credit records."""
    killer_eid: int
    killer_team: int
    killer_hero: str
    offset: int
    paired_0x0F: Optional[CreditEvent] = None
    nearby_credits: List[CreditEvent] = field(default_factory=list)

    def get_teammate_credits(self, player_teams: Dict[int, int]) -> List[CreditEvent]:
        """Get credits for same-team players (excluding killer)."""
        killer_team = player_teams.get(self.killer_eid)
        if killer_team is None:
            return []

        teammate_credits = []
        for credit in self.nearby_credits:
            if credit.eid == self.killer_eid:
                continue
            if player_teams.get(credit.eid) == killer_team:
                teammate_credits.append(credit)
        return teammate_credits


def scan_credit_records(data: bytes) -> List[CreditEvent]:
    """Scan all credit records in frame data."""
    credits = []
    offset = 0
    while True:
        idx = data.find(CREDIT_HEADER, offset)
        if idx == -1:
            break

        if idx + 12 <= len(data):
            try:
                eid = struct.unpack('>H', data[idx+5:idx+7])[0]
                value = struct.unpack('>f', data[idx+7:idx+11])[0]
                action_byte = data[idx+11]

                credits.append(CreditEvent(
                    eid=eid,
                    value=value,
                    action_byte=action_byte,
                    offset=idx
                ))
            except:
                pass

        offset = idx + 1

    return credits


def find_minion_kill_clusters(credits: List[CreditEvent],
                                player_eids: Set[int],
                                player_teams: Dict[int, int],
                                player_heroes: Dict[int, str],
                                window_bytes: int = 200) -> List[MinionKillCluster]:
    """
    Find 0x0E minion kill events and collect surrounding credit records.

    Args:
        credits: All credit records from the replay
        player_eids: Valid player entity IDs
        player_teams: eid -> team_id mapping
        player_heroes: eid -> hero_name mapping
        window_bytes: Search window around 0x0E event
    """
    clusters = []

    # Find all 0x0E events (minion kills)
    minion_kills = [c for c in credits if c.action_byte == 0x0E and c.eid in player_eids]

    for mk in minion_kills:
        # Find paired 0x0F (should be very close, same entity)
        paired_0x0F = None
        for c in credits:
            if (c.action_byte == 0x0F and
                c.eid == mk.eid and
                abs(c.offset - mk.offset) < 100):
                paired_0x0F = c
                break

        # Collect all credits within window
        nearby = [
            c for c in credits
            if abs(c.offset - mk.offset) <= window_bytes
        ]

        clusters.append(MinionKillCluster(
            killer_eid=mk.eid,
            killer_team=player_teams.get(mk.eid, -1),
            killer_hero=player_heroes.get(mk.eid, "Unknown"),
            offset=mk.offset,
            paired_0x0F=paired_0x0F,
            nearby_credits=nearby
        ))

    return clusters


def analyze_sharing_patterns(clusters: List[MinionKillCluster],
                               player_teams: Dict[int, int]) -> Dict:
    """Analyze gold/XP sharing patterns across minion kill clusters."""

    stats = {
        'total_minion_kills': len(clusters),
        'paired_0x0F_count': sum(1 for c in clusters if c.paired_0x0F is not None),
        'paired_0x0F_rate': 0.0,
        '0x0E_0x0F_value_diff': [],
        'teammate_0x08_burst': [],  # Passive gold bursts to teammates
        'teammate_0x02_xp': [],      # XP to teammates
        'teammate_0x06_income': [],  # Gold income to teammates
        'teammate_0x0F_share': [],   # 0x0F gold to teammates
        'action_byte_distribution': Counter(),
        'sharing_event_count': 0,
        'kills_with_sharing': 0,
    }

    for cluster in clusters:
        # 0x0F pairing analysis
        if cluster.paired_0x0F:
            diff = abs(cluster.paired_0x0F.value - 1.0)  # 0x0E always 1.0
            stats['0x0E_0x0F_value_diff'].append(diff)

        # Action byte distribution
        for credit in cluster.nearby_credits:
            stats['action_byte_distribution'][credit.action_byte] += 1

        # Teammate credit analysis
        teammate_credits = cluster.get_teammate_credits(player_teams)

        if teammate_credits:
            stats['kills_with_sharing'] += 1

        for tc in teammate_credits:
            stats['action_byte_distribution'][f'teammate_{tc.action_byte:02X}'] += 1

            if tc.action_byte == 0x08:
                # Passive gold - check if burst (>0.6)
                if tc.value > 0.6:
                    stats['teammate_0x08_burst'].append(tc.value)
                    stats['sharing_event_count'] += 1
            elif tc.action_byte == 0x02:
                stats['teammate_0x02_xp'].append(tc.value)
                stats['sharing_event_count'] += 1
            elif tc.action_byte == 0x06:
                if tc.value > 0:  # Positive = income
                    stats['teammate_0x06_income'].append(tc.value)
                    stats['sharing_event_count'] += 1
            elif tc.action_byte == 0x0F:
                stats['teammate_0x0F_share'].append(tc.value)
                stats['sharing_event_count'] += 1

    # Calculate rates
    if stats['total_minion_kills'] > 0:
        stats['paired_0x0F_rate'] = stats['paired_0x0F_count'] / stats['total_minion_kills']
        stats['sharing_rate'] = stats['kills_with_sharing'] / stats['total_minion_kills']

    return stats


def analyze_single_replay(replay_dir: str) -> Dict:
    """Analyze minion sharing patterns in a single full replay."""
    print(f"\n{'='*80}")
    print(f"Analyzing: {replay_dir}")
    print(f"{'='*80}")

    cache_dir = Path(replay_dir)
    vgr_files = sorted(cache_dir.glob('*.0.vgr'))

    if not vgr_files:
        print(f"❌ No .0.vgr files found in {replay_dir}")
        return {}

    vgr0 = vgr_files[0]
    print(f"[DATA] Loading replay: {vgr0.name}")

    # Decode replay to get player info
    decoder = UnifiedDecoder(str(vgr0))
    decoded = decoder.decode()

    # Build player mappings (convert LE to BE for entity IDs)
    player_eids = set()
    player_teams = {}
    player_heroes = {}

    for p in decoded.all_players:
        eid_be = _le_to_be(p.entity_id)
        player_eids.add(eid_be)
        # DecodedPlayer uses 'team' (str: "left"/"right"), convert to numeric team_id
        team_id = 1 if p.team == "left" else 2
        player_teams[eid_be] = team_id
        player_heroes[eid_be] = p.hero_name

    print(f"[DATA] Players: {len(player_eids)}")
    for eid in sorted(player_eids):
        hero = player_heroes[eid]
        team = player_teams[eid]
        print(f"  eid {eid:04X} ({eid:5d}): {hero:15s} team={team}")

    # Scan all credit records across all frames
    print(f"\n[STAGE:begin:credit_scanning]")
    all_credits = []
    frame_count = 0

    for vgr_file in sorted(cache_dir.glob('*.vgr')):
        with open(vgr_file, 'rb') as f:
            data = f.read()
            credits = scan_credit_records(data)
            all_credits.extend(credits)
            frame_count += 1

    print(f"[DATA] Scanned {frame_count} frames")
    print(f"[DATA] Found {len(all_credits)} total credit records")

    # Action byte distribution
    action_dist = Counter(c.action_byte for c in all_credits)
    print(f"\n[FINDING] Credit record action byte distribution:")
    for action_byte in sorted(action_dist.keys()):
        count = action_dist[action_byte]
        print(f"  0x{action_byte:02X}: {count:6d} events")

    print(f"[STAGE:status:success]")
    print(f"[STAGE:end:credit_scanning]")

    # Find minion kill clusters
    print(f"\n[STAGE:begin:cluster_analysis]")
    clusters = find_minion_kill_clusters(all_credits, player_eids, player_teams, player_heroes)
    print(f"[DATA] Found {len(clusters)} minion kill clusters (0x0E events)")

    # Analyze sharing patterns
    stats = analyze_sharing_patterns(clusters, player_teams)

    print(f"\n[FINDING] 0x0E/0x0F Pairing:")
    print(f"  Total 0x0E events: {stats['total_minion_kills']}")
    print(f"  Paired 0x0F events: {stats['paired_0x0F_count']}")
    print(f"  [STAT:pairing_rate] {stats['paired_0x0F_rate']:.1%}")

    if stats['0x0E_0x0F_value_diff']:
        avg_diff = sum(stats['0x0E_0x0F_value_diff']) / len(stats['0x0E_0x0F_value_diff'])
        print(f"  [STAT:avg_value_diff] {avg_diff:.4f}")

    print(f"\n[FINDING] Teammate Sharing Detection:")
    print(f"  Minion kills with teammate credits: {stats['kills_with_sharing']}")
    print(f"  [STAT:sharing_rate] {stats.get('sharing_rate', 0):.1%}")
    print(f"  Total sharing events: {stats['sharing_event_count']}")

    print(f"\n[FINDING] Sharing Mechanisms:")
    print(f"  Teammate 0x08 bursts (>0.6): {len(stats['teammate_0x08_burst'])}")
    if stats['teammate_0x08_burst']:
        avg_burst = sum(stats['teammate_0x08_burst']) / len(stats['teammate_0x08_burst'])
        print(f"    [STAT:avg_0x08_burst] {avg_burst:.2f}")
        print(f"    Range: {min(stats['teammate_0x08_burst']):.2f} - {max(stats['teammate_0x08_burst']):.2f}")

    print(f"  Teammate 0x02 (XP): {len(stats['teammate_0x02_xp'])}")
    if stats['teammate_0x02_xp']:
        avg_xp = sum(stats['teammate_0x02_xp']) / len(stats['teammate_0x02_xp'])
        print(f"    [STAT:avg_0x02_xp] {avg_xp:.2f}")
        print(f"    Range: {min(stats['teammate_0x02_xp']):.2f} - {max(stats['teammate_0x02_xp']):.2f}")

    print(f"  Teammate 0x06 income: {len(stats['teammate_0x06_income'])}")
    if stats['teammate_0x06_income']:
        avg_income = sum(stats['teammate_0x06_income']) / len(stats['teammate_0x06_income'])
        print(f"    [STAT:avg_0x06_income] {avg_income:.2f}")

    print(f"  Teammate 0x0F gold: {len(stats['teammate_0x0F_share'])}")
    if stats['teammate_0x0F_share']:
        avg_gold = sum(stats['teammate_0x0F_share']) / len(stats['teammate_0x0F_share'])
        print(f"    [STAT:avg_0x0F_gold] {avg_gold:.2f}")

    print(f"[STAGE:status:success]")
    print(f"[STAGE:end:cluster_analysis]")

    # Per-player distribution
    print(f"\n[STAGE:begin:player_distribution]")
    player_minion_kills = Counter()
    for cluster in clusters:
        player_minion_kills[cluster.killer_eid] += 1

    print(f"\n[FINDING] Per-player minion kill distribution:")
    for team_id in [1, 2]:
        team_players = [eid for eid in player_eids if player_teams[eid] == team_id]
        team_total = sum(player_minion_kills[eid] for eid in team_players)
        print(f"\n  Team {team_id}: {team_total} total minion kills")
        for eid in sorted(team_players):
            count = player_minion_kills[eid]
            hero = player_heroes[eid]
            pct = (count / team_total * 100) if team_total > 0 else 0
            print(f"    {hero:15s} (eid {eid:04X}): {count:4d} ({pct:5.1f}%)")

    print(f"[STAGE:status:success]")
    print(f"[STAGE:end:player_distribution]")

    # Sample cluster inspection
    print(f"\n[STAGE:begin:sample_inspection]")
    print(f"\n[FINDING] Sample minion kill clusters (first 5):")
    for i, cluster in enumerate(clusters[:5]):
        print(f"\n  Cluster {i+1}: eid {cluster.killer_eid:04X} ({cluster.killer_hero}) at offset {cluster.offset}")
        print(f"    Paired 0x0F: {'YES' if cluster.paired_0x0F else 'NO'}")
        if cluster.paired_0x0F:
            print(f"      Value: {cluster.paired_0x0F.value:.2f}, Offset delta: {cluster.paired_0x0F.offset - cluster.offset}")

        teammate_credits = cluster.get_teammate_credits(player_teams)
        print(f"    Teammate credits: {len(teammate_credits)}")
        for tc in teammate_credits[:3]:  # Show first 3
            action_name = {0x02: 'XP', 0x06: 'Gold', 0x08: 'Passive', 0x0F: 'MinionGold'}.get(tc.action_byte, f'0x{tc.action_byte:02X}')
            print(f"      eid {tc.eid:04X}: {action_name} = {tc.value:.2f} (offset delta: {tc.offset - cluster.offset})")

    print(f"[STAGE:status:success]")
    print(f"[STAGE:end:sample_inspection]")

    return stats


def main():
    """Analyze multiple full replays for minion sharing patterns."""
    replay_dirs = [
        'D:/Desktop/My Folder/Game/VG/vg replay/22.06.07/EA vs SEA/cache1/cache',
        'D:/Desktop/My Folder/Game/VG/vg replay/23.02.09/cache',
        'D:/Desktop/My Folder/Game/VG/vg replay/22.11.02/cache/cache',
    ]

    print("[OBJECTIVE] Analyze minion kill gold/XP sharing patterns in full replays (1,200+ kills)")

    all_stats = []
    for replay_dir in replay_dirs:
        if Path(replay_dir).exists():
            stats = analyze_single_replay(replay_dir)
            if stats:
                all_stats.append(stats)
        else:
            print(f"⚠️ Directory not found: {replay_dir}")

    # Aggregate statistics
    if all_stats:
        print(f"\n{'='*80}")
        print(f"AGGREGATE STATISTICS ({len(all_stats)} replays)")
        print(f"{'='*80}")

        total_kills = sum(s['total_minion_kills'] for s in all_stats)
        total_paired = sum(s['paired_0x0F_count'] for s in all_stats)
        total_sharing = sum(s['kills_with_sharing'] for s in all_stats)

        print(f"[STAT:total_minion_kills] {total_kills}")
        print(f"[STAT:total_paired_0x0F] {total_paired}")
        print(f"[STAT:aggregate_pairing_rate] {total_paired/total_kills:.1%}")
        print(f"[STAT:aggregate_sharing_rate] {total_sharing/total_kills:.1%}")

        # Aggregate sharing mechanisms
        all_0x08 = sum(len(s['teammate_0x08_burst']) for s in all_stats)
        all_0x02 = sum(len(s['teammate_0x02_xp']) for s in all_stats)
        all_0x06 = sum(len(s['teammate_0x06_income']) for s in all_stats)
        all_0x0F = sum(len(s['teammate_0x0F_share']) for s in all_stats)

        print(f"\n[FINDING] Aggregate sharing mechanisms:")
        print(f"  Teammate 0x08 bursts: {all_0x08}")
        print(f"  Teammate 0x02 (XP): {all_0x02}")
        print(f"  Teammate 0x06 income: {all_0x06}")
        print(f"  Teammate 0x0F gold: {all_0x0F}")

    print(f"\n[LIMITATION] Analysis based on byte proximity (±200 bytes) - may include unrelated credits")
    print(f"[LIMITATION] No timestamp validation - temporal correlation not verified")
    print(f"[LIMITATION] Assumes all sharing happens through credit records - alternative mechanisms unknown")


if __name__ == '__main__':
    main()
