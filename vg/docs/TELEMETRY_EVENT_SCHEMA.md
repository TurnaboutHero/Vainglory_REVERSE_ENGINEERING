# Vainglory Telemetry Event Schema Reference

**Source Documentation**: [Vainglory API Telemetry Documentation](https://gamelocker.gitbooks.io/vainglory/content/en/telemetry.html)

**Last Updated**: 2026-02-15

**Note**: The official Vainglory API is deprecated and no longer operational. This documentation is based on archived API documentation for reverse engineering VGR replay files.

---

## Overview

Vainglory telemetry provides detailed insights into match events, including:
- What happened during the match
- When each event occurred (timestamp)
- Where events occurred (position vectors for applicable events)
- Who was involved (actors, targets, teams)

## Event Structure

All telemetry events follow this basic structure:

```json
{
  "time": "2017-03-17T00:38:32+0000",
  "type": "EventTypeName",
  "payload": {
    // Event-specific fields
  }
}
```

### Common Fields

- **time**: ISO 8601 timestamp (e.g., "2017-02-18T06:37:15+0000")
- **type**: String indicating the event type
- **payload**: Object containing event-specific data

### Team Representation

- **Pre-match events**: Teams appear as `1` or `2`
- **Match events**: Teams appear as `Left` or `Right`
  - Team `1` = `Left` side
  - Team `2` = `Right` side

### Position Vectors

Positions are given as three-value arrays `[x, z, y]`:
- First value: X coordinate
- Second value: Z coordinate
- Third value: Y coordinate

Example: `[39.39, 0.01, 27.26]`

---

## Pre-Match Events

### HeroBan

Recorded when a hero is banned during draft mode.

**Payload Fields**:
- `Team`: String - Team that banned the hero (1 or 2)
- `Hero`: String - Name of the banned hero

**Example**:
```json
{
  "time": "2017-03-17T00:38:00+0000",
  "type": "HeroBan",
  "payload": {
    "Team": "1",
    "Hero": "*Reim*"
  }
}
```

---

### HeroSelect

Recorded when a player selects a hero during draft.

**Payload Fields**:
- `Team`: String - Team number (1 or 2)
- `Actor`: String - Player identifier
- `Hero`: String - Selected hero name

**Example**:
```json
{
  "time": "2017-03-17T00:38:15+0000",
  "type": "HeroSelect",
  "payload": {
    "Team": "1",
    "Actor": "*Player1*",
    "Hero": "*Kestrel*"
  }
}
```

---

### HeroSkinSelect

Recorded when a player selects a skin for their hero.

**Payload Fields**:
- `Team`: String - Team number (1 or 2)
- `Actor`: String - Player identifier
- `Skin`: String - Skin name/identifier

**Example**:
```json
{
  "time": "2017-03-17T00:38:20+0000",
  "type": "HeroSkinSelect",
  "payload": {
    "Team": "1",
    "Actor": "*Player1*",
    "Skin": "Kestrel_Skin_Season3"
  }
}
```

---

## Match Events - Combat

### DealDamage

Recorded when any actor (player, turret, minion, etc.) deals damage to another.

**Payload Fields**:
- `Team`: String - Team of the actor dealing damage
- `Actor`: String - Entity dealing damage
- `Target`: String - Entity receiving damage
- `Source`: String - Source of damage (ability name, auto-attack, etc.)
- `Damage`: Number - Amount of damage dealt
- `Delt`: Number - Actual damage dealt (after mitigation)
- `IsHero`: Boolean - Whether the actor is a hero
- `TargetIsHero`: Boolean - Whether the target is a hero

**Example**:
```json
{
  "time": "2017-02-18T06:37:15+0000",
  "type": "DealDamage",
  "payload": {
    "Team": "Left",
    "Actor": "*Kestrel*",
    "Target": "*Lyra*",
    "Source": "HERO_ABILITY_KESTREL_C_NAME",
    "Damage": 500,
    "Delt": 320,
    "IsHero": 1,
    "TargetIsHero": 1
  }
}
```

---

### KillActor

Recorded when a player kills anything in game (hero, minion, miner, jungle monster, etc.).

**Payload Fields**:
- `Team`: String - Team of the killer
- `Actor`: String - Entity that performed the kill
- `Killed`: String - Entity that was killed
- `KilledTeam`: String - Team of the killed entity
- `Gold`: String - Gold awarded for the kill
- `IsHero`: Number - Whether the killer is a hero (1 or 0)
- `TargetIsHero`: Number - Whether the killed entity is a hero (1 or 0)
- `Position`: Array - Location where kill occurred [x, z, y]

**Notes**:
- KillActor and EarnXP events typically occur together
- Position field may not be present in all versions

**Example**:
```json
{
  "time": "2017-03-17T00:40:23+0000",
  "type": "KillActor",
  "payload": {
    "Team": "Left",
    "Actor": "*Koshka*",
    "Killed": "*Reim*",
    "KilledTeam": "Right",
    "Gold": "300",
    "IsHero": 1,
    "TargetIsHero": 1,
    "Position": [25.00, 0.00, 25.00]
  }
}
```

---

### NPCkillNPC

Recorded when one non-player actor kills another (e.g., Kraken killing a turret, minion killing another minion).

**Payload Fields**:
- `Team`: String - Team of the NPC that performed the kill
- `Actor`: String - NPC that performed the kill
- `Killed`: String - NPC that was killed
- `KilledTeam`: String - Team of the killed NPC
- `Position`: Array - Location where kill occurred [x, z, y]

**Example**:
```json
{
  "time": "2017-03-17T00:45:12+0000",
  "type": "NPCkillNPC",
  "payload": {
    "Team": "Left",
    "Actor": "*Kraken*",
    "Killed": "*Turret*",
    "KilledTeam": "Right",
    "Position": [45.00, 0.00, 45.00]
  }
}
```

---

## Match Events - Abilities & Items

### UseAbility

Recorded when a player uses a hero ability.

**Payload Fields**:
- `Team`: String - Team of the player
- `Actor`: String - Hero using the ability
- `Ability`: String - Name/identifier of the ability used
- `Position`: Array - Location where ability was used [x, z, y]

**Example**:
```json
{
  "time": "2017-03-17T00:39:08+0000",
  "type": "UseAbility",
  "payload": {
    "Team": "Right",
    "Actor": "*Kestrel*",
    "Ability": "HERO_ABILITY_KESTREL_A_NAME",
    "Position": [39.39, 0.01, 27.26]
  }
}
```

---

### UseItemAbility

Recorded when a player uses an activatable item (e.g., Travel Boots, Reflex Block).

**Payload Fields**:
- `Team`: String - Team of the player
- `Actor`: String - Hero using the item
- `Ability`: String - Name of the item used
- `Position`: Array - Location where item was used [x, z, y]
- `TargetActor`: String - Target of the item ability (or "None")
- `TargetPosition`: Array - Target location [x, z, y]

**Example**:
```json
{
  "time": "2017-03-31T03:10:17+0000",
  "type": "UseItemAbility",
  "payload": {
    "Team": "Left",
    "Actor": "*Lyra*",
    "Ability": "Travel Boots",
    "Position": [-17.51, 0.01, 41.63],
    "TargetActor": "None",
    "TargetPosition": [-17.51, 0.01, 41.63]
  }
}
```

---

### LearnAbility

Recorded when a player upgrades/learns an ability.

**Payload Fields**:
- `Team`: String - Team of the player
- `Actor`: String - Hero learning the ability
- `Ability`: String - Name of the ability learned/upgraded
- `Level`: Number - New level of the ability

**Example**:
```json
{
  "time": "2017-03-17T00:39:45+0000",
  "type": "LearnAbility",
  "payload": {
    "Team": "Left",
    "Actor": "*Koshka*",
    "Ability": "HERO_ABILITY_KOSHKA_A_NAME",
    "Level": 2
  }
}
```

---

## Match Events - Economy

### BuyItem

Recorded when a player purchases an item from the shop.

**Payload Fields**:
- `Team`: String - Team of the player
- `Actor`: String - Hero buying the item
- `Item`: String - Name of the item purchased
- `Cost`: Number - Gold cost of the item
- `Position`: Array (optional) - Location of purchase [x, z, y]

**Notes**: Position field was added later to help determine which shop was used.

**Example**:
```json
{
  "time": "2017-03-17T00:38:45+0000",
  "type": "BuyItem",
  "payload": {
    "Team": "Left",
    "Actor": "*Koshka*",
    "Item": "Weapon Blade",
    "Cost": 300
  }
}
```

---

### SellItem

Recorded when a player sells an item.

**Payload Fields**:
- `Team`: String - Team of the player
- `Actor`: String - Hero selling the item
- `Item`: String - Name of the item sold
- `Cost`: Number - Gold received from selling (typically 60% of purchase price)

**Example**:
```json
{
  "time": "2017-03-17T00:42:30+0000",
  "type": "SellItem",
  "payload": {
    "Team": "Right",
    "Actor": "*Reim*",
    "Item": "Weapon Blade",
    "Cost": 180
  }
}
```

---

## Match Events - Progression

### EarnXP

Recorded when a player gains experience points from any source.

**Payload Fields**:
- `Team`: String - Team of the player
- `Actor`: String - Hero earning XP
- `Source`: String - Source of the XP (enemy killed, shared XP, etc.)
- `Amount`: Number - Amount of XP earned
- `Shared With`: Number - Number of teammates sharing the XP

**Example**:
```json
{
  "time": "2017-03-17T00:39:09+0000",
  "type": "EarnXP",
  "payload": {
    "Team": "Left",
    "Actor": "*Koshka*",
    "Source": "*JungleMinion_TreeEnt*",
    "Amount": 67,
    "Shared With": 1
  }
}
```

---

### LevelUp

Recorded when a player's hero gains a level.

**Payload Fields**:
- `Team`: String - Team of the player
- `Actor`: String - Hero leveling up
- `Level`: Number - New level reached
- `LifetimeGold`: Number - Total gold earned by the hero

**Example**:
```json
{
  "time": "2017-03-17T00:39:09+0000",
  "type": "LevelUp",
  "payload": {
    "Team": "Left",
    "Actor": "*Koshka*",
    "Level": 2,
    "LifetimeGold": 500
  }
}
```

---

## Match Events - Gold Sources

### GoldFromTowerKill

Recorded when a player earns gold from destroying a turret.

**Payload Fields**:
- `Team`: String - Team of the player
- `Actor`: String - Hero earning the gold
- `Amount`: Number - Gold amount earned

**Example**:
```json
{
  "time": "2017-03-31T03:05:21+0000",
  "type": "GoldFromTowerKill",
  "payload": {
    "Team": "Left",
    "Actor": "*Kestrel*",
    "Amount": 300
  }
}
```

---

### GoldFromGoldMine

Recorded when a player earns gold from their team capturing the gold miner.

**Payload Fields**:
- `Team`: String - Team of the player
- `Actor`: String - Hero earning the gold
- `Amount`: Number - Gold amount earned

**Example**:
```json
{
  "time": "2017-03-31T03:06:45+0000",
  "type": "GoldFromGoldMine",
  "payload": {
    "Team": "Right",
    "Actor": "*Lyra*",
    "Amount": 150
  }
}
```

---

### GoldFromKrakenKill

Recorded when a player earns gold from their team killing an enemy-released Kraken.

**Payload Fields**:
- `Team`: String - Team of the player
- `Actor`: String - Hero earning the gold
- `Amount`: Number - Gold amount earned (typically 500)

**Example**:
```json
{
  "time": "2017-03-31T03:07:43+0000",
  "type": "GoldFromKrakenKill",
  "payload": {
    "Team": "Right",
    "Actor": "*Kestrel*",
    "Amount": 500
  }
}
```

---

## Match Events - Spawning

### PlayerFirstSpawn

Recorded when a player spawns for the first time at the start of the match.

**Payload Fields**:
- `Team`: String - Team of the player
- `Actor`: String - Hero spawning

**Example**:
```json
{
  "time": "2017-03-17T00:38:32+0000",
  "type": "PlayerFirstSpawn",
  "payload": {
    "Team": "Right",
    "Actor": "*Alpha*"
  }
}
```

---

## Additional Event Types

Based on community implementations and GitHub issues, the following event types may also exist in telemetry data:

### Potential Event Types (Unconfirmed Schema)

- **Respawn**: When a player respawns after death
- **WentInvisible**: When a hero enters stealth/invisibility
- **WentVisible**: When a hero exits stealth/invisibility
- **BuyItemUndo**: When a player undoes an item purchase
- **ChangeHero**: Hero selection changes (possibly in brawl modes)
- **Vampirism**: Possible event for lifesteal/healing mechanics
- **WardPlaced**: Scout cam/vision ward placement
- **ChestOpen**: Opening chests in certain game modes

**Note**: These event types are inferred from API discussions and may not have complete documentation.

---

## Match Data Structure

### Participant Stats

Participant objects contain a `stats` attribute with the following fields:

**Core Stats**:
- `kills`: Number - Hero kills
- `deaths`: Number - Number of deaths
- `assists`: Number - Assist count
- `farm`: Number - Minions killed
- `minionKills`: Number - Minion kills
- `jungleKills`: Number - Jungle monster kills
- `crystalMineCaptures`: Number - Crystal miner captures
- `goldMineCaptures`: Number - Gold miner captures
- `krakenCaptures`: Number - Kraken captures
- `turretCaptures`: Number - Turrets destroyed

**Economy Stats**:
- `gold`: Number - Total gold earned during match
- `itemGrants`: Object - Items purchased and counts
  - Format: `{"Item Name": count, ...}`
  - Example: `{"Weapon Blade": 2, "Sorrowblade": 1, "Six Sins": 1}`
- `itemSells`: Object - Items sold
- `itemUses`: Number - Activated item uses

**Other Stats**:
- `level`: Number - Final hero level
- `skillTier`: String - Player's skill tier (e.g., "Rock Solid - Gold")
- `karmaLevel`: Number - Player's karma level
- `firstAfkTime`: Number - Time when player first went AFK
- `wentAfk`: Boolean - Whether player went AFK

**Note**: The server returns raw identifiers (e.g., `*1000_Item_HalcyonPotion`), while client libraries convert these to human-readable names (e.g., "Halcyon Potion").

### Roster Stats

Roster objects contain team-level statistics:

- `acesEarned`: Number - Number of aces (all enemy heroes dead)
- `gold`: Number - Total team gold
- `heroKills`: Number - Total team hero kills
- `krakenCaptures`: Number - Team Kraken captures
- `side`: String - "left" or "right"
- `turretKills`: Number - Turrets destroyed by team
- `turretsRemaining`: Number - Turrets remaining for team

### Match Stats

Match-level statistics:

- `endGameReason`: String - "victory", "surrender", "afk", etc.
- `queue`: String - Queue type (e.g., "5v5_pvp_ranked", "casual_aral")
- `duration`: Number - Match duration in seconds
- `gameMode`: String - Game mode identifier

---

## Data Format Notes

### Actor/Hero Naming

Heroes and entities are typically wrapped in asterisks in the raw API data:
- `*Kestrel*` - Hero name
- `*JungleMinion_TreeEnt*` - Jungle monster
- `*Turret*` - Structure

### Item Naming

Items follow a coded format in raw data:
- Server format: `*1000_Item_HalcyonPotion*`
- Client format: `Halcyon Potion`

### Ability Naming

Abilities use internal identifiers:
- Format: `HERO_ABILITY_[HERONAME]_[SLOT]_NAME`
- Example: `HERO_ABILITY_KESTREL_A_NAME`
- Slots: A (first ability), B (second ability), C (ultimate)

---

## References & Resources

### Primary Documentation
- [Vainglory API Telemetry Documentation](https://gamelocker.gitbooks.io/vainglory/content/en/telemetry.html) - Official telemetry reference
- [Vainglory Cheatsheet](https://devhints.io/vainglory) - Community quick reference

### GitHub Resources
- [vainglory-assets](https://github.com/SuperEvilMegacorp/vainglory-assets) - Official schemas and assets
- [BuyItem Position Issue #30](https://github.com/SuperEvilMegacorp/vainglory-assets/issues/30) - Position field discussion
- [Visibility Status Issue #46](https://github.com/SuperEvilMegacorp/vainglory-assets/issues/46) - WentVisible/WentInvisible events

### Community Implementations
- [vainglory npm package](https://www.npmjs.com/package/vainglory) - JavaScript API wrapper
- [gamelocker_api](https://github.com/cyberarm/gamelocker_api) - Ruby API client
- [VG-Telemetry-Timeline](https://github.com/dimxasnewfrozen/VG-Telemtry-Timeline) - Telemetry visualization

### API Status
- The official Vainglory API is **deprecated and no longer operational**
- Historical data may still be available through archived sources
- This documentation is maintained for reverse engineering purposes

---

## Application to VGR Reverse Engineering

This telemetry schema serves as a reference for mapping binary patterns in VGR replay files to known game events. Key mapping strategies:

1. **Event Type Detection**: Look for binary signatures that correlate with event frequencies
2. **Timestamp Correlation**: Match event timing patterns in VGR files
3. **Position Data**: Coordinate vectors may help identify movement/location events
4. **Actor/Target Pairs**: Combat events follow consistent actor→target patterns
5. **Gold/XP Transactions**: Economic events have predictable value ranges

### Cross-Reference Files

- `vg/core/event_pattern_detector.py` - Event pattern detection implementation
- `vg/analysis/deep_event_mapper.py` - Deep event mapping analysis
- `vg/core/vgr_parser.py` - VGR binary parsing
- `vg/docs/HERO_DETECTION_ANALYSIS.md` - Hero detection research

---

**Compiled by**: Librarian Agent (oh-my-claudecode:researcher)
**Date**: 2026-02-15
**Purpose**: VGR reverse engineering reference documentation
