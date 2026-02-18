#!/usr/bin/env python3
"""Cross-validate unknown headers across multiple matches."""
import struct
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from vg.core.unified_decoder import _le_to_be
from vg.core.vgr_parser import VGRParser

HEADERS = {
    '10_04_43': bytes([0x10, 0x04, 0x43]),
    '10_04_28': bytes([0x10, 0x04, 0x28]),
    '10_04_45': bytes([0x10, 0x04, 0x45]),
}

ROLE_MAP = {
    'Lyra': 'SUP', 'Lorelai': 'SUP', 'Lance': 'SUP', 'Phinn': 'SUP',
    'Ardan': 'SUP', 'Grace': 'SUP', 'Yates': 'SUP', 'Catherine': 'SUP',
    'Caine': 'CAR', 'Kestrel': 'CAR', 'Kinetic': 'CAR', 'Baron': 'CAR',
    'Gwen': 'CAR', 'Skaarf': 'CAR', 'Vox': 'CAR', 'Ringo': 'CAR',
    'Grumpjaw': 'TOP', 'Tony': 'TOP', 'Inara': 'TOP', 'Warhawk': 'TOP',
    'Samuel': 'MID', 'Skye': 'MID', 'Ishtar': 'MID', 'Reza': 'MID',
    'Magnus': 'MID', 'Blackfeather': 'MID', 'Celeste': 'MID', 'Petal': 'MID',
    'Karas': 'JNG',
}

REPLAYS = [
    ('Finals1 5v5', r'D:\Desktop\My Folder\Game\VG\vg replay\Tournament_Replays\SFC vs Law Enforcers (Finals)\1'),
    ('Finals3 5v5', r'D:\Desktop\My Folder\Game\VG\vg replay\Tournament_Replays\SFC vs Law Enforcers (Finals)\3'),
    ('Semi1 5v5', r'D:\Desktop\My Folder\Game\VG\vg replay\Tournament_Replays\SFC vs Team Stooopid (Semi)\1'),
    ('HF 3v3', r'D:\Desktop\My Folder\Game\VG\vg replay\21.11.04\cache'),
    ('Casual 5v5', r'D:\Desktop\My Folder\Game\VG\vg replay\22.05.16\cache'),
]


def load_data(replay_dir):
    rdir = Path(replay_dir)
    vgr_files = list(rdir.glob('*.0.vgr'))
    if not vgr_files:
        return None, None, None
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
        return None, None, None
    return data, parsed, replay


def scan_header(data, hdr, valid_eids):
    per_player = defaultdict(int)
    total = 0
    pos = 0
    while True:
        idx = data.find(hdr, pos)
        if idx == -1:
            break
        pos = idx + 1
        if idx + 13 > len(data):
            continue
        if data[idx + 3:idx + 5] != b'\x00\x00':
            continue
        eid = struct.unpack_from('>H', data, idx + 5)[0]
        total += 1
        if eid in valid_eids:
            per_player[eid] += 1
    return total, dict(per_player)


def main():
    for match_label, replay_dir in REPLAYS:
        data, parsed, replay = load_data(replay_dir)
        if data is None:
            print(f'\n[SKIP] {match_label}: not found')
            continue

        players = parsed['teams'].get('left', []) + parsed['teams'].get('right', [])
        eid_map = {}
        for pl in players:
            eid_be = _le_to_be(pl['entity_id'])
            eid_map[eid_be] = (pl['name'], pl.get('hero_name', '?'))
        valid_eids = set(eid_map.keys())

        mode = parsed.get('match_info', {}).get('mode', '?')
        print(f'\n{"=" * 80}')
        print(f'{match_label} | {mode} | {len(players)} players | {len(data) / 1024 / 1024:.1f}MB')
        print(f'{"=" * 80}')

        for hname, hdr in HEADERS.items():
            total, per_player = scan_header(data, hdr, valid_eids)
            player_total = sum(per_player.values())
            print(f'  [{hname}] total={total:5d}, player={player_total:5d}')
            for eid, cnt in sorted(per_player.items(), key=lambda x: -x[1]):
                name, hero = eid_map.get(eid, ('?', '?'))
                role = ROLE_MAP.get(hero, '???')
                print(f'    {name:20s} {hero:15s} [{role:3s}] {cnt:5d}')


if __name__ == '__main__':
    main()
