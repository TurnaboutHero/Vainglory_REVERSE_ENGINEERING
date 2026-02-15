# Vainglory External Research Findings
## Comprehensive Documentation & API Analysis

**Research Date:** 2026-02-15
**Purpose:** Find external resources to aid in Vainglory replay (.vgr) binary format reverse engineering

---

## Executive Summary

The Vainglory API (GameLocker) provided detailed telemetry data in JSON format that captured all match events including kills, deaths, assists, hero selections, and combat actions. While the API is now deprecated, extensive documentation and community resources remain available that describe the exact structure of match events. This telemetry data provides a reference schema that can guide identification of corresponding binary patterns in replay files.

**Key Finding:** Telemetry events show the logical structure of match data. By mapping telemetry event schemas to binary patterns in .vgr files, we can reverse engineer the replay format.

---

## 1. Official Vainglory API (GameLocker)

### API Overview
- **Service Name:** GameLocker
- **Endpoint:** `https://api.dc01.gamelockerapp.com/shards/`
- **Status:** DEPRECATED - API no longer operational
- **Provider:** MadGlory (partnership with Super Evil Megacorp)

### Documentation Sources

#### Primary Documentation
- **[Telemetry Documentation](https://gamelocker.gitbooks.io/vainglory/content/en/telemetry.html)** - Complete list of telemetry event types with JSON schemas
- **[GitHub: vainglory-assets](https://github.com/SuperEvilMegacorp/vainglory-assets)** - Community schemas, dictionaries, and art assets
- **[GitHub: vainglory-docs](https://github.com/SuperEvilMegacorp/vainglory-docs)** - Official documentation and guides
- **[Vainglory Cheatsheet](https://devhints.io/vainglory)** - Quick reference guide (devhints.io)
- **[GitHub: Cheatsheet Source](https://github.com/rstacruz/cheatsheets/blob/master/vainglory.md)** - Markdown source for API reference

---

## 2. Telemetry Event Schema Reference

### Event Structure
Telemetry events follow this general structure:
```json
{
  "time": "2017-03-17T00:39:09+0000",
  "type": "EventType",
  "payload": {
    // Event-specific data
  }
}
```

### Critical Event Types for Replay Analysis

#### KillActor Event
**Triggers:** When any actor kills another (hero, minion, jungle monster, turret)

```json
{
  "time": "2017-03-17T00:39:09+0000",
  "type": "KillActor",
  "payload": {
    "Team": "Left",
    "Actor": "*Koshka*",
    "Killed": "*JungleMinion_TreeEnt*",
    "KilledTeam": "Neutral",
    "Gold": "80",
    "IsHero": 1,
    "TargetIsHero": 0,
    "Position": [-21.95, 0, 24]
  }
}
```

**Relevance to Binary Analysis:**
- Hero names use `*HeroName*` format
- Position data: `[x, z, y]` coordinates
- Boolean flags: `IsHero`, `TargetIsHero`
- Gold values stored as strings

#### DealDamage Event
**Triggers:** When damage is dealt between actors

```json
{
  "time": "2017-03-17T00:38:32+0000",
  "type": "DealDamage",
  "payload": {
    "Team": "Left",
    "Actor": "*Ringo*",
    "Target": "*Vox*",
    "Source": "Unknown",
    "Damage": 100,
    "Delt": 95,
    "IsHero": 1,
    "TargetIsHero": 1
  }
}
```

**Relevance to Binary Analysis:**
- Separate fields for intended vs actual damage
- Source field (ability/item/basic attack)
- Team affiliations

#### NPCkillNPC Event
**Triggers:** When non-player actors kill each other (Kraken kills turret, minions fight, etc.)

**Fields:**
- Team, Actor, Killed, KilledTeam
- Gold, IsHero, TargetIsHero, Position

#### EarnXP Event
**Triggers:** When a player earns experience (often paired with KillActor)

**Fields:**
- Team, Actor, Source, Amount, Shared

#### LevelUp Event
**Triggers:** When a player reaches a new level

```json
{
  "type": "LevelUp",
  "payload": {
    "Team": "Left",
    "Actor": "*Koshka*",
    "Level": 6,
    "LifetimeGold": 4500
  }
}
```

#### LearnAbility Event
**Triggers:** When a player upgrades an ability

**Fields:**
- Team, Actor, Ability (identifier), Level

**Note:** Time gap between LevelUp and LearnAbility indicates player decision time

#### Pre-Match Events

**HeroBan:**
```json
{
  "type": "HeroBan",
  "payload": {
    "Team": "Left",
    "Hero": "*Kestrel*"
  }
}
```

**HeroSelect:**
```json
{
  "type": "HeroSelect",
  "payload": {
    "Team": "Left",
    "Hero": "*Ringo*",
    "Player": "PlayerName",
    "Handle": "IGN"
  }
}
```

**HeroSkinSelect:**
- Tracks cosmetic selections

**HeroSwap:**
- Draft mode hero trading between players

### Other Important Events
- **BuyItem** - Item purchases (position data requested in Issue #30)
- **SellItem** - Item sales
- **UseAbility** - Ability activation
- **UseItemAbility** - Activated item usage
- **GoldFromGoldMine** - Gold mine capture
- **Vampirism** - Lifesteal events
- **Position updates** - Movement tracking

### Team & Position Data

**Team Representation:**
- Pre-match: Teams are `1` or `2`
- In-match: Teams are `Left` or `Right`
- Mapping: `1 = Left`, `2 = Right`

**Position Vectors:**
- Format: `[x, z, y]`
- First value: x coordinate
- Second value: z coordinate (often 0 for ground level)
- Third value: y coordinate

### Actor Name Format

**Pattern:** Actors are wrapped in asterisks
- Heroes: `*Koshka*`, `*Ringo*`, `*Vox*`
- Jungle monsters: `*JungleMinion_TreeEnt*`
- Turrets: `*Turret*`
- Items: `*1000_Item_HalcyonPotion*`

**Item Format:** `*[ID]_Item_[Name]*`
- Example: `*1000_Item_HalcyonPotion*` → "Halcyon Potion"
- API includes field mappings for conversion to human-readable names

---

## 3. Community Tools & SDKs

### JavaScript/Node.js
**[vainglory (npm)](https://www.npmjs.com/package/vainglory)**
- **Repository:** [seripap/vainglory](https://github.com/seripap/vainglory)
- **Status:** DEPRECATED (API no longer exists)
- **Features:**
  - Methods named from official API reference
  - `.resolve()` method for telemetry data
  - Returns raw telemetry JSON from CDN URLs

**[gamelocker-vainglory](https://github.com/cforbes/gamelocker-vainglory)**
- Documentation service implementation
- Multiple forks available

### Python
**[madglory-ezl (PyPI)](https://pypi.org/project/madglory-ezl/)**
- **Repository:** [Skillz4Killz/madglory](https://github.com/Skillz4Killz/madglory)
- **Released:** July 16, 2017
- **Installation:** `pip install madglory-ezl`
- **Status:** Inactive maintenance
- **Usage:**
```python
import gamelocker
api = gamelocker.Vainglory(api_key)
player = api.player(player_id)
```

**[gamelocker-vainglory-py](https://github.com/ClarkThyLord/gamelocker-vainglory-py)**
- Wrapper for MadGlory APIs

### Ruby
**[gamelocker_api](https://github.com/cyberarm/gamelocker_api)**
- Unofficial API client for Vainglory Developer API
- Includes telemetry method for accessing data from URLs

**[vainglory-api-ruby](https://github.com/cbortz/vainglory-api-ruby)**
- Ruby library wrapper

### Go
**[vainglory-go-client](https://github.com/madglory/vainglory-go-client)**
- Proof of concept Go client for Vainglory Developer API

### Other Languages
- **Swift:** VaingloryAPI (CocoaPods)
- **Clojure:** [csm/vainglory](https://github.com/csm/vainglory) - Data-driven Swagger API client

---

## 4. Hero & Item Data Resources

### Hero Data

**[oberocks/vainglory-base-stats](https://github.com/oberocks/vainglory-base-stats)**
- **File:** [vainglory.json](https://github.com/oberocks/vainglory-base-stats/blob/master/vainglory.json)
- **Content:** Hard-coded master JSON file from game data
- **Access:**
  - Heroes: `json["heroes"]`
  - Items: `json["items"]`
- **Includes:** Base stats, recommended builds, hero abilities
- **Images:** Thumbnails for heroes, abilities, and items
- **Recent Updates:** Includes SILVERNAIL and latest heroes

**[psenough/vainglory_draft_simulator](https://github.com/psenough/vainglory_draft_simulator)**
- **File:** [vaingloryfire-list-of-heroes.json](https://github.com/psenough/vainglory_draft_simulator/blob/gh-pages/scrapped-data/vaingloryfire-list-of-heroes.json)
- **Content:** Scraped hero list with URLs and image paths
- **Heroes Included:** Adagio, Alpha, Anka, Ardan, Baptiste, Baron, Blackfeather, Catherine, Celeste, Churnwalker, and more

### Item Data

**[Vainglory Tools - Items Reference](https://shoutcasting.mattmct.com/vg-items-reference)**
- Work-in-progress JSON database for developers
- All item data with IDs and mappings

**Item Categories:**
1. Weapon (enhances damage through basic attacks and abilities)
2. Crystal
3. Defense
4. Utility
5. Other

---

## 5. Stat Tracking Platforms

### VGPRO.gg
- **URL:** [https://vgpro.gg/](https://vgpro.gg/)
- **Features:** Pro builds, hero stats, personal player statistics
- **Status:** Most used stat tracking website in community
- **Data Source:** GameLocker API

### VainSocial
- **Status:** RETIRED
- **Features:** TrueSkill ratings, advanced statistics
- **Similar to:** VGPRO.gg

### Community Notes
- All stat trackers used the same GameLocker API
- API downtime affected all platforms simultaneously
- API stopped updating before game shutdown, breaking stat trackers

---

## 6. Community Resources

### Forums & Wikis
- **[VaingloryFire](https://www.vaingloryfire.com/)** - Meta discussion, guides, builds
  - [Complete Hidden Stats Guide](https://www.vaingloryfire.com/vainglory/guide/complete-guide-to-vainglorys-hidden-stats-and-calculations-by-an-engineer-4311) - Engineer's breakdown
- **[Vainglory Wiki (Fandom)](https://vainglory.fandom.com/)** - Heroes, items, lore
- **[Bubbleland - Vainglory Communities](https://bubbleland.org/vainglory-communities)** - Community directory
- **[VG Community Forums](https://vgforums.net/)** - Discussion forum

### Replay Guides
- **[Bubbleland Replay Guide](https://bubbleland.org/vainglory-replay-guide)** - How to access and manage replays
  - Windows: PopcornOne's vaingloryreplay software
  - Android: `/Android/data/com.superevilmegacorp.game/cache`
  - **Note:** Replay files deleted after new match or exiting replay mode (must back up)

### Developer Community
- **Discord Server:** Associated with vainglory-assets repository
- **Purpose:** Common hangout for library and app developers
- **Resources:** API learning, troubleshooting, collaboration

### Visualization Projects
**[dimxasnewfrozen/VG-Telemtry-Timeline](https://github.com/dimxasnewfrozen/VG-Telemtry-Timeline)**
- Builds canvas timeline visualizations from telemetry data
- Example of telemetry data usage

**[Vainglory Tools - Hero Stats Charts](https://shoutcasting.mattmct.com/vg-hero-charts)**
- Statistical analysis tools
- Chart generation from game data

---

## 7. E.V.I.L. Engine Information

### Engine Overview
- **Name:** E.V.I.L. Engine
- **Developer:** Super Evil Megacorp
- **Type:** Proprietary mobile game engine
- **Named:** 2012
- **Current Status:** Active development for multiple games including Netflix Games project

### Technical Characteristics
- **Built from scratch** for mobile MOBA requirements
- **Console-quality graphics** optimized for mobile
- **60 FPS** performance target on mobile devices
- **Sub-30ms** responsive and precise controls
- **Server-authoritative architecture** - Entire gameplay runs on server, not client
- **Metal graphics optimization** - Higher framerates, reduced load times
- **Platform:** iOS and Android optimized

### Relevance to Reverse Engineering
- Server-authoritative design suggests replay files may be server event logs
- Client receives serialized game state updates
- Replay format likely mirrors server-to-client communication protocol

### References
- [Game Developer - Why SEMC Built Proprietary Engine](https://www.gamedeveloper.com/production/why-super-evil-megacorp-built-a-proprietary-mobile-moba-engine)
- [Game Developer - $19M Funding for Engine Tech](https://www.gamedeveloper.com/business/-i-vainglory-i-dev-nets-19m-to-improve-engine-tech)
- [IGDB - E.V.I.L. Engine](https://www.igdb.com/game_engines/evil-engine)

**Note:** No public documentation of E.V.I.L. engine internals or APIs found

---

## 8. Replay File (.vgr) Format

### File Information
- **Extension:** `.vgr`
- **Naming Pattern:** UUID-UUID.version.vgr
  - Example: `dddbf79c-0f0b-11e6-940f-06c5ee41a4a5-41c6404f-bb7e-40c0-b790-f9cb6048f14d.15.vgr`

### File Locations
- **Windows:** AppData folder (managed by PopcornOne's vaingloryreplay tool)
- **Android:** `/Android/data/com.superevilmegacorp.game/cache`

### Lifecycle
- Files automatically deleted after playing another match
- Files deleted when exiting replay mode
- Must manually back up to preserve

### Reverse Engineering Status
- **No public documentation** of .vgr binary format found
- **No parser implementations** found on GitHub
- **Community focus** was on API data, not replay files
- **Tools available:** Only playback software, no parsers

### Potential Format Hypotheses
Based on general game development practices:

**Serialization Candidates:**
- **Protocol Buffers (protobuf):** Common for game networking, compact binary
- **MessagePack:** Efficient binary serialization, JSON-like structure
- **Custom binary format:** Most likely given proprietary E.V.I.L. engine

**Structure Hypotheses:**
1. **Event stream:** Sequential log of server events (matches telemetry structure)
2. **State snapshots + deltas:** Periodic full state + incremental changes
3. **Compressed event log:** Binary equivalent of telemetry JSON

---

## 9. Mapping Telemetry to Binary Patterns

### Strategy for Reverse Engineering

#### Known Telemetry → Binary Correlation
1. **Find matches with known telemetry data**
   - Download telemetry JSON from old API archives
   - Obtain corresponding .vgr replay file
   - Search for patterns in binary that match telemetry timestamps/events

2. **Event Pattern Detection**
   - KillActor events should have consistent binary signatures
   - Hero names (`*Koshka*`) may appear as string literals or hashed IDs
   - Position vectors `[x, z, y]` likely stored as float32 triplets
   - Timestamps may be Unix epoch or game-time deltas

3. **Statistical Analysis**
   - Count event types in telemetry
   - Count similar binary patterns in .vgr
   - Correlation should reveal event markers

#### Field Identification Priorities

**High-Value Fields:**
- Event type markers (KillActor, DealDamage, etc.)
- Timestamps (critical for event sequencing)
- Actor IDs (hero/entity references)
- Position data (x, z, y coordinates as floats)
- Team affiliations (Left/Right, 1/2)

**Binary Search Patterns:**
- Hero names: Search for "Koshka", "Ringo", "Vox" as ASCII strings
- Magic numbers: File headers, section markers
- Repeated structures: Event records of fixed size
- Float arrays: Position vectors as IEEE 754

---

## 10. Key Insights for Current Reverse Engineering Effort

### Critical Findings

1. **Telemetry provides the schema**
   - Every match event is documented with exact field names
   - JSON structure shows logical data organization
   - Event types provide vocabulary for binary analysis

2. **Hero detection correlation**
   - Your current work shows 0% hero detection accuracy
   - Telemetry shows heroes use `*HeroName*` format in strings
   - Heroes may be stored as:
     - String literals with asterisks
     - Integer IDs mapped to hero dictionary
     - Hashed strings for compression

3. **Event pattern detection validation**
   - Telemetry shows expected event sequences (EarnXP + KillActor paired)
   - Binary patterns should mirror these correlations
   - Time gaps between LevelUp and LearnAbility indicate decision points

4. **Position data validation**
   - Telemetry uses `[x, z, y]` float vectors
   - Search for triplets of IEEE 754 float32/float64
   - Valid game map coordinates have known bounds

5. **Team and side information**
   - Pre-match: 1/2
   - In-match: Left/Right
   - Binary should show this transition

### Recommendations

1. **Obtain telemetry + replay pairs**
   - Check if community members archived matched datasets
   - Use telemetry as ground truth to validate binary parsing

2. **Search for hero name strings**
   - Look for "Koshka", "Ringo", "Vox" without asterisks
   - Look for "Hero_" prefixes
   - Check for hero ID enums

3. **Validate event detection with telemetry counts**
   - Parse telemetry: count KillActor events
   - Parse binary: count suspected kill signatures
   - Numbers should match

4. **Focus on file structure first**
   - Identify header, metadata, event stream sections
   - Find event count fields
   - Locate timestamp references

---

## 11. Archived API Access Attempts

### Web Archive Search Results
- `site:web.archive.org developer.vainglorygame.com` - No results
- `site:web.archive.org gamelocker.gitbooks.io` - No results (site: operator not supported)

### Alternative Archive Access
- **GitBook documentation** still live at gamelocker.gitbooks.io (as of research date)
- **GitHub repositories** provide full documentation backups
- **Community mirrors** may exist on Discord/forums

### API Endpoint Status
- `https://api.dc01.gamelockerapp.com/shards/` - No longer operational
- All SDK examples return connection errors
- Telemetry CDN URLs may still work if you have direct links from old match data

---

## 12. General Reverse Engineering Resources

### Tools Mentioned (Not Vainglory-Specific)
- **Hex Editors:** HxD, 010 Editor, ImHex
- **Binary Analysis:** Binwalk, Radare2, Ghidra
- **File Format Analysis:** QuickBMS (script-based extraction)
- **Serialization Tools:** protoc (Protocol Buffers), msgpack parsers

### Methodologies
- **[Wolfire Games - Reverse Engineering Binary Files](http://blog.wolfire.com/2010/04/Reverse-Engineering-Binary-Files)**
- **[Apriorit - Reverse Engineer Proprietary Formats](https://www.apriorit.com/dev-blog/780-reverse-reverse-engineer-a-proprietary-file-format)**
- **[Wikibooks - Reverse Engineering File Formats](https://en.wikibooks.org/wiki/Reverse_Engineering/File_Formats)**
- **[GitHub - awesome-game-file-format-reversing](https://github.com/VelocityRa/awesome-game-file-format-reversing)**

---

## 13. Unanswered Questions & Next Steps

### Questions for Community
1. Does anyone have matched telemetry JSON + .vgr replay file pairs?
2. Are there Discord servers with active Vainglory modding communities?
3. Did anyone successfully parse .vgr files for custom tools?
4. Were replay files ever documented in official dev resources?

### Next Research Steps
1. **Join Vainglory Discord servers** - Ask about replay file structure
2. **Check Reddit archives** - r/vainglorygame may have technical discussions
3. **Contact former API developers** - GitHub contributors may have insights
4. **Search for academic papers** - MOBA networking/replay research

### Binary Analysis Next Steps
1. **Hex dump comparison** - Compare multiple .vgr files for common structures
2. **Entropy analysis** - Identify compressed vs uncompressed sections
3. **String extraction** - Pull all ASCII strings, look for hero/item names
4. **Pattern detection** - Statistical analysis of byte sequences
5. **File carving** - Look for embedded data structures (JSON, protobuf, msgpack)

---

## Sources & References

### Official Documentation
- [Vainglory Telemetry - GameLocker GitBook](https://gamelocker.gitbooks.io/vainglory/content/en/telemetry.html)
- [GitHub: SuperEvilMegacorp/vainglory-assets](https://github.com/SuperEvilMegacorp/vainglory-assets)
- [GitHub: SuperEvilMegacorp/vainglory-docs](https://github.com/gamelocker/vainglory-docs)

### API Client Libraries
- [npm: vainglory](https://www.npmjs.com/package/vainglory) | [GitHub: seripap/vainglory](https://github.com/seripap/vainglory)
- [PyPI: madglory-ezl](https://pypi.org/project/madglory-ezl/) | [GitHub: Skillz4Killz/madglory](https://github.com/Skillz4Killz/madglory)
- [GitHub: cyberarm/gamelocker_api](https://github.com/cyberarm/gamelocker_api) (Ruby)
- [GitHub: cbortz/vainglory-api-ruby](https://github.com/cbortz/vainglory-api-ruby)
- [GitHub: madglory/vainglory-go-client](https://github.com/madglory/vainglory-go-client)

### Community Resources
- [Vainglory Cheatsheet - DevHints](https://devhints.io/vainglory)
- [GitHub: rstacruz/cheatsheets/vainglory.md](https://github.com/rstacruz/cheatsheets/blob/master/vainglory.md)
- [VaingloryFire - Complete Stats Guide](https://www.vaingloryfire.com/vainglory/guide/complete-guide-to-vainglorys-hidden-stats-and-calculations-by-an-engineer-4311)
- [Bubbleland - Vainglory Replay Guide](https://bubbleland.org/vainglory-replay-guide)
- [Bubbleland - Vainglory Communities](https://bubbleland.org/vainglory-communities)

### Data Resources
- [GitHub: oberocks/vainglory-base-stats](https://github.com/oberocks/vainglory-base-stats)
- [GitHub: psenough/vainglory_draft_simulator](https://github.com/psenough/vainglory_draft_simulator)
- [Vainglory Tools - Items Reference](https://shoutcasting.mattmct.com/vg-items-reference)
- [Vainglory Tools - Hero Stats Charts](https://shoutcasting.mattmct.com/vg-hero-charts)

### Visualization Projects
- [GitHub: dimxasnewfrozen/VG-Telemtry-Timeline](https://github.com/dimxasnewfrozen/VG-Telemtry-Timeline)

### E.V.I.L. Engine
- [Game Developer - Proprietary Engine Article](https://www.gamedeveloper.com/production/why-super-evil-megacorp-built-a-proprietary-mobile-moba-engine)
- [Game Developer - $19M Funding](https://www.gamedeveloper.com/business/-i-vainglory-i-dev-nets-19m-to-improve-engine-tech)
- [IGDB - E.V.I.L. Engine](https://www.igdb.com/game_engines/evil-engine)

### Stat Trackers
- [VGPRO.gg](https://vgpro.gg/)

### Wikis & Databases
- [Vainglory Wiki (Fandom)](https://vainglory.fandom.com/)
- [VaingloryFire](https://www.vaingloryfire.com/)
- [VG Community Forums](https://vgforums.net/)

### General Reverse Engineering
- [Wolfire Games - Reverse Engineering Binary Files](http://blog.wolfire.com/2010/04/Reverse-Engineering-Binary-Files)
- [Apriorit - Reverse Engineer Proprietary Formats](https://www.apriorit.com/dev-blog/780-reverse-reverse-engineer-a-proprietary-file-format)
- [Wikibooks - Reverse Engineering File Formats](https://en.wikibooks.org/wiki/Reverse_Engineering/File_Formats)
- [GitHub: VelocityRa/awesome-game-file-format-reversing](https://github.com/VelocityRa/awesome-game-file-format-reversing)

---

## Conclusion

The Vainglory GameLocker API telemetry documentation provides a comprehensive schema for match events that should correspond directly to data stored in .vgr replay files. While no existing parsers or format documentation for .vgr files were found, the telemetry JSON structure serves as a "rosetta stone" for understanding what data should be present and how it's logically organized.

**Primary value of this research:**
1. Complete event type enumeration (KillActor, DealDamage, LevelUp, etc.)
2. Exact field names and data types for each event
3. Actor name formatting conventions (`*HeroName*`)
4. Position vector structure `[x, z, y]`
5. Team representation mapping (1/2 → Left/Right)
6. Event correlation patterns (EarnXP + KillActor pairing)

**Recommended next action:** Obtain telemetry JSON + .vgr pairs to correlate known data with binary patterns, enabling validation of parsing hypotheses.
