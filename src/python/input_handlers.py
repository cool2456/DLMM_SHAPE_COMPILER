"""
Input handlers for loading target vectors from external sources.
Supports JSON files, CSV files, and API endpoints.
"""

import numpy as np
import json
import csv
import urllib.request
import urllib.error
from typing import Tuple, Dict, Any, Optional, List


class InputValidationError(Exception):
    """Raised when input data fails validation."""
    pass


class APIFetchError(Exception):
    """Raised when API request fails."""
    pass


def validate_target_vector(
    vector: np.ndarray,
    min_bins: int = 3,
    max_bins: int = 500
) -> Tuple[bool, str]:
    """
    Validate a target vector for use in optimization.

    Args:
        vector: NumPy array of liquidity values
        min_bins: Minimum allowed bin count
        max_bins: Maximum allowed bin count

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not isinstance(vector, np.ndarray):
        return False, f"Expected numpy array, got {type(vector).__name__}"

    if vector.ndim != 1:
        return False, f"Expected 1D array, got {vector.ndim}D"

    if len(vector) < min_bins:
        return False, f"Too few bins: {len(vector)} < {min_bins}"

    if len(vector) > max_bins:
        return False, f"Too many bins: {len(vector)} > {max_bins}"

    if np.any(np.isnan(vector)):
        return False, "Vector contains NaN values"

    if np.any(np.isinf(vector)):
        return False, "Vector contains Inf values"

    if np.any(vector < 0):
        return False, "Vector contains negative values"

    if np.sum(vector) < 1e-12:
        return False, "Vector is all zeros or near-zero"

    return True, ""


def normalize_target_vector(
    raw: np.ndarray,
    method: str = "sum"
) -> np.ndarray:
    """
    Normalize a raw liquidity vector.

    Args:
        raw: Raw liquidity values
        method: Normalization method
            - "sum": Divide by sum (probability distribution, sums to 1)
            - "max": Divide by max (0-1 range)
            - "none": Keep raw values

    Returns:
        Normalized numpy array
    """
    if method == "none":
        return raw.astype(np.float64)

    raw = raw.astype(np.float64)

    if method == "sum":
        total = np.sum(raw)
        if total < 1e-12:
            return raw
        return raw / total

    elif method == "max":
        maximum = np.max(raw)
        if maximum < 1e-12:
            return raw
        return raw / maximum

    else:
        raise ValueError(f"Unknown normalization method: {method}")


def load_target_from_json(file_path: str) -> Tuple[np.ndarray, Dict[str, Any]]:
    """
    Load target vector from a JSON file.

    Expected JSON format:
    {
        "bins": [0.01, 0.02, 0.15, ...],
        "metadata": {
            "source": "external",
            "timestamp": "2026-01-27T10:00:00Z",
            "bin_step": 25,
            "active_bin_id": 8345123
        },
        "normalize": true  // optional, default true
    }

    Args:
        file_path: Path to JSON file

    Returns:
        Tuple of (target_vector, metadata)

    Raises:
        InputValidationError: If JSON is invalid or vector fails validation
    """
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
    except FileNotFoundError:
        raise InputValidationError(f"File not found: {file_path}")
    except json.JSONDecodeError as e:
        raise InputValidationError(f"Invalid JSON in {file_path}: {e}")

    # Extract bins array
    if "bins" not in data:
        raise InputValidationError("JSON must contain 'bins' array")

    bins = data["bins"]
    if not isinstance(bins, list):
        raise InputValidationError("'bins' must be an array")

    try:
        vector = np.array(bins, dtype=np.float64)
    except (ValueError, TypeError) as e:
        raise InputValidationError(f"Cannot convert bins to numeric array: {e}")

    # Validate
    is_valid, error = validate_target_vector(vector)
    if not is_valid:
        raise InputValidationError(f"Invalid target vector: {error}")

    # Normalize if requested (default: True)
    should_normalize = data.get("normalize", True)
    if should_normalize:
        vector = normalize_target_vector(vector, method="sum")

    # Extract metadata
    metadata = data.get("metadata", {})
    metadata["source_file"] = file_path
    metadata["bin_count"] = len(vector)

    return vector, metadata


def load_target_from_csv(
    file_path: str,
    column: str = "liquidity"
) -> Tuple[np.ndarray, Dict[str, Any]]:
    """
    Load target vector from a CSV file.

    Supports two formats:
    1. Single column (bin index inferred from row):
       liquidity
       0.01
       0.02
       ...

    2. Two columns (explicit bin indices):
       bin_id,liquidity
       0,0.01
       1,0.02
       ...

    Args:
        file_path: Path to CSV file
        column: Column name for liquidity values (default: "liquidity")

    Returns:
        Tuple of (target_vector, metadata)

    Raises:
        InputValidationError: If CSV is invalid or vector fails validation
    """
    try:
        with open(file_path, 'r', newline='') as f:
            # Detect if header exists
            sample = f.read(1024)
            f.seek(0)
            has_header = csv.Sniffer().has_header(sample)

            if has_header:
                reader = csv.DictReader(f)
                rows = list(reader)

                if not rows:
                    raise InputValidationError("CSV file is empty")

                # Determine format based on columns
                fieldnames = reader.fieldnames or []

                if "bin_id" in fieldnames and column in fieldnames:
                    # Two-column format with explicit bin IDs
                    bin_data = [(int(row["bin_id"]), float(row[column])) for row in rows]
                    bin_data.sort(key=lambda x: x[0])

                    # Check for gaps
                    max_bin = max(b[0] for b in bin_data)
                    vector = np.zeros(max_bin + 1)
                    for bin_id, value in bin_data:
                        vector[bin_id] = value

                elif column in fieldnames:
                    # Single column format
                    vector = np.array([float(row[column]) for row in rows])

                else:
                    # Try first column
                    first_col = fieldnames[0] if fieldnames else None
                    if first_col:
                        vector = np.array([float(row[first_col]) for row in rows])
                    else:
                        raise InputValidationError(f"Column '{column}' not found in CSV")
            else:
                # No header, treat as single column of values
                reader = csv.reader(f)
                values = [float(row[0]) for row in reader if row]
                vector = np.array(values)

    except FileNotFoundError:
        raise InputValidationError(f"File not found: {file_path}")
    except (ValueError, TypeError, KeyError) as e:
        raise InputValidationError(f"Error parsing CSV {file_path}: {e}")

    # Validate
    is_valid, error = validate_target_vector(vector)
    if not is_valid:
        raise InputValidationError(f"Invalid target vector: {error}")

    # Normalize
    vector = normalize_target_vector(vector, method="sum")

    # Metadata
    metadata = {
        "source_file": file_path,
        "bin_count": len(vector),
        "format": "csv"
    }

    return vector, metadata


def fetch_target_from_api(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    timeout: int = 30
) -> Tuple[np.ndarray, Dict[str, Any]]:
    """
    Fetch target vector from an API endpoint.

    Expected JSON response format (same as load_target_from_json):
    {
        "bins": [0.01, 0.02, 0.15, ...],
        "metadata": {...},
        "normalize": true
    }

    Args:
        url: API endpoint URL
        headers: Optional HTTP headers (for auth tokens, API keys, etc.)
        timeout: Request timeout in seconds

    Returns:
        Tuple of (target_vector, metadata)

    Raises:
        APIFetchError: If request fails
        InputValidationError: If response is invalid
    """
    headers = headers or {}

    # Build request
    req = urllib.request.Request(url, headers=headers)

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            if response.status != 200:
                raise APIFetchError(f"API returned status {response.status}")

            content = response.read().decode('utf-8')
            data = json.loads(content)

    except urllib.error.HTTPError as e:
        raise APIFetchError(f"HTTP error {e.code}: {e.reason}")
    except urllib.error.URLError as e:
        raise APIFetchError(f"URL error: {e.reason}")
    except json.JSONDecodeError as e:
        raise APIFetchError(f"Invalid JSON response: {e}")
    except TimeoutError:
        raise APIFetchError(f"Request timed out after {timeout}s")

    # Parse response (same format as JSON file)
    if "bins" not in data:
        raise InputValidationError("API response must contain 'bins' array")

    bins = data["bins"]
    if not isinstance(bins, list):
        raise InputValidationError("'bins' must be an array")

    try:
        vector = np.array(bins, dtype=np.float64)
    except (ValueError, TypeError) as e:
        raise InputValidationError(f"Cannot convert bins to numeric array: {e}")

    # Validate
    is_valid, error = validate_target_vector(vector)
    if not is_valid:
        raise InputValidationError(f"Invalid target vector: {error}")

    # Normalize if requested
    should_normalize = data.get("normalize", True)
    if should_normalize:
        vector = normalize_target_vector(vector, method="sum")

    # Extract metadata
    metadata = data.get("metadata", {})
    metadata["source_url"] = url
    metadata["bin_count"] = len(vector)

    return vector, metadata


def parse_api_headers(header_strings: List[str]) -> Dict[str, str]:
    """
    Parse CLI header arguments into a dictionary.

    Args:
        header_strings: List of "Key: Value" strings

    Returns:
        Dictionary of header name -> value
    """
    headers = {}
    for h in header_strings:
        if ':' not in h:
            raise ValueError(f"Invalid header format: '{h}'. Expected 'Key: Value'")
        key, value = h.split(':', 1)
        headers[key.strip()] = value.strip()
    return headers
