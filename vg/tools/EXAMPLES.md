# VG Tools - Usage Examples

Quick start examples for the network capture and batch parsing tools.

---

## mitm_capture.py Examples

### Basic Traffic Capture

```bash
# Start mitmproxy with the capture addon
mitmdump -s vg/tools/mitm_capture.py

# Output will be saved to ./captures/ directory
# Each VG-related request/response is logged as JSON
```

### Custom Output Directory

```bash
# Specify custom output directory
mitmdump -s vg/tools/mitm_capture.py --set output_dir=D:/VG_Traffic/session1

# Web UI for easier inspection
mitmweb -s vg/tools/mitm_capture.py --set output_dir=D:/VG_Traffic/session1
# Then open http://localhost:8081 in browser
```

### Android Device/Emulator Setup

```bash
# 1. Start mitmproxy
mitmdump -s vg/tools/mitm_capture.py

# 2. Configure Android device/emulator proxy
# Settings -> Wi-Fi -> Long press network -> Modify -> Proxy -> Manual
# Host: <your_pc_ip>  (e.g., 192.168.1.100)
# Port: 8080

# 3. Install CA certificate
# Open browser on device: http://mitm.it
# Download and install Android certificate

# 4. Launch VG:CE
# Traffic will be captured automatically
```

### Extract Frida SSL Bypass Script

```bash
# Save the built-in Frida script
cd vg/tools
grep -A 20 "FRIDA_SSL_BYPASS_JS" mitm_capture.py | tail -n +2 > ssl_bypass.js

# Or extract manually from the script
python -c "from mitm_capture import FRIDA_SSL_BYPASS_JS; print(FRIDA_SSL_BYPASS_JS)" > ssl_bypass.js

# Use with Frida
frida -U -f com.superevilmegacorp.game -l ssl_bypass.js --no-pause
```

### Sample Output

```json
{
  "timestamp": "2026-02-15T10:45:23.456789",
  "method": "POST",
  "url": "https://api.vainglory.com/match/result",
  "host": "api.vainglory.com",
  "status_code": 200,
  "request_headers": {
    "content-type": "application/json",
    "authorization": "Bearer ..."
  },
  "response_headers": {
    "content-type": "application/json"
  },
  "request_body": {
    "match_id": "abc123",
    "players": [...]
  },
  "response_body": {
    "success": true,
    "elo_change": {
      "player1": +15,
      "player2": -12
    }
  }
}
```

---

## replay_batch_parser.py Examples

### Basic Batch Parsing

```bash
# Parse all replays in directory
python vg/tools/replay_batch_parser.py D:/VG_Replays/

# Output is saved to vg/output/batch_parse_results.json by default
```

### Custom Output File

```bash
# Save to specific location
python vg/tools/replay_batch_parser.py D:/VG_Replays/ --output my_analysis.json

# Or use short flag
python vg/tools/replay_batch_parser.py D:/VG_Replays/ -o stats.json
```

### Real Example with Existing Data

```bash
# Parse the data directory in this project
python vg/tools/replay_batch_parser.py vg/data/

# Sample output console:
# Found 5 replay files
#   Parsed 5/5...
#
# ==================================================
# Total replays: 5
# Successful: 5
# Unique players: 30
# Hero picks: 15 unique heroes
# Top heroes: {'Ringo': 3, 'Catherine': 2, 'Lyra': 2, ...}
# Saved to: vg/output/batch_parse_results.json
```

### Sample Output Structure

```json
{
  "total_replays": 5,
  "successful": 5,
  "failed": 0,
  "unique_players": 30,
  "game_modes": {
    "GameMode_5v5_Ranked": 3,
    "GameMode_HF_Casual": 2
  },
  "hero_picks": {
    "Ringo": 3,
    "Catherine": 2,
    "Lyra": 2,
    "Ardan": 1,
    "Baron": 1
  },
  "replays": [
    {
      "file": "D:/VG_Replays/2024-01-15/replay1.0.vgr",
      "game_mode": "GameMode_5v5_Ranked",
      "map_mode": "unknown",
      "players": [
        {
          "name": "PlayerName",
          "hero_name": "Ringo",
          "hero_id": 10,
          "team": "left",
          "entity_id": 1234
        }
      ],
      "player_count": 10,
      "success": true
    }
  ]
}
```

---

## Combined Workflow: VGR + MITM Integration

This is the ultimate workflow for extracting complete match data.

### Step 1: Prepare Capture Environment

```bash
# Terminal 1: Start MITM capture
mitmdump -s vg/tools/mitm_capture.py --set output_dir=./session_2026_02_15

# Terminal 2: (Optional) Start Frida for SSL bypass
frida -U -f com.superevilmegacorp.game -l ssl_bypass.js --no-pause
```

### Step 2: Play Matches

- Launch VG:CE on Android device/emulator
- Play 3-5 matches
- Network traffic is captured automatically
- VGR replays are saved to device storage

### Step 3: Extract VGR Replays

```bash
# Pull replays from Android device
adb pull /sdcard/Android/data/com.superevilmegacorp.game/files/ReplayCache/ ./replays/

# Or from emulator (LDPlayer example)
# Check: C:\Users\<user>\Pictures\LDPlayer\com.superevilmegacorp.game\ReplayCache\
```

### Step 4: Parse Both Sources

```bash
# Parse network captures (already saved in session_2026_02_15/)

# Parse VGR replays
python vg/tools/replay_batch_parser.py ./replays/ -o vgr_data.json
```

### Step 5: Match and Merge Data

```python
# match_data.py - Manual matching script
import json
from datetime import datetime

# Load both sources
with open('session_2026_02_15/vg_capture_123456.json') as f:
    mitm_data = json.load(f)

with open('vgr_data.json') as f:
    vgr_data = json.load(f)

# Match by player names and timestamp proximity
for replay in vgr_data['replays']:
    player_names = [p['name'] for p in replay['players']]

    # Find MITM capture with matching player names
    for capture in mitm_data:
        if 'players' in capture.get('response_body', {}):
            mitm_players = [p['name'] for p in capture['response_body']['players']]

            # Check overlap
            overlap = set(player_names) & set(mitm_players)
            if len(overlap) >= 6:  # At least 6 players match
                print(f"Match found!")
                print(f"  VGR: {replay['file']}")
                print(f"  MITM: {capture['url']}")
                print(f"  Players: {overlap}")

                # Merge data
                merged = {
                    'vgr_file': replay['file'],
                    'mitm_url': capture['url'],
                    'players': []
                }

                for p in replay['players']:
                    # Find corresponding MITM data
                    mitm_player = next(
                        (mp for mp in capture['response_body']['players'] if mp['name'] == p['name']),
                        None
                    )

                    merged['players'].append({
                        'name': p['name'],
                        'hero': p['hero_name'],  # From VGR
                        'team': p['team'],       # From VGR
                        'kda': mitm_player.get('kda') if mitm_player else None,  # From MITM
                        'items': mitm_player.get('items') if mitm_player else None,  # From MITM
                    })

                # Save merged result
                with open(f"merged_{replay['file'].split('/')[-1]}.json", 'w') as f:
                    json.dump(merged, f, indent=2)
```

---

## Troubleshooting

### mitm_capture.py

**No captures appearing:**
```bash
# Check if VG:CE is using the proxy
# On Android, test proxy with browser first
# Visit http://mitm.it - if it loads, proxy is working

# Check mitmproxy is listening
netstat -an | grep 8080  # Linux/Mac
netstat -an | findstr 8080  # Windows
```

**SSL errors:**
```bash
# Install CA certificate as system certificate (requires root)
# Or use Frida SSL bypass (see examples above)
```

### replay_batch_parser.py

**Import errors:**
```bash
# Make sure you're in project root
cd D:/Documents/GitHub/VG_REVERSE_ENGINEERING/

# Run as module
python -m vg.tools.replay_batch_parser vg/data/ -o results.json
```

**No replays found:**
```bash
# Check directory structure
# Replays should be *.0.vgr files
# Script searches recursively, so subdirectories are OK
ls -R vg/data/ | grep "\.0\.vgr"
```

---

## Tips and Best Practices

### MITM Capture

1. **Start capture before launching game** - captures login and auth
2. **Use web UI (mitmweb) for live inspection** - easier to see what's happening
3. **Filter by domain** - VG endpoints likely include "vainglory", "semc", "superevilmegacorp"
4. **Save Frida script separately** - reusable for future sessions

### Batch Parsing

1. **Organize replays by date** - easier to correlate with MITM captures
2. **Parse incrementally** - parse new sessions separately, then merge
3. **Keep raw data** - original VGR files are valuable, don't delete after parsing
4. **Export to CSV for analysis** - easier to work with in Excel/Google Sheets

### Data Matching

1. **Use player names as primary key** - most reliable matching field
2. **Check timestamp proximity** - MITM and VGR should be within minutes
3. **Validate game mode** - both sources should report same mode
4. **Count players** - sanity check for 3v3 vs 5v5

---

## Next Steps

After using these tools, you'll have:
- ✓ Network traffic captures (MITM JSON)
- ✓ Parsed replay data (VGR JSON)
- ✓ Batch statistics (hero picks, player stats)

**Next phases:**
1. Automate VGR + MITM matching
2. Build database schema for storage
3. Create web API for queries
4. Implement real-time capture daemon

See `vg/docs/MITM_GUIDE.md` Phase 3 for details.
