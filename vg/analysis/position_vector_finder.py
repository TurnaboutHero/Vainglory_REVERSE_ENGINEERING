"""
Position Vector Finder for Vainglory Replay Binary Data

Scans replay frame files for IEEE 754 float32 position vectors.
Looks for valid coordinate triplets [x, z, y] that match map boundaries.
"""

import struct
import json
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from collections import defaultdict


# Map coordinate boundaries
MAP_BOUNDS = {
    'x': (-100, 100),
    'y': (-100, 100),
    'z': (-10, 10)
}

# Known player entity IDs
PLAYER_ENTITY_IDS = [56325, 56581, 56837, 57093, 57349, 57605]

# Event structure: [EntityID 2B LE][00 00][ActionCode 1B][Payload ~32B]
EVENT_HEADER_SIZE = 5  # 2 bytes entity ID + 2 bytes padding + 1 byte action code


class PositionVector:
    """Represents a potential position vector found in binary data."""

    def __init__(self, offset: int, x: float, z: float, y: float, confidence: str = "unknown"):
        self.offset = offset
        self.x = x
        self.z = z
        self.y = y
        self.confidence = confidence

    def to_dict(self) -> Dict:
        return {
            'offset': self.offset,
            'x': round(self.x, 3),
            'z': round(self.z, 3),
            'y': round(self.y, 3),
            'confidence': self.confidence,
            'distance_from_origin': round((self.x**2 + self.y**2 + self.z**2)**0.5, 3)
        }

    def is_valid_3d(self) -> bool:
        """Check if coordinates fall within expected map bounds."""
        return (MAP_BOUNDS['x'][0] <= self.x <= MAP_BOUNDS['x'][1] and
                MAP_BOUNDS['y'][0] <= self.y <= MAP_BOUNDS['y'][1] and
                MAP_BOUNDS['z'][0] <= self.z <= MAP_BOUNDS['z'][1])

    def is_valid_2d(self) -> bool:
        """Check if x,y coordinates are valid (ignoring z)."""
        return (MAP_BOUNDS['x'][0] <= self.x <= MAP_BOUNDS['x'][1] and
                MAP_BOUNDS['y'][0] <= self.y <= MAP_BOUNDS['y'][1])


class PositionVectorFinder:
    """Finds and analyzes position vectors in Vainglory replay binary data."""

    def __init__(self, replay_cache_dir: str):
        self.replay_cache_dir = Path(replay_cache_dir)
        self.results = {
            'frames_analyzed': [],
            'position_vectors': [],
            'player_entity_positions': [],
            'statistics': {},
            'clusters': []
        }

    def read_frame_file(self, frame_number: int) -> Optional[bytes]:
        """Read a specific frame file from the replay cache."""
        # Find files matching the frame number pattern
        pattern = f"*.{frame_number}.vgr"
        matches = list(self.replay_cache_dir.glob(pattern))

        if not matches:
            print(f"[LIMITATION] Frame {frame_number} not found")
            return None

        frame_file = matches[0]
        with open(frame_file, 'rb') as f:
            data = f.read()

        print(f"[DATA] Frame {frame_number}: {len(data)} bytes from {frame_file.name}")
        return data

    def scan_for_float32_triplets(self, data: bytes, frame_number: int) -> List[PositionVector]:
        """Scan binary data for valid float32 position triplets."""
        positions = []

        # Scan every 4-byte aligned offset
        for offset in range(0, len(data) - 11, 4):  # Need 12 bytes for 3 floats
            try:
                # Read 3 consecutive float32 values
                x = struct.unpack('<f', data[offset:offset+4])[0]
                z = struct.unpack('<f', data[offset+4:offset+8])[0]
                y = struct.unpack('<f', data[offset+8:offset+12])[0]

                # Check for NaN or Inf
                if not all(abs(v) < 1e6 for v in [x, z, y]):
                    continue

                pos = PositionVector(offset, x, z, y)

                # Validate as 3D position
                if pos.is_valid_3d():
                    pos.confidence = "3d_valid"
                    positions.append(pos)
                # Check for 2D position (z might not be position data)
                elif pos.is_valid_2d() and abs(z) < 1.0:
                    pos.confidence = "2d_valid_z_small"
                    positions.append(pos)

            except struct.error:
                continue

        print(f"[FINDING] Frame {frame_number}: Found {len(positions)} potential position vectors")
        return positions

    def find_player_entity_positions(self, data: bytes, frame_number: int) -> List[Dict]:
        """Find positions near known player entity IDs."""
        player_positions = []

        # Scan for player entity IDs
        for i in range(len(data) - 37):  # Need at least 37 bytes for event
            # Read 2-byte little-endian entity ID
            entity_id = struct.unpack('<H', data[i:i+2])[0]

            if entity_id in PLAYER_ENTITY_IDS:
                # Check for padding bytes (00 00)
                if data[i+2:i+4] == b'\x00\x00':
                    action_code = data[i+4]

                    # Scan the 32-byte payload for float32 triplets
                    payload_start = i + EVENT_HEADER_SIZE
                    payload_end = min(payload_start + 32, len(data) - 11)

                    for offset in range(payload_start, payload_end, 4):
                        try:
                            x = struct.unpack('<f', data[offset:offset+4])[0]
                            z = struct.unpack('<f', data[offset+4:offset+8])[0]
                            y = struct.unpack('<f', data[offset+8:offset+12])[0]

                            if not all(abs(v) < 1e6 for v in [x, z, y]):
                                continue

                            pos = PositionVector(offset, x, z, y)

                            if pos.is_valid_3d() or pos.is_valid_2d():
                                player_positions.append({
                                    'frame': frame_number,
                                    'entity_id': entity_id,
                                    'action_code': action_code,
                                    'event_offset': i,
                                    'position_offset': offset,
                                    'position': pos.to_dict(),
                                    'bytes_before_position': (data[i:offset]).hex()[:40]
                                })

                        except struct.error:
                            continue

        print(f"[FINDING] Frame {frame_number}: Found {len(player_positions)} player entity positions")
        return player_positions

    def analyze_position_context(self, data: bytes, offset: int, context_bytes: int = 16) -> Dict:
        """Analyze bytes surrounding a position vector."""
        start = max(0, offset - context_bytes)
        end = min(len(data), offset + 12 + context_bytes)

        context = {
            'before_hex': data[start:offset].hex(),
            'position_hex': data[offset:offset+12].hex(),
            'after_hex': data[offset+12:end].hex()
        }

        # Check for entity ID patterns before position
        if offset >= 5:
            possible_entity_id = struct.unpack('<H', data[offset-5:offset-3])[0]
            if possible_entity_id in PLAYER_ENTITY_IDS:
                context['possible_entity_id'] = possible_entity_id

        return context

    def cluster_positions(self, positions: List[PositionVector], max_distance: float = 5.0) -> List[List[PositionVector]]:
        """Simple clustering of nearby positions."""
        if not positions:
            return []

        clusters = []
        used = set()

        for i, pos1 in enumerate(positions):
            if i in used:
                continue

            cluster = [pos1]
            used.add(i)

            for j, pos2 in enumerate(positions[i+1:], start=i+1):
                if j in used:
                    continue

                # Calculate distance
                dist = ((pos1.x - pos2.x)**2 + (pos1.y - pos2.y)**2 + (pos1.z - pos2.z)**2)**0.5

                if dist <= max_distance:
                    cluster.append(pos2)
                    used.add(j)

            clusters.append(cluster)

        return clusters

    def analyze_frame(self, frame_number: int) -> bool:
        """Analyze a single frame file."""
        data = self.read_frame_file(frame_number)
        if not data:
            return False

        # Scan for all position vectors
        positions = self.scan_for_float32_triplets(data, frame_number)

        # Find player entity positions specifically
        player_positions = self.find_player_entity_positions(data, frame_number)

        # Analyze context for first 10 positions
        positions_with_context = []
        for pos in positions[:10]:
            context = self.analyze_position_context(data, pos.offset)
            pos_dict = pos.to_dict()
            pos_dict['context'] = context
            pos_dict['frame'] = frame_number
            positions_with_context.append(pos_dict)

        # Cluster analysis
        clusters = self.cluster_positions(positions)
        cluster_summary = []
        for idx, cluster in enumerate(clusters[:5]):  # Top 5 clusters
            if len(cluster) > 1:
                avg_x = sum(p.x for p in cluster) / len(cluster)
                avg_y = sum(p.y for p in cluster) / len(cluster)
                avg_z = sum(p.z for p in cluster) / len(cluster)
                cluster_summary.append({
                    'cluster_id': idx,
                    'size': len(cluster),
                    'center': {'x': round(avg_x, 2), 'y': round(avg_y, 2), 'z': round(avg_z, 2)}
                })

        # Store results
        self.results['frames_analyzed'].append(frame_number)
        self.results['position_vectors'].extend(positions_with_context)
        self.results['player_entity_positions'].extend(player_positions)

        if cluster_summary:
            self.results['clusters'].append({
                'frame': frame_number,
                'clusters': cluster_summary
            })

        print(f"[STAT:frame_{frame_number}_positions] {len(positions)}")
        print(f"[STAT:frame_{frame_number}_player_positions] {len(player_positions)}")
        print(f"[STAT:frame_{frame_number}_clusters] {len([c for c in clusters if len(c) > 1])}")

        return True

    def compute_statistics(self):
        """Compute aggregate statistics across all analyzed frames."""
        all_positions = self.results['position_vectors']

        if not all_positions:
            return

        x_coords = [p['x'] for p in all_positions]
        y_coords = [p['y'] for p in all_positions]
        z_coords = [p['z'] for p in all_positions]

        self.results['statistics'] = {
            'total_positions_found': len(all_positions),
            'total_player_positions': len(self.results['player_entity_positions']),
            'x_range': [round(min(x_coords), 2), round(max(x_coords), 2)],
            'y_range': [round(min(y_coords), 2), round(max(y_coords), 2)],
            'z_range': [round(min(z_coords), 2), round(max(z_coords), 2)],
            'x_mean': round(sum(x_coords) / len(x_coords), 2),
            'y_mean': round(sum(y_coords) / len(y_coords), 2),
            'z_mean': round(sum(z_coords) / len(z_coords), 2)
        }

        print(f"\n[FINDING] Aggregate Statistics:")
        print(f"[STAT:total_positions] {self.results['statistics']['total_positions_found']}")
        print(f"[STAT:total_player_positions] {self.results['statistics']['total_player_positions']}")
        print(f"[STAT:x_range] {self.results['statistics']['x_range']}")
        print(f"[STAT:y_range] {self.results['statistics']['y_range']}")
        print(f"[STAT:z_range] {self.results['statistics']['z_range']}")

    def save_results(self, output_path: str):
        """Save analysis results to JSON."""
        self.compute_statistics()

        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, 'w') as f:
            json.dump(self.results, f, indent=2)

        print(f"\n[FINDING] Results saved to {output_file}")
        print(f"[STAT:output_size] {output_file.stat().st_size} bytes")


def main():
    """Main analysis workflow."""
    print("[OBJECTIVE] Locate IEEE 754 float32 position vectors in Vainglory replay binary data")

    replay_cache_dir = "D:/Desktop/My Folder/Game/VG/vg replay/21.11.04/cache/"
    output_path = "D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/position_vector_analysis.json"

    finder = PositionVectorFinder(replay_cache_dir)

    # Analyze frames 10, 50, 90 for cross-validation
    frames_to_analyze = [10, 50, 90]

    for frame_num in frames_to_analyze:
        print(f"\n{'='*60}")
        print(f"Analyzing Frame {frame_num}")
        print(f"{'='*60}")
        finder.analyze_frame(frame_num)

    # Save results
    finder.save_results(output_path)

    print("\n[LIMITATION] Analysis limited to float32 triplets at 4-byte alignment")
    print("[LIMITATION] Cannot distinguish between position vectors and other float data without additional context")
    print("[LIMITATION] Player entity detection assumes event structure [EntityID 2B LE][00 00][ActionCode 1B]")


if __name__ == "__main__":
    main()
