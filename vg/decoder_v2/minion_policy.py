"""Optional conservative minion export policies for decoder_v2."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple

from vg.core.unified_decoder import _le_to_be
from vg.core.vgr_parser import VGRParser

from .credit_events import iter_credit_events


MINION_POLICY_NONE = "none"
MINION_POLICY_NONFINALS_BASELINE_0E = "nonfinals-baseline-0e"
MINION_POLICY_NONFINALS_OR_LOW_MIXED_RATIO_EXPERIMENTAL = "nonfinals-or-low-mixed-ratio-experimental"
MINION_POLICY_CHOICES = (
    MINION_POLICY_NONE,
    MINION_POLICY_NONFINALS_BASELINE_0E,
    MINION_POLICY_NONFINALS_OR_LOW_MIXED_RATIO_EXPERIMENTAL,
)
LOW_MIXED_RATIO_THRESHOLD = 0.13513513513513514
MIXED_02_VALUES = {20.0, -50.0}


@dataclass(frozen=True)
class MinionPolicyPlayerDecision:
    player_name: str
    accepted: bool
    baseline_0e: int
    mixed_total: int
    mixed_ratio: float
    reason: str

    def to_dict(self) -> Dict[str, object]:
        return {
            "player_name": self.player_name,
            "accepted": self.accepted,
            "baseline_0e": self.baseline_0e,
            "mixed_total": self.mixed_total,
            "mixed_ratio": self.mixed_ratio,
            "reason": self.reason,
        }


def _is_finals_series(replay_file: str) -> bool:
    return "Law Enforcers (Finals)" in str(Path(replay_file).parent.parent)


def collect_player_minion_policy_context(replay_file: str) -> Dict[str, Dict[str, float]]:
    """Collect per-player baseline and mixed-subfamily counts for policy evaluation."""
    parsed = VGRParser(replay_file, auto_truth=False).parse()
    player_map = {
        _le_to_be(player["entity_id"]): player["name"]
        for team in ("left", "right")
        for player in parsed["teams"][team]
        if player.get("entity_id")
    }
    rows = {
        name: {"baseline_0e": 0, "mixed_total": 0, "mixed_ratio": 0.0}
        for name in player_map.values()
    }
    for event in iter_credit_events(replay_file):
        name = player_map.get(event.entity_id_be)
        if not name:
            continue
        if event.action == 0x0E and event.value is not None and abs(event.value - 1.0) < 0.01:
            rows[name]["baseline_0e"] += 1
        if event.action == 0x02 and event.value is not None and round(event.value, 2) in MIXED_02_VALUES:
            rows[name]["mixed_total"] += 1

    for row in rows.values():
        baseline = row["baseline_0e"]
        row["mixed_ratio"] = (row["mixed_total"] / baseline) if baseline else 0.0
    return rows


def evaluate_minion_policy(
    policy: str,
    replay_file: str,
    completeness_status: str,
) -> Tuple[bool, str]:
    """Return whether optional minion export is allowed for a replay."""
    if policy == MINION_POLICY_NONE:
        return False, "Minion export policy disabled."

    if completeness_status != "complete_confirmed":
        return False, "Minion export withheld because replay completeness is not confirmed."

    if policy == MINION_POLICY_NONFINALS_BASELINE_0E:
        if _is_finals_series(replay_file):
            return False, "Minion export withheld for Finals-series replays under this policy."
        return True, "Minion export accepted using baseline 0x0E counts for non-Finals replays."

    if policy == MINION_POLICY_NONFINALS_OR_LOW_MIXED_RATIO_EXPERIMENTAL:
        if _is_finals_series(replay_file):
            return False, "Use player-level decisions for Finals-series replays under this experimental policy."
        return True, "Minion export accepted using baseline 0x0E counts for non-Finals replays."

    return False, f"Unknown minion policy: {policy}"


def evaluate_player_minion_policy(
    policy: str,
    replay_file: str,
    completeness_status: str,
) -> Dict[str, MinionPolicyPlayerDecision]:
    """Evaluate optional per-player minion export decisions."""
    if policy == MINION_POLICY_NONE:
        return {}

    context = collect_player_minion_policy_context(replay_file)
    finals = _is_finals_series(replay_file)
    decisions: Dict[str, MinionPolicyPlayerDecision] = {}

    for player_name, row in context.items():
        baseline = int(row["baseline_0e"])
        mixed_total = int(row["mixed_total"])
        mixed_ratio = float(row["mixed_ratio"])

        if policy == MINION_POLICY_NONE:
            decisions[player_name] = MinionPolicyPlayerDecision(
                player_name=player_name,
                accepted=False,
                baseline_0e=baseline,
                mixed_total=mixed_total,
                mixed_ratio=mixed_ratio,
                reason="Minion export policy disabled.",
            )
        elif completeness_status != "complete_confirmed":
            decisions[player_name] = MinionPolicyPlayerDecision(
                player_name=player_name,
                accepted=False,
                baseline_0e=baseline,
                mixed_total=mixed_total,
                mixed_ratio=mixed_ratio,
                reason="Minion export withheld because replay completeness is not confirmed.",
            )
        elif policy == MINION_POLICY_NONFINALS_BASELINE_0E:
            accepted = not finals
            decisions[player_name] = MinionPolicyPlayerDecision(
                player_name=player_name,
                accepted=accepted,
                baseline_0e=baseline,
                mixed_total=mixed_total,
                mixed_ratio=mixed_ratio,
                reason="Accepted for non-Finals replay." if accepted else "Withheld for Finals-series replay.",
            )
        elif policy == MINION_POLICY_NONFINALS_OR_LOW_MIXED_RATIO_EXPERIMENTAL:
            accepted = (not finals) or (mixed_ratio <= LOW_MIXED_RATIO_THRESHOLD)
            reason = (
                "Accepted for non-Finals replay."
                if not finals
                else f"Accepted under experimental low-mixed-ratio gate (<= {LOW_MIXED_RATIO_THRESHOLD:.6f})."
                if accepted
                else f"Withheld because mixed_ratio exceeds experimental gate (> {LOW_MIXED_RATIO_THRESHOLD:.6f})."
            )
            decisions[player_name] = MinionPolicyPlayerDecision(
                player_name=player_name,
                accepted=accepted,
                baseline_0e=baseline,
                mixed_total=mixed_total,
                mixed_ratio=mixed_ratio,
                reason=reason,
            )
        else:
            decisions[player_name] = MinionPolicyPlayerDecision(
                player_name=player_name,
                accepted=False,
                baseline_0e=baseline,
                mixed_total=mixed_total,
                mixed_ratio=mixed_ratio,
                reason=f"Unknown minion policy: {policy}",
            )

    return decisions
