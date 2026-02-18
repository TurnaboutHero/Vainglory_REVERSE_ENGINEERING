#!/usr/bin/env python3
"""
Header Deep Analysis - Comprehensive investigation of the top unknown event headers.

Targets the 5 most frequent unknown [XX 04 YY] headers:
  1. [10 04 2B] - 408K/match, 166B spacing, 16% playerEID
  2. [24 04 3F] - 176K/match, 396B spacing, 50% playerEID
  3. [10 04 15] - 104K/match, 901B spacing, 20% playerEID
  4. [18 04 0D] -  68K/match, 1088B spacing, 0% playerEID
  5. [05 04 00] -  60K/match, 1242B spacing, has timestamps

For each header:
  - Extract and dump 40-byte payloads
  - Decode all uint16 BE / uint32 BE / float32 BE interpretations
  - Map entity IDs present in payload
  - Measure inter-event timing (frame-based + embedded timestamps)
  - Cross-correlate with kill/death events (proximity within ±200B)
  - Per-player (entity) frequency analysis
  - Compare [24 04 3F] vs [28 04 3F] structure

Usage:
    python -m vg.analysis.header_deep_analysis [replay_dir] [-n 3]
"""

import struct
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import List, Tuple, Dict, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

# ── Known entity ranges ──────────────────────────────────────────────────────
PLAYER_EID_RANGE   = range(1500, 1510)
TURRET_EID_RANGE   = range(1000, 20000)
MINION_EID_RANGE   = range(20000, 50000)
HERO_EID_RANGE     = range(50000, 60000)   # players in-match EID
OBJECTIVE_EID_RANGE = range(2000, 2200)

# ── Headers under investigation ───────────────────────────────────────────────
TARGET_HEADERS = [
    (0x10, 0x04, 0x2B),  # H1 - most frequent unknown
    (0x24, 0x04, 0x3F),  # H2 - player-action variant?
    (0x10, 0x04, 0x15),  # H3
    (0x18, 0x04, 0x0D),  # H4 - no playerEID
    (0x05, 0x04, 0x00),  # H5 - timing/sync?
]

# Known decoded reference (for cross-comparison)
KILL_HDR   = bytes([0x18, 0x04, 0x1C])
DEATH_HDR  = bytes([0x08, 0x04, 0x31])
HBEAT_HDR  = bytes([0x18, 0x04, 0x3E])   # player heartbeat
ACTION_HDR = bytes([0x28, 0x04, 0x3F])   # player action (48B)

PAYLOAD_DUMP_BYTES = 40   # bytes to capture after header
MAX_SAMPLES        = 500  # max event instances per header for stats
HEX_SAMPLES        = 10   # how many to hex-dump per header


# ── Replay loading ─────────────────────────────────────────────────────────────

def load_replay(zero_vgr: Path) -> Tuple[bytes, List[Tuple[int, bytes]]]:
    """Load all frames (skip 0=metadata). Returns (full_data, [(frame_idx, bytes)])."""
    stem = zero_vgr.stem.rsplit('.', 1)[0]
    frame_dir = zero_vgr.parent
    files = list(frame_dir.glob(f"{stem}.*.vgr"))

    def _idx(p: Path) -> int:
        try:
            return int(p.stem.split('.')[-1])
        except ValueError:
            return -1

    files.sort(key=_idx)
    frames = [(i, f.read_bytes()) for f in files
              if (i := _idx(f)) > 0]
    full = b"".join(d for _, d in frames)
    return full, frames


def find_all(data: bytes, pattern: bytes, limit: int = MAX_SAMPLES) -> List[int]:
    """Find all occurrences of pattern up to limit."""
    positions = []
    pos = 0
    while len(positions) < limit:
        idx = data.find(pattern, pos)
        if idx == -1:
            break
        positions.append(idx)
        pos = idx + 1
    return positions


# ── Binary decode helpers ──────────────────────────────────────────────────────

def try_f32_be(data: bytes, offset: int) -> Optional[float]:
    if offset + 4 > len(data):
        return None
    v = struct.unpack_from(">f", data, offset)[0]
    if not (-1e9 < v < 1e9):
        return None
    return v


def try_u16_be(data: bytes, offset: int) -> Optional[int]:
    if offset + 2 > len(data):
        return None
    return struct.unpack_from(">H", data, offset)[0]


def try_u32_be(data: bytes, offset: int) -> Optional[int]:
    if offset + 4 > len(data):
        return None
    return struct.unpack_from(">I", data, offset)[0]


def is_timestamp(v: float) -> bool:
    return 1.0 < v < 3600.0  # 1s to 60min


def is_player_eid(v: int) -> bool:
    return v in PLAYER_EID_RANGE


def classify_eid(v: int) -> str:
    if v in PLAYER_EID_RANGE:
        return "PLAYER_BLOCK"
    if v in OBJECTIVE_EID_RANGE:
        return "OBJECTIVE"
    if v in TURRET_EID_RANGE:
        return "TURRET"
    if v in MINION_EID_RANGE:
        return "MINION"
    if v in HERO_EID_RANGE:
        return "HERO_EID"
    if v == 0:
        return "ZERO"
    if v == 0xFFFF:
        return "FFFF"
    return f"unk({v})"


# ── Per-header analysis ────────────────────────────────────────────────────────

def analyse_header(data: bytes, header: tuple, full_data: bytes,
                   frames: List[Tuple[int, bytes]]) -> dict:
    h_bytes = bytes(header)
    h_hex = f"{header[0]:02X} {header[1]:02X} {header[2]:02X}"

    positions = find_all(full_data, h_bytes)
    total_count = full_data.count(h_bytes)  # actual full count
    n = len(positions)

    if n == 0:
        return {"header": h_hex, "count": 0, "note": "not found"}

    # ── 1. Payload matrix: collect 40 bytes after header ──────────────────────
    payloads = []
    for p in positions:
        end = min(p + 3 + PAYLOAD_DUMP_BYTES, len(full_data))
        payloads.append(full_data[p + 3: end])

    # ── 2. Byte-by-byte most-common values at each payload offset ──────────────
    byte_freq = {}
    for off in range(PAYLOAD_DUMP_BYTES):
        vals = [pl[off] for pl in payloads if off < len(pl)]
        if not vals:
            continue
        ctr = Counter(vals)
        top, top_cnt = ctr.most_common(1)[0]
        byte_freq[off] = {
            "top_byte": f"{top:02X}",
            "pct": round(top_cnt / len(vals) * 100, 1),
            "unique": len(ctr),
        }

    # ── 3. Entity-ID scan at payload offsets +0..+6 ───────────────────────────
    # Standard pattern: [header 3B][00 00][eid BE 2B]...
    eid_at_offset = defaultdict(Counter)
    for p in positions:
        for off in range(0, 8):
            v = try_u16_be(full_data, p + 3 + off)
            if v is not None:
                cat = classify_eid(v)
                if cat != f"unk({v})":
                    eid_at_offset[off][cat] += 1

    # Most likely EID offset
    best_eid_off = None
    best_eid_cnt = 0
    for off, ctr in eid_at_offset.items():
        player_cnt = ctr.get("PLAYER_BLOCK", 0) + ctr.get("HERO_EID", 0)
        if player_cnt > best_eid_cnt:
            best_eid_cnt = player_cnt
            best_eid_off = off

    # Per-entity frequency (at best EID offset)
    per_entity: Counter = Counter()
    if best_eid_off is not None:
        for p in positions:
            v = try_u16_be(full_data, p + 3 + best_eid_off)
            if v is not None:
                per_entity[v] += 1

    # ── 4. Timestamp scan at payload offsets 0..16 ────────────────────────────
    ts_candidates = defaultdict(list)
    for p in positions[:200]:
        for off in range(0, 18, 2):
            v = try_f32_be(full_data, p + 3 + off)
            if v is not None and is_timestamp(v):
                ts_candidates[off].append(v)

    ts_summary = {}
    for off, vals in ts_candidates.items():
        if len(vals) > n * 0.15:  # present in >15% of samples
            ts_summary[off] = {
                "count": len(vals),
                "pct": round(len(vals) / min(n, 200) * 100, 1),
                "min": round(min(vals), 2),
                "max": round(max(vals), 2),
                "sample": [round(v, 2) for v in vals[:5]],
            }

    # ── 5. Inter-event spacing (byte distance) ────────────────────────────────
    spacings = [positions[i+1] - positions[i] for i in range(min(n-1, 999))]
    avg_spacing   = round(sum(spacings) / len(spacings), 1) if spacings else 0
    modal_spacing = Counter(spacings).most_common(1)[0][0] if spacings else 0

    # ── 6. Timing by frame ────────────────────────────────────────────────────
    frame_counts: Counter = Counter()
    for fi, fd in frames:
        frame_counts[fi] = fd.count(h_bytes)
    frame_list = sorted(frame_counts.items())
    # Check if monotonically growing (linear with game time)
    counts_by_frame = [c for _, c in frame_list]
    # Pearson-like: correlation between frame_idx and cumsum
    cumsum = []
    s = 0
    for c in counts_by_frame:
        s += c
        cumsum.append(s)
    n_fr = len(cumsum)
    if n_fr > 3:
        xs = list(range(n_fr))
        xm = sum(xs) / n_fr
        ym = sum(cumsum) / n_fr
        num = sum((x - xm) * (y - ym) for x, y in zip(xs, cumsum))
        den = (sum((x - xm)**2 for x in xs) * sum((y - ym)**2 for y in cumsum))**0.5
        linear_r = round(num / den, 3) if den > 0 else 0.0
    else:
        linear_r = 0.0

    per_frame_avg = round(total_count / max(len(frames), 1), 1)

    # ── 7. Cross-correlation with kill/death events ───────────────────────────
    PROX = 200  # bytes proximity window
    kill_positions  = find_all(full_data, KILL_HDR,  limit=2000)
    death_positions = find_all(full_data, DEATH_HDR, limit=2000)
    kill_set  = set(kill_positions)
    death_set = set(death_positions)

    near_kill  = 0
    near_death = 0
    for p in positions[:300]:
        for kp in kill_positions:
            if abs(p - kp) <= PROX:
                near_kill += 1
                break
        for dp in death_positions:
            if abs(p - dp) <= PROX:
                near_death += 1
                break

    pct_near_kill  = round(near_kill  / min(n, 300) * 100, 1)
    pct_near_death = round(near_death / min(n, 300) * 100, 1)

    # ── 8. Constant / padding byte detection ─────────────────────────────────
    CONST_THRESHOLD = 0.90
    constant_offsets = {
        off: info for off, info in byte_freq.items()
        if info["pct"] >= CONST_THRESHOLD * 100
    }

    # ── 9. Fixed-width structure hypothesis ───────────────────────────────────
    # Look for the modal spacing as a "record size" hint
    if spacings:
        spacing_ctr = Counter(spacings)
        top3_spacings = spacing_ctr.most_common(3)
    else:
        top3_spacings = []

    # ── 10. Hex dump - 10 representative samples ─────────────────────────────
    step = max(1, n // HEX_SAMPLES)
    hex_samples = []
    for i in range(0, min(n, HEX_SAMPLES * step), step):
        p = positions[i]
        raw = full_data[p: min(p + 3 + PAYLOAD_DUMP_BYTES, len(full_data))]
        # Annotate EID and float fields
        notes = []
        for off in range(0, 8):
            v = try_u16_be(raw, 3 + off)
            if v is not None:
                cat = classify_eid(v)
                if cat not in (f"unk({v})", "ZERO", "FFFF"):
                    notes.append(f"+{3+off}: EID={v}({cat})")
        for off in range(0, 20, 2):
            v = try_f32_be(raw, 3 + off)
            if v is not None and is_timestamp(v):
                notes.append(f"+{3+off}: ts={v:.2f}s")
        hex_samples.append({
            "pos": p,
            "hex": raw.hex(' '),
            "notes": notes,
        })

    # ── 11. Compare with ACTION_HDR [28 04 3F] if analysing H2 ───────────────
    action_compare = None
    if header == (0x24, 0x04, 0x3F):
        action_pos = find_all(full_data, ACTION_HDR, limit=20)
        action_dumps = []
        for p in action_pos[:5]:
            raw = full_data[p: min(p + 3 + PAYLOAD_DUMP_BYTES, len(full_data))]
            action_dumps.append(raw.hex(' '))
        h2_dumps = [s["hex"] for s in hex_samples[:5]]
        action_compare = {
            "[28 04 3F] ACTION dumps": action_dumps,
            "[24 04 3F] this header dumps": h2_dumps,
        }

    # ── 12. Summary hypothesis ────────────────────────────────────────────────
    hypothesis = _form_hypothesis(
        header, n, total_count, avg_spacing, per_frame_avg, linear_r,
        best_eid_off, best_eid_cnt, per_entity, ts_summary,
        pct_near_kill, pct_near_death, constant_offsets, top3_spacings
    )

    return {
        "header": h_hex,
        "total_count_in_replay": total_count,
        "samples_analysed": n,
        "avg_spacing_bytes": avg_spacing,
        "modal_spacing_bytes": modal_spacing,
        "top3_spacings": top3_spacings,
        "per_frame_avg": per_frame_avg,
        "frame_linear_r": linear_r,
        "best_eid_offset": best_eid_off,
        "best_eid_match_count": best_eid_cnt,
        "per_entity_counts": dict(per_entity.most_common(15)),
        "eid_at_each_offset": {k: dict(v) for k, v in eid_at_offset.items()},
        "timestamp_offsets": ts_summary,
        "near_kill_pct": pct_near_kill,
        "near_death_pct": pct_near_death,
        "constant_offsets": constant_offsets,
        "byte_freq_summary": {
            off: info for off, info in byte_freq.items() if off < 16
        },
        "hex_samples": hex_samples,
        "action_compare": action_compare,
        "hypothesis": hypothesis,
    }


def _form_hypothesis(header, n, total, avg_spacing, per_frame_avg,
                     linear_r, best_eid_off, best_eid_cnt, per_entity,
                     ts_summary, pct_near_kill, pct_near_death,
                     constant_offsets, top3_spacings) -> str:
    h_hex = f"[{header[0]:02X} 04 {header[2]:02X}]"

    parts = []

    # Frequency class
    if total > 300_000:
        parts.append("VERY HIGH FREQUENCY (>300K/match)")
    elif total > 100_000:
        parts.append("HIGH FREQUENCY (100-300K/match)")
    elif total > 50_000:
        parts.append("MEDIUM FREQUENCY (50-100K/match)")
    else:
        parts.append(f"LOWER FREQUENCY ({total}/match)")

    # Linear growth -> periodic/heartbeat-like
    if linear_r > 0.98:
        parts.append(f"monotone linear growth (r={linear_r}) -> PERIODIC/TICK event")

    # Entity binding
    if best_eid_cnt > n * 0.4:
        top_eid = per_entity.most_common(3)
        parts.append(f"entity-bound at payload+{best_eid_off} "
                     f"({best_eid_cnt}/{n} hits, top EIDs: {top_eid})")
        # Uniform vs hero-dependent
        if len(per_entity) >= 5:
            counts = list(per_entity.values())
            ratio = max(counts) / (min(counts) + 1)
            if ratio < 2.0:
                parts.append("UNIFORM per-entity distribution -> not hero-dependent")
            else:
                parts.append(f"HERO-DEPENDENT (ratio max/min={ratio:.1f})")

    # Timestamps
    if ts_summary:
        off_list = list(ts_summary.keys())
        parts.append(f"embedded timestamps at payload offsets {off_list}")

    # Proximity to kills/deaths
    if pct_near_kill > 30:
        parts.append(f"fires near kills ({pct_near_kill:.0f}% within 200B) -> possible combat event")
    if pct_near_death > 30:
        parts.append(f"fires near deaths ({pct_near_death:.0f}% within 200B)")

    # Structural hints from modal spacing
    if top3_spacings:
        modal, modal_cnt = top3_spacings[0]
        modal_pct = round(modal_cnt / (n - 1) * 100, 1) if n > 1 else 0
        if modal_pct > 30:
            parts.append(f"fixed-width records? modal spacing={modal}B ({modal_pct:.0f}% of gaps)")

    # Constant padding bytes
    pad_offsets = [off for off, info in constant_offsets.items()
                   if info["top_byte"] == "00"]
    if pad_offsets:
        parts.append(f"00-padding at offsets {pad_offsets[:6]}")

    # Header-specific reasoning
    if header == (0x10, 0x04, 0x2B):
        parts.append("HYPOTHESIS: per-entity periodic state update "
                     "(24B fixed-width records; covers all entity types incl. turrets/minions; "
                     "not player-exclusive)")
    elif header == (0x24, 0x04, 0x3F):
        parts.append("HYPOTHESIS: extended entity/action record "
                     "([28 04 3F]=48B vs [24 04 3F]=~40B; entity ID appears TWICE at +5 and +9; "
                     "may be entity-pair interaction or dual-target action)")
    elif header == (0x10, 0x04, 0x15):
        parts.append("HYPOTHESIS: entity attribute tick "
                     "(HP/mana/cooldown snapshot - fires per entity per frame)")
    elif header == (0x18, 0x04, 0x0D):
        parts.append("HYPOTHESIS: non-player entity state update "
                     "(0% playerEID - purely for minion/structure/NPC entities; "
                     "likely lifecycle or position update)")
    elif header == (0x05, 0x04, 0x00):
        parts.append("HYPOTHESIS: frame sync / timing marker "
                     "(first byte 0x05 is unusually small; may be a frame-boundary "
                     "or tick-rate synchronisation record rather than per-entity event)")

    return " | ".join(parts)


# ── Replay-level summary printer ──────────────────────────────────────────────

def print_analysis(result: dict, replay_name: str):
    print(f"\n{'='*80}")
    print(f"  REPLAY: {replay_name}")
    print(f"{'='*80}")

    for hdr_result in result:
        h = hdr_result["header"]
        print(f"\n{'─'*70}")
        print(f"  HEADER [{h}]  count={hdr_result['total_count_in_replay']:,}  "
              f"samples={hdr_result['samples_analysed']}")
        print(f"  avg_spacing={hdr_result['avg_spacing_bytes']}B  "
              f"per_frame={hdr_result['per_frame_avg']}  "
              f"linear_r={hdr_result['frame_linear_r']}")
        print(f"  near_kill={hdr_result['near_kill_pct']}%  "
              f"near_death={hdr_result['near_death_pct']}%")

        # Entity distribution
        if hdr_result["best_eid_offset"] is not None:
            print(f"  best_EID_offset=+{hdr_result['best_eid_offset']}  "
                  f"hits={hdr_result['best_eid_match_count']}")
        pe = hdr_result["per_entity_counts"]
        if pe:
            top5 = list(pe.items())[:5]
            print(f"  per-entity top5: {top5}")

        # Timestamp fields
        ts = hdr_result["timestamp_offsets"]
        if ts:
            for off, info in ts.items():
                print(f"  timestamp at +{off}: {info['pct']}% "
                      f"range [{info['min']}-{info['max']}]s  samples={info['sample']}")

        # Byte frequency for first 12 bytes
        bfreq = hdr_result["byte_freq_summary"]
        row = "  byte_freq[0..11]: "
        for off in range(12):
            info = bfreq.get(off)
            if info:
                row += f" +{off}:{info['top_byte']}({info['pct']:.0f}%)"
        print(row)

        # Constant offsets
        cst = hdr_result["constant_offsets"]
        if cst:
            cst_str = ", ".join(f"+{k}={v['top_byte']}({v['pct']:.0f}%)"
                                for k, v in list(cst.items())[:8])
            print(f"  constant bytes: {cst_str}")

        # Hex dump samples
        print(f"\n  --- HEX DUMP (10 samples, header + 40B payload) ---")
        for s in hdr_result["hex_samples"]:
            note_str = "  # " + " | ".join(s["notes"]) if s["notes"] else ""
            print(f"    @{s['pos']:08X}: {s['hex']}{note_str}")

        # ACTION_HDR comparison for H2
        if hdr_result.get("action_compare"):
            ac = hdr_result["action_compare"]
            print(f"\n  --- COMPARE [28 04 3F] vs [24 04 3F] ---")
            print("  [28 04 3F] ACTION samples:")
            for d in ac.get("[28 04 3F] ACTION dumps", [])[:3]:
                print(f"    {d}")
            print("  [24 04 3F] THIS samples:")
            for d in ac.get("[24 04 3F] this header dumps", [])[:3]:
                print(f"    {d}")

        # Hypothesis
        print(f"\n  HYPOTHESIS: {hdr_result['hypothesis']}")


# ── Top-5 per header across replays ───────────────────────────────────────────

def cross_replay_summary(all_results: List[dict]):
    """Aggregate per-header stats across multiple replays."""
    print(f"\n{'='*80}")
    print(f"  CROSS-REPLAY SUMMARY ({len(all_results)} replays)")
    print(f"{'='*80}")

    # Collect per-header data across replays
    header_agg = defaultdict(lambda: {
        "counts": [], "linear_rs": [], "per_frame_avgs": [],
        "near_kill_pcts": [], "near_death_pcts": [],
        "entity_counts_all": Counter(),
        "hypothesis_parts": [],
    })

    for replay_result in all_results:
        for hdr in replay_result["headers"]:
            key = hdr["header"]
            agg = header_agg[key]
            agg["counts"].append(hdr["total_count_in_replay"])
            agg["linear_rs"].append(hdr["frame_linear_r"])
            agg["per_frame_avgs"].append(hdr["per_frame_avg"])
            agg["near_kill_pcts"].append(hdr["near_kill_pct"])
            agg["near_death_pcts"].append(hdr["near_death_pct"])
            for eid, cnt in hdr["per_entity_counts"].items():
                agg["entity_counts_all"][eid] += cnt

    for h_hex, agg in header_agg.items():
        counts = agg["counts"]
        n = len(counts)
        print(f"\n  [{h_hex}]")
        print(f"    count: min={min(counts):,}  max={max(counts):,}  "
              f"avg={round(sum(counts)/n):,}  (across {n} replays)")
        lr = agg["linear_rs"]
        print(f"    linear_r: avg={round(sum(lr)/n, 3)}  "
              f"(all >{0.95}? {'YES' if all(r > 0.95 for r in lr) else 'NO'})")
        nk = agg["near_kill_pcts"]
        nd = agg["near_death_pcts"]
        print(f"    near_kill_avg={round(sum(nk)/n, 1)}%  "
              f"near_death_avg={round(sum(nd)/n, 1)}%")
        top_eids = agg["entity_counts_all"].most_common(5)
        if top_eids:
            print(f"    top entity IDs (all replays): {top_eids}")


# ── Main ───────────────────────────────────────────────────────────────────────

def run_analysis(replay_dir_str: str, max_replays: int = 3):
    replay_dir = Path(replay_dir_str)
    zero_files = sorted(replay_dir.rglob("*.0.vgr"))
    zero_files = [f for f in zero_files if not f.name.startswith("._")]

    if not zero_files:
        print(f"No .0.vgr files found in {replay_dir}")
        return

    replays_to_use = zero_files[:max_replays]
    print(f"[OBJECTIVE] Deep-analysis of 5 unknown headers across "
          f"{len(replays_to_use)} replays")
    print(f"Targets: {['{:02X} 04 {:02X}'.format(h[0], h[2]) for h in TARGET_HEADERS]}")
    print()

    all_results = []

    for zero_path in replays_to_use:
        rname = zero_path.stem.rsplit('.', 1)[0]
        print(f"[STAGE:begin:load_replay_{rname[:20]}]")
        print(f"  Loading {zero_path.parent.name}/{zero_path.name}")
        try:
            full_data, frames = load_replay(zero_path)
        except Exception as e:
            print(f"  ERROR: {e}")
            print(f"[STAGE:status:fail]")
            continue
        print(f"  {len(full_data):,} bytes across {len(frames)} frames")
        print(f"[STAGE:status:success]")
        print(f"[STAGE:end:load_replay_{rname[:20]}]")

        # ── Analyse each target header ────────────────────────────────────────
        print(f"[STAGE:begin:analyse_headers_{rname[:20]}]")
        header_results = []
        for hdr in TARGET_HEADERS:
            hr = analyse_header(bytes(hdr), hdr, full_data, frames)
            header_results.append(hr)
            print(f"  [{hr['header']}] count={hr['total_count_in_replay']:,}  "
                  f"samples={hr['samples_analysed']}  "
                  f"spacing={hr['avg_spacing_bytes']}B  "
                  f"linear_r={hr['frame_linear_r']}  "
                  f"near_kill={hr['near_kill_pct']}%")

        print(f"[STAGE:status:success]")
        print(f"[STAGE:end:analyse_headers_{rname[:20]}]")

        replay_result = {"replay": rname, "headers": header_results}
        all_results.append(replay_result)

        # Detailed print for this replay
        print_analysis(header_results, rname)

    # ── Cross-replay aggregate ────────────────────────────────────────────────
    if len(all_results) > 1:
        cross_replay_summary(all_results)

    # ── Final findings ────────────────────────────────────────────────────────
    print(f"\n{'='*80}")
    print("  FINDINGS SUMMARY")
    print(f"{'='*80}")

    if all_results:
        # Use first replay as canonical
        for hdr in all_results[0]["headers"]:
            h = hdr["header"]
            count = hdr["total_count_in_replay"]
            hyp = hdr["hypothesis"]
            print(f"\n[FINDING] [{h}] count={count:,}")
            # Break hypothesis into readable lines
            for part in hyp.split(" | "):
                print(f"  {part}")
            ts_offsets = list(hdr["timestamp_offsets"].keys())
            if ts_offsets:
                print(f"  [STAT:ts_offsets_{h.replace(' ','')}] "
                      f"timestamps present at payload offsets {ts_offsets}")
            pe = hdr["per_entity_counts"]
            if pe:
                top = list(pe.items())[:3]
                print(f"  [STAT:top_entities_{h.replace(' ','')}] {top}")
            near_k = hdr["near_kill_pct"]
            near_d = hdr["near_death_pct"]
            print(f"  [STAT:proximity_{h.replace(' ','')}] "
                  f"near_kill={near_k}% near_death={near_d}%")

    print(f"\n[LIMITATION] Analysis covers {len(all_results)} replays (target=3); "
          "conclusions may not generalise across all game modes.")
    print("[LIMITATION] 'near_kill/death' uses byte proximity (200B window), "
          "not exact temporal correlation; coincidental hits possible.")
    print("[LIMITATION] Entity IDs in [10 04 2B] / [10 04 15] may be non-player "
          "entities not in the player-block EID range (1500-1509).")


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Deep structural analysis of top-5 unknown VGR event headers"
    )
    parser.add_argument(
        "replay_dir", nargs="?",
        default=r"D:\Desktop\My Folder\Game\VG\vg replay",
        help="Directory containing replay subfolders"
    )
    parser.add_argument(
        "-n", "--num-replays", type=int, default=3,
        help="Number of replays to analyse (default: 3)"
    )
    args = parser.parse_args()
    run_analysis(args.replay_dir, args.num_replays)


if __name__ == "__main__":
    main()
