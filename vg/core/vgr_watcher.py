#!/usr/bin/env python3
"""
VGR Auto Watcher - Automatically backup Vainglory replays when detected
Monitors the Temp folder and saves new replays to a backup directory.
"""

import os
import sys
import time
import shutil
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional, Set
import argparse


class VGRWatcher:
    """Watches for new Vainglory replays and backs them up automatically"""
    
    def __init__(self, backup_dir: str, temp_path: Optional[str] = None):
        """
        Initialize the watcher.
        
        Args:
            backup_dir: Directory to save backups
            temp_path: Path to Temp directory (default: system TEMP)
        """
        self.temp_path = Path(temp_path) if temp_path else Path(os.environ.get('TEMP', os.environ.get('TMP', 'C:\\Temp')))
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        
        self.known_replays: Set[str] = set()
        self.last_backup_hash: Optional[str] = None
        
    def _get_current_replay(self) -> Optional[str]:
        """Get the name of the current replay in Temp"""
        for vgr_file in self.temp_path.glob('*.0.vgr'):
            return vgr_file.stem.rsplit('.', 1)[0]
        return None
    
    def _get_replay_hash(self, replay_name: str) -> str:
        """Get hash of replay content to detect changes"""
        first_frame = self.temp_path / f"{replay_name}.0.vgr"
        if first_frame.exists():
            return hashlib.md5(first_frame.read_bytes()[:1024]).hexdigest()
        return ""
    
    def _count_frames(self, replay_name: str) -> int:
        """Count frames for a replay"""
        return len(list(self.temp_path.glob(f"{replay_name}.*.vgr")))
    
    def backup_replay(self, replay_name: str) -> Optional[Path]:
        """
        Backup a replay to the backup directory.
        
        Args:
            replay_name: Name of the replay to backup
            
        Returns:
            Path to backup directory or None if failed
        """
        frame_count = self._count_frames(replay_name)
        if frame_count == 0:
            return None
        
        # Create dated subfolder
        date_str = datetime.now().strftime('%y.%m.%d')
        backup_subdir = self.backup_dir / date_str / "cache"
        backup_subdir.mkdir(parents=True, exist_ok=True)
        
        # Check if already backed up
        existing = backup_subdir / f"{replay_name}.0.vgr"
        if existing.exists():
            print(f"  ⏭ Already backed up: {replay_name[:40]}...")
            return backup_subdir
        
        # Copy all frames
        copied = 0
        for vgr_file in self.temp_path.glob(f"{replay_name}.*.vgr"):
            shutil.copy2(vgr_file, backup_subdir / vgr_file.name)
            copied += 1
        
        # Copy manifest
        manifest = self.temp_path / f"replayManifest-{replay_name.split('-')[0]}.txt"
        if manifest.exists():
            shutil.copy2(manifest, backup_subdir / manifest.name)
        
        print(f"  ✓ Backed up: {replay_name[:40]}... ({copied} frames)")
        return backup_subdir
    
    def scan_once(self) -> bool:
        """
        Scan for new replays once.
        
        Returns:
            True if a new replay was found and backed up
        """
        replay_name = self._get_current_replay()
        if not replay_name:
            return False
        
        # Check if this is a new/changed replay
        replay_hash = self._get_replay_hash(replay_name)
        if replay_hash == self.last_backup_hash:
            return False
        
        # New replay detected!
        self.backup_replay(replay_name)
        self.last_backup_hash = replay_hash
        return True
    
    def watch(self, interval: int = 5):
        """
        Continuously watch for new replays.
        
        Args:
            interval: Seconds between checks
        """
        print(f"🔍 VGR Auto Watcher 시작")
        print(f"   감시 폴더: {self.temp_path}")
        print(f"   백업 폴더: {self.backup_dir}")
        print(f"   체크 간격: {interval}초")
        print(f"   종료: Ctrl+C")
        print()
        
        try:
            while True:
                replay_name = self._get_current_replay()
                if replay_name:
                    replay_hash = self._get_replay_hash(replay_name)
                    frame_count = self._count_frames(replay_name)
                    
                    if replay_hash != self.last_backup_hash and frame_count > 10:
                        # Wait a bit to ensure replay is fully written
                        time.sleep(2)
                        new_frame_count = self._count_frames(replay_name)
                        
                        if new_frame_count == frame_count:  # Stable
                            print(f"\n🎮 새 리플레이 감지! ({frame_count} frames)")
                            self.backup_replay(replay_name)
                            self.last_backup_hash = replay_hash
                
                time.sleep(interval)
                
        except KeyboardInterrupt:
            print("\n\n👋 Watcher 종료")


def main():
    parser = argparse.ArgumentParser(
        description='VGR Auto Watcher - Automatically backup Vainglory replays'
    )
    parser.add_argument(
        'backup_dir',
        nargs='?',
        default='./vgr_backups',
        help='Directory to save backups (default: ./vgr_backups)'
    )
    parser.add_argument(
        '-t', '--temp',
        help='Override temp directory path'
    )
    parser.add_argument(
        '-i', '--interval',
        type=int,
        default=5,
        help='Check interval in seconds (default: 5)'
    )
    parser.add_argument(
        '--once',
        action='store_true',
        help='Scan once and exit (no continuous watching)'
    )
    
    args = parser.parse_args()
    
    watcher = VGRWatcher(args.backup_dir, args.temp)
    
    if args.once:
        if watcher.scan_once():
            print("백업 완료!")
        else:
            print("새로운 리플레이가 없습니다.")
    else:
        watcher.watch(args.interval)


if __name__ == '__main__':
    main()
