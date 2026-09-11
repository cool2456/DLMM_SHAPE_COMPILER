import numpy as np
from scipy.optimize import nnls
import matplotlib.pyplot as plt
import sys
import json
import argparse
from datetime import datetime
import time
from typing import Tuple, Dict, Any, Optional


from input_handlers import (
    load_target_from_json,
    load_target_from_csv,
    fetch_target_from_api,
    normalize_target_vector,
    parse_api_headers,
    InputValidationError,
    APIFetchError
)
from rebalancer import (
    compute_target_hash,
    load_rebalance_state,
    save_rebalance_state,
    should_rebalance,
    update_state,
    format_json_output
)

def rectangle(center, width, B):
    left = int(np.round(center - (width - 1) / 2))
    vec = np.zeros(B)
    left_clamped = max(0, left)
    right_clamped = min(B, left + width)
    if left_clamped < right_clamped:
        vec[left_clamped:right_clamped] = 1.0
    return vec

def curve(center, width, B):
    vec = np.zeros(B)
    maxd = width / 2.0

    for i in range(B):
        d = abs(i - center)
        v = max(0, (maxd - d) / (maxd + 1e-12))
        vec[i] = v
    return vec

def bid_ask(center, width, B):
    vec = np.zeros(B)
    maxd = width / 2.0

    for i in range(B):
        if i < (center - maxd) or i > (center + maxd):
            v = 0
        else:
            d = abs(i - center)
            v = max(0, 1 - (maxd - d) / (maxd + 1e-12))
        vec[i] = v
    return vec

def one_hot(index: int, B: int) -> np.ndarray:
    vec = np.zeros(B, dtype=float)
    vec[index] = 1.0
    return vec

def w_template(
    B: int,
    v1: int,
    p: int,
    v2: int,
    peak: float = 1.0,
    valley: float = 0.35,
) -> np.ndarray:
    if not (0 < v1 < p < v2 < B - 1):
        return np.zeros(B, dtype=float)

    xs = np.array([0, v1, p, v2, B - 1], dtype=float)
    ys = np.array([peak, valley, peak, valley, peak], dtype=float)

    x_full = np.arange(B, dtype=float)
    vec = np.interp(x_full, xs, ys)
    vec = np.clip(vec, 0.0, None)

    s = float(np.sum(vec))
    if s <= 1e-12:
        return np.zeros(B, dtype=float)
    return vec / s

def dip_template(
    B: int,
    left: int,
    right: int,
    floor: float = 0.25,
    outside: float = 1.0,
) -> np.ndarray:
    if not (0 <= left < right < B):
        return np.zeros(B, dtype=float)

    vec = np.full(B, outside, dtype=float)
    vec[left:right + 1] = floor
    vec = np.clip(vec, 0.0, None)

    s = float(np.sum(vec))
    if s <= 1e-12:
        return np.zeros(B, dtype=float)
    return vec / s

def create_piecewise_target(
    B: int,
    knots: list[tuple[int, float]],
    smooth_window: int = 0
) -> np.ndarray:
    
    if B <= 1:
        raise ValueError("B must be >= 2")
    if len(knots) < 2:
        raise ValueError("Need at least 2 knots")

    xs = np.array([k[0] for k in knots], dtype=int)
    ys = np.array([k[1] for k in knots], dtype=float)

    if np.any(xs < 0) or np.any(xs >= B):
        raise ValueError(f"All knot x positions must be in [0, {B - 1}]")

    order = np.argsort(xs)
    xs = xs[order]
    ys = ys[order]

    x_full = np.arange(B, dtype=float)
    t = np.interp(x_full, xs.astype(float), ys.astype(float))
    t = np.clip(t, 0.0, None)

    if smooth_window and smooth_window >= 3:
        if smooth_window % 2 == 0:
            raise ValueError("smooth_window must be odd")
        kernel = np.ones(smooth_window, dtype=float) / smooth_window
        t = np.convolve(t, kernel, mode="same")
        t = np.clip(t, 0.0, None)

    s = float(np.sum(t))
    if s <= 1e-12:
        raise ValueError("Target is all zeros after processing; check knots/values")
    return t / s

def generate_templates(
    B: int,
    center_range=None,
    width_range=None,
    center_step=None,
    width_step=None,
    max_templates: int = 10000,
    include_one_hot: bool = True,
):
    if center_range is None:
        center_range = (0, B - 1)

    if width_range is None:
        min_width = max(3, B // 10)
        max_width = B
        width_range = (min_width, max_width)

    if center_step is None:
        center_step = max(1, B // 30)

    if width_step is None:
        width_range_size = width_range[1] - width_range[0]
        width_step = max(1, width_range_size // 15)

    templates: list[np.ndarray] = []
    params: list[dict] = []

    strategy_funcs = [rectangle, curve, bid_ask]

    centers = range(center_range[0], center_range[1] + 1, center_step)
    widths = range(width_range[0], width_range[1] + 1, width_step)

    for func in strategy_funcs:
        for center in centers:
            for width in widths:
                vec = func(center, width, B)
                vec_sum = float(np.sum(vec))
                if vec_sum < 1e-12:
                    continue
                vec = vec / vec_sum

                templates.append(vec)
                params.append({
                    "type": func.__name__,
                    "center": int(center),
                    "width": int(width),
                })

                if len(templates) >= max_templates:
                    print(f"Warning: Template count capped at {max_templates}")
                    return np.array(templates), params
                
    valley_steps = max(1, B // 20)
    for v1 in range(5, B - 25, valley_steps):
        for v2 in range(v1 + 10, B - 5, valley_steps):
            p = (v1 + v2) // 2

            vec = w_template(B, v1=v1, p=p, v2=v2, peak=1.0, valley=0.35)
            if float(np.sum(vec)) < 1e-12:
                continue

            templates.append(vec)
            params.append({
                "type": "w_template",
                "v1": int(v1),
                "p": int(p),
                "v2": int(v2),
                "valley": 0.35,
            })

            if len(templates) >= max_templates:
                print(f"Warning: Template count capped at {max_templates}")
                return np.array(templates), params
            
    dip_steps = max(1, B // 18)
    dip_widths = [max(3, B // 12), max(5, B // 8), max(7, B // 6)]
    for left in range(0, B - 3, dip_steps):
        for w in dip_widths:
            right = min(B - 1, left + w)
            if right <= left:
                continue

            vec = dip_template(B, left=left, right=right, floor=0.25, outside=1.0)
            if float(np.sum(vec)) < 1e-12:
                continue

            templates.append(vec)
            params.append({
                "type": "dip_template",
                "left": int(left),
                "right": int(right),
                "floor": 0.25,
            })

            if len(templates) >= max_templates:
                print(f"Warning: Template count capped at {max_templates}")
                return np.array(templates), params

    if include_one_hot:
        for i in range(B):
            vec = one_hot(i, B)
            templates.append(vec)
            params.append({
                "type": "one_hot",
                "center": int(i),
                "width": 1,
            })

            if len(templates) >= max_templates:
                print(f"Warning: Template count capped at {max_templates}")
                return np.array(templates), params

    return np.array(templates), params
def _compute_r_squared(target: np.ndarray, approximation: np.ndarray) -> float:
    ss_res = np.sum((target - approximation) ** 2)
    ss_tot = np.sum((target - np.mean(target)) ** 2) + 1e-12
    return 1 - ss_res / ss_tot

class DimensionMismatchError(Exception):
    pass

def _print_param(p: Dict[str, Any]) -> None:
    ptype = p.get("type", "unknown")
    if ptype in {"rectangle", "curve", "bid_ask", "one_hot"}:
        print(f"  {ptype:12s} center={p.get('center')} width={p.get('width')}")
    elif ptype == "w_template":
        print(f"  {ptype:12s} v1={p.get('v1')} p={p.get('p')} v2={p.get('v2')} valley={p.get('valley')}")
    elif ptype == "dip_template":
        print(f"  {ptype:12s} left={p.get('left')} right={p.get('right')} floor={p.get('floor')}")
    else:
        print(f"  {ptype:12s} params={p}")

def greedy_select_templates(
    target: np.ndarray,
    templates: np.ndarray,
    k: int,
    verbose: bool = True,
    min_improvement: float = 1e-6
) -> tuple:
    if templates.shape[1] != len(target):
        raise DimensionMismatchError(
            f"Dimension mismatch: templates have {templates.shape[1]} bins, "
            f"target has {len(target)} bins.\n"
            f"Regenerate templates with B={len(target)} to match target."
        )

    start_time = time.time()
    n_templates = len(templates)
    selected_idx: list[int] = []
    remaining_idx = set(range(n_templates))

    if verbose:
        print(f"\nGreedy forward selection for {k} templates from {n_templates} candidates...")

    current_r2 = 0.0
    nnls_count = 0

    for iteration in range(k):
        best_r2 = -np.inf
        best_idx = None

        for idx in remaining_idx:
            trial_idx = selected_idx + [idx]
            trial_templates = templates[trial_idx]

            weights, _ = nnls(trial_templates.T, target)
            nnls_count += 1

            approx = trial_templates.T @ weights

            approx_sum = float(np.sum(approx))
            t_sum = float(np.sum(target))
            if approx_sum > 1e-12:
                approx = approx * (t_sum / approx_sum)

            r2 = _compute_r_squared(target, approx)

            if r2 > best_r2:
                best_r2 = r2
                best_idx = idx

        improvement = best_r2 - current_r2
        if iteration > 0 and improvement < min_improvement:
            if verbose:
                print(
                    f"  Early stop at step {iteration + 1}: improvement {improvement:.6f} < threshold {min_improvement}")
            break

        selected_idx.append(best_idx)
        remaining_idx.remove(best_idx)
        current_r2 = best_r2

        if verbose:
            print(
                f"  Step {iteration + 1}: Added template {best_idx}, R² = {best_r2:.6f} (improvement: {improvement:.6f})")

    total_time = time.time() - start_time

    timing_info = {
        'total_time': total_time,
        'nnls_solves': nnls_count,
        'candidates_evaluated': n_templates,
        'strategies_selected': len(selected_idx)
    }

    if verbose and total_time > 0:
        print(
            f"\n  Performance: {nnls_count} NNLS solves in {total_time:.3f}s ({nnls_count / total_time:.0f} solves/sec)")

    return selected_idx, timing_info

# nnls approximation 
def approximate_nnls(target: np.ndarray, templates: np.ndarray, params: list = None, max_strategies=None):
    if templates.shape[1] != len(target):
        raise DimensionMismatchError(
            f"Dimension mismatch: templates have {templates.shape[1]} bins, "
            f"target has {len(target)} bins.\n"
            f"Regenerate templates with B={len(target)} to match target."
        )

    #nnls step 1: full solution
    weights, _ = nnls(templates.T, target)

    nonzero = np.where(weights > 1e-6)[0]
    print(f"Initial NNLS: {len(nonzero)} non-zero strategies")
    print(f"  Indices: {nonzero}")
    print(f"  Weights: {weights[nonzero]}")

    # solution from raw weigth rather than normalized weights
    full_approximation = templates.T @ weights

    full_sum = float(np.sum(full_approximation))
    t_sum = float(np.sum(target))
    if full_sum > 1e-12:
        full_approximation *= (t_sum / full_sum)

    full_r_squared = _compute_r_squared(target, full_approximation)

    truncated = False
    truncated_r_squared = None

    # use greedy
    if max_strategies is not None and len(nonzero) > max_strategies:
        truncated = True

        selected_idx, _timing_info = greedy_select_templates(
            target, templates, max_strategies,
            verbose=True
        )
        top_k_idx = np.array(selected_idx)

        print(f"\nGreedy selection chose indices: {top_k_idx}")
        if params is not None:
            for idx in top_k_idx:
                _print_param(params[idx])

        # solve nnls with selected tmepaltes to get final weights
        reduced_templates = templates[top_k_idx]
        reduced_weights, _ = nnls(reduced_templates.T, target)

        print(f"  Final weights: {reduced_weights}")

        # get fullw eight vector
        weights = np.zeros(len(templates))
        weights[top_k_idx] = reduced_weights
        nonzero = top_k_idx[reduced_weights > 1e-6]

    print(f"\nFinal: {len(nonzero)} strategies with non-zero weights")
    print(f"  Indices: {nonzero}")
    print(f"  Weights (raw): {weights[nonzero]}")

    # do it with raw weights
    approximation = templates.T @ weights

    # mass match thing
    approx_sum = float(np.sum(approximation))
    t_sum = float(np.sum(target))
    if approx_sum > 1e-12:
        approximation *= (t_sum / approx_sum)

    final_r_squared = _compute_r_squared(target, approximation)
    residual = np.linalg.norm(target - approximation)

    # i just included normalized weights for export please dont use this this is the reason why it was failing earlier.
    weight_sum = float(np.sum(weights))
    weights_normalized = weights / (weight_sum + 1e-12)

    print(f"  Weights (normalized for reporting): {weights_normalized[nonzero]}")

    if truncated:
        truncated_r_squared = final_r_squared
        r_squared_loss = full_r_squared - truncated_r_squared
        print(f"\nTruncation metrics:")
        print(f"  Full solution R²:      {full_r_squared:.6f}")
        print(f"  Truncated solution R²: {truncated_r_squared:.6f}")
        print(f"  R² loss from truncation: {r_squared_loss:.6f}")

    strategies = []
    if params is not None:
        strategies = [(params[i], float(weights_normalized[i])) for i in nonzero]

    result = {
        "weights": weights_normalized,
        "weights_raw": weights,
        "approximation": approximation,
        "residual": float(residual),
        "r_squared": float(final_r_squared),
        "strategies": strategies,
        "full_r_squared": float(full_r_squared),
        "truncated": truncated,
    }

    if truncated:
        result["truncated_r_squared"] = float(truncated_r_squared)
        result["r_squared_loss"] = float(full_r_squared - truncated_r_squared)

    return result


#targets 
def create_gaussian_target(B, center=None, sigma=10):
    if center is None:
        center = B // 2

    x = np.arange(B)
    target = np.exp(-0.5 * ((x - center) / sigma) ** 2)
    target = target / (target.sum() + 1e-12)
    return target

def create_chaos_target(
    B: int,
    seed: Optional[int] = None,
    n_spikes_range: tuple[int, int] = (3, 8),
    spike_sigma_range: tuple[float, float] = (0.8, 4.5),
    noise_scale: float = 0.15,
) -> np.ndarray:
    rng = np.random.default_rng(seed)

    x = np.arange(B, dtype=float)
    vec = np.zeros(B, dtype=float)
    n_spikes = int(rng.integers(n_spikes_range[0], n_spikes_range[1] + 1))

    for _ in range(n_spikes):
        center = float(rng.integers(0, B))
        sigma = float(rng.uniform(spike_sigma_range[0], spike_sigma_range[1]))
        amp = float(rng.uniform(0.4, 1.6))
        vec += amp * np.exp(-0.5 * ((x - center) / sigma) ** 2)
    noise = rng.random(B) * noise_scale
    vec += noise
    n_dips = int(rng.integers(1, 4))
    for _ in range(n_dips):
        left = int(rng.integers(0, max(1, B - 3)))
        width = int(rng.integers(max(2, B // 18), max(3, B // 6)))
        right = min(B - 1, left + width)
        depth = float(rng.uniform(0.15, 0.60))
        vec[left:right + 1] *= depth

    vec = np.clip(vec, 0.0, None)
    s = float(np.sum(vec))
    if s <= 1e-12:
        raise ValueError("Chaos target became all zeros; adjust params.")
    return vec / s


def create_target_distribution(
    target_type: str,
    B: int,
    center: int,
    sigma: float,
    width: int,
    seed: Optional[int] = None
) -> np.ndarray:
    if target_type == "gaussian":
        return create_gaussian_target(B, center=center, sigma=sigma)
    elif target_type == "uniform":
        target = rectangle(center, width, B)
        return target / (np.sum(target) + 1e-12)
    elif target_type == "curve":
        target = curve(center, width, B)
        return target / (np.sum(target) + 1e-12)
    elif target_type == "bid_ask":
        target = bid_ask(center, width, B)
        return target / (np.sum(target) + 1e-12)
    elif target_type == "wshape":
        knots = [
            (0, 0.0215),
            (18, 0.0080),
            (35, 0.0210),
            (52, 0.0075),
            (B - 1, 0.0215),
        ]
        return create_piecewise_target(B, knots, smooth_window=0)
    elif target_type == "chaos":
        return create_chaos_target(B, seed=seed)
    else:
        raise ValueError(f"Unknown target type: {target_type}")

def visualize_results(target: np.ndarray, result: dict, B: int):
    approximation = result['approximation']

    plt.figure(figsize=(12, 5))

    plt.subplot(1, 3, 1)
    plt.bar(range(B), target, alpha=0.7, color='blue', edgecolor='black', linewidth=0.5)
    plt.title('Target Position', fontsize=14, fontweight='bold')
    plt.xlabel('Bin')
    plt.ylabel('Liquidity')
    plt.grid(True, alpha=0.3)

    plt.subplot(1, 3, 2)
    plt.bar(range(B), approximation, alpha=0.7, color='green', edgecolor='black', linewidth=0.5)
    plt.title('NNLS Approximation', fontsize=14, fontweight='bold')
    plt.xlabel('Bin')
    plt.ylabel('Liquidity')
    plt.grid(True, alpha=0.3)

    plt.subplot(1, 3, 3)
    x = np.arange(B)
    plt.plot(x, target, 'b-', linewidth=2, label='Target', marker='o', markersize=3, alpha=0.7)
    plt.plot(x, approximation, 'g--', linewidth=2, label='Approximation', marker='s', markersize=3, alpha=0.7)
    plt.fill_between(x, target, approximation, alpha=0.2, color='red', label='Error')
    plt.title(f'Comparison (R²={result["r_squared"]:.3f})', fontsize=14, fontweight='bold')
    plt.xlabel('Bin')
    plt.ylabel('Liquidity')
    plt.legend()
    plt.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.show()

    # Strategy contributions
    plt.figure(figsize=(14, 6))

    plt.subplot(1, 2, 1)
    bottom = np.zeros(B)
    colors = plt.cm.tab10(np.linspace(0, 1, len(result['strategies'])))

    for i, (strat, weight) in enumerate(result['strategies'][:8]):
        if strat['type'] == 'rectangle':
            strategy_vec = rectangle(strat['center'], strat['width'], B)
            strategy_vec = strategy_vec / (np.sum(strategy_vec) + 1e-12)
        elif strat['type'] == 'curve':
            strategy_vec = curve(strat['center'], strat['width'], B)
            strategy_vec = strategy_vec / (np.sum(strategy_vec) + 1e-12)
        elif strat['type'] == 'bid_ask':
            strategy_vec = bid_ask(strat['center'], strat['width'], B)
            strategy_vec = strategy_vec / (np.sum(strategy_vec) + 1e-12)
        elif strat['type'] == 'w_template':
            strategy_vec = w_template(
                B,
                v1=int(strat['v1']),
                p=int(strat['p']),
                v2=int(strat['v2']),
                peak=1.0,
                valley=float(strat.get('valley', 0.35)),
            )
        elif strat['type'] == 'dip_template':
            strategy_vec = dip_template(
                B,
                left=int(strat['left']),
                right=int(strat['right']),
                floor=float(strat.get('floor', 0.25)),
                outside=1.0,
            )
        elif strat['type'] == 'one_hot':
            strategy_vec = one_hot(int(strat['center']), B)
        else:
            continue

        contribution = strategy_vec * float(weight)
        plt.bar(range(B), contribution, bottom=bottom, alpha=0.8,
                label=f"{strat.get('type', 'unk')}",
                color=colors[i % len(colors)])
        bottom += contribution

    plt.title('Strategy Contributions (Stacked)', fontsize=14, fontweight='bold')
    plt.xlabel('Bin')
    plt.ylabel('Liquidity')
    plt.legend(fontsize=8, loc='upper right')
    plt.grid(True, alpha=0.3)

    plt.subplot(1, 2, 2)
    error = target - approximation
    plt.bar(range(B), error, alpha=0.7, color='red', edgecolor='black', linewidth=0.5)
    plt.axhline(y=0, color='black', linestyle='-', linewidth=1)
    plt.title('Approximation Error', fontsize=14, fontweight='bold')
    plt.xlabel('Bin')
    plt.ylabel('Error (Target - Approximation)')
    plt.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.show()

def export_strategy_plan(result: dict, output_path: str, pool_config: dict = None) -> dict:
    plan = {
        "version": "1.0",
        "generated_at": datetime.now().isoformat(),
        "metrics": {
            "r_squared": float(result["r_squared"]),
            "residual": float(result["residual"]),
            "truncated": result.get("truncated", False),
            "full_r_squared": float(result.get("full_r_squared", result["r_squared"]))
        },
        "strategies": [
            dict(strat, weight=float(weight))
            for strat, weight in result["strategies"]
        ]
    }

    if pool_config:
        plan["pool_config"] = pool_config

    with open(output_path, 'w') as f:
        json.dump(plan, f, indent=2)

    print(f"\nStrategy plan exported to: {output_path}")
    return plan

def load_strategy_plan(input_path: str) -> dict:
    with open(input_path, 'r') as f:
        return json.load(f)
def parse_args():
    parser = argparse.ArgumentParser(
        description="DLMM Compiler - Optimize liquidity distributions for Meteora DLMM",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    input_group = parser.add_argument_group('External Input')
    input_group.add_argument("--input-json", type=str, metavar="FILE",
                             help="Path to JSON file with target distribution vector")
    input_group.add_argument("--input-csv", type=str, metavar="FILE",
                             help="Path to CSV file with target distribution")
    input_group.add_argument("--input-csv-column", type=str, default="liquidity",
                             help="Column name for liquidity values in CSV (default: liquidity)")
    input_group.add_argument("--input-api", type=str, metavar="URL",
                             help="API endpoint URL to fetch target distribution")
    input_group.add_argument("--api-header", action="append", dest="api_headers",
                             metavar="HEADER",
                             help="HTTP header for API request (format: 'Key: Value'). Can be repeated.")
    input_group.add_argument("--normalize", type=str, default="sum",
                             choices=["sum", "max", "none"],
                             help="Normalization method for input vectors (default: sum)")

    target_group = parser.add_argument_group('Generated Target (when no external input)')
    target_group.add_argument("--target", type=str, default="gaussian",
                              choices=["gaussian", "uniform", "curve", "bid_ask", "wshape", "chaos"],
                              help="Target distribution type (default: gaussian)")
    target_group.add_argument("--center", type=int, default=34,
                              help="Center bin for target distribution (default: 34)")
    target_group.add_argument("--sigma", type=float, default=12,
                              help="Sigma for Gaussian target (default: 12)")
    target_group.add_argument("--width", type=int, default=25,
                              help="Width for uniform/curve/bid_ask target (default: 25)")
    target_group.add_argument("--bins", type=int, default=69,
                              help="Total number of bins (default: 69, auto-detected for external input)")

    opt_group = parser.add_argument_group('Optimization')
    opt_group.add_argument("--max-strategies", type=int, default=3,
                           help="Maximum number of strategies to use (default: 3)")

    rebalance_group = parser.add_argument_group('Rebalancing')
    rebalance_group.add_argument("--state-file", type=str, metavar="FILE",
                                 help="Path to state file for tracking rebalancing")
    rebalance_group.add_argument("--diff-threshold", type=float, default=0.05,
                                 help="Minimum R-squared difference to trigger rebalance (default: 0.05)")
    rebalance_group.add_argument("--force", action="store_true",
                                 help="Force rebalance even if threshold not met")

    output_group = parser.add_argument_group('Output')
    output_group.add_argument("--output", "-o", type=str, default=None, metavar="FILE",
                              help="Output JSON file path for strategy plan")
    output_group.add_argument("--json-output", action="store_true",
                              help="Output results as JSON to stdout (for automation)")
    output_group.add_argument("--plot", action="store_true",
                              help="Show visualization plots")
    output_group.add_argument("--quiet", "-q", action="store_true",
                              help="Suppress verbose output")

    return parser.parse_args()
def resolve_target(args) -> Tuple[np.ndarray, int, Dict[str, Any]]:
    metadata: Dict[str, Any] = {}

    if args.input_json:
        target, metadata = load_target_from_json(args.input_json)
        B = len(target)
        metadata["input_type"] = "json"

    elif args.input_csv:
        target, metadata = load_target_from_csv(
            args.input_csv,
            column=args.input_csv_column
        )
        B = len(target)
        metadata["input_type"] = "csv"

    elif args.input_api:
        headers = parse_api_headers(args.api_headers) if args.api_headers else {}
        target, metadata = fetch_target_from_api(args.input_api, headers)
        B = len(target)
        metadata["input_type"] = "api"

    else:
        B = args.bins
        target = create_target_distribution(
            args.target, B, args.center, args.sigma, args.width, seed=getattr(args, "seed", None)
        )
        metadata = {
            "input_type": "generated",
            "distribution_type": args.target,
            "bin_count": B
        }

    if args.normalize != "sum" and "input_type" in metadata and metadata["input_type"] != "generated":
        target = normalize_target_vector(target, method=args.normalize)

    return target, B, metadata

def main():
    args = parse_args()
    try:
        return _main_impl(args)
    except (InputValidationError, APIFetchError, DimensionMismatchError) as e:
        if args.json_output:
            output = {
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
            print(json.dumps(output, indent=2))
            sys.exit(1)
        else:
            raise

def _main_impl(args):
    if not args.quiet:
        if args.input_json:
            print(f"Loading target from JSON: {args.input_json}")
        elif args.input_csv:
            print(f"Loading target from CSV: {args.input_csv}")
        elif args.input_api:
            print(f"Fetching target from API: {args.input_api}")
        else:
            print(f"Creating target distribution ({args.target})...")
            print(f"  Center: {args.center}, Bins: {args.bins}")

    target, B, input_metadata = resolve_target(args)

    if not args.quiet:
        print(f"  Target vector: {B} bins")

    target_hash = compute_target_hash(target)

    state = None
    do_rebalance = True
    rebalance_reason = "no_state_file"

    if args.state_file:
        state = load_rebalance_state(args.state_file)

    if not args.quiet:
        print(f"\nGenerating templates for B={B}...")
    templates, params = generate_templates(B)
    if not args.quiet:
        print(f"Generated {len(params)} templates")

    if not args.quiet:
        print(f"\nRunning NNLS optimization (max_strategies={args.max_strategies})...")
    result = approximate_nnls(target, templates, params, max_strategies=args.max_strategies)

    if args.state_file and state:
        last_r2 = state.get("last_r_squared")
        last_hash = state.get("last_target_hash")
        target_changed = (last_hash != target_hash)

        do_rebalance, rebalance_reason = should_rebalance(
            current_r2=result['r_squared'],
            last_r2=last_r2,
            threshold=args.diff_threshold,
            target_changed=target_changed,
            force=args.force
        )

        if not args.quiet:
            print(f"\nRebalancing check: {rebalance_reason}")
            print(f"  Should rebalance: {do_rebalance}")

    strategies_for_output = [
        dict(strat, weight=float(weight))
        for strat, weight in result["strategies"]
    ]

    if args.json_output:
        if args.state_file:
            if do_rebalance:
                output = format_json_output(
                    status="rebalanced",
                    reason=rebalance_reason,
                    current_r2=state.get("last_r_squared") if state else None,
                    new_r2=result['r_squared'],
                    plan_file=args.output,
                    strategies=strategies_for_output
                )
            else:
                output = format_json_output(
                    status="skipped",
                    reason=rebalance_reason,
                    current_r2=result['r_squared']
                )
        else:
            output = format_json_output(
                status="completed",
                reason="no_state_tracking",
                current_r2=result['r_squared'],
                plan_file=args.output,
                strategies=strategies_for_output
            )
        print(json.dumps(output, indent=2))

    elif not args.quiet:
        print(f"\n" + "=" * 50)
        print("OPTIMIZATION RESULTS")
        print("=" * 50)
        print(f"  R-squared: {result['r_squared']:.4f}")
        print(f"  Residual: {result['residual']:.6f}")
        print(f"  Strategies: {len(result['strategies'])}")

        if result.get('truncated', False):
            print(f"\n  Truncation info:")
            print(f"    Full solution R²: {result['full_r_squared']:.4f}")
            print(f"    R² loss: {result.get('r_squared_loss', 0):.4f}")

        print(f"\nSelected strategies:")
        for i, (strat, weight) in enumerate(result['strategies'], 1):
            print(f"  {i}. {_print_param(strat) if False else ''}".rstrip())
            # Pretty one-line print:
            ptype = strat.get("type", "unknown")
            if ptype in {"rectangle", "curve", "bid_ask", "one_hot"}:
                print(f"     {ptype:12s} center={strat.get('center')} width={strat.get('width')} | w={weight:.4f}")
            elif ptype == "w_template":
                print(f"     {ptype:12s} v1={strat.get('v1')} p={strat.get('p')} v2={strat.get('v2')} | w={weight:.4f}")
            elif ptype == "dip_template":
                print(f"     {ptype:12s} left={strat.get('left')} right={strat.get('right')} | w={weight:.4f}")
            else:
                print(f"     {ptype:12s} params={strat} | w={weight:.4f}")

    if args.output and do_rebalance:
        plan = export_strategy_plan(result, args.output)
        if input_metadata:
            plan["input_metadata"] = input_metadata

    if args.state_file:
        action = "rebalanced" if do_rebalance else "skipped"
        state = update_state(
            state if state else {},
            target_hash=target_hash,
            r_squared=result['r_squared'],
            strategies=strategies_for_output,
            action=action,
            reason=rebalance_reason
        )
        save_rebalance_state(args.state_file, state)
        if not args.quiet and not args.json_output:
            print(f"\nState saved to: {args.state_file}")

    if args.plot:
        visualize_results(target, result, B)

    return result

if __name__ == "__main__":
    main()
