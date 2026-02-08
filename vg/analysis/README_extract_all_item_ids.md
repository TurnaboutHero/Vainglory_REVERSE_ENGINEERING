# Extract All Item IDs - Usage Guide

## Overview
Automatically extracts all item IDs from VG replay files using the `FF FF FF FF [XX 00]` pattern and compares them against the known ITEM_ID_MAP.

## Script Location
```
d:\Documents\GitHub\VG_REVERSE_ENGINEERING\vg\analysis\extract_all_item_ids.py
```

## Usage

### Basic Command
```bash
python vg/analysis/extract_all_item_ids.py "<replay_folder_path>"
```

### Example
```bash
python vg/analysis/extract_all_item_ids.py "D:\Desktop\My Folder\Game\VG\vg replay\replay-test\item buy test"
```

### Save Output to File
```bash
python vg/analysis/extract_all_item_ids.py "<replay_folder_path>" > output.json 2>&1
```

## Output Format

### JSON Structure
```json
{
  "replay_folder": "path/to/replay",
  "total_frames": 7,
  "analysis": {
    "total_unique_items_found": 18,
    "known_items_found": 10,
    "known_items_missing": 55,
    "new_items_discovered": 8
  },
  "known_items": [...],
  "new_items": [...],
  "missing_items": [...]
}
```

### Known Items (Found)
Items that exist in ITEM_ID_MAP and were found in the replay:
```json
{
  "id": 101,
  "name": "Weapon Blade",
  "category": "Weapon",
  "tier": 1,
  "found": true,
  "first_frame": 5,
  "frame_count": 2,
  "total_occurrences": 2
}
```

### New Items (Discovered)
Items NOT in ITEM_ID_MAP but found in the replay:
```json
{
  "id": 105,
  "first_frame": 5,
  "found_in_frames": [5, 6],
  "total_occurrences": 2
}
```

### Missing Items
Items in ITEM_ID_MAP but NOT found in this replay:
```json
{
  "id": 121,
  "name": "Sorrowblade",
  "category": "Weapon",
  "tier": 3,
  "note": "Not found with FF FF FF FF pattern in this replay"
}
```

## How It Works

1. **Scans all .vgr frame files** in the replay folder
2. **Searches for pattern**: `FF FF FF FF [XX 00]` where XX is interpreted as little-endian uint16
3. **Filters to item range**: Only IDs between 101-429 are considered
4. **Compares with known mappings**: Cross-references with `vg/core/vgr_mapping.py::ITEM_ID_MAP`
5. **Generates report**: Categorizes items as known/new/missing

## Key Findings from Test Replay

### Discovered Items (Total: 18)
- **Known items found**: 10 (Weapon Blade, Book of Eulogies, Swift Shooter, etc.)
- **New items discovered**: 8 (IDs: 105-110, 188, 255)

### Notable New Items
- **IDs 105-110**: Appear in frames 5-6 (likely additional tier 1 weapon items)
- **ID 188**: Appears in ALL frames with 217 total occurrences (possibly a system/status item)
- **ID 255**: Appears once in frame 6 (special item or marker)

## Technical Details

### Pattern Recognition
```python
MARKER = b'\xFF\xFF\xFF\xFF'  # 4-byte marker
ITEM_ID_RANGE = (101, 429)    # Valid item ID range
```

### Frame Detection
- Searches for .vgr files directly in folder
- Falls back to subdirectories if not found
- Processes all frames sequentially

### Performance
- Fast: Processes 7 frames in < 1 second
- Memory efficient: Streams frame data
- No external dependencies beyond Python stdlib + vg.core

## Next Steps

To add newly discovered items to the mapping:
1. Review `new_items` section in output
2. Identify item names through game testing or asset analysis
3. Update `vg/core/vgr_mapping.py::ITEM_ID_MAP` with new entries

## Example Output
See: `vg/output/item_extraction_report.json`
