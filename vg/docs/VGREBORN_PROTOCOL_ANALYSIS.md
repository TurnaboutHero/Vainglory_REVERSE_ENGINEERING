# VGReborn Protocol Analysis

## Research Query
Investigation of the VGReborn project and related Vainglory resources to understand network protocols, binary data structures, and replay file formats.

**Primary Repository:** https://github.com/VaingloryReborn/VGReborn
**Research Date:** 2026-02-15

---

## Executive Summary

VGReborn is a community-driven project that uses MITM (Man-in-the-Middle) proxy technology to monitor and track Vainglory Community Edition game traffic. The project intercepts HTTP traffic to `rpc.kindred-live.net` and parses JSON-formatted API calls rather than binary protocols.

**Key Finding:** VGReborn does NOT parse VGR replay files or handle binary game protocols. It monitors HTTP-based RPC calls to track player states and matchmaking activities.

---

## VGReborn Architecture

### Project Structure
```
VGReborn/
├── web/                    # Frontend application
├── mitm-monitor/          # Network traffic monitoring service
│   ├── src/
│   │   ├── index.ts       # Main entry point
│   │   ├── types.ts       # Type definitions
│   │   ├── handlers/
│   │   │   └── actionDispatcher.ts
│   │   ├── lib/
│   │   │   └── supabase.ts
│   │   └── services/
│   │       ├── userService.ts
│   │       └── wgService.ts
├── supabase/              # Backend infrastructure
└── IP-whitelist.txt       # Access controls
```

### Technology Stack
- **Language:** TypeScript (90.2%), JavaScript, HTML, CSS
- **Runtime:** Node.js
- **Dependencies:**
  - `ws` v8.19.0 - WebSocket for real-time communication
  - `@supabase/supabase-js` v1.35.7 - Database client
- **Build Tools:** TypeScript, ts-node, nodemon

### MITM Implementation

#### Data Interception Method
The mitm-monitor does NOT perform deep packet inspection or binary protocol parsing. Instead:

1. **Log Stream Reading:** Reads journalctl logs from a separate MITM proxy service
   ```bash
   journalctl -u mitm-proxy
   ```

2. **HTTP Traffic Filtering:** Extracts JSON-formatted log entries containing:
   - Client IP addresses
   - HTTP methods and URLs
   - Request/response headers
   - Request/response bodies (JSON format)
   - HTTP status codes

3. **Endpoint Targeting:** Filters for requests to `rpc.kindred-live.net`

4. **Action Extraction:** Parses the URL path to extract the final segment as an action identifier

#### Notable Absences
- No packet capture libraries (pcap)
- No binary parsing utilities
- No protobuf dependencies
- No network interception frameworks
- No VGR replay file handling

---

## Tracked Game Actions

The VGReborn system monitors 12 Vainglory RPC actions:

### Session Management
1. **startSessionForPlayer** - Session initialization
   - Captures: location, player UUID, country/region
2. **endSession** - Logout/session termination

### Player State Tracking
3. **update** - State transitions
   - States: `offline`, `online`, `menus`, `gaming`, `matching`, `recording`
   - Monitors: menus → online, playing → gaming

### Matchmaking
4. **joinLobby** - Queue entry
   - Extracts: lobby type (e.g., "5v5_pvp_casual")
   - Contains validation logic (rejects casual 5v5 lobbies)
5. **exitLobby** - Queue departure
6. **queryPendingMatch** - Match availability checks

### Social Features
7. **friendListAll** - Friend list access

### Post-Match
8. **recordMatchExperienceMetrics** - Analytics collection
9. **notifyExitPostMatch** - Match conclusion handling

### Player Data
10. **getPlayerInfo** - Player data retrieval
11. **renamePlayerHandle** - Name changes

---

## Data Structures

### MitmLogEntry Interface
```typescript
interface MitmLogEntry {
  time?: string;
  client_ip?: string | null;
  method?: string;
  url?: string;
  status?: number;
  req_headers?: object;
  req_body?: any;
  res_body?: any;
  [key: string]: any;
}
```

### CacheEntry Interface
```typescript
interface CacheEntry {
  timestamp: number;
  data?: {
    userId: string;
    user: any;
  } | null;
}
```

### Player State Management
- **State Values:** `offline`, `online`, `menus`, `gaming`, `matching`, `recording`
- **Cache Duration:** 24 hours (max 1,000 entries)
- **Activity Timeout:** 2 minutes → offline
- **Cleanup Interval:** 10 minutes
- **Memory Cleanup:** Records older than 30 minutes removed

---

## Official Vainglory API Research

### API Background
- **Original API:** gamelocker API (deprecated, no longer operational)
- **Endpoint Format:** `https://api.dc01.gamelockerapp.com/shards/{region}/matches`
- **Regions:** na, eu, sa, ea, sg
- **Status:** API shut down when Vainglory closed in 2019

### Telemetry System

#### Event Structure
All telemetry events follow this pattern:
```json
{
  "time": "2017-02-18T06:37:15+0000",
  "type": "EventType",
  "payload": {
    // Event-specific data
  }
}
```

#### Known Event Types

**Combat Events:**
- **DealDamage** - Damage dealt
  - Fields: `Team`, `Actor`, `Target`, `Source`, `Damage`, `Delt`, `IsHero`, `TargetIsHero`

- **KillActor** - Entity killed
  - Fields: `Team`, `Actor`, `Killed`, `KilledTeam`, `Gold`, `IsHero`, `TargetIsHero`, `Position`

**Economy Events:**
- **BuyItem** - Item purchased
  - Fields: `Team`, `Actor`, `Item`, `Cost`, `RemainingGold`, `Position`

**Player Events:**
- **PlayerFirstSpawn** - First spawn
  - Fields: `Team`, `Actor`

- **LevelUp** - Level gained
  - Fields: `Team`, `Actor`, `Level`, `LifetimeGold`

#### Position Format
Positions are represented as 3D vectors:
```json
"Position": [x, z, y]
```
- First value: x coordinate
- Second value: z coordinate
- Third value: y coordinate

#### Team Representation
- Pre-match: `1` or `2`
- In-match: `Left` or `Right`
- Mapping: `1` = `Left`, `2` = `Right`

#### Actor/Entity Format
Entities use encoded identifiers with prefixes:
- Items: `*1000_Item_HalcyonPotion*`
- Heroes: `*Gwen*`, `*Ringo*`, etc.

### Community Resources

**SuperEvilMegacorp/vainglory-assets Repository:**
- **Purpose:** Community-provided schemas, dictionaries, and assets
- **Components:**
  - `assets/` - Hero and item images
  - `dictionaries/` - Key-to-human-readable translation
  - `schemas/2.7/` - API object definitions
  - `telemetry_event_info.md` - Event documentation
- **License:** MIT
- **Status:** 62 stars, 41 forks, archived (API deprecated)

**API Wrapper Libraries:**
- JavaScript: `seripap/vainglory` (deprecated, archived 2019-09-12)
- Response format: JSON:API specification
- Models: Match, Player, Roster, Participant, Asset

---

## VGR Replay File Format

### File Naming Convention
```
dddbf79c-0f0b-11e6-940f-06c5ee41a4a5-41c6404f-bb7e-40c0-b790-f9cb6048f14d.15.vgr
```
- Format: `{uuid1}-{uuid2}.{number}.vgr`
- Extension: `.vgr`

### Technical Information
**CRITICAL FINDING:** No public documentation exists for the VGR binary format structure.

**What We Know:**
- VGR files are binary replay files created by Vainglory
- Files contain recorded match data
- Located in game's replay directory

**What We DON'T Know:**
- Binary structure/layout
- Encoding format (protobuf, custom binary, etc.)
- Compression method (if any)
- Header format
- Event serialization format
- How it relates to telemetry API data

**Why There's No Information:**
1. Vainglory shut down in 2019, development ceased
2. Super Evil Megacorp never published VGR format specifications
3. VGReborn project monitors HTTP API, not replay files
4. Community focused on live API rather than replay parsing

---

## Protocol Analysis: What VGReborn Reveals

### Network Architecture

#### RPC Server
- **Endpoint:** `rpc.kindred-live.net`
- **Protocol:** HTTP-based RPC
- **Format:** JSON request/response bodies
- **Authentication:** Session tokens in request bodies

#### Request Structure
```
POST https://rpc.kindred-live.net/{action}
Headers: [standard HTTP headers]
Body: JSON with params array
```

Example action: `startSessionForPlayer`, `update`, `joinLobby`

#### Response Structure
```json
{
  "returnValue": {
    // Action-specific response data
  }
}
```

### Data Extraction Patterns

**From Response Bodies:**
```typescript
const returnValue = res_body?.returnValue;
// Extract country, region, player UUID, match status, etc.
```

**From Request Bodies:**
```typescript
const params = req_body?.params;
// Extract lobby type, player handle, configuration
```

### Implementation Notes

1. **JSON Parsing Safety:** Code includes error handling for malformed JSON
2. **Validation Logic:** Specific business rules (e.g., rejecting casual 5v5)
3. **Caching Strategy:** 24-hour cache with size limits to reduce DB load
4. **State Management:** In-memory Maps for tracking active users
5. **Cleanup Automation:** Background services for offline detection

---

## Reverse Engineering Insights

### What Can Be Learned from VGReborn

**Positive Findings:**
1. **RPC Action Catalog:** 12 documented game actions
2. **Player State Model:** State machine with 6 states
3. **API Endpoint:** `rpc.kindred-live.net` domain
4. **Request Format:** JSON-based RPC calls
5. **Session Management:** Token-based authentication pattern

**Limitations:**
1. **No Binary Protocol Access:** Only monitors HTTP layer
2. **No Game Logic:** Doesn't see actual gameplay packets
3. **No Replay Parsing:** VGR files not handled
4. **No Event Stream:** Doesn't capture real-time game events
5. **Limited Visibility:** Only sees RPC calls, not UDP game traffic

### Potential Approaches for VGR Analysis

Given the lack of documentation, here are potential reverse engineering approaches:

#### 1. Binary Structure Analysis
```python
# Examine file headers
with open('replay.vgr', 'rb') as f:
    magic_bytes = f.read(4)  # Check for magic number
    header = f.read(256)      # Examine header structure
```

#### 2. Pattern Recognition
- Look for repeated byte sequences (entity IDs)
- Identify variable-length encoding patterns
- Search for timestamp patterns
- Find position coordinate patterns (float triplets)

#### 3. Cross-Reference with Telemetry API
If VGR files contain similar events to telemetry API:
- Event types might use same encoding
- Entity IDs might match API format (`*Hero*`)
- Timestamps might be Unix epoch or similar
- Team/position data might use same structure

#### 4. E.V.I.L. Engine Analysis
Vainglory was built with the proprietary **E.V.I.L. engine** (NOT Unity):
- Server-authoritative architecture
- Custom binary formats (no standard Unity serialization)
- May use protobuf or custom serialization
- Reverse engineer game binary directly (no Unity asset bundles)

#### 5. Network Traffic Capture
If Vainglory CE still runs:
- Capture UDP game traffic (not just HTTP RPC)
- Compare captured packets to VGR file structure
- Identify real-time event encoding
- Map network messages to replay data

---

## Related Technologies

### Protocol Buffers in Game Networking
Based on industry research:

**Common Usage:**
- Binary serialization for client-server communication
- Compact format for mobile games
- Fast cross-platform serialization
- Language-neutral schema definitions

**Vainglory Possibility:**
While not confirmed, Vainglory MAY have used protobuf given:
- Mobile MOBA requiring efficient networking
- E.V.I.L. engine is server-authoritative (custom proprietary engine, NOT Unity)
- Industry standard for game networking
- Super Evil Megacorp's technical sophistication

**NOTE:** Vainglory does NOT use Unity. It uses the proprietary E.V.I.L. engine.
Standard Unity reverse engineering tools (IL2CPPDumper, AssetRipper) do NOT apply.

---

## Recommendations for VGR Reverse Engineering

### Immediate Actions
1. **Hex Dump Analysis:** Examine VGR file structure manually
2. **Entropy Analysis:** Check for compression/encryption
3. **String Scanning:** Search for readable text (hero names, items)
4. **Pattern Matching:** Look for UUID, timestamp, coordinate patterns

### Medium-Term Approaches
1. **Unity Binary Analysis:** Extract and analyze game binaries
2. **Asset Extraction:** Look for schema files in Unity assets
3. **Network Capture:** If game still runs, capture live traffic
4. **Community Contact:** Reach out to VGReborn developers directly

### Tools to Consider
- **Hex Editors:** HxD, 010 Editor
- **Binary Analysis:** Kaitai Struct, binwalk, Ghidra, IDA
- **Network:** Wireshark, mitmproxy
- **Protobuf:** protoc, protobuf-inspector
- **Note:** Unity tools (AssetStudio, IL2CPPDumper) do NOT apply - E.V.I.L. engine

### Key Questions to Answer
1. Does VGR use protobuf, MessagePack, or custom serialization?
2. Are events stored sequentially or indexed?
3. Is there compression (gzip, zlib, etc.)?
4. How are variable-length fields encoded?
5. What's the relationship between VGR and telemetry API format?

---

## Comparison: HTTP API vs VGR Files

| Aspect | HTTP Telemetry API | VGR Replay Files |
|--------|-------------------|------------------|
| **Format** | JSON (text) | Binary |
| **Access** | HTTP requests | Local file |
| **Documentation** | Partially documented | No documentation |
| **Structure** | JSON:API spec | Unknown |
| **Events** | Array of events | Unknown encoding |
| **Parsability** | Easy (JSON) | Requires reverse engineering |
| **Size** | Larger (text) | Smaller (binary) |
| **Timestamp** | ISO 8601 strings | Unknown encoding |
| **Position** | JSON arrays | Unknown encoding |
| **Entities** | String identifiers | Unknown encoding |

---

## Sources & References

### Primary Research
- [VGReborn GitHub Repository](https://github.com/VaingloryReborn/VGReborn)
- [Vainglory CE Organization](https://github.com/vaingloryce)
- [SuperEvilMegacorp/vainglory-assets](https://github.com/SuperEvilMegacorp/vainglory-assets)
- [seripap/vainglory API Client](https://github.com/seripap/vainglory)

### Documentation
- [Vainglory Telemetry Documentation](https://gamelocker.gitbooks.io/vainglory/content/en/telemetry.html)
- [Vainglory API NPM Package](https://www.npmjs.com/package/vainglory)
- [Vainglory Replay Guide - Bubbleland](https://bubbleland.org/vainglory-replay-guide)

### Technical Resources
- [Practical IL2CPP Reverse Engineering: Protobuf](https://katyscode.wordpress.com/2020/08/10/practical-il2cpp-protobuf/)
- [Unity Protocol Buffers - AngryAnt](https://www.angryant.com/2017/02/17/Unity-Protocol-Buffers/)
- [Reverse Engineering Network Protocols - Jack Hacks](https://jhalon.github.io/reverse-engineering-protocols/)
- [Reverse Engineering Game Network Protocols](https://shalzuth.com/Blog/DeepDiveIntoGameNetworkProtocols)

### Community Resources
- [VaingloryFire API Discussion](https://www.vaingloryfire.com/vainglory/forum/new-player-help/vainglory-api-38321)
- [Vainglory Assets Issues (GitHub)](https://github.com/SuperEvilMegacorp/vainglory-assets/issues/30)
- [VG Telemetry Timeline Project](https://github.com/dimxasnewfrozen/VG-Telemtry-Timeline)

---

## Conclusions

### What VGReborn Teaches Us

**Architecture Insights:**
- Vainglory uses HTTP-based RPC for metagame features (matchmaking, sessions, friends)
- Game uses JSON for API communication (at least for non-gameplay features)
- Session management uses token-based authentication
- Player state tracked server-side with 6 distinct states

**Protocol Details:**
- RPC endpoint: `rpc.kindred-live.net`
- 12 documented RPC actions
- JSON request/response format
- Params array for request data
- ReturnValue object for responses

**Limitations:**
- VGReborn does NOT help with VGR binary format
- No access to real-time gameplay packets
- Only monitors metagame HTTP traffic
- Does not parse or handle replay files

### Gap Analysis

**What We Still Need:**
1. VGR binary format specification
2. Real-time game event protocol (likely UDP)
3. Entity ID encoding scheme
4. Event serialization format
5. Protobuf schemas (if used)
6. Replay file header structure
7. Data compression details
8. Coordinate encoding format

### Next Steps

**For VGR Binary Analysis:**
1. Start with hex dump examination
2. Look for magic bytes and headers
3. Search for known patterns (UUIDs, hero names)
4. Check for protobuf markers
5. Analyze file size vs match duration correlation
6. Compare multiple VGR files for common structure

**For E.V.I.L. Engine Analysis (NOT Unity):**
1. Extract Vainglory APK/IPA
2. Analyze native binaries directly (no IL2CPP - custom engine)
3. Search for protobuf definitions in binary
4. Look for serialization code in disassembled binary
5. Find network protocol implementations
6. Note: Standard Unity tools do NOT apply

**For Community Engagement:**
1. Contact VGReborn developers directly
2. Ask about VGR file handling plans
3. Share findings with community
4. Collaborate on reverse engineering efforts
5. Check if any game traffic capture exists

---

## Addendum: VGReborn MITM Monitor Code Samples

### Action Dispatcher Logic
The VGReborn project tracks these specific actions with custom handling:

```typescript
// Pseudo-code representation of actionDispatcher.ts logic

switch(action) {
  case 'startSessionForPlayer':
    // Extract player UUID, location, country
    break;

  case 'update':
    // Track state transitions (menus, online, gaming)
    break;

  case 'joinLobby':
    // Extract lobby type, validate (reject casual 5v5)
    break;

  case 'queryPendingMatch':
    // Check match availability
    break;

  case 'friendListAll':
    // Social features
    break;

  case 'recordMatchExperienceMetrics':
    // Post-match analytics
    break;

  // ... other actions
}
```

### User Service Caching
```typescript
// Cache management for user data
const userCache = new Map<string, CacheEntry>();
const CACHE_DURATION = 24 * 60 * 60 * 1000; // 24 hours
const MAX_CACHE_SIZE = 1000;

// Activity tracking
const lastActiveMap = new Map<string, number>();
const OFFLINE_THRESHOLD = 2 * 60 * 1000; // 2 minutes
const CLEANUP_INTERVAL = 10 * 60 * 1000; // 10 minutes
```

---

**Report Generated:** 2026-02-15
**Researcher:** Claude Sonnet 4.5 (Librarian Agent)
**Project:** VG_REVERSE_ENGINEERING
