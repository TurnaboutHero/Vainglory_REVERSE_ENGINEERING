#!/usr/bin/env python3
"""
VGR Database Builder - Build hero/item database for Vainglory
"""

import sqlite3
import json
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime
from vgr_parser import VGRParser

# All heroes from VaingloryFire wiki
HEROES_DATA = [
    # name, role, attack_type
    ("Adagio", "Captain", "Ranged"),
    ("Alpha", "Warrior", "Melee"),
    ("Amael", "Mage", "Ranged"),
    ("Anka", "Assassin", "Melee"),
    ("Ardan", "Captain", "Melee"),
    ("Baptiste", "Mage", "Ranged"),
    ("Baron", "Sniper", "Ranged"),
    ("Blackfeather", "Assassin", "Melee"),
    ("Caine", "Sniper", "Ranged"),
    ("Catherine", "Captain", "Melee"),
    ("Celeste", "Mage", "Ranged"),
    ("Churnwalker", "Captain", "Melee"),
    ("Flicker", "Captain", "Melee"),
    ("Fortress", "Captain", "Melee"),
    ("Glaive", "Warrior", "Melee"),
    ("Grace", "Captain", "Melee"),
    ("Grumpjaw", "Warrior", "Melee"),
    ("Gwen", "Sniper", "Ranged"),
    ("Idris", "Assassin", "Melee"),
    ("Inara", "Warrior", "Melee"),
    ("Ishtar", "Sniper", "Ranged"),
    ("Joule", "Warrior", "Melee"),
    ("Karas", "Assassin", "Melee"),
    ("Kensei", "Warrior", "Melee"),
    ("Kestrel", "Sniper", "Ranged"),
    ("Kinetic", "Sniper", "Ranged"),
    ("Koshka", "Assassin", "Melee"),
    ("Krul", "Warrior", "Melee"),
    ("Lance", "Captain", "Melee"),
    ("Leo", "Warrior", "Melee"),
    ("Lorelai", "Captain", "Ranged"),
    ("Lyra", "Captain", "Ranged"),
    ("Magnus", "Mage", "Ranged"),
    ("Malene", "Mage", "Ranged"),
    ("Miho", "Assassin", "Melee"),
    ("Ozo", "Warrior", "Melee"),
    ("Petal", "Mage", "Ranged"),
    ("Phinn", "Captain", "Melee"),
    ("Reim", "Mage", "Melee"),
    ("Reza", "Assassin", "Melee"),
    ("Ringo", "Sniper", "Ranged"),
    ("Rona", "Warrior", "Melee"),
    ("Samuel", "Mage", "Ranged"),
    ("San Feng", "Warrior", "Melee"),
    ("SAW", "Sniper", "Ranged"),
    ("Shin", "Captain", "Melee"),
    ("Silvernail", "Sniper", "Ranged"),
    ("Skaarf", "Mage", "Ranged"),
    ("Skye", "Mage", "Ranged"),
    ("Taka", "Assassin", "Melee"),
    ("Tony", "Warrior", "Melee"),
    ("Varya", "Mage", "Ranged"),
    ("Viola", "Captain", "Ranged"),
    ("Vox", "Sniper", "Ranged"),
    ("Warhawk", "Sniper", "Ranged"),
    ("Yates", "Captain", "Melee"),
    ("Ylva", "Assassin", "Melee"),
]

# Korean names mapping (official translations from Namu Wiki)
KOREAN_NAMES = {
    "Adagio": "아다지오",
    "Alpha": "알파",
    "Amael": "아마엘",
    "Anka": "앙카",
    "Ardan": "아단",
    "Baptiste": "바티스트",
    "Baron": "바론",
    "Blackfeather": "흑깃",
    "Caine": "케인",
    "Catherine": "캐서린",
    "Celeste": "셀레스트",
    "Churnwalker": "어둠추적자",
    "Flicker": "플리커",
    "Fortress": "포트리스",
    "Glaive": "글레이브",
    "Grace": "그레이스",
    "Grumpjaw": "사슬니",
    "Gwen": "그웬",
    "Idris": "이드리스",
    "Inara": "이나라",
    "Ishtar": "이슈타르",
    "Joule": "쥴",
    "Karas": "카라스",
    "Kensei": "켄세이",
    "Kestrel": "케스트럴",
    "Kinetic": "키네틱",
    "Koshka": "코쉬카",
    "Krul": "크럴",
    "Lance": "랜스",
    "Leo": "레오",
    "Lorelai": "로렐라이",
    "Lyra": "라이라",
    "Magnus": "마그누스",
    "Malene": "말렌",
    "Miho": "미호",
    "Ozo": "오조",
    "Petal": "페탈",
    "Phinn": "핀",
    "Reim": "라임",
    "Reza": "레자",
    "Ringo": "링고",
    "Rona": "로나",
    "Samuel": "사무엘",
    "San Feng": "삼봉",
    "SAW": "쏘우",
    "Shin": "신",
    "Silvernail": "실버네일",
    "Skaarf": "스카프",
    "Skye": "스카이",
    "Taka": "타카",
    "Tony": "토니",
    "Varya": "바리야",
    "Viola": "비올라",
    "Vox": "복스",
    "Warhawk": "워호크",
    "Yates": "예이츠",
    "Ylva": "일바",
}

# Item categories
ITEMS_DATA = [
    # Weapon items
    ("Weapon Blade", "Weapon", "Basic", 1),
    ("Book of Eulogies", "Weapon", "Basic", 1),
    ("Swift Shooter", "Weapon", "Basic", 1),
    ("Minion's Foot", "Weapon", "Basic", 1),
    ("Heavy Steel", "Weapon", "Tier 2", 2),
    ("Six Sins", "Weapon", "Tier 2", 2),
    ("Blazing Salvo", "Weapon", "Tier 2", 2),
    ("Lucky Strike", "Weapon", "Tier 2", 2),
    ("Piercing Spear", "Weapon", "Tier 2", 2),
    ("Barbed Needle", "Weapon", "Tier 2", 2),
    ("Sorrowblade", "Weapon", "Tier 3", 3),
    ("Serpent Mask", "Weapon", "Tier 3", 3),
    ("Tornado Trigger", "Weapon", "Tier 3", 3),
    ("Tyrant's Monocle", "Weapon", "Tier 3", 3),
    ("Bonesaw", "Weapon", "Tier 3", 3),
    ("Poisoned Shiv", "Weapon", "Tier 3", 3),
    ("Breaking Point", "Weapon", "Tier 3", 3),
    ("Tension Bow", "Weapon", "Tier 3", 3),
    ("Spellsword", "Weapon", "Tier 3", 3),
    
    # Crystal items
    ("Crystal Bit", "Crystal", "Basic", 1),
    ("Energy Battery", "Crystal", "Basic", 1),
    ("Hourglass", "Crystal", "Basic", 1),
    ("Eclipse Prism", "Crystal", "Tier 2", 2),
    ("Heavy Prism", "Crystal", "Tier 2", 2),
    ("Piercing Shard", "Crystal", "Tier 2", 2),
    ("Chronograph", "Crystal", "Tier 2", 2),
    ("Void Battery", "Crystal", "Tier 2", 2),
    ("Shatterglass", "Crystal", "Tier 3", 3),
    ("Frostburn", "Crystal", "Tier 3", 3),
    ("Eve of Harvest", "Crystal", "Tier 3", 3),
    ("Broken Myth", "Crystal", "Tier 3", 3),
    ("Clockwork", "Crystal", "Tier 3", 3),
    ("Alternating Current", "Crystal", "Tier 3", 3),
    ("Dragon's Eye", "Crystal", "Tier 3", 3),
    ("Spellfire", "Crystal", "Tier 3", 3),
    
    # Defense items  
    ("Light Shield", "Defense", "Basic", 1),
    ("Light Armor", "Defense", "Basic", 1),
    ("Oakheart", "Defense", "Basic", 1),
    ("Kinetic Shield", "Defense", "Tier 2", 2),
    ("Coat of Plates", "Defense", "Tier 2", 2),
    ("Dragonheart", "Defense", "Tier 2", 2),
    ("Reflex Block", "Defense", "Tier 2", 2),
    ("Aegis", "Defense", "Tier 3", 3),
    ("Metal Jacket", "Defense", "Tier 3", 3),
    ("Fountain of Renewal", "Defense", "Tier 3", 3),
    ("Crucible", "Defense", "Tier 3", 3),
    ("Atlas Pauldron", "Defense", "Tier 3", 3),
    ("Slumbering Husk", "Defense", "Tier 3", 3),
    ("Pulseweave", "Defense", "Tier 3", 3),
    ("Capacitor Plate", "Defense", "Tier 3", 3),
    
    # Utility items
    ("Sprint Boots", "Utility", "Basic", 1),
    ("Travel Boots", "Utility", "Tier 2", 2),
    ("Journey Boots", "Utility", "Tier 3", 3),
    ("Halcyon Chargers", "Utility", "Tier 3", 3),
    ("War Treads", "Utility", "Tier 3", 3),
    ("Teleport Boots", "Utility", "Tier 3", 3),
    ("Flare", "Utility", "Consumable", 1),
    ("Scout Trap", "Utility", "Consumable", 1),
    ("Flare Gun", "Utility", "Tier 2", 2),
    ("Contraption", "Utility", "Tier 3", 3),
    ("Superscout 2000", "Utility", "Tier 3", 3),
    ("Nullwave Gauntlet", "Utility", "Tier 3", 3),
    ("Echo", "Utility", "Tier 3", 3),
    ("Stormcrown", "Utility", "Tier 3", 3),
    ("Aftershock", "Crystal", "Tier 3", 3),
]


class VGDatabase:
    """Vainglory SQLite database manager"""
    
    def __init__(self, db_path: str = "vainglory.db"):
        self.db_path = Path(db_path)
        self.conn: Optional[sqlite3.Connection] = None
        
    def connect(self):
        """Connect to database"""
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        
    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
            
    def create_tables(self):
        """Create database tables"""
        cursor = self.conn.cursor()
        
        # Heroes table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS heroes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                name_ko TEXT,
                role TEXT,
                attack_type TEXT,
                image_path TEXT,
                wiki_url TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Items table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                category TEXT,
                tier_name TEXT,
                tier INTEGER,
                image_path TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Skins table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS skins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hero_id INTEGER,
                name TEXT NOT NULL,
                rarity TEXT,
                image_path TEXT,
                FOREIGN KEY (hero_id) REFERENCES heroes(id)
            )
        ''')
        
        # Matches table (for replay data)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                replay_name TEXT UNIQUE,
                game_mode TEXT,
                frame_count INTEGER,
                duration INTEGER, -- Match duration in seconds
                winning_team INTEGER, -- 1: Left (Blue), 2: Right (Red)
                match_date TIMESTAMP,
                file_path TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Match players table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS match_players (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                match_id INTEGER,
                player_name TEXT,
                player_uuid TEXT,
                team INTEGER,
                hero_id INTEGER,
                kills INTEGER DEFAULT 0,
                deaths INTEGER DEFAULT 0,
                assists INTEGER DEFAULT 0,
                minion_kills INTEGER DEFAULT 0,
                gold INTEGER DEFAULT 0,
                items TEXT, -- JSON array of item names
                FOREIGN KEY (match_id) REFERENCES matches(id),
                FOREIGN KEY (hero_id) REFERENCES heroes(id)
            )
        ''')
        
        self.conn.commit()
        
    def populate_heroes(self):
        """Insert hero data"""
        cursor = self.conn.cursor()
        
        for name, role, attack_type in HEROES_DATA:
            name_ko = KOREAN_NAMES.get(name, "")
            wiki_url = f"https://www.vaingloryfire.com/vainglory/wiki/heroes/{name.lower().replace(' ', '-')}"
            
            cursor.execute('''
                INSERT OR REPLACE INTO heroes (name, name_ko, role, attack_type, wiki_url)
                VALUES (?, ?, ?, ?, ?)
            ''', (name, name_ko, role, attack_type, wiki_url))
        
        self.conn.commit()
        return len(HEROES_DATA)
        
    def populate_items(self):
        """Insert item data"""
        cursor = self.conn.cursor()
        
        for name, category, tier_name, tier in ITEMS_DATA:
            cursor.execute('''
                INSERT OR REPLACE INTO items (name, category, tier_name, tier)
                VALUES (?, ?, ?, ?)
            ''', (name, category, tier_name, tier))
        
        self.conn.commit()
        return len(ITEMS_DATA)
    
    def get_heroes(self) -> List[Dict]:
        """Get all heroes"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM heroes ORDER BY name')
        return [dict(row) for row in cursor.fetchall()]
    
    def get_items(self) -> List[Dict]:
        """Get all items"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM items ORDER BY category, tier, name')
        return [dict(row) for row in cursor.fetchall()]
    
    def search_hero(self, query: str) -> List[Dict]:
        """Search heroes by name"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM heroes 
            WHERE name LIKE ? OR name_ko LIKE ?
            ORDER BY name
        ''', (f'%{query}%', f'%{query}%'))
        return [dict(row) for row in cursor.fetchall()]
    
    def export_json(self, output_path: str):
        """Export database to JSON"""
        data = {
            'heroes': self.get_heroes(),
            'items': self.get_items(),
        }
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return output_path

    def import_replay(self, file_path: str):
        """Parse and import a replay file into the database"""
        try:
            parser = VGRParser(file_path)
            data = parser.parse()
            
            cursor = self.conn.cursor()
            
            # Insert Match
            match_info = data['match_info']
            cursor.execute('''
                INSERT OR IGNORE INTO matches 
                (replay_name, game_mode, frame_count, duration, winning_team, match_date, file_path)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                data['replay_name'],
                match_info['mode'],
                match_info['total_frames'],
                match_info.get('duration', 0),
                match_info.get('winning_team', 0),
                data.get('parsed_at'), # Should use actual match date if available
                file_path
            ))
            
            match_id = cursor.lastrowid
            if not match_id:
                # Already exists (or ignored)
                # Ideally we want to get the ID if it exists? 
                # For now assume if IGNORE triggered, we skip players
                # But lastrowid might be None if ignored.
                # Check replay existence.
                check = cursor.execute("SELECT id FROM matches WHERE replay_name=?", (data['replay_name'],)).fetchone()
                if check:
                    print(f"  Skipping existing replay: {data['replay_name']}")
                    return False
                return False # Should not happen if insert succeeded
                
            # Insert Players
            all_players = data['teams']['left'] + data['teams']['right']
            for p in all_players:
                team_value = p.get('team_id')
                if team_value is None:
                    team_label = p.get('team')
                    if team_label == 'left':
                        team_value = 1
                    elif team_label == 'right':
                        team_value = 2
                    else:
                        team_value = 0

                # Find Hero ID if not set (fallback)
                hero_id = p.get('hero_id')
                if not hero_id and p.get('hero_name') != 'Unknown':
                    # Look up by name
                    h_res = cursor.execute("SELECT id FROM heroes WHERE name=?", (p['hero_name'],)).fetchone()
                    if h_res:
                        hero_id = h_res[0]
                
                cursor.execute('''
                    INSERT INTO match_players 
                    (match_id, player_name, player_uuid, team, hero_id, kills, deaths, assists, minion_kills, gold, items)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    match_id,
                    p['name'],
                    p['uuid'],
                    team_value,
                    hero_id,
                    p.get('kills', 0),
                    p.get('deaths', 0),
                    p.get('assists', 0),
                    p.get('minion_kills', 0),
                    p.get('gold', 0),
                    json.dumps(p.get('items', []))
                ))
            
            self.conn.commit()
            return True
            
        except Exception as e:
            print(f"Error importing {file_path}: {e}")
            import traceback
            traceback.print_exc()
            return False


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='VGR Database Builder')
    parser.add_argument('command', choices=['init', 'heroes', 'items', 'search', 'export', 'import'],
                        help='Command to run')
    parser.add_argument('-q', '--query', help='Search query')
    parser.add_argument('-i', '--input', help='Input directory or file for import')
    parser.add_argument('-o', '--output', default='vg_data.json', help='Output file for export')
    parser.add_argument('--db', default='vainglory.db', help='Database file path')
    
    args = parser.parse_args()
    
    db = VGDatabase(args.db)
    db.connect()
    
    if args.command == 'init':
        db.create_tables()
        hero_count = db.populate_heroes()
        item_count = db.populate_items()
        print(f"✓ 데이터베이스 초기화 완료!")
        print(f"  - 영웅: {hero_count}개")
        print(f"  - 아이템: {item_count}개")
        print(f"  - 저장 위치: {db.db_path}")
        
    elif args.command == 'heroes':
        heroes = db.get_heroes()
        for h in heroes:
            print(f"{h['name']:15} ({h['name_ko']}) - {h['role']}")
            
    elif args.command == 'items':
        items = db.get_items()
        current_category = None
        for item in items:
            if item['category'] != current_category:
                current_category = item['category']
                print(f"\n=== {current_category} ===")
            print(f"  [{item['tier']}] {item['name']}")
            
    elif args.command == 'search':
        if not args.query:
            print("검색어를 입력하세요: -q <검색어>")
        else:
            results = db.search_hero(args.query)
            if results:
                for h in results:
                    print(f"{h['name']} ({h['name_ko']}) - {h['role']}, {h['attack_type']}")
            else:
                print("결과 없음")
                
    elif args.command == 'export':
        output = db.export_json(args.output)
        print(f"✓ JSON 내보내기 완료: {output}")
        
    elif args.command == 'import':
        if not args.input:
            print("입력 경로를 지정하세요: --input <경로>")
        else:
            path = Path(args.input)
            files = []
            if path.is_file():
                files = [path]
            elif path.is_dir():
                # Find .vgr files (first segment only to avoid duplicates if split)
                # Use rglob for recursive search
                files = list(path.rglob('*.0.vgr'))
                if not files: # Maybe not numbered?
                    files = list(path.rglob('*.vgr'))
            
            print(f"Found {len(files)} replays to import...")
            success_count = 0
            for f in files:
                print(f"Importing {f.name}...")
                if db.import_replay(str(f)):
                    success_count += 1
            
            print(f"✓ 가져오기 완료: {success_count}/{len(files)} 성공")
    
    db.close()


if __name__ == '__main__':
    main()
