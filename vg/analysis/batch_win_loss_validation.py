#!/usr/bin/env python3
"""
Batch Win/Loss Detection Validation
Tests WinLossDetector across multiple replays from tournament and regular matches.
"""

import sys
import json
import time
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
from collections import defaultdict

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from vg.analysis.win_loss_detector import WinLossDetector, MatchOutcome


class BatchValidator:
    """Batch validation for win/loss detection"""

    def __init__(self, replay_base_dir: str):
        self.replay_base_dir = Path(replay_base_dir)
        self.results: List[Dict] = []
        self.stats = {
            'total': 0,
            'success': 0,
            'failed': 0,
            'errors': 0,
            'total_confidence': 0.0,
            'by_method': defaultdict(int),
            'by_mode': defaultdict(int)
        }

    def find_replay_files(self, max_replays: int = 15) -> List[Path]:
        """
        Find replay files from date folders and tournament folders.

        Returns up to max_replays .0.vgr files.
        """
        replay_files = []

        # Tournament replays (prioritize these - known competitive matches)
        tournament_dir = self.replay_base_dir / "Tournament_Replays"
        if tournament_dir.exists():
            for subdir in tournament_dir.iterdir():
                if subdir.is_dir() and subdir.name != "__MACOSX":
                    # Search recursively for .0.vgr files
                    for vgr_file in subdir.rglob("*.0.vgr"):
                        if not vgr_file.name.startswith("._"):
                            replay_files.append(vgr_file)
                            print(f"[DATA] Found tournament replay: {subdir.name}/{vgr_file.parent.name}")

        # Regular date-based replays
        date_folders = [
            d for d in self.replay_base_dir.iterdir()
            if d.is_dir() and d.name not in ["Tournament_Replays", "__MACOSX", "vaingloryreplay-master", "replay-test", "리플레이팩"]
        ]

        # Sort by name (date format)
        date_folders.sort(reverse=True)

        for date_folder in date_folders:
            if len(replay_files) >= max_replays:
                break

            # Look for cache subdirectory
            cache_dir = date_folder / "cache"
            if cache_dir.exists():
                vgr_files = list(cache_dir.glob("*.0.vgr"))
                for vgr_file in vgr_files[:2]:  # Take up to 2 replays per date folder
                    if not vgr_file.name.startswith("._"):
                        replay_files.append(vgr_file)
                        print(f"[DATA] Found replay in {date_folder.name}/cache")
                        if len(replay_files) >= max_replays:
                            break

        print(f"\n[DATA] Total replays to test: {len(replay_files)}")
        return replay_files[:max_replays]

    def analyze_single_replay(self, replay_path: Path) -> Dict:
        """
        Analyze a single replay and collect detailed metrics.

        Returns dict with:
        - replay_name, path, success, winner, confidence, method
        - turret_counts, cluster_gap, crystal_events
        - error (if failed)
        """
        result = {
            'replay_name': replay_path.parent.name,
            'path': str(replay_path),
            'success': False,
            'winner': 'unknown',
            'confidence': 0.0,
            'method': 'none',
            'turret_team1': 0,
            'turret_team2': 0,
            'cluster_gap': 0,
            'total_frames': 0,
            'crystal_frame': 0,
            'error': None,
            'analysis_time': 0.0
        }

        print(f"\n{'='*70}")
        print(f"Analyzing: {result['replay_name']}")
        print(f"Path: {replay_path}")
        print(f"{'='*70}")

        try:
            start_time = time.time()

            # Run detector
            detector = WinLossDetector(str(replay_path), debug=False)
            outcome: Optional[MatchOutcome] = detector.detect_winner()

            analysis_time = time.time() - start_time
            result['analysis_time'] = analysis_time

            if outcome:
                result['success'] = True
                result['winner'] = outcome.winner
                result['confidence'] = outcome.confidence
                result['method'] = outcome.method
                result['turret_team1'] = outcome.left_turrets_destroyed
                result['turret_team2'] = outcome.right_turrets_destroyed
                result['total_frames'] = outcome.total_frames
                result['crystal_frame'] = outcome.crystal_destruction_frame

                print(f"\n[FINDING] Winner: {outcome.winner} (confidence: {outcome.confidence:.1%})")
                print(f"[STAT:crystal_frame] {outcome.crystal_destruction_frame}")
                print(f"[STAT:total_frames] {outcome.total_frames}")
                print(f"[STAT:team1_turrets] {outcome.left_turrets_destroyed}")
                print(f"[STAT:team2_turrets] {outcome.right_turrets_destroyed}")
                print(f"[STAT:analysis_time] {analysis_time:.2f}s")

                self.stats['success'] += 1
                self.stats['total_confidence'] += outcome.confidence
                self.stats['by_method'][outcome.method] += 1
            else:
                result['error'] = "Detection failed - no outcome"
                print(f"\n[LIMITATION] Detection failed - could not determine winner")
                self.stats['failed'] += 1

        except Exception as e:
            result['error'] = str(e)
            print(f"\n[ERROR] Analysis failed: {e}")
            self.stats['errors'] += 1

        self.stats['total'] += 1
        self.results.append(result)

        return result

    def run_batch_validation(self, max_replays: int = 15):
        """Execute batch validation"""
        print("[STAGE:begin:batch_validation]")
        print(f"[OBJECTIVE] Validate win/loss detection across {max_replays} replays\n")

        # Find replays
        replay_files = self.find_replay_files(max_replays)

        if not replay_files:
            print("[LIMITATION] No replay files found")
            print("[STAGE:status:fail]")
            print("[STAGE:end:batch_validation]")
            return

        # Analyze each replay
        for replay_file in replay_files:
            self.analyze_single_replay(replay_file)

        print("[STAGE:status:success]")
        print("[STAGE:end:batch_validation]")

    def generate_statistics(self) -> Dict:
        """Calculate aggregate statistics"""
        stats = {
            'total_replays': self.stats['total'],
            'successful_detections': self.stats['success'],
            'failed_detections': self.stats['failed'],
            'errors': self.stats['errors'],
            'success_rate': self.stats['success'] / self.stats['total'] if self.stats['total'] > 0 else 0.0,
            'average_confidence': self.stats['total_confidence'] / self.stats['success'] if self.stats['success'] > 0 else 0.0,
            'detection_methods': dict(self.stats['by_method']),
            'winner_distribution': {
                'left': sum(1 for r in self.results if r['winner'] == 'left'),
                'right': sum(1 for r in self.results if r['winner'] == 'right'),
                'team1': sum(1 for r in self.results if r['winner'] == 'team1'),
                'team2': sum(1 for r in self.results if r['winner'] == 'team2'),
                'unknown': sum(1 for r in self.results if r['winner'] == 'unknown')
            },
            'average_analysis_time': sum(r['analysis_time'] for r in self.results) / len(self.results) if self.results else 0.0
        }

        # Confidence distribution
        confidences = [r['confidence'] for r in self.results if r['success']]
        if confidences:
            stats['confidence_distribution'] = {
                'min': min(confidences),
                'max': max(confidences),
                'median': sorted(confidences)[len(confidences)//2]
            }

        return stats

    def save_results(self, output_dir: Path):
        """Save results to JSON and markdown report"""
        output_dir.mkdir(parents=True, exist_ok=True)

        # Generate statistics
        stats = self.generate_statistics()

        # JSON output
        json_output = {
            'metadata': {
                'timestamp': datetime.now().isoformat(),
                'replay_base_dir': str(self.replay_base_dir),
                'total_analyzed': self.stats['total']
            },
            'statistics': stats,
            'results': self.results
        }

        json_path = output_dir / "win_loss_batch_validation.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(json_output, f, indent=2, ensure_ascii=False)

        print(f"\n[FINDING] JSON results saved to {json_path}")

        # Markdown report
        self._generate_markdown_report(output_dir, stats)

    def _generate_markdown_report(self, output_dir: Path, stats: Dict):
        """Generate markdown summary report"""
        md_path = output_dir / "win_loss_batch_report.md"

        with open(md_path, 'w', encoding='utf-8') as f:
            f.write("# Win/Loss Detection Batch Validation Report\n\n")
            f.write(f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

            # Executive Summary
            f.write("## Executive Summary\n\n")
            f.write(f"Validated win/loss detection algorithm across **{stats['total_replays']} replays** ")
            f.write(f"from tournament matches and regular gameplay.\n\n")
            f.write(f"**Success Rate**: {stats['success_rate']:.1%} ")
            f.write(f"({stats['successful_detections']}/{stats['total_replays']} replays)\n\n")
            f.write(f"**Average Confidence**: {stats['average_confidence']:.1%}\n\n")

            # Key Statistics
            f.write("## Key Statistics\n\n")
            f.write("| Metric | Value |\n")
            f.write("|--------|-------|\n")
            f.write(f"| Total Replays | {stats['total_replays']} |\n")
            f.write(f"| Successful Detections | {stats['successful_detections']} |\n")
            f.write(f"| Failed Detections | {stats['failed_detections']} |\n")
            f.write(f"| Errors | {stats['errors']} |\n")
            f.write(f"| Success Rate | {stats['success_rate']:.1%} |\n")
            f.write(f"| Average Confidence | {stats['average_confidence']:.1%} |\n")
            f.write(f"| Average Analysis Time | {stats['average_analysis_time']:.2f}s |\n")

            # Confidence Distribution
            if 'confidence_distribution' in stats:
                f.write("\n### Confidence Distribution\n\n")
                f.write("| Statistic | Value |\n")
                f.write("|-----------|-------|\n")
                f.write(f"| Minimum | {stats['confidence_distribution']['min']:.1%} |\n")
                f.write(f"| Median | {stats['confidence_distribution']['median']:.1%} |\n")
                f.write(f"| Maximum | {stats['confidence_distribution']['max']:.1%} |\n")

            # Detection Methods
            f.write("\n## Detection Methods Used\n\n")
            for method, count in stats['detection_methods'].items():
                f.write(f"- **{method}**: {count} replays\n")

            # Winner Distribution
            f.write("\n## Winner Distribution\n\n")
            f.write("| Team | Count |\n")
            f.write("|------|-------|\n")
            for team, count in stats['winner_distribution'].items():
                f.write(f"| {team} | {count} |\n")

            # Detailed Results
            f.write("\n## Detailed Results\n\n")
            f.write("| Replay | Winner | Confidence | Method | Turrets T1/T2 | Crystal Frame |\n")
            f.write("|--------|--------|------------|--------|---------------|---------------|\n")

            for result in self.results:
                name = result['replay_name'][:30]  # Truncate long names
                winner = result['winner']
                conf = f"{result['confidence']:.1%}" if result['success'] else "N/A"
                method = result['method'][:20]
                turrets = f"{result['turret_team1']}/{result['turret_team2']}"
                crystal = result['crystal_frame'] if result['success'] else "N/A"

                f.write(f"| {name} | {winner} | {conf} | {method} | {turrets} | {crystal} |\n")

            # Failed Cases
            failed_results = [r for r in self.results if not r['success']]
            if failed_results:
                f.write("\n## Failed Detection Cases\n\n")
                for result in failed_results:
                    f.write(f"### {result['replay_name']}\n\n")
                    f.write(f"**Error**: {result['error']}\n\n")
                    f.write(f"**Path**: `{result['path']}`\n\n")

            # Limitations
            f.write("\n## Limitations\n\n")
            f.write("- **Sample Size**: Limited to available replay files\n")
            f.write("- **Match Mode**: Unable to distinguish 3v3 vs 5v5 from current data\n")
            f.write("- **Surrender Detection**: Algorithm assumes crystal destruction; surrenders may fail\n")
            f.write("- **Team Mapping**: left/right/team1/team2 labels may vary based on entity ID clustering\n")

            f.write("\n---\n")
            f.write("*Generated by batch_win_loss_validation.py*\n")

        print(f"[FINDING] Markdown report saved to {md_path}")


def main():
    """CLI entry point"""
    import argparse

    parser = argparse.ArgumentParser(
        description='Batch validation for win/loss detection'
    )
    parser.add_argument(
        '--replay-dir',
        default='D:/Desktop/My Folder/Game/VG/vg replay/',
        help='Base directory containing replay folders'
    )
    parser.add_argument(
        '--output-dir',
        default='D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output',
        help='Output directory for results'
    )
    parser.add_argument(
        '--max-replays',
        type=int,
        default=15,
        help='Maximum number of replays to test'
    )

    args = parser.parse_args()

    # Run validation
    validator = BatchValidator(args.replay_dir)
    validator.run_batch_validation(max_replays=args.max_replays)

    # Print summary
    print("\n" + "="*70)
    print("VALIDATION SUMMARY")
    print("="*70)

    stats = validator.generate_statistics()

    print(f"\n[STAT:total_replays] {stats['total_replays']}")
    print(f"[STAT:success_rate] {stats['success_rate']:.1%}")
    print(f"[STAT:average_confidence] {stats['average_confidence']:.1%}")
    print(f"[STAT:successful_detections] {stats['successful_detections']}")
    print(f"[STAT:failed_detections] {stats['failed_detections']}")
    print(f"[STAT:errors] {stats['errors']}")

    print(f"\n[FINDING] Success rate: {stats['success_rate']:.1%} ({stats['successful_detections']}/{stats['total_replays']})")
    print(f"[FINDING] Average confidence for successful detections: {stats['average_confidence']:.1%}")

    # Save results
    validator.save_results(Path(args.output_dir))

    print("\n[STAGE:begin:reporting]")
    print(f"Results saved to {args.output_dir}")
    print("[STAGE:status:success]")
    print("[STAGE:end:reporting]")


if __name__ == '__main__':
    main()
