#!/usr/bin/env python3
"""
VGR Replay Loader - Load saved Vainglory replays into the game
Replaces the current practice match replay with a saved replay.
"""

import os
import sys
import shutil
import json
import argparse
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Tuple


class VGRLoader:
    """Loads saved .vgr replay files into Vainglory game"""
    
    # Default paths
    DEFAULT_TEMP_PATH = Path(os.environ.get('TEMP', os.environ.get('TMP', 'C:\\Temp')))
    
    def __init__(self, temp_path: Optional[str] = None):
        """
        Initialize the loader.
        
        Args:
            temp_path: Path to Temp directory where Vainglory stores replays.
                      Defaults to system TEMP.
        """
        self.temp_path = Path(temp_path) if temp_path else self.DEFAULT_TEMP_PATH
        
    def find_active_replay(self) -> Optional[Tuple[str, Path]]:
        """
        Find the currently active replay in the Temp directory.
        
        Returns:
            Tuple of (replay_name, first_frame_path) or None if not found
        """
        # Look for .0.vgr files in temp
        for vgr_file in self.temp_path.glob('*.0.vgr'):
            replay_name = vgr_file.stem.rsplit('.', 1)[0]
            return (replay_name, vgr_file)
        return None
    
    def count_frames(self, directory: Path, replay_name: str) -> int:
        """Count the number of frames for a replay"""
        return len(list(directory.glob(f"{replay_name}.*.vgr")))
    
    def backup_active_replay(self, backup_dir: Optional[str] = None) -> Optional[Path]:
        """
        Backup the currently active replay.
        
        Args:
            backup_dir: Directory to store backup. Defaults to temp_path/vgr_backups
            
        Returns:
            Path to backup directory or None if no active replay
        """
        active = self.find_active_replay()
        if not active:
            return None
            
        replay_name, first_frame = active
        backup_path = Path(backup_dir) if backup_dir else self.temp_path / 'vgr_backups' / datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path.mkdir(parents=True, exist_ok=True)
        
        # Copy all frames
        for vgr_file in self.temp_path.glob(f"{replay_name}.*.vgr"):
            shutil.copy2(vgr_file, backup_path / vgr_file.name)
        
        # Copy manifest if exists
        manifest = self.temp_path / f"replayManifest-{replay_name.split('-')[0]}.txt"
        if manifest.exists():
            shutil.copy2(manifest, backup_path / manifest.name)
            
        return backup_path
    
    def load_replay(self, source_dir: str, source_name: Optional[str] = None) -> dict:
        """
        Load a saved replay into the game's temp directory.
        
        IMPORTANT: You must first start a Solo Practice match and surrender,
        then stay on the results screen before running this.
        
        Args:
            source_dir: Directory containing the saved replay files
            source_name: Name of the replay to load. If None, uses most recent.
            
        Returns:
            Dictionary with load results
        """
        source_path = Path(source_dir)
        
        # Find the active replay to overwrite
        active = self.find_active_replay()
        if not active:
            return {
                'success': False,
                'error': 'No active replay found in temp directory. Please start a Solo Practice match and surrender first.',
                'temp_path': str(self.temp_path)
            }
        
        target_name, _ = active
        
        # Find source replay
        if source_name:
            source_first_frame = source_path / f"{source_name}.0.vgr"
            if not source_first_frame.exists():
                # Search in subdirectories
                for frame in source_path.rglob(f"{source_name}.0.vgr"):
                    source_first_frame = frame
                    source_path = frame.parent
                    break
        else:
            # Find most recent
            source_first_frame = None
            for frame in source_path.rglob('*.0.vgr'):
                if source_first_frame is None or frame.stat().st_mtime > source_first_frame.stat().st_mtime:
                    source_first_frame = frame
            if source_first_frame:
                source_path = source_first_frame.parent
                source_name = source_first_frame.stem.rsplit('.', 1)[0]
        
        if not source_first_frame or not source_first_frame.exists():
            return {
                'success': False,
                'error': f'Source replay not found in {source_dir}'
            }
        
        # Count frames
        source_frame_count = self.count_frames(source_path, source_name)
        target_frame_count = self.count_frames(self.temp_path, target_name)
        
        # Delete old frames
        for vgr_file in self.temp_path.glob(f"{target_name}.*.vgr"):
            vgr_file.unlink()
        
        # Copy new frames with target name
        copied = 0
        for i in range(source_frame_count):
            src = source_path / f"{source_name}.{i}.vgr"
            dst = self.temp_path / f"{target_name}.{i}.vgr"
            if src.exists():
                shutil.copy2(src, dst)
                copied += 1
        
        return {
            'success': True,
            'source_replay': source_name,
            'source_dir': str(source_path),
            'source_frames': source_frame_count,
            'target_replay': target_name,
            'target_dir': str(self.temp_path),
            'frames_copied': copied,
            'message': 'Replay loaded! Click "Watch Replay" in the game now.'
        }
    
    def list_saved_replays(self, search_dir: str) -> List[dict]:
        """
        List all saved replays in a directory.
        
        Args:
            search_dir: Directory to search
            
        Returns:
            List of replay info dictionaries
        """
        replays = []
        search_path = Path(search_dir)
        
        seen = set()
        for vgr_file in search_path.rglob('*.0.vgr'):
            replay_name = vgr_file.stem.rsplit('.', 1)[0]
            if replay_name in seen:
                continue
            seen.add(replay_name)
            
            frame_count = self.count_frames(vgr_file.parent, replay_name)
            file_stat = vgr_file.stat()
            
            replays.append({
                'name': replay_name,
                'path': str(vgr_file.parent),
                'frames': frame_count,
                'size_mb': round(sum(f.stat().st_size for f in vgr_file.parent.glob(f"{replay_name}.*.vgr")) / 1024 / 1024, 2),
                'modified': datetime.fromtimestamp(file_stat.st_mtime).isoformat()
            })
        
        return sorted(replays, key=lambda x: x['modified'], reverse=True)


def main():
    parser = argparse.ArgumentParser(
        description='VGR Replay Loader - Load saved Vainglory replays into the game'
    )
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # List command
    list_parser = subparsers.add_parser('list', help='List saved replays')
    list_parser.add_argument('directory', help='Directory to search for replays')
    
    # Load command
    load_parser = subparsers.add_parser('load', help='Load a replay into the game')
    load_parser.add_argument('source', help='Source directory containing replay files')
    load_parser.add_argument('-n', '--name', help='Specific replay name to load')
    load_parser.add_argument('-t', '--temp', help='Override temp directory path')
    
    # Status command
    status_parser = subparsers.add_parser('status', help='Check current replay status')
    status_parser.add_argument('-t', '--temp', help='Override temp directory path')
    
    args = parser.parse_args()
    
    if args.command == 'list':
        loader = VGRLoader()
        replays = loader.list_saved_replays(args.directory)
        print(json.dumps(replays, indent=2, ensure_ascii=False))
        
    elif args.command == 'load':
        loader = VGRLoader(args.temp)
        result = loader.load_replay(args.source, args.name)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        
    elif args.command == 'status':
        loader = VGRLoader(args.temp)
        active = loader.find_active_replay()
        if active:
            name, path = active
            frames = loader.count_frames(path.parent, name)
            print(json.dumps({
                'active_replay': name,
                'path': str(path.parent),
                'frames': frames
            }, indent=2))
        else:
            print(json.dumps({
                'active_replay': None,
                'message': 'No active replay. Start a practice match and surrender first.'
            }, indent=2))
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
