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

def _front_rear_nodes(bridle_nodes_data):
    """
    Replicate the exact node-selection logic used in
    generate_bridle_connections_data.main() to identify the control-tape
    attachment nodes, so both modules always agree on which nodes are
    "front" (depower) and "rear" (steering).
    """
    node_coordinates = {n[0]: n[1:4] for n in bridle_nodes_data["data"]}

    lowest_nodes = sorted(  # 4 lowest bridle nodes (2 front, 2 rear) by z
        node_coordinates, key=lambda n: node_coordinates[n][2]
    )[:4]

    lowest_nodes = sorted(  # split front/rear by x
        lowest_nodes, key=lambda n: node_coordinates[n][0]
    )

    front_nodes, rear_nodes = lowest_nodes[:2], lowest_nodes[2:]
    return node_coordinates, front_nodes, rear_nodes

def _distance_to_bridle_point(bridle_point_node, node_coordinates, node_ids):
    """Mean euclidean distance from bridle_point_node to the given nodes.

    The two attachment nodes (left/right) are symmetric, so their distance
    to the KCU point should already match closely; averaging just guards
    against small asymmetries instead of arbitrarily picking one side.
    """
    distances = [
        np.linalg.norm(np.asarray(node_coordinates[n], dtype=float) - bridle_point_node)
        for n in node_ids
    ]
    
    return np.mean(distances)

def main(bridle_lines, bridle_nodes_data=None, bridle_point_node=None):
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
                    'noncompressive', #linktype
                    970,  # density
                ]
            )
    
    # --- inject control tapes automatically ---
    # steering_tape / depower_tape connect bridle_point_node (the KCU) to the
    # front/rear-most bridle nodes (see generate_bridle_connections_data.main).
    if bridle_nodes_data is not None and bridle_point_node is not None:
        node_coordinates, front_nodes, rear_nodes = _front_rear_nodes(bridle_nodes_data)
        print("DEBUG bridle_point_node:", bridle_point_node)
        print("DEBUG node_coordinates shape:", len(node_coordinates))
        print("DEBUG front_nodes:", front_nodes)
        print("DEBUG rear_nodes:", rear_nodes)
        depower_length = _distance_to_bridle_point(
            bridle_point_node, node_coordinates, front_nodes
        )
        print("DEBUG depower_length:", depower_length)
        print("DEBUG steering_length:", steering_length)
        steering_length = _distance_to_bridle_point(
            bridle_point_node, node_coordinates, rear_nodes
        )
    else: # Fallback
        depower_length = 0.001
        steering_length = 0.001

    max_bridle_lines_diameter = max(line[2] for line in bridle_lines)

    bridle_lines_data += [
        ["steering_tape", steering_length, max_bridle_lines_diameter, "dyneema", "noncompressive", 970],
        ["depower_tape", depower_length, max_bridle_lines_diameter, "dyneema", "noncompressive", 970],
    ]

    return {
        "headers": ["name", "l0", "d", "material", "linktype", "density"],
        "data": bridle_lines_data,
    }
