#!/usr/bin/env python3
"""
Kill Sequence Detector - N-gram Analysis for Kill/Death Events

Hypothesis: Kill/death events are encoded as multi-event sequences, not single action codes.
This script analyzes 2-gram and 3-gram patterns of action codes to identify sequences that
only occur near death events.

Truth data: 15K/15D total in 21.11.04 replay
Team 1: Phinn(56325), Yates(56581), Caine(56837)
Team 2: Petal(57093), Karas(57349), Baron(57605)
"""

import sys
import json
from pathlib import Path
from collections import Counter, defaultdict
from typing import List, Dict, Tuple, Set
import struct

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.vgr_parser import VGRParser


class EventSequence:
    """Represents an event sequence for a player"""
    def __init__(self, entity_id: int, player_name: str):
        self.entity_id = entity_id
        self.player_name = player_name
        self.events: List[Tuple[int, int]] = []  # [(frame_idx, action_code), ...]

    def add_event(self, frame_idx: int, action_code: int):
        self.events.append((frame_idx, action_code))

    def get_ngrams(self, n: int) -> List[Tuple[int, Tuple[int, ...]]]:
        """
        Get n-grams with their frame positions.
        Returns: [(frame_idx, (code1, code2, ...)), ...]
        """
        if len(self.events) < n:
            return []

        ngrams = []
        for i in range(len(self.events) - n + 1):
            frame_idx = self.events[i][0]
            codes = tuple(e[1] for e in self.events[i:i+n])
            ngrams.append((frame_idx, codes))

        return ngrams


class KillSequenceDetector:
    """Detect kill/death event sequences through n-gram analysis"""

    # Truth data for 21.11.04
    TRUTH_DEATHS = {
        'Phinn': 3,    # Team 1
        'Yates': 4,
        'Caine': 3,
        'Petal': 1,    # Team 2
        'Karas': 2,
        'Baron': 2,
    }

    TEAM_MAPPING = {
        'Phinn': 1, 'Yates': 1, 'Caine': 1,
        'Petal': 2, 'Karas': 2, 'Baron': 2,
    }

    def __init__(self, replay_cache_dir: str):
        self.replay_cache_dir = Path(replay_cache_dir)
        self.frames: List[bytes] = []
        self.player_sequences: Dict[str, EventSequence] = {}
        self.death_candidate_frames: Dict[str, List[int]] = defaultdict(list)

    def load_replay_frames(self):
        """Load all replay frames in order"""
        print("[STAGE:begin:frame_loading]")

        vgr_files = sorted(
            self.replay_cache_dir.glob("*.vgr"),
            key=lambda p: int(p.stem.split('.')[-1])
        )

        print(f"[DATA] Loading {len(vgr_files)} frames...")

        for vgr_file in vgr_files:
            with open(vgr_file, 'rb') as f:
                self.frames.append(f.read())

        print(f"[DATA] Loaded {len(self.frames)} frames")
        print("[STAGE:status:success]")
        print("[STAGE:end:frame_loading]")

    def parse_player_metadata(self):
        """Parse player metadata from first frame"""
        print("[STAGE:begin:metadata_parsing]")

        # Use VGRParser to get player entity IDs
        parser = VGRParser(str(self.replay_cache_dir), detect_heroes=False)
        data = parser.parse()

        # Extract entity IDs and create sequences
        for team_name in ['left', 'right']:
            for player in data['teams'][team_name]:
                name = player['name']
                entity_id = player.get('entity_id')

                if entity_id is not None:
                    self.player_sequences[name] = EventSequence(entity_id, name)
                    print(f"[DATA] Player {name}: entity_id={entity_id}")

        print(f"[DATA] Initialized {len(self.player_sequences)} player sequences")
        print("[STAGE:status:success]")
        print("[STAGE:end:metadata_parsing]")

    def extract_player_events(self):
        """Extract all events for each player across all frames"""
        print("[STAGE:begin:event_extraction]")

        total_events = 0

        for frame_idx, frame_data in enumerate(self.frames):
            if frame_idx % 20 == 0:
                print(f"[DATA] Processing frame {frame_idx}/{len(self.frames)}...")

            for player_name, sequence in self.player_sequences.items():
                entity_id = sequence.entity_id

                # Search for [entity_id][00 00][action_code] pattern
                pattern_base = entity_id.to_bytes(2, 'little') + b'\x00\x00'

                idx = 0
                while True:
                    idx = frame_data.find(pattern_base, idx)
                    if idx == -1:
                        break

                    if idx + 4 < len(frame_data):
                        action_code = frame_data[idx + 4]
                        sequence.add_event(frame_idx, action_code)
                        total_events += 1

                    idx += 1

        print(f"[DATA] Extracted {total_events} total events")

        # Show event counts per player
        for name, sequence in self.player_sequences.items():
            print(f"[STAT:{name}_events] {len(sequence.events)}")

        print("[STAGE:status:success]")
        print("[STAGE:end:event_extraction]")

    def detect_death_candidates(self):
        """
        Detect death candidate frames using sudden_drop heuristic.
        A death likely causes a sudden drop in event activity.
        """
        print("[STAGE:begin:death_detection]")

        WINDOW_SIZE = 5  # frames to compare
        DROP_THRESHOLD = 0.5  # 50% drop in activity

        for name, sequence in self.player_sequences.items():
            # Count events per frame
            events_per_frame = defaultdict(int)
            for frame_idx, _ in sequence.events:
                events_per_frame[frame_idx] += 1

            # Find sudden drops
            frame_indices = sorted(events_per_frame.keys())

            for i in range(len(frame_indices) - WINDOW_SIZE):
                current_frame = frame_indices[i]
                next_frames = frame_indices[i+1:i+1+WINDOW_SIZE]

                current_activity = events_per_frame[current_frame]
                avg_next_activity = sum(events_per_frame[f] for f in next_frames) / len(next_frames)

                if current_activity > 0:
                    drop_ratio = avg_next_activity / current_activity

                    if drop_ratio < DROP_THRESHOLD and current_activity >= 3:
                        self.death_candidate_frames[name].append(current_frame)

        # Report candidates
        for name, frames in self.death_candidate_frames.items():
            truth_deaths = self.TRUTH_DEATHS.get(name, 0)
            print(f"[FINDING] {name}: {len(frames)} death candidates vs {truth_deaths} truth deaths")
            print(f"[STAT:{name}_candidates] {frames}")

        print("[STAGE:status:success]")
        print("[STAGE:end:death_detection]")

    def analyze_ngrams(self, n: int = 2):
        """
        Analyze n-gram patterns and compare frequency near death candidates.

        Returns:
            dict: Analysis results for n-grams
        """
        print(f"[STAGE:begin:ngram_analysis_n={n}]")

        results = {
            'n': n,
            'players': {},
        }

        for name, sequence in self.player_sequences.items():
            ngrams = sequence.get_ngrams(n)

            # Overall n-gram frequency
            overall_freq = Counter(ngram for _, ngram in ngrams)

            # N-grams near death candidates (within ±5 frames)
            death_frames = set(self.death_candidate_frames[name])
            death_ngrams = Counter()

            for frame_idx, ngram in ngrams:
                # Check if this n-gram is near any death candidate
                for death_frame in death_frames:
                    if abs(frame_idx - death_frame) <= 5:
                        death_ngrams[ngram] += 1
                        break

            # Find n-grams that are enriched near deaths
            enriched_ngrams = []

            for ngram, death_count in death_ngrams.items():
                overall_count = overall_freq[ngram]

                # Calculate enrichment ratio
                # (death_count / total_death_contexts) / (overall_count / total_contexts)
                total_death_contexts = sum(death_ngrams.values())
                total_contexts = len(ngrams)

                if total_death_contexts > 0 and total_contexts > 0:
                    death_density = death_count / total_death_contexts
                    overall_density = overall_count / total_contexts

                    if overall_density > 0:
                        enrichment = death_density / overall_density

                        # Only report if enriched and occurs near multiple deaths
                        if enrichment > 2.0 and death_count >= 2:
                            enriched_ngrams.append({
                                'ngram': [f"0x{c:02X}" for c in ngram],
                                'death_count': death_count,
                                'overall_count': overall_count,
                                'enrichment': round(enrichment, 2),
                            })

            # Sort by enrichment
            enriched_ngrams.sort(key=lambda x: -x['enrichment'])

            results['players'][name] = {
                'total_ngrams': len(ngrams),
                'unique_ngrams': len(overall_freq),
                'death_candidate_frames': self.death_candidate_frames[name],
                'enriched_ngrams': enriched_ngrams[:20],  # Top 20
            }

            print(f"[FINDING] {name}: {len(enriched_ngrams)} enriched {n}-grams near deaths")

        print(f"[STAGE:status:success]")
        print(f"[STAGE:end:ngram_analysis_n={n}]")

        return results

    def analyze_cross_team_patterns(self):
        """
        Analyze killer's event patterns when victim dies.

        For each death candidate:
        - Identify the victim's team
        - Check all enemy players' events in the same time window
        - Find n-grams that occur for enemies during victim deaths
        """
        print("[STAGE:begin:cross_team_analysis]")

        results = {
            'victim_killer_patterns': {}
        }

        WINDOW = 5  # frames before/after death

        # Build dynamic team mapping from parsed player data
        dynamic_team_map = {}
        for pname in self.player_sequences:
            # Try hero name mapping first, then infer from entity ID
            for hero, team in self.TEAM_MAPPING.items():
                if hero.lower() in pname.lower():
                    dynamic_team_map[pname] = team
                    break
            if pname not in dynamic_team_map:
                # Fallback: assign based on entity ID (odd index = team 1, even = team 2)
                idx = list(self.player_sequences.keys()).index(pname)
                dynamic_team_map[pname] = 1 if idx < len(self.player_sequences) // 2 else 2

        for victim_name, death_frames in self.death_candidate_frames.items():
            victim_team = dynamic_team_map.get(victim_name, 0)
            if victim_team == 0:
                continue

            # Get enemy players
            enemy_players = [
                name for name, team in dynamic_team_map.items()
                if team != victim_team
            ]

            # For each death, collect enemy n-grams in the window
            enemy_ngrams_at_deaths = defaultdict(lambda: Counter())

            for death_frame in death_frames:
                frame_window = range(max(0, death_frame - WINDOW), death_frame + WINDOW + 1)

                for enemy_name in enemy_players:
                    if enemy_name not in self.player_sequences:
                        continue

                    sequence = self.player_sequences[enemy_name]

                    # Get 2-grams in this window
                    for frame_idx, ngram in sequence.get_ngrams(2):
                        if frame_idx in frame_window:
                            enemy_ngrams_at_deaths[enemy_name][ngram] += 1

            results['victim_killer_patterns'][victim_name] = {
                'death_count': len(death_frames),
                'enemy_patterns': {}
            }

            for enemy_name, ngram_counts in enemy_ngrams_at_deaths.items():
                # Find most common enemy n-grams during this victim's deaths
                top_ngrams = ngram_counts.most_common(10)

                results['victim_killer_patterns'][victim_name]['enemy_patterns'][enemy_name] = [
                    {
                        'ngram': [f"0x{c:02X}" for c in ngram],
                        'count': count,
                    }
                    for ngram, count in top_ngrams
                ]

        print("[STAGE:status:success]")
        print("[STAGE:end:cross_team_analysis]")

        return results

    def find_unique_death_ngrams(self):
        """
        Find n-grams that ONLY occur near death candidates.
        These are the strongest kill/death sequence candidates.
        """
        print("[STAGE:begin:unique_ngram_search]")

        results = {
            'unique_death_ngrams': {}
        }

        for name, sequence in self.player_sequences.items():
            death_frames = set(self.death_candidate_frames[name])

            # Get all 2-grams and 3-grams
            for n in [2, 3]:
                ngrams = sequence.get_ngrams(n)

                # Classify each unique n-gram
                ngram_contexts = defaultdict(lambda: {'death': 0, 'normal': 0})

                for frame_idx, ngram in ngrams:
                    is_near_death = any(abs(frame_idx - df) <= 3 for df in death_frames)

                    if is_near_death:
                        ngram_contexts[ngram]['death'] += 1
                    else:
                        ngram_contexts[ngram]['normal'] += 1

                # Find n-grams that ONLY occur near deaths
                unique_death = []

                for ngram, counts in ngram_contexts.items():
                    if counts['death'] >= 2 and counts['normal'] == 0:
                        unique_death.append({
                            'ngram': [f"0x{c:02X}" for c in ngram],
                            'death_occurrences': counts['death'],
                        })

                if unique_death:
                    key = f"{name}_unique_{n}grams"
                    results['unique_death_ngrams'][key] = unique_death
                    print(f"[FINDING] {name}: {len(unique_death)} UNIQUE {n}-grams only at deaths")

        print("[STAGE:status:success]")
        print("[STAGE:end:unique_ngram_search]")

        return results

    def run_full_analysis(self) -> Dict:
        """Run complete analysis pipeline"""
        print("[OBJECTIVE] Identify kill/death event sequences through n-gram analysis")

        self.load_replay_frames()
        self.parse_player_metadata()
        self.extract_player_events()
        self.detect_death_candidates()

        # Analyze n-grams
        results = {
            'replay': str(self.replay_cache_dir),
            'truth_data': self.TRUTH_DEATHS,
            'analysis': {}
        }

        # 2-gram analysis
        results['analysis']['2grams'] = self.analyze_ngrams(n=2)

        # 3-gram analysis
        results['analysis']['3grams'] = self.analyze_ngrams(n=3)

        # Cross-team patterns
        results['analysis']['cross_team'] = self.analyze_cross_team_patterns()

        # Unique death n-grams
        results['analysis']['unique_death'] = self.find_unique_death_ngrams()

        return results


def main():
    replay_cache = Path("D:/Desktop/My Folder/Game/VG/vg replay/21.11.04/cache/")
    output_path = Path("D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/kill_sequence_analysis.json")

    # Create output directory
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Run analysis
    detector = KillSequenceDetector(str(replay_cache))
    results = detector.run_full_analysis()

    # Save results
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\n[FINDING] Analysis complete - results saved to {output_path}")
    print(f"[STAT:total_players] {len(results['analysis']['2grams']['players'])}")

    # Summary
    print("\n=== SUMMARY ===")
    for name, data in results['analysis']['2grams']['players'].items():
        enriched_count = len(data['enriched_ngrams'])
        print(f"{name}: {enriched_count} enriched 2-grams")


if __name__ == '__main__':
    main()
