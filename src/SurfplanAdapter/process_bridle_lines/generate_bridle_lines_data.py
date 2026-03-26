import numpy as np


def _to_float(value, default):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _extract_fields(bridle_line, index):
    """
    Extract canonical fields from a bridle line record.

    Canonical order:
      [point1, point2, name, length, diameter, material]

    Legacy order (accepted for backwards compatibility):
      [point1, point2, diameter, name, length, material]
    """
    p1, p2 = bridle_line[0], bridle_line[1]
    material = bridle_line[5] if len(bridle_line) > 5 else None

    if isinstance(bridle_line[2], str):
        name = bridle_line[2].strip() or f"line_{index + 1}"
        length = _to_float(bridle_line[3] if len(bridle_line) > 3 else None, 0.0)
        diameter = _to_float(bridle_line[4] if len(bridle_line) > 4 else None, 0.002)
    else:
        # Legacy swapped ordering.
        name = (
            str(bridle_line[3]).strip()
            if len(bridle_line) > 3 and str(bridle_line[3]).strip()
            else f"line_{index + 1}"
        )
        length = _to_float(bridle_line[4] if len(bridle_line) > 4 else None, 0.0)
        diameter = _to_float(bridle_line[2], 0.002)

    # Defensive conversion: if a value looks like millimeters, convert to meters.
    if diameter > 0.05:
        diameter /= 1000.0

    return p1, p2, name, length, diameter, material


def main(bridle_lines):
    """
    Generate bridle lines data for YAML output.

    Parameters:
        bridle_lines: List of bridle line data from main_process_surfplan
                     Canonical: [point1, point2, name, length, diameter, material]
                     Legacy supported: [point1, point2, diameter, name, length, material]

    Returns:
        dict: Bridle lines data formatted for YAML
    """
    bridle_lines_data = []

    for i, bridle_line in enumerate(bridle_lines):
        if bridle_line and len(bridle_line) >= 5:
            p1, p2, name, length, diameter, material = _extract_fields(bridle_line, i)

            # Use provided length, or calculate as distance between points if not available
            if length > 0:
                rest_length = length
            else:
                rest_length = np.linalg.norm(
                    np.asarray(p2, dtype=float) - np.asarray(p1, dtype=float)
                )

            # Internal convention is meters. Default to 2 mm when absent.
            line_diameter_m = diameter if diameter > 0 else 0.002

            bridle_lines_data.append(
                [
                    name,  # Use actual line name
                    float(rest_length),  # rest_length
                    float(line_diameter_m),  # diameter in meters
                    material if material else "dyneema",  # material
                    970,  # density
                ]
            )

    return {
        "headers": ["name", "rest_length", "diameter", "material", "density"],
        "data": bridle_lines_data,
    }
