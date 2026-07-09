def main(bridle_lines, bridle_nodes_data, len_wing_sections):
    """
    Generate bridle connections data for YAML output.
    If symmetrical nodes exist (positive y-coordinates), create connections for both sides.

    Parameters:
        bridle_lines: List of bridle line data from main_process_surfplan
                     Canonical: [point1, point2, name, length, diameter, material]
                     Legacy supported: [point1, point2, diameter, name, length, material]
        bridle_nodes_data: Bridle nodes data to reference node IDs

    Returns:
        dict: Bridle connections data formatted for YAML
    """
    bridle_connections_data = []

    # Create mapping from points to node IDs
    point_to_node_id = {}
    for node_data in bridle_nodes_data["data"]:
        node_id, x, y, z = node_data[0], node_data[1], node_data[2], node_data[3]
        point_to_node_id[(x, y, z)] = node_id

    # Check if we have symmetrical nodes (both negative and positive y-coordinates)
    y_coords = [node_data[2] for node_data in bridle_nodes_data["data"]]
    has_negative_y = any(y < 0 for y in y_coords)
    has_positive_y = any(y > 0 for y in y_coords)
    has_symmetrical_nodes = has_negative_y and has_positive_y

    for i, bridle_line in enumerate(bridle_lines):
        if bridle_line and len(bridle_line) >= 5:
            p1, p2 = bridle_line[0], bridle_line[1]
            if isinstance(bridle_line[2], str):
                name = bridle_line[2]
            elif len(bridle_line) > 3 and isinstance(bridle_line[3], str):
                # Backwards-compatibility for legacy swapped ordering.
                name = bridle_line[3]
            else:
                name = f"line_{i + 1}"

            # Find corresponding node IDs for original connections
            p1_tuple = (float(p1[0]), float(p1[1]), float(p1[2]))
            p2_tuple = (float(p2[0]), float(p2[1]), float(p2[2]))

            ci = point_to_node_id.get(p1_tuple, 0)
            cj = point_to_node_id.get(p2_tuple, 0)

            if ci > 0 and cj > 0:
                bridle_connections_data.append(
                    [
                        name,  # Use actual line name
                        ci + len_wing_sections,  # ci (start node)
                        cj + len_wing_sections,  # cj (end node)
                    ]
                )

                # If we have symmetrical nodes, create mirrored connections
                if has_symmetrical_nodes:
                    # Find the mirrored points (with y-coordinate sign flipped)
                    p1_mirrored = (float(p1[0]), float(-p1[1]), float(p1[2]))
                    p2_mirrored = (float(p2[0]), float(-p2[1]), float(p2[2]))

                    ci_mirrored = point_to_node_id.get(p1_mirrored, 0)
                    cj_mirrored = point_to_node_id.get(p2_mirrored, 0)

                    if ci_mirrored > 0 and cj_mirrored > 0:
                        bridle_connections_data.append(
                            [
                                name,  # Same line name for symmetrical connection
                                ci_mirrored
                                + len_wing_sections,  # mirrored start node with offset
                                cj_mirrored
                                + len_wing_sections,  # mirrored end node with offset
                            ]
                        )
    
    # --- inject virtual control tapes automatically ---
    # Find lowest bridle nodes (bar/control attachment points)

    node_coordinates = {
        node[0]: (node[1], node[2], node[3])
        for node in bridle_nodes_data["data"]
    }

    # Select the 4 lowest nodes in Z
    lowest_nodes = sorted(
        node_coordinates.keys(),
        key=lambda n: node_coordinates[n][2]   # z coordinate
    )[:4]

    print(f"--------------> lowest_nodes by z: {lowest_nodes}")

    if len(lowest_nodes) == 4:

        # Sort by X coordinate:
        # smaller X = front bridles
        # larger X = rear bridles (brmain)
        lowest_nodes_sorted_x = sorted(
            lowest_nodes,
            key=lambda n: node_coordinates[n][0]
        )

        front_nodes = lowest_nodes_sorted_x[:2]
        rear_nodes = lowest_nodes_sorted_x[-2:]

        # Sort left/right using Y coordinate
        front_nodes = sorted(
            front_nodes,
            key=lambda n: node_coordinates[n][1]
        )

        rear_nodes = sorted(
            rear_nodes,
            key=lambda n: node_coordinates[n][1]
        )

        print(f"--------------> front_nodes (depower): {front_nodes}")
        print(f"--------------> rear_nodes (steering): {rear_nodes}")

        # Convert bridle node IDs to global particle IDs
        front_nodes = [
            n + len_wing_sections
            for n in front_nodes
        ]

        rear_nodes = [
            n + len_wing_sections
            for n in rear_nodes
        ]

        # Front bridles -> depower tape
        for node in front_nodes:
            bridle_connections_data.append(
                ["depower_tape", node, 0]
            )

        # Rear bridles -> steering tape
        for node in rear_nodes:
            bridle_connections_data.append(
                ["steering_tape", node, 0]
            )

    return {"headers": ["name", "ci", "cj"], "data": bridle_connections_data}
