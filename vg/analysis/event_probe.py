#!/usr/bin/env python3
"""
Event probe for Vainglory replays.
Extracts per-entity action counts and optionally correlates with truth data.

Phase 2 Enhancement: Statistical correlation analysis with p-values and exact match validation.
"""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

import numpy as np
from scipy import stats

from vgr_mapping import HERO_NAME_TO_ID
from vgr_parser import VGRParser


def read_all_frames(frame_dir: Path, replay_name: str) -> bytes:
    frames = list(frame_dir.glob(f"{replay_name}.*.vgr"))

    def frame_index(path: Path) -> int:
        try:
            return int(path.stem.split(".")[-1])
        except ValueError:
            return 0

    frames.sort(key=frame_index)
    return b"".join(frame.read_bytes() for frame in frames)


def load_truth(path: Optional[str]) -> Dict[str, Any]:
    if not path:
        return {}
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    matches = data.get("matches", [])
    return {m.get("replay_name"): m for m in matches if m.get("replay_name")}


def iter_replays(path: Path, batch: bool) -> List[Path]:
    if path.is_file() and path.name.endswith(".0.vgr"):
        return [path]
    if path.is_dir():
        if batch:
            replays = []
            for vgr in path.rglob("*.0.vgr"):
                if vgr.name.startswith("._") or "__MACOSX" in vgr.parts:
                    continue
                replays.append(vgr)
            return replays
        # non-batch: take first .0.vgr
        for vgr in path.rglob("*.0.vgr"):
            if vgr.name.startswith("._") or "__MACOSX" in vgr.parts:
                continue
            return [vgr]
    return []


def compute_correlations(rows: List[Dict[str, Any]], top_n: int = 20) -> Dict[str, List[Dict[str, Any]]]:
    """
    Compute Pearson correlations between action counts and K/D/A stats.
    Enhanced with p-values and confidence levels.
    """
    all_actions = set()
    for row in rows:
        all_actions.update(row["counts"].keys())
    actions = sorted(all_actions)
    action_index = {a: i for i, a in enumerate(actions)}

    X = np.zeros((len(rows), len(actions)), dtype=np.float64)
    for i, row in enumerate(rows):
        for act, cnt in row["counts"].items():
            X[i, action_index[act]] = cnt

    def top_corr(target_key: str) -> List[Dict[str, Any]]:
        y = np.array([row[target_key] for row in rows], dtype=np.float64)
        corrs = []
        for i, act in enumerate(actions):
            x = X[:, i]
            if x.std() == 0 or y.std() == 0:
                continue
            # Pearson correlation with p-value
            corr, pvalue = stats.pearsonr(x, y)
            # Confidence level
            if pvalue < 0.01:
                confidence = "high"
            elif pvalue < 0.05:
                confidence = "medium"
            else:
                confidence = "low"
            corrs.append((abs(corr), corr, pvalue, confidence, act))
        corrs.sort(reverse=True)
        return [
            {"action": act, "corr": round(corr, 4), "pvalue": round(pvalue, 6), "confidence": confidence}
            for _, corr, pvalue, confidence, act in corrs[:top_n]
        ]

    return {
        "kills": top_corr("kills"),
        "deaths": top_corr("deaths"),
        "assists": top_corr("assists"),
        "gold": top_corr("gold"),
        "minion_kills": top_corr("minion_kills"),
    }


def validate_exact_matches(rows: List[Dict[str, Any]], candidate_actions: List[str]) -> Dict[str, Dict[str, Any]]:
    """
    Validate if specific action codes exactly match K/D/A counts.
    This is crucial for confirming events like death (0x80).
    """
    results = {}

    for action in candidate_actions:
        exact_matches = 0
        within_one = 0
        total = 0
        errors = []

        for row in rows:
            action_count = row["counts"].get(action, 0)

            # Check against each stat
            for stat in ["kills", "deaths", "assists"]:
                stat_value = row.get(stat, 0)
                if stat_value == 0:
                    continue  # Skip zero values for meaningful validation

                total += 1
                diff = abs(action_count - stat_value)

                if diff == 0:
                    exact_matches += 1
                elif diff <= 1:
                    within_one += 1
                else:
                    errors.append({
                        "player": row.get("name", "unknown"),
                        "stat": stat,
                        "action_count": action_count,
                        "truth_value": stat_value,
                        "diff": diff
                    })

        if total > 0:
            results[action] = {
                "exact_match_rate": round(exact_matches / total, 4),
                "within_one_rate": round((exact_matches + within_one) / total, 4),
                "total_comparisons": total,
                "sample_errors": errors[:5]  # Keep only first 5 errors
            }

    return results


def find_death_action_candidates(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Find action codes that might represent death events.
    Criteria: action_count should closely match deaths count.
    """
    all_actions = set()
    for row in rows:
        all_actions.update(row["counts"].keys())

    candidates = []

    for action in sorted(all_actions):
        matches = 0
        total = 0
        total_diff = 0

        for row in rows:
            deaths = row.get("deaths", 0)
            action_count = row["counts"].get(action, 0)

            if deaths > 0:  # Only count players who died
                total += 1
                diff = abs(action_count - deaths)
                total_diff += diff

                if diff == 0:
                    matches += 1

        if total >= 5:  # Minimum sample size
            match_rate = matches / total
            avg_error = total_diff / total

            if match_rate > 0.1 or avg_error < 3.0:  # Relaxed criteria
                candidates.append({
                    "action": action,
                    "exact_match_rate": round(match_rate, 4),
                    "avg_error": round(avg_error, 4),
                    "sample_size": total
                })

    # Sort by exact match rate descending
    candidates.sort(key=lambda x: (-x["exact_match_rate"], x["avg_error"]))
    return candidates[:20]


def analyze_event_payload(data: bytes, entity_id: int, action_code: int, window: int = 20) -> List[Dict[str, Any]]:
    """
    Analyze payload bytes following specific action events.
    Returns samples of byte patterns after the action code.
    """
    base = entity_id.to_bytes(2, 'little') + b'\x00\x00'
    target_action = action_code
    samples = []

    idx = 0
    while len(samples) < 10:  # Limit samples
        idx = data.find(base, idx)
        if idx == -1:
            break
        if idx + 5 + window >= len(data):
            break

        action = data[idx + 4]
        if action == target_action:
            payload = data[idx + 5:idx + 5 + window]
            samples.append({
                "offset": idx,
                "payload_hex": payload.hex(),
                "payload_bytes": list(payload)
            })

        idx += 1

    return samples


def compare_action_patterns(rows: List[Dict[str, Any]], stat: str) -> Dict[str, Any]:
    """
    Compare action patterns between players with stat=0 and stat>0.
    Identifies actions that appear significantly more in one group.
    """
    zero_group = [r for r in rows if r.get(stat, 0) == 0]
    nonzero_group = [r for r in rows if r.get(stat, 0) > 0]

    if not zero_group or not nonzero_group:
        return {"error": "Not enough data in groups"}

    # Aggregate action counts per group
    def aggregate_counts(group: List[Dict]) -> Dict[str, float]:
        total = Counter()
        for row in group:
            total.update(row["counts"])
        # Normalize by group size
        return {k: v / len(group) for k, v in total.items()}

    zero_avg = aggregate_counts(zero_group)
    nonzero_avg = aggregate_counts(nonzero_group)

    # Find actions with biggest difference (nonzero - zero)
    all_actions = set(zero_avg.keys()) | set(nonzero_avg.keys())
    diffs = []

    for action in all_actions:
        z = zero_avg.get(action, 0)
        nz = nonzero_avg.get(action, 0)
        if nz > 0 or z > 0:
            ratio = nz / (z + 0.1)  # Avoid division by zero
            diffs.append({
                "action": action,
                "zero_avg": round(z, 2),
                "nonzero_avg": round(nz, 2),
                "diff": round(nz - z, 2),
                "ratio": round(ratio, 2)
            })

    # Sort by difference (actions more common in nonzero group)
    diffs.sort(key=lambda x: -x["diff"])

    return {
        "stat": stat,
        "zero_count": len(zero_group),
        "nonzero_count": len(nonzero_group),
        "top_positive_diff": diffs[:10],
        "top_negative_diff": sorted(diffs, key=lambda x: x["diff"])[:10]
    }


def find_multiplied_matches(rows: List[Dict[str, Any]], stat: str, multipliers: List[int] = [1, 2, 3]) -> List[Dict[str, Any]]:
    """
    Find action codes where count / multiplier matches the stat.
    Useful for events that fire multiple times per stat (e.g., death start + death end).
    """
    all_actions = set()
    for row in rows:
        all_actions.update(row["counts"].keys())

    results = []

    for action in sorted(all_actions):
        for mult in multipliers:
            exact = 0
            within_1 = 0
            total = 0

            for row in rows:
                stat_value = row.get(stat, 0)
                action_count = row["counts"].get(action, 0)

                # Skip if stat is 0 (no meaningful comparison)
                if stat_value == 0:
                    continue

                total += 1
                expected = stat_value * mult
                diff = abs(action_count - expected)

                if diff == 0:
                    exact += 1
                if diff <= 1:
                    within_1 += 1

            if total >= 10:  # Minimum sample size
                exact_rate = exact / total
                if exact_rate > 0.2:  # Only keep promising candidates
                    results.append({
                        "action": action,
                        "multiplier": mult,
                        "exact_rate": round(exact_rate, 4),
                        "within_1_rate": round(within_1 / total, 4),
                        "sample_size": total
                    })

    results.sort(key=lambda x: -x["exact_rate"])
    return results[:15]


def analyze_stat_matches(rows: List[Dict[str, Any]], stat: str) -> List[Dict[str, Any]]:
    """
    Analyze which action codes best match a specific stat (kills, deaths, or assists).
    Returns top candidates with detailed match statistics.
    """
    all_actions = set()
    for row in rows:
        all_actions.update(row["counts"].keys())

    candidates = []

    for action in sorted(all_actions):
        exact = 0
        within_1 = 0
        within_2 = 0
        total = 0
        total_diff = 0
        details = []

        for row in rows:
            stat_value = row.get(stat, 0)
            action_count = row["counts"].get(action, 0)

            # Include all players, even those with stat=0
            total += 1
            diff = abs(action_count - stat_value)
            total_diff += diff

            if diff == 0:
                exact += 1
            if diff <= 1:
                within_1 += 1
            if diff <= 2:
                within_2 += 1

            # Track mismatches for debugging
            if stat_value > 0 and diff > 0:
                details.append({
                    "name": row.get("name", "?"),
                    "expected": stat_value,
                    "got": action_count,
                    "diff": diff
                })

        if total > 0:
            avg_error = total_diff / total
            candidates.append({
                "action": action,
                "exact_match": exact,
                "exact_rate": round(exact / total, 4),
                "within_1_rate": round(within_1 / total, 4),
                "within_2_rate": round(within_2 / total, 4),
                "avg_error": round(avg_error, 4),
                "sample_size": total,
                "mismatches": details[:3]  # Sample mismatches
            })

    # Sort by exact match rate, then by avg_error
    candidates.sort(key=lambda x: (-x["exact_rate"], x["avg_error"]))
    return candidates[:15]


def main() -> int:
    parser = argparse.ArgumentParser(description="VGR event probe")
    parser.add_argument("path", help="Replay folder or .0.vgr file")
    parser.add_argument("--batch", action="store_true", help="Scan all .0.vgr under path")
    parser.add_argument("--truth", help="Truth JSON path (optional)")
    parser.add_argument("--output", default="event_probe_output.json", help="Output JSON path")
    parser.add_argument("--hero-probe", action="store_true", help="Probe hero-id offsets near entity events")
    parser.add_argument("--hero-window", type=int, default=80, help="Window size for hero probe")
    parser.add_argument("--top-actions", type=int, default=20, help="Top action counts per player to keep")
    args = parser.parse_args()

    replays = iter_replays(Path(args.path), args.batch)
    if not replays:
        print("No .0.vgr files found.")
        return 1

    truth_map = load_truth(args.truth)

    output = {"replays": [], "summary": {}}
    truth_rows = []
    hero_probe_counts = Counter()
    hero_probe_action = defaultdict(Counter)

    for replay in replays:
        parser_obj = VGRParser(str(replay), auto_truth=False)
        parsed = parser_obj.parse()
        replay_name = parsed["replay_name"]
        all_data = read_all_frames(replay.parent, replay_name)

        players = []
        for team in ("left", "right"):
            players.extend(parsed["teams"][team])

        truth_match = truth_map.get(replay_name)
        truth_players = truth_match.get("players", {}) if truth_match else {}

        replay_entry = {
            "replay_name": replay_name,
            "replay_file": str(replay),
            "players": [],
            "truth_available": bool(truth_match),
        }

        for player in players:
            name = player["name"]
            entity_id = player.get("entity_id")
            if entity_id is None:
                continue
            counts = parser_obj._scan_entity_actions(all_data, entity_id)
            # keep top action counts for readability
            counts_sorted = dict(Counter(counts).most_common(args.top_actions))
            entry = {
                "name": name,
                "entity_id": entity_id,
                "action_counts": counts_sorted,
            }
            tdata = truth_players.get(name)
            if tdata:
                entry["truth"] = {
                    "hero_name": tdata.get("hero_name"),
                    "kills": tdata.get("kills"),
                    "deaths": tdata.get("deaths"),
                    "assists": tdata.get("assists"),
                    "gold": tdata.get("gold"),
                    "minion_kills": tdata.get("minion_kills"),
                    "bounty": tdata.get("bounty"),
                }
                truth_rows.append({
                    "name": name,
                    "counts": counts,  # Full counts for analysis
                    "kills": tdata.get("kills", 0),
                    "deaths": tdata.get("deaths", 0),
                    "assists": tdata.get("assists", 0),
                    "gold": tdata.get("gold", 0),
                    "minion_kills": tdata.get("minion_kills", 0),
                })

                if args.hero_probe and tdata.get("hero_name"):
                    hero_id = HERO_NAME_TO_ID.get(tdata["hero_name"].lower())
                    if hero_id:
                        hero_bytes = bytes([hero_id, 0, 0, 0])
                        base = entity_id.to_bytes(2, "little") + b"\x00\x00"
                        idx = 0
                        while True:
                            idx = all_data.find(base, idx)
                            if idx == -1:
                                break
                            if idx + 4 >= len(all_data):
                                break
                            action = all_data[idx + 4]
                            window = all_data[idx:idx + args.hero_window]
                            hpos = window.find(hero_bytes)
                            if hpos != -1:
                                hero_probe_counts[hpos] += 1
                                hero_probe_action[hpos][action] += 1
                            idx += 1

            replay_entry["players"].append(entry)

        output["replays"].append(replay_entry)

    if truth_rows:
        output["summary"]["correlations"] = compute_correlations(truth_rows)
        output["summary"]["truth_players"] = len(truth_rows)

        # Phase 2: Detailed stat analysis
        output["summary"]["stat_analysis"] = {
            "deaths": analyze_stat_matches(truth_rows, "deaths"),
            "kills": analyze_stat_matches(truth_rows, "kills"),
            "assists": analyze_stat_matches(truth_rows, "assists"),
        }

        # Legacy: Death action candidates
        death_candidates = find_death_action_candidates(truth_rows)
        output["summary"]["death_candidates"] = death_candidates

        # Validate specific actions (including 0x80)
        candidate_actions = ["0x80", "0x44", "0x19", "0x02"]  # Known candidates
        candidate_actions.extend([c["action"] for c in death_candidates[:3]])
        candidate_actions = list(set(candidate_actions))

        exact_validation = validate_exact_matches(truth_rows, candidate_actions)
        output["summary"]["exact_validation"] = exact_validation

        # Summary statistics
        print(f"\n=== Phase 2 Correlation Analysis ===")
        print(f"Truth players analyzed: {len(truth_rows)}")

        print(f"\n--- Deaths Analysis ---")
        for c in output["summary"]["stat_analysis"]["deaths"][:5]:
            print(f"  {c['action']}: exact={c['exact_rate']:.2%}, within_1={c['within_1_rate']:.2%}, avg_err={c['avg_error']:.2f}")

        print(f"\n--- Kills Analysis ---")
        for c in output["summary"]["stat_analysis"]["kills"][:5]:
            print(f"  {c['action']}: exact={c['exact_rate']:.2%}, within_1={c['within_1_rate']:.2%}, avg_err={c['avg_error']:.2f}")

        print(f"\n--- Assists Analysis ---")
        for c in output["summary"]["stat_analysis"]["assists"][:5]:
            print(f"  {c['action']}: exact={c['exact_rate']:.2%}, within_1={c['within_1_rate']:.2%}, avg_err={c['avg_error']:.2f}")

        # Pattern comparison analysis
        output["summary"]["pattern_comparison"] = {
            "deaths": compare_action_patterns(truth_rows, "deaths"),
            "kills": compare_action_patterns(truth_rows, "kills"),
        }

        print(f"\n--- Pattern Comparison (deaths=0 vs deaths>0) ---")
        deaths_comp = output["summary"]["pattern_comparison"]["deaths"]
        print(f"  Groups: zero={deaths_comp['zero_count']}, nonzero={deaths_comp['nonzero_count']}")
        print(f"  Actions more common in deaths>0 group:")
        for item in deaths_comp["top_positive_diff"][:5]:
            print(f"    {item['action']}: diff={item['diff']:+.1f} (zero_avg={item['zero_avg']:.1f}, nonzero_avg={item['nonzero_avg']:.1f})")

        # Multiplied match analysis (for events that fire multiple times per stat)
        output["summary"]["multiplied_matches"] = {
            "deaths": find_multiplied_matches(truth_rows, "deaths"),
            "kills": find_multiplied_matches(truth_rows, "kills"),
        }

        print(f"\n--- Multiplied Match Analysis (deaths) ---")
        print(f"  Looking for action_count = deaths * multiplier")
        for item in output["summary"]["multiplied_matches"]["deaths"][:5]:
            print(f"    {item['action']} x{item['multiplier']}: exact={item['exact_rate']:.2%}, within_1={item['within_1_rate']:.2%}")

    if args.hero_probe and hero_probe_counts:
        top_offsets = []
        for off, cnt in hero_probe_counts.most_common(10):
            actions = hero_probe_action[off].most_common(5)
            top_offsets.append({
                "offset": off,
                "count": cnt,
                "top_actions": [{"action": f"0x{a:02X}", "count": c} for a, c in actions],
            })
        output["summary"]["hero_probe"] = {
            "top_offsets": top_offsets
        }

    Path(args.output).write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
