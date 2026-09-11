"""
Rebalancing state management for automated liquidity optimization.
Tracks optimization history and determines when rebalancing is needed.
"""

import json
import hashlib
import numpy as np
from datetime import datetime
from typing import Tuple, Dict, Any, Optional, List


def compute_target_hash(target: np.ndarray) -> str:
    """
    Compute a stable hash of a target vector for change detection.

    Args:
        target: Normalized target vector

    Returns:
        SHA256 hash string prefixed with "sha256:"
    """
    # Round to 6 decimal places for stability
    rounded = np.round(target, decimals=6)
    # Convert to bytes in a consistent way
    data = rounded.tobytes()
    hash_value = hashlib.sha256(data).hexdigest()[:16]  # First 16 chars is enough
    return f"sha256:{hash_value}"


def load_rebalance_state(state_file: str) -> Dict[str, Any]:
    """
    Load rebalancing state from a JSON file.

    Args:
        state_file: Path to state file

    Returns:
        State dictionary, or empty state if file doesn't exist
    """
    try:
        with open(state_file, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return create_empty_state()
    except json.JSONDecodeError:
        # Corrupted state file, start fresh
        return create_empty_state()


def create_empty_state() -> Dict[str, Any]:
    """Create a new empty state dictionary."""
    return {
        "version": "1.0",
        "last_run": None,
        "last_target_hash": None,
        "last_r_squared": None,
        "current_strategies": [],
        "history": []
    }


def save_rebalance_state(state_file: str, state: Dict[str, Any]) -> None:
    """
    Save rebalancing state to a JSON file.

    Args:
        state_file: Path to state file
        state: State dictionary to save
    """
    with open(state_file, 'w') as f:
        json.dump(state, f, indent=2)


def should_rebalance(
    current_r2: float,
    last_r2: Optional[float],
    threshold: float,
    target_changed: bool,
    force: bool = False
) -> Tuple[bool, str]:
    """
    Determine if rebalancing is needed based on metrics.

    Args:
        current_r2: R-squared of current optimization against new target
        last_r2: R-squared from previous run (None if first run)
        threshold: Minimum R-squared improvement to trigger rebalance
        target_changed: Whether the target distribution has changed
        force: Force rebalance regardless of metrics

    Returns:
        Tuple of (should_rebalance, reason)
    """
    if force:
        return True, "forced"

    if last_r2 is None:
        return True, "initial_run"

    if target_changed:
        return True, "target_changed"

    # Check if R-squared has degraded significantly
    r2_diff = last_r2 - current_r2
    if r2_diff >= threshold:
        return True, f"r_squared_degraded (diff={r2_diff:.4f})"

    return False, f"no_change_needed (diff={r2_diff:.4f})"


def update_state(
    state: Dict[str, Any],
    target_hash: str,
    r_squared: float,
    strategies: List[Dict[str, Any]],
    action: str,
    reason: str
) -> Dict[str, Any]:
    """
    Update state with new optimization results.

    Args:
        state: Current state dictionary
        target_hash: Hash of the target vector
        r_squared: R-squared metric from optimization
        strategies: List of selected strategies
        action: Action taken ("rebalanced" or "skipped")
        reason: Reason for the action

    Returns:
        Updated state dictionary
    """
    now = datetime.now().isoformat()

    state["last_run"] = now
    state["last_target_hash"] = target_hash
    state["last_r_squared"] = r_squared
    state["current_strategies"] = strategies

    # Append to history (keep last 100 entries)
    history_entry = {
        "timestamp": now,
        "r_squared": r_squared,
        "action": action,
        "reason": reason,
        "strategy_count": len(strategies)
    }
    state["history"].append(history_entry)
    state["history"] = state["history"][-100:]  # Keep only last 100

    return state


def format_json_output(
    status: str,
    reason: str,
    current_r2: float,
    new_r2: Optional[float] = None,
    plan_file: Optional[str] = None,
    strategies: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Format output for JSON mode (automation-friendly).

    Args:
        status: Status string ("rebalanced", "skipped", "error")
        reason: Reason for the status
        current_r2: Current R-squared value
        new_r2: New R-squared after optimization (if rebalanced)
        plan_file: Path to output plan file (if written)
        strategies: Selected strategies (if rebalanced)

    Returns:
        JSON-serializable dictionary
    """
    output = {
        "status": status,
        "reason": reason,
        "current_r_squared": current_r2,
        "timestamp": datetime.now().isoformat()
    }

    if new_r2 is not None:
        output["new_r_squared"] = new_r2
        if current_r2 is not None:
            output["improvement"] = new_r2 - current_r2

    if plan_file is not None:
        output["plan_file"] = plan_file

    if strategies is not None:
        output["strategy_count"] = len(strategies)

    return output
