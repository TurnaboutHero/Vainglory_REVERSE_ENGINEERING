#!/usr/bin/env python3
"""
Header-Hero Correlation - Correlate unknown headers with hero ability characteristics.

Tags each hero with: projectile, summon, melee, ranged, targeted, skillshot, CC
Then correlates with [10 04 43], [10 04 28], [10 04 45] event counts.
"""
import struct
import sys
from collections import defaultdict, Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from vg.core.unified_decoder import _le_to_be
from vg.core.vgr_parser import VGRParser

# Hero characteristics based on VG game knowledge
# Tags: proj=projectile abilities, summon=pet/spawned entities, melee=melee basic,
#       ranged=ranged basic, rapid=rapid fire, splash=AoE basic, bounce=ricochet,
#       cc=crowd control, dash=mobility, trap=placed trap, area=area denial
HERO_TRAITS = {
    # Carries (ranged basic attackers)
    'Caine':    {'ranged', 'proj', 'bounce', 'rapid'},
    'Kestrel':  {'ranged', 'proj', 'rapid', 'trap'},
    'Kinetic':  {'ranged', 'proj', 'rapid'},
    'Baron':    {'ranged', 'proj', 'splash', 'summon'},  # rockets = splash + spawned mortar zones
    'Gwen':    {'ranged', 'proj', 'rapid'},
    'Vox':      {'ranged', 'proj', 'bounce'},
    'Ringo':    {'ranged', 'proj'},
    'Skaarf':   {'ranged', 'proj', 'area'},
    # Mages / Mid (ranged ability-focused)
    'Samuel':   {'ranged', 'proj', 'area'},
    'Skye':     {'ranged', 'proj', 'rapid'},  # Forward Barrage = extremely rapid missiles
    'Celeste':  {'ranged', 'proj', 'area'},
    'Ishtar':   {'ranged', 'proj'},  # stance switching
    'Magnus':   {'ranged', 'proj', 'cc'},
    'Malene':   {'ranged', 'proj'},  # light/dark forms
    'Petal':    {'ranged', 'summon'},  # munions are summoned pets
    # Melee fighters / assassins
    'Blackfeather': {'melee', 'dash'},
    'Reza':     {'melee', 'dash', 'proj'},  # has ranged ult projectile
    'Karas':    {'melee', 'dash'},
    'Ozo':      {'melee', 'dash', 'cc'},
    'Warhawk':  {'melee', 'dash', 'cc'},
    'San Feng': {'melee', 'cc', 'proj'},
    'Leo':      {'melee', 'dash'},
    # Tanks / Top (melee tanky)
    'Grumpjaw': {'melee', 'cc'},  # basic atk passive stacks, Stuffed = targeted cc
    'Tony':     {'melee', 'cc'},
    'Inara':    {'melee', 'cc', 'area'},
    'Phinn':    {'melee', 'cc', 'proj'},  # Forced Accord = hook projectile (rare)
    'Reim':     {'melee', 'cc', 'area'},
    # Supports
    'Lyra':     {'ranged', 'area', 'summon'},  # sigils, portal = spawned entities
    'Lorelai':  {'ranged', 'area', 'summon', 'cc'},  # pools = spawned
    'Lance':    {'melee', 'cc', 'proj'},  # Gythian Wall = skillshot
    'Ardan':    {'melee', 'cc', 'dash', 'proj'},  # Vanguard, Gauntlet
    'Grace':    {'melee', 'cc'},
    'Yates':    {'melee', 'cc'},  # chain grab = targeted, no projectile
    'Catherine': {'melee', 'cc'},
    # Other
    'Baptiste': {'ranged', 'cc', 'area'},
    'Ylva':     {'melee', 'trap'},  # stealth + traps
    'Flicker':  {'melee', 'cc'},
}

HEADERS = {
    '10_04_43': bytes([0x10, 0x04, 0x43]),
    '10_04_28': bytes([0x10, 0x04, 0x28]),
    '10_04_45': bytes([0x10, 0x04, 0x45]),
    '10_04_2B': bytes([0x10, 0x04, 0x2B]),
    '18_04_8A': bytes([0x18, 0x04, 0x8A]),
}

REPLAYS = [
    ('Finals1', r'D:\Desktop\My Folder\Game\VG\vg replay\Tournament_Replays\SFC vs Law Enforcers (Finals)\1'),
    ('Finals2', r'D:\Desktop\My Folder\Game\VG\vg replay\Tournament_Replays\SFC vs Law Enforcers (Finals)\2'),
    ('Finals3', r'D:\Desktop\My Folder\Game\VG\vg replay\Tournament_Replays\SFC vs Law Enforcers (Finals)\3'),
    ('Finals4', r'D:\Desktop\My Folder\Game\VG\vg replay\Tournament_Replays\SFC vs Law Enforcers (Finals)\4'),
    ('Semi1', r'D:\Desktop\My Folder\Game\VG\vg replay\Tournament_Replays\SFC vs Team Stooopid (Semi)\1'),
    ('Semi2', r'D:\Desktop\My Folder\Game\VG\vg replay\Tournament_Replays\SFC vs Team Stooopid (Semi)\2'),
    ('Maitun1', r'D:\Desktop\My Folder\Game\VG\vg replay\Tournament_Replays\SFC vs Maitun Gaming\1'),
    ('Maitun2', r'D:\Desktop\My Folder\Game\VG\vg replay\Tournament_Replays\SFC vs Maitun Gaming\2'),
    ('HF3v3', r'D:\Desktop\My Folder\Game\VG\vg replay\21.11.04\cache'),
    ('Buffalo1', r'D:\Desktop\My Folder\Game\VG\vg replay\Tournament_Replays\Buffalo vs RRONE\1'),
    ('Buffalo2', r'D:\Desktop\My Folder\Game\VG\vg replay\Tournament_Replays\Buffalo vs RRONE\2'),
]


def load_data(replay_dir):
    rdir = Path(replay_dir)
    vgr_files = list(rdir.glob('*.0.vgr'))
    if not vgr_files:
        return None, None
    replay = vgr_files[0]
    frame_dir = replay.parent
    stem = replay.stem.rsplit('.', 1)[0]
    frames = []
    for f in sorted(frame_dir.glob(f'{stem}.*.vgr'), key=lambda p: int(p.stem.split('.')[-1])):
        idx = int(f.stem.split('.')[-1])
        if idx > 0:
            frames.append(f.read_bytes())
    data = b''.join(frames)
    try:
        p = VGRParser(str(replay), detect_heroes=False, auto_truth=False)
        parsed = p.parse()
    except Exception:
        return None, None
    return data, parsed


def scan_headers(data, valid_eids):
    results = {}
    for hname, hdr in HEADERS.items():
        per_player = defaultdict(int)
        pos = 0
        while True:
            idx = data.find(hdr, pos)
            if idx == -1:
                break
            pos = idx + 1
            if idx + 7 > len(data):
                continue
            if data[idx + 3:idx + 5] != b'\x00\x00':
                continue
            eid = struct.unpack_from('>H', data, idx + 5)[0]
            if eid in valid_eids:
                per_player[eid] += 1
        results[hname] = dict(per_player)
    return results


def main():
    # Collect all (hero, header_counts) across all matches
    all_rows = []  # (match, hero, traits, {header: count}, duration)

    for match_label, replay_dir in REPLAYS:
        data, parsed = load_data(replay_dir)
        if data is None:
            continue

        players = parsed['teams'].get('left', []) + parsed['teams'].get('right', [])
        eid_map = {}
        for pl in players:
            eid_be = _le_to_be(pl['entity_id'])
            eid_map[eid_be] = (pl['name'], pl.get('hero_name', '?'))
        valid_eids = set(eid_map.keys())

        duration = parsed.get('match_info', {}).get('duration', 0)
        header_results = scan_headers(data, valid_eids)

        for eid in valid_eids:
            name, hero = eid_map[eid]
            traits = HERO_TRAITS.get(hero, set())
            counts = {}
            for hname in HEADERS:
                counts[hname] = header_results[hname].get(eid, 0)
            all_rows.append((match_label, hero, traits, counts))

    # Aggregate by hero
    hero_agg = defaultdict(lambda: defaultdict(list))
    for match, hero, traits, counts in all_rows:
        for hname, cnt in counts.items():
            hero_agg[hero][hname].append(cnt)

    # Print correlation table
    print(f'{"Hero":15s} {"Traits":35s}', end='')
    for h in HEADERS:
        label = h.replace('_', '')
        print(f' {label:>10s}', end='')
    print(f' {"N":>3s}')
    print('-' * 120)

    rows_for_sort = []
    for hero in sorted(hero_agg):
        traits = HERO_TRAITS.get(hero, set())
        trait_str = ','.join(sorted(traits)) if traits else '???'
        avgs = {}
        n = 0
        for hname in HEADERS:
            vals = hero_agg[hero][hname]
            avgs[hname] = sum(vals) / len(vals) if vals else 0
            n = len(vals)
        rows_for_sort.append((hero, trait_str, avgs, n))

    # Sort by 10_04_43 desc
    rows_for_sort.sort(key=lambda r: -r[2].get('10_04_43', 0))

    for hero, trait_str, avgs, n in rows_for_sort:
        print(f'{hero:15s} {trait_str:35s}', end='')
        for h in HEADERS:
            print(f' {avgs[h]:10.0f}', end='')
        print(f' {n:3d}')

    # Trait correlation analysis
    print(f'\n{"="*80}')
    print('TRAIT CORRELATION ANALYSIS')
    print(f'{"="*80}')

    for hname in ['10_04_43', '10_04_28', '10_04_45']:
        print(f'\n--- {hname} ---')
        trait_totals = defaultdict(list)
        for hero, trait_str, avgs, n in rows_for_sort:
            traits = HERO_TRAITS.get(hero, set())
            val = avgs[hname]
            for t in traits:
                trait_totals[t].append(val)
            if not traits:
                trait_totals['???'].append(val)

        for trait in sorted(trait_totals, key=lambda t: -sum(trait_totals[t]) / len(trait_totals[t])):
            vals = trait_totals[trait]
            avg = sum(vals) / len(vals)
            print(f'  {trait:12s}: avg={avg:7.0f}  n={len(vals):2d}  range=[{min(vals):.0f}-{max(vals):.0f}]')


if __name__ == '__main__':
    main()
