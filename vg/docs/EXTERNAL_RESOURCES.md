# Vainglory Replay Parsing - External Resources Research

**Research Date:** 2026-02-15
**Focus:** GitHub repositories, documentation, and tools for Vainglory VGR replay parsing and reverse engineering

---

## Executive Summary

This document catalogs external resources for reverse engineering the Vainglory VGR binary replay format. While no complete open-source VGR binary parser was found, significant resources exist for the Vainglory API telemetry format, hero/item mappings, and community revival projects.

**Key Finding:** The Vainglory API provided JSON telemetry data (not binary VGR files), which contains similar event information but in a different format.

---

## 1. Official Repositories

### 1.1 SuperEvilMegacorp/vainglory-assets
- **URL:** https://github.com/SuperEvilMegacorp/vainglory-assets
- **Description:** Official community-provided art, schemas, and assets for the Vainglory API
- **Status:** Archived (API no longer exists)
- **Key Contents:**
  - JSON schemas for API objects
  - Dictionaries mapping API keys to human-readable values (heroes, items)
  - Community art assets
  - Documentation and guides
- **Relevance:** HIGH - Contains hero/item ID mappings and telemetry schemas
- **Note:** API returned encoded values like `*1000_Item_HalcyonPotion*` with dictionaries to decode them

### 1.2 Vainglory API Documentation (GameLocker)
- **URL:** https://gamelocker.gitbooks.io/vainglory/content/en/telemetry.html
- **Alternative:** https://vainglory-gamelocker-documentation.readthedocs.io/en/master/introduction.html
- **Description:** Official Vainglory API documentation
- **Status:** Historical reference (API deprecated)
- **Key Contents:**
  - Complete telemetry event type reference
  - Event structure and field definitions
  - Position coordinate system documentation
  - Team representation (1=Left, 2=Right)
- **Relevance:** CRITICAL - Event schemas may match binary VGR format

---

## 2. Community Revival Projects

### 2.1 VaingloryReborn/VGReborn
- **URL:** https://github.com/VaingloryReborn/VGReborn
- **Description:** Open-source project to revive Vainglory Community Edition
- **Last Updated:** Active (2024+)
- **Technology:** MITM (Man-in-the-Middle) proxy, VPN accelerator
- **Features:**
  - Player state tracking (online, matching, in-game)
  - Match record capture
  - Rank tier calculation
  - Real-time statistics
  - Room management system
- **Relevance:** VERY HIGH - Uses MITM to intercept game traffic; may have network protocol insights
- **Reddit Discussion:** https://www.reddit.com/r/vainglorygame/comments/1qlp212/ive_retrofitted_vainglory_with_ranked_match/
- **Key Files to Investigate:** Server code, protocol handlers, packet parsers

### 2.2 Vainglory Community Edition Organization
- **URL:** https://github.com/vaingloryce
- **Description:** Official Vainglory Community Edition GitHub organization
- **Status:** Active community effort
- **Relevance:** MEDIUM - May contain server implementation details

---

## 3. Data & Statistics Tools

### 3.1 stevekm/vainstats
- **URL:** https://github.com/stevekm/vainstats
- **Language:** Python
- **Description:** VainGlory player stats Dash app & CLI tool
- **Features:**
  - Match data retrieval via API
  - Player statistics tracking
  - KDA extraction
- **API Endpoint:** `https://api.dc01.gamelockerapp.com/shards/`
- **Regions:** na, eu, sa, ea, sg
- **Relevance:** MEDIUM - Shows how to extract KDA from API (not binary replays)
- **Key Insight:** API provided last 3 hours of matches by default

### 3.2 oberocks/vainglory-base-stats
- **URL:** https://github.com/oberocks/vainglory-base-stats
- **Format:** JSON
- **Description:** Master file of hero and item stats, hard-coded from game
- **Contents:**
  - Complete hero database (`heroes` key)
  - Complete item database (`items` key)
  - Base statistics and attributes
- **Relevance:** HIGH - Essential for mapping entity IDs to hero/item names
- **File:** vainglory.json

### 3.3 zeroclutch/vainglory-counter-data
- **URL:** https://github.com/zeroclutch/vainglory-counter-data
- **Description:** Hero counter analysis tool
- **Data Range:** Patch 3.0 onwards
- **Relevance:** LOW - Match analysis, not parsing

---

## 4. API Client Wrappers (Deprecated)

All API clients are deprecated as the official API no longer exists, but source code may reveal data structures.

### 4.1 seripap/vainglory (JavaScript)
- **URL:** https://github.com/seripap/vainglory
- **Language:** JavaScript
- **Status:** DEPRECATED
- **Features:**
  - Automatic field decoding (actor, items)
  - KDA extraction from participant stats
  - Telemetry data retrieval
- **Relevance:** MEDIUM - Shows field mapping logic

### 4.2 ClarkThyLord/gamelocker-vainglory-py (Python)
- **URL:** https://github.com/ClarkThyLord/gamelocker-vainglory-py
- **Language:** Python
- **Status:** DEPRECATED
- **Usage:** `gamelocker.Vainglory(api_key)`
- **Relevance:** MEDIUM - Python implementation of API client

### 4.3 cyberarm/gamelocker_api (Ruby)
- **URL:** https://github.com/cyberarm/gamelocker_api
- **Language:** Ruby
- **Status:** DEPRECATED
- **Relevance:** LOW - Alternative implementation

---

## 5. Telemetry Event Documentation

### 5.1 Event Types Documented

Based on search results, the following telemetry events are confirmed:

#### Core Combat Events
- **DealDamage**
  - Fields: `Team`, `Actor`, `Target`, `Source`, `Damage`, `Delt`, `IsHero`, `TargetIsHero`
  - Example: `Team: "Left", Actor: "*Skaarf*", Target: "*Vox*", Damage: 105, Delt: 80`

- **KillActor**
  - Fields: `Team`, `Actor`, `Killed`, `KilledTeam`, `Gold`, `IsHero`, `TargetIsHero`, `Position`
  - Example: `Team: "Left", Actor: "*Koshka*", Killed: "*JungleMinion_TreeEnt*", Gold: "80", Position: [-21.95, 0, 24]`

#### Progression Events
- **EarnXP**
  - Fields: `Team`, `Actor`, `Source`, `Amount`, `Shared With`
  - Note: Does not track XP trickle (per-second gains)

#### Economy Events
- **BuyItem**
  - Fields: `Team`, `Actor`, `Item`, `Cost`, (possibly `Position`)
  - GitHub Issue: https://github.com/SuperEvilMegacorp/vainglory-assets/issues/30

#### Vision Events
- **Revealed/Hidden Status**
  - Tracks hero visibility state
  - GitHub Issue: https://github.com/SuperEvilMegacorp/vainglory-assets/issues/46

### 5.2 Coordinate System
- **Format:** 3-value vector `[x, z, y]`
- **Mapping:**
  - Index 0: x coordinate
  - Index 1: z coordinate
  - Index 2: y coordinate
- **Use Cases:** Heatmaps, timeline visualization, position tracking

### 5.3 Team Encoding
- **Pre-match events:** 1 or 2
- **Match events:** "Left" or "Right"
- **Mapping:** 1 = Left side, 2 = Right side

---

## 6. E.V.I.L. Engine Technical Details

### 6.1 Engine Overview
- **Developer:** Super Evil Megacorp
- **Type:** Proprietary cross-platform MOBA engine
- **Platforms:** Windows, macOS, iOS, Android
- **Performance:** Up to 120 FPS

### 6.2 Architecture
- **Server Authority:** Full gameplay runs server-side (not client-side)
- **Graphics:** Metal SDK integration (Apple platforms)
- **Network:** Custom multiplayer protocol for touch devices

### 6.3 Performance Metrics
- **3v3 Mode:** 1.2M polygons, 100 animated actors, 60 FPS
- **5v5 Mode:** 3M+ polygons, 200+ animated actors

### 6.4 Relevance to Reverse Engineering
- Server-authoritative design suggests replays may be server-generated
- Custom engine means proprietary binary formats
- No publicly documented replay format

**Reference:** https://www.gamedeveloper.com/production/why-super-evil-megacorp-built-a-proprietary-mobile-moba-engine

---

## 7. Related Game Replay Parsers (Reference)

### 7.1 Dota 2 Parsers
- **dotabuff/manta** - Dota 2 Source 2 replay parser (Go)
  - URL: https://github.com/dotabuff/manta
  - Fully functional, targets Source 2 engine

- **dotabuff/yasha** - Dota 2 Source 1 replay parser (Go)
  - URL: https://github.com/dotabuff/yasha
  - Parses replays since ~2012

- **mbax/yasp** - Open source Dota 2 replay parsing & statistics
  - URL: https://github.com/mbax/yasp
  - Blog: https://blog.opendota.com/2016/05/13/learnings/

### 7.2 Unity Game Reverse Engineering Tools
- **AssetRipper/AssetRipper**
  - URL: https://github.com/AssetRipper/AssetRipper
  - Extracts Unity assets and asset bundles
  - **Note:** Vainglory uses E.V.I.L. engine, not Unity

---

## 8. Community Resources

### 8.1 Discord Servers
- **Official Vainglory Discord:** https://discord.com/invite/vainglory
  - Managed by SEMC
- **Reverse Engineering Discord:** https://discord.com/invite/reverse-engineering-391398885819547652
  - 23,670+ members, focus on modding and exploitation

### 8.2 Forums
- **VG Forums:** https://vgforums.net/
  - Community-run, replaced official SEMC forum
  - CE Server discussions

- **VaingloryFire:** https://www.vaingloryfire.com/
  - Strategy guides and meta discussions
  - Historical technical discussions

- **Reddit:** r/vainglorygame
  - VGReborn development discussions
  - Community updates

### 8.3 Information Sites
- **Bubbleland:** https://bubbleland.org/
  - VGR replay guide
  - Download links
  - Community directory

- **Vainglory Tools:** https://shoutcasting.mattmct.com/
  - Item reference (JSON database)
  - Hero stats charts
  - Tools for analysts/coaches

---

## 9. VGR File Format Information

### 9.1 What We Know
- **Extension:** `.vgr`
- **Associated Software:** VaingloryReplay by PopcornOne (Windows)
- **Purpose:** Save and view Vainglory match replays
- **Format:** Binary (not self-describing)

### 9.2 What We Don't Know
- Binary structure/schema
- Header format
- Event encoding
- Compression method
- Entity ID mappings within binary

### 9.3 Potential Approaches
1. **Network Capture:** Use VGReborn's MITM approach to capture replay transmission
2. **Binary Analysis:** Reverse engineer VaingloryReplay software
3. **Pattern Matching:** Compare API telemetry JSON with binary replay data
4. **Community Collaboration:** Engage VGReborn developers

---

## 10. Key Gaps & Next Steps

### 10.1 Critical Gaps
- No public VGR binary format specification
- No open-source VGR parser found
- Limited documentation on binary replay structure
- Unclear if VGR files use protobuf, custom binary, or other serialization

### 10.2 Recommended Actions

#### Immediate
1. **Clone vainglory-assets repo:** Extract all hero/item ID mappings
   ```bash
   git clone https://github.com/SuperEvilMegacorp/vainglory-assets.git
   ```

2. **Study telemetry documentation:** Map event types to current parser needs
   - URL: https://gamelocker.gitbooks.io/vainglory/content/en/telemetry.html

3. **Analyze VGReborn:** Contact project or study MITM implementation
   - URL: https://github.com/VaingloryReborn/VGReborn

#### Short-term
4. **Binary pattern analysis:** Compare VGR files against known formats
   - Test for protobuf magic bytes
   - Check for JSON compression (gzip, zlib)
   - Look for event type signatures from API docs

5. **Community outreach:**
   - Post on VG Forums seeking binary format knowledge
   - Join Vainglory Discord, ask in developer channels
   - Contact VGReborn team directly

#### Long-term
6. **Network capture:** Set up MITM proxy during CE matches
7. **Reverse engineer VaingloryReplay.exe:** Use IDA/Ghidra on Windows replay viewer
8. **Collaborate:** Share findings with VGReborn team for mutual benefit

---

## 11. Reference Links Summary

### Essential Resources
- [Vainglory Telemetry Docs](https://gamelocker.gitbooks.io/vainglory/content/en/telemetry.html) - Event type reference
- [vainglory-assets](https://github.com/SuperEvilMegacorp/vainglory-assets) - Hero/item mappings
- [VGReborn](https://github.com/VaingloryReborn/VGReborn) - Community revival with MITM
- [vainglory-base-stats](https://github.com/oberocks/vainglory-base-stats) - JSON game data

### Development Tools
- [vainstats](https://github.com/stevekm/vainstats) - Python API client example
- [gamelocker-vainglory-py](https://github.com/ClarkThyLord/gamelocker-vainglory-py) - Python wrapper

### Community
- [Bubbleland](https://bubbleland.org/) - CE resources and guides
- [VG Forums](https://vgforums.net/) - Community forum
- [Vainglory Discord](https://discord.com/invite/vainglory) - Official Discord

### Technical Background
- [E.V.I.L. Engine Article](https://www.gamedeveloper.com/production/why-super-evil-megacorp-built-a-proprietary-mobile-moba-engine) - Engine architecture

---

## 12. Search Query Record

Searches performed 2026-02-15:

1. `GitHub vainglory replay parser vgr`
2. `GitHub vainglory api replay data structures`
3. `GitHub SEMC Super Evil Megacorp vainglory`
4. `GitHub vainglory community edition VG:CE`
5. `GitHub EVIL engine replay parser MOBA`
6. `vgr file format vainglory binary structure`
7. `vainglory telemetry data structure event types`
8. `GitHub vainglory-assets schemas telemetry`
9. `vainglory replay binary parser open source`
10. `vainglory game data entity ID hero mapping`
11. `vainglory E.V.I.L engine technical details`
12. `gamelocker vainglory API documentation`
13. `vainglory item ID list complete database JSON`
14. `site:github.com vainglory hero actor mapping`
15. `vainglory match telemetry complete event list`
16. `vainglory LearnedSpell EarnXP telemetry event`
17. `vainglory community edition server protocol`
18. `GitHub vainglory python parser telemetry`
19. `vainglory *.vgr file specification`
20. `vainglory reverse engineering discord community`

---

## Conclusion

While no complete open-source VGR binary parser exists, substantial resources are available for understanding Vainglory's data structures through the deprecated API. The VGReborn project represents the most promising lead for understanding modern replay formats via MITM network capture. The official telemetry documentation provides a strong foundation for mapping event types, even if the serialization format differs between API JSON and binary VGR files.

**Next Critical Step:** Obtain and analyze actual VGR binary files to identify serialization format (protobuf, MessagePack, custom binary, etc.) and compare structure against known telemetry event schemas.
