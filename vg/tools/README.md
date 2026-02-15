# VG Reverse Engineering Tools

Practical tools for network capture and batch replay analysis.

## Tools Overview

### 1. mitm_capture.py - MITM Network Capture

mitmproxy addon for capturing VG:CE network traffic.

**Features:**
- Filters VG-related endpoints automatically
- Captures HTTP/HTTPS requests and responses
- Saves structured JSON logs with timestamps
- Includes Frida SSL pinning bypass reference

**Usage:**

```bash
# Basic usage
mitmdump -s vg/tools/mitm_capture.py

# Custom output directory
mitmdump -s vg/tools/mitm_capture.py --set output_dir=./my_captures

# Web UI mode (easier to inspect traffic)
mitmweb -s vg/tools/mitm_capture.py --set output_dir=./captures
```

**Output Format:**

```json
{
  "timestamp": "2026-02-15T10:30:45.123456",
  "method": "POST",
  "url": "https://api.vainglory.com/match/accept",
  "host": "api.vainglory.com",
  "status_code": 200,
  "request_body": {...},
  "response_body": {...}
}
```

**Frida SSL Bypass:**

The script includes a Frida JavaScript snippet for bypassing SSL pinning. Extract it with:

```bash
python vg/tools/mitm_capture.py --save-frida-script --output ssl_bypass.js

# Use with Frida
frida -U -f com.superevilmegacorp.game -l ssl_bypass.js --no-pause
```

---

### 2. replay_batch_parser.py - Batch Replay Analysis

Batch processes all VGR replay files and generates unified statistics.

**Features:**
- Parses all .vgr replays in a directory tree
- Aggregates players, heroes, items across all matches
- Calculates pick rates, win rates, KDA statistics
- Outputs JSON or CSV format

**Usage:**

```bash
# Basic usage (JSON to stdout)
python vg/tools/replay_batch_parser.py D:/VG_Replays/

# Save to file
python vg/tools/replay_batch_parser.py D:/VG_Replays/ -o summary.json

# CSV export (hero stats)
python vg/tools/replay_batch_parser.py D:/VG_Replays/ --format csv-heroes -o heroes.csv

# CSV export (player stats)
python vg/tools/replay_batch_parser.py D:/VG_Replays/ --format csv-players -o players.csv

# Enable hero detection
python vg/tools/replay_batch_parser.py D:/VG_Replays/ --detect-heroes -o summary.json

# Summary only (without full replay data)
python vg/tools/replay_batch_parser.py D:/VG_Replays/ --summary-only -o summary.json
```

**Output Structure:**

```json
{
  "metadata": {
    "total_replays": 50,
    "unique_players": 120,
    "unique_heroes": 35,
    "unique_items": 42
  },
  "heroes": {
    "summary": [
      {
        "hero": "Ringo",
        "picks": 25,
        "pick_rate": "50.0%",
        "wins": 15,
        "losses": 10,
        "win_rate": "60.0%",
        "avg_kda": "3.45",
        "avg_kills": "8.2",
        "avg_deaths": "4.1",
        "avg_assists": "6.0"
      }
    ]
  },
  "players": {
    "summary": [
      {
        "player": "PlayerName",
        "games": 12,
        "wins": 8,
        "losses": 4,
        "win_rate": "66.7%",
        "avg_kda": "3.12",
        "most_played_hero": "Ringo"
      }
    ]
  },
  "replays": [...]
}
```

---

## Prerequisites

### For mitm_capture.py

```bash
pip install mitmproxy
```

**Optional (for SSL pinning bypass):**
```bash
# Frida tools (PC)
pip install frida-tools

# Frida server (Android device)
# Download from: https://github.com/frida/frida/releases
# See MITM_GUIDE.md for detailed setup
```

### For replay_batch_parser.py

The tool uses the existing `VGRParser` from `vg/core/vgr_parser.py`, so no additional dependencies are needed beyond what's already in the project.

---

## Integration with MITM Guide

These tools implement the workflows described in `vg/docs/MITM_GUIDE.md`:

- **mitm_capture.py**: Implements Phase 1 (basic traffic capture) and Phase 2 (SSL bypass reference)
- **replay_batch_parser.py**: Supports VGR data extraction for VGR + MITM integration (Phase 3)

---

## Common Workflows

### 1. Capture Game Traffic

```bash
# Terminal 1: Start mitmproxy
mitmdump -s vg/tools/mitm_capture.py --set output_dir=./game_captures

# Terminal 2: If needed, bypass SSL pinning with Frida
python vg/tools/mitm_capture.py --save-frida-script
frida -U -f com.superevilmegacorp.game -l ssl_bypass.js --no-pause

# Play the game - traffic will be captured automatically
```

### 2. Batch Analyze Replays

```bash
# Parse all replays and generate stats
python vg/tools/replay_batch_parser.py D:/VG_Replays/ -o batch_summary.json

# Export hero statistics to CSV for spreadsheet analysis
python vg/tools/replay_batch_parser.py D:/VG_Replays/ --format csv-heroes -o hero_stats.csv

# Export player statistics
python vg/tools/replay_batch_parser.py D:/VG_Replays/ --format csv-players -o player_stats.csv
```

### 3. Combined VGR + MITM Analysis

```bash
# 1. Capture network traffic during gameplay
mitmdump -s vg/tools/mitm_capture.py --set output_dir=./session1

# 2. After match, parse the replay
python vg/core/vgr_parser.py path/to/replay/ -o replay1.json

# 3. Match capture data with replay data by:
#    - Player names
#    - Timestamp proximity
#    - Game mode
# (Manual matching for now; automated integration coming in Phase 3)
```

---

## Troubleshooting

### mitm_capture.py

**Problem: No traffic captured**
- Ensure Android device/emulator proxy is configured correctly
- Check CA certificate is installed
- Verify VG:CE is using HTTP/HTTPS (not UDP)

**Problem: SSL errors**
- SSL pinning is active - use Frida bypass
- Ensure CA certificate is in system trust store (requires root)

**Problem: Empty response bodies**
- Check if content is binary/encrypted
- Use Wireshark for TCP/UDP analysis

### replay_batch_parser.py

**Problem: Import error for VGRParser**
- Run from project root: `python -m vg.tools.replay_batch_parser`
- Or add project root to PYTHONPATH

**Problem: No replays found**
- Check directory path contains `.vgr` files
- Replays should be in subdirectories by date

---

## Related Documentation

- [MITM Guide](../docs/MITM_GUIDE.md) - Detailed MITM setup and network analysis
- [VGR Parser](../core/vgr_parser.py) - Core replay parsing module
- [VGR Mapping](../core/vgr_mapping.py) - Hero and item ID mappings

---

## Contributing

These tools are focused and practical. Enhancements welcome:

- Additional traffic filters for mitm_capture.py
- More export formats for replay_batch_parser.py
- Automated VGR + MITM data matching
- Real-time traffic analysis
