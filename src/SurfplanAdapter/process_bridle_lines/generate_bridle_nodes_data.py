def main(bridle_lines):
    """
    Generate bridle nodes data for YAML output.
    If all nodes have negative y-coordinates, create symmetrical nodes with positive y.

    Parameters:
        bridle_lines: List of bridle line data from main_process_surfplan

    Returns:
        dict: Bridle nodes data formatted for YAML
    """
    bridle_nodes_data = []
    node_id = 1

    # Create unique nodes from bridle line endpoints
    unique_points = set()
    for bridle_line in bridle_lines:
        if bridle_line and len(bridle_line) >= 5:
            p1, p2 = bridle_line[0], bridle_line[1]
            unique_points.add(tuple(p1))
            unique_points.add(tuple(p2))

    # Convert to sorted list for consistent ordering
    unique_points = sorted(list(unique_points))

    # Add original nodes
    for point in unique_points:
        bridle_nodes_data.append(
            [
                node_id,
                float(point[0]),
                float(point[1]),
                float(point[2]),
                "knot",  # Default to knot, could be "pulley" based on analysis
            ]
        )
        node_id += 1

    # Add symmetrical nodes with positive y, skipping points already on the symmetry plane
    for point in unique_points:
        if point[1] == 0.0:
            continue
        bridle_nodes_data.append(
            [
                node_id,
                float(point[0]),
                float(-point[1]),  # Mirror the y-coordinate
                float(point[2]),
                "knot",
            ]
        )
        node_id += 1

    return {"headers": ["id", "x", "y", "z", "type"], "data": bridle_nodes_data}
