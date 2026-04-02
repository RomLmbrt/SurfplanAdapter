import yaml
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.cm as cm
from pathlib import Path
from collections import defaultdict


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _get_header_map(table):
    headers = table.get("headers", []) if isinstance(table, dict) else []
    return {str(name): idx for idx, name in enumerate(headers)}


def _extract_is_strut_flags(wing_sections, wing_airfoils):
    """
    Build per-section strut flags from wing_airfoils info_dict['is_strut'].
    """
    if not wing_airfoils:
        return np.array([False for _ in wing_sections], dtype=bool)

    airfoil_is_strut = {}
    for row in wing_airfoils:
        if not row:
            continue
        airfoil_id = row[0]
        info_dict = row[2] if len(row) > 2 and isinstance(row[2], dict) else {}
        airfoil_is_strut[airfoil_id] = bool(info_dict.get("is_strut", False))

    return np.array(
        [bool(airfoil_is_strut.get(section[0], False)) for section in wing_sections]
    )


def _extract_bridle_mass_nodes(config):
    """
    Convert bridle line masses into lumped node masses.

    Returns
    -------
    tuple
        (bridle_nodes, total_bridle_mass, n_bridle_segments)
        where bridle_nodes is a list of [position, mass].
    """
    bridle_nodes_table = config.get("bridle_nodes") or config.get("bridle_particles")
    bridle_lines_table = config.get("bridle_lines")
    bridle_connections_table = config.get("bridle_connections")

    if not (bridle_nodes_table and bridle_lines_table and bridle_connections_table):
        return [], 0.0, 0

    node_headers = _get_header_map(bridle_nodes_table)
    line_headers = _get_header_map(bridle_lines_table)
    conn_headers = _get_header_map(bridle_connections_table)

    node_id_idx = node_headers.get("id", 0)
    node_x_idx = node_headers.get("x", 1)
    node_y_idx = node_headers.get("y", 2)
    node_z_idx = node_headers.get("z", 3)
    node_type_idx = node_headers.get("type", None)

    conn_name_idx = conn_headers.get("name", 0)
    conn_ci_idx = conn_headers.get("ci", 1)
    conn_cj_idx = conn_headers.get("cj", 2)

    line_name_idx = line_headers.get("name", 0)
    line_rest_length_idx = line_headers.get("rest_length", 1)
    line_diameter_idx = line_headers.get("diameter", 2)
    line_material_idx = line_headers.get("material", 3)
    line_density_idx = line_headers.get("density", None)

    node_coords = {}
    node_types = {}
    for row in bridle_nodes_table.get("data", []):
        if not row:
            continue
        node_id = int(row[node_id_idx])
        node_coords[node_id] = np.array(
            [
                _safe_float(row[node_x_idx], 0.0),
                _safe_float(row[node_y_idx], 0.0),
                _safe_float(row[node_z_idx], 0.0),
            ],
            dtype=float,
        )
        if node_type_idx is not None and len(row) > node_type_idx:
            node_types[node_id] = str(row[node_type_idx]).lower()

    if not node_coords:
        return [], 0.0, 0

    material_density_lookup = {}
    for key, value in config.items():
        if isinstance(value, dict) and "density" in value:
            material_density_lookup[str(key)] = _safe_float(value.get("density"), 0.0)

    line_properties = {}
    for row in bridle_lines_table.get("data", []):
        if not row:
            continue
        line_name = str(row[line_name_idx])
        rest_length = _safe_float(row[line_rest_length_idx], 0.0)
        diameter = _safe_float(row[line_diameter_idx], 0.002)
        if diameter > 0.05:
            diameter /= 1000.0

        material = (
            str(row[line_material_idx])
            if line_material_idx is not None and len(row) > line_material_idx
            else "dyneema"
        )
        density = (
            _safe_float(row[line_density_idx], 0.0)
            if line_density_idx is not None and len(row) > line_density_idx
            else 0.0
        )
        if density <= 0.0:
            density = material_density_lookup.get(material, 970.0)

        line_properties[line_name] = {
            "rest_length": rest_length,
            "diameter": diameter if diameter > 0 else 0.002,
            "density": density if density > 0 else 970.0,
        }

    bridle_mass_by_node = defaultdict(float)
    total_bridle_mass = 0.0
    n_bridle_segments = 0

    for row in bridle_connections_table.get("data", []):
        if not row:
            continue
        line_name = str(row[conn_name_idx])
        ci = int(row[conn_ci_idx])
        cj = int(row[conn_cj_idx])

        if ci not in node_coords or cj not in node_coords:
            continue

        line_prop = line_properties.get(line_name)
        if line_prop is None:
            continue

        geometric_length = float(np.linalg.norm(node_coords[cj] - node_coords[ci]))
        segment_length = (
            line_prop["rest_length"]
            if line_prop["rest_length"] > 0
            else geometric_length
        )
        if segment_length <= 0:
            continue

        area = np.pi * (line_prop["diameter"] * 0.5) ** 2
        segment_mass = line_prop["density"] * area * segment_length

        bridle_mass_by_node[ci] += 0.5 * segment_mass
        bridle_mass_by_node[cj] += 0.5 * segment_mass
        total_bridle_mass += segment_mass
        n_bridle_segments += 1

    pulley_mass = _safe_float(config.get("pulley_mass"), 0.0)
    if pulley_mass > 0:
        for node_id, node_type in node_types.items():
            if node_type == "pulley":
                bridle_mass_by_node[node_id] += pulley_mass
                total_bridle_mass += pulley_mass

    bridle_nodes = [
        [node_coords[node_id], node_mass]
        for node_id, node_mass in bridle_mass_by_node.items()
        if node_mass > 0
    ]

    return bridle_nodes, total_bridle_mass, n_bridle_segments


def _select_bridle_source_config(primary_config, yaml_file_path):
    """
    Resolve config source for bridle data.

    If the primary file has no bridle sections (e.g. aero_geometry.yaml),
    fall back to sibling config_kite.yaml when available.
    """
    if all(
        key in primary_config for key in ("bridle_lines", "bridle_connections")
    ) and any(key in primary_config for key in ("bridle_nodes", "bridle_particles")):
        return primary_config, str(yaml_file_path)

    sibling_config_path = Path(yaml_file_path).with_name("config_kite.yaml")
    if sibling_config_path.exists():
        with open(sibling_config_path, "r") as f:
            sibling_config = yaml.safe_load(f)
        if (
            sibling_config
            and all(
                key in sibling_config for key in ("bridle_lines", "bridle_connections")
            )
            and any(
                key in sibling_config for key in ("bridle_nodes", "bridle_particles")
            )
        ):
            return sibling_config, str(sibling_config_path)

    return {}, None


def _extract_tube_data(struc_config):
    """
    Extract LE tube and strut tube geometry from struc_geometry_all_in_surfplan config.

    Returns
    -------
    dict or None
        Dict with 'le_node_positions' (list of (position, diameter)) and
        'struts' (list of dicts with pos_le, pos_te, diam_le, diam_te, length),
        or None if data is not available.
    """
    if not struc_config:
        return None

    wing_particles = struc_config.get("wing_particles")
    le_tubes = struc_config.get("leading_edge_tubes")
    strut_tubes_table = struc_config.get("strut_tubes")

    if not (wing_particles and le_tubes):
        return None

    # Build node position lookup
    wp_headers = _get_header_map(wing_particles)
    node_coords = {}
    for row in wing_particles.get("data", []):
        node_id = int(row[wp_headers.get("id", 0)])
        node_coords[node_id] = np.array(
            [
                _safe_float(row[wp_headers.get("x", 1)]),
                _safe_float(row[wp_headers.get("y", 2)]),
                _safe_float(row[wp_headers.get("z", 3)]),
            ]
        )

    # Extract LE node diameters from tube segments
    le_headers = _get_header_map(le_tubes)
    le_node_diameters = defaultdict(list)

    for row in le_tubes.get("data", []):
        ci = int(row[le_headers.get("ci", 1)])
        cj = int(row[le_headers.get("cj", 2)])
        diameter = _safe_float(row[le_headers.get("diameter", 3)])
        le_node_diameters[ci].append(diameter)
        le_node_diameters[cj].append(diameter)

    # Build (position, diameter) for each LE node
    le_node_positions = []
    for node_id, diams in le_node_diameters.items():
        if node_id in node_coords:
            le_node_positions.append((node_coords[node_id], float(np.mean(diams))))

    # Extract strut data
    struts = []
    if strut_tubes_table:
        st_headers = _get_header_map(strut_tubes_table)
        for row in strut_tubes_table.get("data", []):
            ci = int(row[st_headers.get("ci", 1)])
            cj = int(row[st_headers.get("cj", 2)])
            diam_le = _safe_float(row[st_headers.get("strut_diam_le", 3)])
            diam_te = _safe_float(row[st_headers.get("strut_diam_te", 4)])
            if ci in node_coords and cj in node_coords:
                length = float(np.linalg.norm(node_coords[cj] - node_coords[ci]))
                struts.append(
                    {
                        "pos_le": node_coords[ci],
                        "pos_te": node_coords[cj],
                        "diam_le": diam_le,
                        "diam_te": diam_te,
                        "length": length,
                    }
                )

    return {
        "le_node_positions": le_node_positions,
        "struts": struts,
    }


def _get_le_diameters_at_ribs(tube_data, LE_points):
    """Match LE tube diameters to rib LE positions by nearest-neighbor."""
    le_node_positions = tube_data["le_node_positions"]
    struct_pos = np.array([p[0] for p in le_node_positions])
    struct_diam = np.array([p[1] for p in le_node_positions])

    diameters = np.zeros(len(LE_points))
    for i, le_pt in enumerate(LE_points):
        distances = np.linalg.norm(struct_pos - le_pt, axis=1)
        diameters[i] = struct_diam[np.argmin(distances)]
    return diameters


def find_mass_distributions(
    wing_sections,
    total_wing_mass: float,
    canopy_kg_p_sqm: float,
    le_to_strut_mass_ratio,
    sensor_mass: float,
    is_strut=None,
    tube_data=None,
):
    """
    Calculate mass distributions for wing components.

    Parameters:
    wing_sections (list): List of wing sections data from YAML.
    total_wing_mass (float): Total mass of the wing.
    canopy_kg_p_sqm (float): Canopy mass in kg per square meter.
    le_to_strut_mass_ratio (float or None): Ratio of mass between LE and struts.
        If None and tube_data is provided, derived from cylindrical surface areas.
    sensor_mass (float): Mass of the sensor in kilograms.
    is_strut: Boolean array indicating strut ribs.
    tube_data (dict or None): LE tube and strut geometry from _extract_tube_data().

    Returns:
    tuple: Mass distribution arrays and geometry data.
    """
    # Extract leading edge (LE) and trailing edge (TE) points
    # wing_sections data format: [airfoil_id, LE_x, LE_y, LE_z, TE_x, TE_y, TE_z, VUP_x, VUP_y, VUP_z]
    LE_points = np.array(
        [
            [section[1], section[2], section[3]]  # LE_x, LE_y, LE_z
            for section in wing_sections
        ]
    )
    TE_points = np.array(
        [
            [section[4], section[5], section[6]]  # TE_x, TE_y, TE_z
            for section in wing_sections
        ]
    )
    # If no strut info is available, default to no struts.
    if is_strut is None:
        is_strut = np.array([False for _ in wing_sections], dtype=bool)
    else:
        is_strut = np.asarray(is_strut, dtype=bool)

    # Initialize variables
    total_canopy_mass = 0
    total_area = 0
    panels = []
    panel_canopy_mass_list = []

    # Create panels from consecutive LE and TE points
    for i in range(len(LE_points) - 1):
        # Panel vertices
        p1 = LE_points[i]
        p2 = TE_points[i]
        p3 = TE_points[i + 1]
        p4 = LE_points[i + 1]
        panels.append([p1, p2, p3, p4])

        # Calculate panel surface area (approximate as quadrilateral)
        edge1 = np.linalg.norm(p2 - p1)
        edge2 = np.linalg.norm(p3 - p2)
        diagonal = np.linalg.norm(p3 - p1)
        s = (edge1 + edge2 + diagonal) / 2
        area1 = np.sqrt(
            max(0.0, s * (s - edge1) * (s - edge2) * (s - diagonal))
        )  # First triangle
        edge3 = np.linalg.norm(p4 - p3)
        edge4 = np.linalg.norm(p4 - p1)
        s = (edge3 + edge4 + diagonal) / 2
        area2 = np.sqrt(
            max(0.0, s * (s - edge3) * (s - edge4) * (s - diagonal))
        )  # Second triangle
        panel_area = area1 + area2
        total_area += panel_area

        # Calculate panel mass (canopy mass in kg)
        panel_canopy_mass = panel_area * canopy_kg_p_sqm
        panel_canopy_mass_list.append(panel_canopy_mass)
        total_canopy_mass += panel_canopy_mass

    # Calculate mass of other components
    if total_canopy_mass > total_wing_mass:
        raise ValueError(
            "Total panel mass exceeds total wing mass.\nLower canopy mass OR increase total_mass."
        )
    non_canopy_mass = total_wing_mass - total_canopy_mass

    # Distribute the remaining mass
    non_canopy_mass_min_sensor = non_canopy_mass - sensor_mass
    if non_canopy_mass_min_sensor < 0:
        raise ValueError(
            "Sensor mass exceeds non-canopy mass budget. "
            "Lower sensor_mass OR increase total_wing_mass."
        )

    n_le = len(LE_points)
    n_strut_nodes = np.count_nonzero(is_strut)

    # Precompute surface areas from tube geometry if available
    le_diameters = None
    le_seg_SA = None
    strut_SAs = None
    strut_rib_indices = None

    if tube_data is not None:
        le_diameters = _get_le_diameters_at_ribs(tube_data, LE_points)

        # LE tube segment surface areas along path: TE[0]→LE[0]→...→LE[n-1]→TE[-1]
        n_seg = n_le + 1  # (n_le - 1) inter-rib + 2 tip segments
        le_seg_SA = np.zeros(n_seg)
        # Tip segment 0: TE[0] → LE[0]
        le_seg_SA[0] = (
            np.pi * le_diameters[0] * np.linalg.norm(LE_points[0] - TE_points[0])
        )
        # Inter-rib segments
        for i in range(n_le - 1):
            d_avg = 0.5 * (le_diameters[i] + le_diameters[i + 1])
            length = np.linalg.norm(LE_points[i + 1] - LE_points[i])
            le_seg_SA[i + 1] = np.pi * d_avg * length
        # Tip segment n_le: LE[n-1] → TE[-1]
        le_seg_SA[n_le] = (
            np.pi * le_diameters[-1] * np.linalg.norm(TE_points[-1] - LE_points[-1])
        )

        # Strut cylindrical surface areas
        strut_SAs = []
        strut_rib_indices = []
        if tube_data.get("struts"):
            for strut in tube_data["struts"]:
                d_avg = 0.5 * (strut["diam_le"] + strut["diam_te"])
                SA = np.pi * d_avg * strut["length"]
                strut_SAs.append(SA)
                # Match strut LE position to rib index
                dists = np.linalg.norm(LE_points - strut["pos_le"], axis=1)
                strut_rib_indices.append(int(np.argmin(dists)))

        # Derive le_to_strut ratio from geometry if not explicitly set
        if le_to_strut_mass_ratio is None:
            total_le_SA = float(np.sum(le_seg_SA))
            total_strut_SA = float(sum(strut_SAs)) if strut_SAs else 0.0
            if total_le_SA + total_strut_SA > 0:
                le_to_strut_mass_ratio = total_le_SA / (total_le_SA + total_strut_SA)
            else:
                le_to_strut_mass_ratio = 1.0

    # Default ratio if still None (no tube data, no explicit value)
    if le_to_strut_mass_ratio is None:
        le_to_strut_mass_ratio = 0.7

    le_mass = non_canopy_mass_min_sensor * le_to_strut_mass_ratio
    strut_mass = non_canopy_mass_min_sensor * (1 - le_to_strut_mass_ratio)

    if n_strut_nodes == 0:
        le_mass += strut_mass
        strut_mass = 0.0

    #### Distributing the mass over the nodes
    if tube_data is not None and le_seg_SA is not None:
        # --- Surface-area-proportional distribution ---
        total_le_SA = float(np.sum(le_seg_SA))
        if total_le_SA > 0:
            seg_mass = le_mass * le_seg_SA / total_le_SA
        else:
            seg_mass = np.full(len(le_seg_SA), le_mass / len(le_seg_SA))

        # Lump each segment's mass 50/50 to its two endpoint nodes
        le_node_masses = np.zeros(n_le)
        le_tip_te_masses = np.zeros(2)

        le_tip_te_masses[0] = 0.5 * seg_mass[0]  # TE[0] wingtip
        le_node_masses[0] = 0.5 * seg_mass[0] + 0.5 * seg_mass[1]
        for i in range(1, n_le - 1):
            le_node_masses[i] = 0.5 * seg_mass[i] + 0.5 * seg_mass[i + 1]
        le_node_masses[n_le - 1] = 0.5 * seg_mass[n_le - 1] + 0.5 * seg_mass[n_le]
        le_tip_te_masses[1] = 0.5 * seg_mass[n_le]  # TE[-1] wingtip

        # Strut mass proportional to each strut's cylindrical surface area
        strut_node_masses = np.zeros(n_le)
        if n_strut_nodes > 0 and strut_SAs:
            total_strut_SA = sum(strut_SAs)
            if total_strut_SA > 0:
                for SA_j, rib_idx in zip(strut_SAs, strut_rib_indices):
                    # Each strut's mass split to LE + TE nodes, so halve here
                    strut_node_masses[rib_idx] = (
                        0.5 * strut_mass * SA_j / total_strut_SA
                    )
    else:
        # --- Uniform distribution (fallback) ---
        n_total_le_nodes = n_le + 2
        le_mass_uniform = le_mass / n_total_le_nodes
        le_node_masses = np.full(n_le, le_mass_uniform)
        le_tip_te_masses = np.array([le_mass_uniform, le_mass_uniform])

        strut_node_masses = np.zeros(n_le)
        if n_strut_nodes > 0:
            smass_per_node = 0.5 * (strut_mass / n_strut_nodes)
            for i in range(n_le):
                if is_strut[i]:
                    strut_node_masses[i] = smass_per_node

    ## Find leading-edge points where the sensor mass is at
    n_ribs = len(LE_points)
    sensor_points_indices = [int(n_ribs // 2), int(n_ribs // 2) - 1]

    return (
        total_canopy_mass,
        panel_canopy_mass_list,
        le_node_masses,
        strut_node_masses,
        le_tip_te_masses,
        sensor_points_indices,
        LE_points,
        TE_points,
        is_strut,
        total_area,
        le_to_strut_mass_ratio,
    )


def distribute_mass_over_nodes(
    le_node_masses,
    strut_node_masses,
    le_tip_te_masses,
    sensor_mass,
    panel_canopy_mass_list,
    sensor_points_indices,
    LE_points,
    TE_points,
):
    """
    Distribute mass over wing nodes.

    Parameters
    ----------
    le_node_masses : array, shape (n_le,)
        LE tube mass per LE node (surface-area-proportional or uniform).
    strut_node_masses : array, shape (n_le,)
        Strut mass contribution per rib (half-strut mass; 0 for non-strut ribs).
    le_tip_te_masses : array, shape (2,)
        LE tube mass for the two wingtip TE nodes [tip_0, tip_n-1].
    sensor_mass : float
        Total sensor mass split among sensor_points_indices.
    panel_canopy_mass_list : list
        Canopy mass per panel (1/4 goes to each corner node).
    sensor_points_indices : list
        Indices of LE nodes carrying the sensor.
    LE_points, TE_points : arrays
        Node positions.
    """

    import numpy as np

    nodes = []

    n_le = len(LE_points)  # Number of leading-edge nodes
    n_te = len(TE_points)  # Should match n_le if CSV is consistent

    #
    # 1) Distribute mass to LE nodes
    #
    for i, le_point in enumerate(LE_points):
        node_mass = le_node_masses[i]
        # Sensor mass portion (if this LE node is flagged for sensor)
        if i in sensor_points_indices:
            node_mass += sensor_mass / len(sensor_points_indices)
        # Strut mass portion
        node_mass += strut_node_masses[i]

        # ---- Canopy mass portion for LE node i ----
        # This LE node belongs to panel i-1 (if i > 0) and panel i (if i < n_le-1)
        if i > 0:
            node_mass += 0.25 * panel_canopy_mass_list[i - 1]
        if i < n_le - 1:
            node_mass += 0.25 * panel_canopy_mass_list[i]

        # Store node with mass
        nodes.append([le_point, node_mass])

    #
    # 2) Distribute mass to TE nodes
    #
    for i, te_point in enumerate(TE_points):
        node_mass = 0.0

        if i == 0:
            # Outer TE tip -> gets LE tube tip mass
            node_mass += le_tip_te_masses[0]
        elif i == (n_te - 1):
            # Outer TE tip -> gets LE tube tip mass
            node_mass += le_tip_te_masses[1]

        # Always add strut mass (will be 0.0 for non-strut ribs)
        node_mass += strut_node_masses[i]

        # ---- Canopy mass portion for TE node i ----
        # If i>0, we add 0.25 from panel i-1
        if i > 0:
            node_mass += 0.25 * panel_canopy_mass_list[i - 1]
        # If i<n_te-1, we add 0.25 from panel i
        if i < n_te - 1:
            node_mass += 0.25 * panel_canopy_mass_list[i]

        nodes.append([te_point, node_mass])

    # Enforce y-symmetry: average mirror pairs (index i <-> n_le-1-i)
    # so left/right mass distributions are identical.
    for i in range(n_le // 2):
        j = n_le - 1 - i
        # LE mirror pair
        avg_le = 0.5 * (nodes[i][1] + nodes[j][1])
        nodes[i][1] = avg_le
        nodes[j][1] = avg_le
        # TE mirror pair (TE nodes start at index n_le)
        avg_te = 0.5 * (nodes[n_le + i][1] + nodes[n_le + j][1])
        nodes[n_le + i][1] = avg_te
        nodes[n_le + j][1] = avg_te

    return nodes


def compute_structural_node_masses(
    wing_sections_data,
    wing_airfoils_data=None,
    total_wing_mass=10.0,
    canopy_kg_p_sqm=0.05,
    le_to_strut_mass_ratio=None,
    sensor_mass=0.0,
    struc_config=None,
):
    """
    Compute per-node masses for the structural wing mesh.

    Non-printing, non-plotting helper for use in YAML generation.
    Node IDs follow wing_particles convention: odd = LE, even = TE.

    Parameters
    ----------
    wing_sections_data : list
        Section data rows (filtered to structural ribs).
    wing_airfoils_data : list or None
        Airfoil data rows for is_strut extraction.
    total_wing_mass : float
        Total wing mass budget in kg.
    canopy_kg_p_sqm : float
        Canopy fabric mass in kg per square meter.
    le_to_strut_mass_ratio : float or None
        If None, auto-derived from tube surface areas.
    sensor_mass : float
        Sensor mass in kg.
    struc_config : dict or None
        Config dict with wing_particles, leading_edge_tubes, strut_tubes
        (same format as struc_geometry_all_in_surfplan.yaml).

    Returns
    -------
    node_masses : dict
        {node_id (1-based): mass_kg}
    used_le_to_strut_ratio : float
    """
    is_strut = _extract_is_strut_flags(wing_sections_data, wing_airfoils_data)

    tube_data = _extract_tube_data(struc_config) if struc_config else None

    (
        total_canopy_mass,
        panel_canopy_mass_list,
        le_node_masses,
        strut_node_masses,
        le_tip_te_masses,
        sensor_points_indices,
        LE_points,
        TE_points,
        is_strut,
        total_area,
        used_le_to_strut_ratio,
    ) = find_mass_distributions(
        wing_sections_data,
        total_wing_mass,
        canopy_kg_p_sqm,
        le_to_strut_mass_ratio,
        sensor_mass,
        is_strut=is_strut,
        tube_data=tube_data,
    )

    nodes = distribute_mass_over_nodes(
        le_node_masses,
        strut_node_masses,
        le_tip_te_masses,
        sensor_mass,
        panel_canopy_mass_list,
        sensor_points_indices,
        LE_points,
        TE_points,
    )

    # Build node_id -> mass mapping
    # distribute_mass_over_nodes returns: first n_le LE nodes, then n_le TE nodes
    n_le = len(LE_points)
    node_masses = {}
    for i in range(n_le):
        le_node_id = 2 * i + 1  # odd: 1, 3, 5, ...
        te_node_id = 2 * i + 2  # even: 2, 4, 6, ...
        node_masses[le_node_id] = nodes[i][1]
        node_masses[te_node_id] = nodes[n_le + i][1]

    # Enforce y-symmetry: average mirror pairs so left/right masses match.
    # Ribs are sorted by LE_y, so index i mirrors index (n_le - 1 - i).
    for i in range(n_le // 2):
        j = n_le - 1 - i
        le_l, le_r = 2 * i + 1, 2 * j + 1
        te_l, te_r = 2 * i + 2, 2 * j + 2
        avg_le = 0.5 * (node_masses[le_l] + node_masses[le_r])
        avg_te = 0.5 * (node_masses[te_l] + node_masses[te_r])
        node_masses[le_l] = avg_le
        node_masses[le_r] = avg_le
        node_masses[te_l] = avg_te
        node_masses[te_r] = avg_te

    return node_masses, used_le_to_strut_ratio


def calculate_cg(nodes):
    """
    Calculate the center of gravity (CG) of the nodes.

    Parameters:
    nodes (list): A list of nodes, where each node is [position (array), mass (float)].

    Returns:
    tuple: The x, y, z coordinates of the center of gravity.
    """
    total_mass = sum(node[1] for node in nodes)
    x_cg = sum(node[0][0] * node[1] for node in nodes) / total_mass
    y_cg = sum(node[0][1] * node[1] for node in nodes) / total_mass
    z_cg = sum(node[0][2] * node[1] for node in nodes) / total_mass

    return x_cg, y_cg, z_cg


def plot_nodes(
    nodes,
    x_cg,
    y_cg,
    z_cg,
    desired_point,
    LE_points=None,
    TE_points=None,
    is_strut=None,
):
    """
    Parameters
    ----------
    nodes : list
        A list of [ [x,y,z], mass ] for each node.
    x_cg, y_cg, z_cg : float
        Center of gravity coordinates.
    LE_points : array-like, shape (n_ribs, 3), optional
        Leading-edge points corresponding to each rib.
    TE_points : array-like, shape (n_ribs, 3), optional
        Trailing-edge points corresponding to each rib.
    is_strut : array-like of bool, shape (n_ribs,), optional
        Boolean flags indicating where struts exist.
    """

    # Quick helper for setting 3D axes to equal scale
    def set_axes_equal_3d(ax):
        """
        Make axes of 3D plot have equal scale so that spheres appear as spheres,
        cubes as cubes, etc.  This is one possible solution to Matplotlib's
        3D aspect ratio problem.
        """
        x_limits = ax.get_xlim3d()
        y_limits = ax.get_ylim3d()
        z_limits = ax.get_zlim3d()

        x_range = abs(x_limits[1] - x_limits[0])
        y_range = abs(y_limits[1] - y_limits[0])
        z_range = abs(z_limits[1] - z_limits[0])

        max_range = max(x_range, y_range, z_range)
        x_middle = np.mean(x_limits)
        y_middle = np.mean(y_limits)
        z_middle = np.mean(z_limits)

        ax.set_xlim3d([x_middle - max_range / 2, x_middle + max_range / 2])
        ax.set_ylim3d([y_middle - max_range / 2, y_middle + max_range / 2])
        ax.set_zlim3d([z_middle - max_range / 2, z_middle + max_range / 2])

    # Create a new figure + 3D axis
    fig = plt.figure(figsize=(8, 6))
    ax = fig.add_subplot(111, projection="3d")

    # Convert node data into arrays for plotting
    node_positions = np.array([node[0] for node in nodes])  # shape (N, 3)
    node_masses = np.array([node[1] for node in nodes])  # shape (N,)

    # Scatter plot of all nodes, colored by mass
    sc = ax.scatter(
        node_positions[:, 0],
        node_positions[:, 1],
        node_positions[:, 2],
        c=node_masses,
        cmap=cm.cool,
        s=50,
        alpha=0.9,
        label="Wing Nodes colored by mass",
    )

    # Plot the CG as a big red 'X'
    ax.scatter(
        x_cg,
        y_cg,
        z_cg,
        c="red",
        marker="x",
        s=100,
        label=f"Center of Gravity ({x_cg:.2f}, {y_cg:.2f}, {z_cg:.2f})",
    )

    # Plot the point around which the inertia tensor is calculated
    ax.scatter(
        desired_point[0],
        desired_point[1],
        desired_point[2],
        c="green",
        marker="x",
        s=100,
        label=f"Point of Inertia Calculation ({desired_point[0]:.2f}, {desired_point[1]:.2f}, {desired_point[2]:.2f})",
    )
    # Optional: draw the LE “backbone” if provided
    if LE_points is not None and len(LE_points) > 1:
        LE_points = np.array(LE_points)  # shape (n_ribs, 3)
        # add first and last TE_points to this list
        if TE_points is not None:
            LE_points_with_tips = np.vstack([TE_points[0], LE_points, TE_points[-1]])
        ax.plot(
            LE_points_with_tips[:, 0],
            LE_points_with_tips[:, 1],
            LE_points_with_tips[:, 2],
            c="black",
            linewidth=5,
            label="Leading Edge",
        )

    # Optional: draw each strut if we have both LE, TE, and is_strut info
    if (
        LE_points is not None
        and TE_points is not None
        and is_strut is not None
        and len(LE_points) == len(TE_points) == len(is_strut)
    ):
        for i in range(len(LE_points)):
            if is_strut[i]:
                ax.plot(
                    [LE_points[i, 0], TE_points[i, 0]],
                    [LE_points[i, 1], TE_points[i, 1]],
                    [LE_points[i, 2], TE_points[i, 2]],
                    c="black",
                    linewidth=3,
                    label="Strut" if i == 1 else "",
                )
            else:
                ax.plot(
                    [LE_points[i, 0], TE_points[i, 0]],
                    [LE_points[i, 1], TE_points[i, 1]],
                    [LE_points[i, 2], TE_points[i, 2]],
                    c="grey",
                    linewidth=0.5,
                    linestyle="-",
                    label="Rib lines" if i == 0 else "",
                )

    # Add TE line
    if TE_points is not None and len(TE_points) > 1:
        TE_points = np.array(TE_points)
        ax.plot(
            TE_points[:, 0],
            TE_points[:, 1],
            TE_points[:, 2],
            c="grey",
            linewidth=0.5,
            label="Trailing Edge",
        )

    # Add color bar for node masses
    cbar = plt.colorbar(sc, ax=ax, shrink=0.6)
    cbar.set_label("Node Mass (kg)")

    # Label axes and set 3D axes to equal scale
    ax.set_xlabel("X (m)")
    ax.set_ylabel("Y (m)")
    ax.set_zlabel("Z (m)")
    ax.grid(False)
    set_axes_equal_3d(ax)

    ax.legend()
    plt.tight_layout()
    plt.show()


def calculate_inertia(nodes, desired_point):
    """
    Calculate the inertia tensor of the nodes about a desired point.

    Parameters:
    nodes (list): A list of nodes, where each node is [position (array), mass (float)].
    desired_point (array-like): The point [x, y, z] about which the inertia tensor is calculated.

    Returns:
    np.ndarray: The 3x3 inertia tensor.
    """
    desired_point = np.array(desired_point)  # Ensure it's a numpy array
    inertia_tensor = np.zeros((3, 3))  # Initialize 3x3 tensor

    for node in nodes:
        position = node[0]  # Node position [x, y, z]
        mass = node[1]  # Node mass

        # Vector from desired point to node
        r = position - desired_point
        r_x, r_y, r_z = r

        # Update the inertia tensor
        inertia_tensor[0, 0] += mass * (r_y**2 + r_z**2)  # Ixx
        inertia_tensor[1, 1] += mass * (r_x**2 + r_z**2)  # Iyy
        inertia_tensor[2, 2] += mass * (r_x**2 + r_y**2)  # Izz
        inertia_tensor[0, 1] -= mass * r_x * r_y  # Ixy
        inertia_tensor[0, 2] -= mass * r_x * r_z  # Ixz
        inertia_tensor[1, 2] -= mass * r_y * r_z  # Iyz

    # Symmetric off-diagonal elements
    inertia_tensor[1, 0] = inertia_tensor[0, 1]
    inertia_tensor[2, 0] = inertia_tensor[0, 2]
    inertia_tensor[2, 1] = inertia_tensor[1, 2]

    return inertia_tensor


def main(
    yaml_file_path,
    total_wing_mass=10.0,
    canopy_kg_p_sqm=0.05,
    le_to_strut_mass_ratio=None,
    sensor_mass=0.5,
    desired_point=[0, 0, 0],
    is_show_plot=True,
    include_bridle_mass=True,
):
    """
    Calculate CG and inertia using a config_kite.yaml file.

    Parameters
    ----------
    le_to_strut_mass_ratio : float or None
        If None, auto-derived from tube surface areas in struc_geometry_all_in_surfplan.yaml.
        If that file is absent, falls back to 0.7.
    """
    # Load geometry from YAML
    with open(yaml_file_path, "r") as f:
        config = yaml.safe_load(f)
    # Extract wing_sections data
    wing_sections = config["wing_sections"]["data"]
    wing_airfoils = config.get("wing_airfoils", {}).get("data", [])
    is_strut = _extract_is_strut_flags(wing_sections, wing_airfoils)

    # Try to load structural geometry for tube data
    tube_data = None
    struc_yaml_path = Path(yaml_file_path).with_name(
        "struc_geometry_all_in_surfplan.yaml"
    )
    if struc_yaml_path.exists():
        with open(struc_yaml_path, "r") as f:
            struc_config = yaml.safe_load(f)
        tube_data = _extract_tube_data(struc_config)

    (
        total_canopy_mass,
        panel_canopy_mass_list,
        le_node_masses,
        strut_node_masses,
        le_tip_te_masses,
        sensor_points_indices,
        LE_points,
        TE_points,
        is_strut,
        total_area,
        used_le_to_strut_ratio,
    ) = find_mass_distributions(
        wing_sections,
        total_wing_mass,
        canopy_kg_p_sqm,
        le_to_strut_mass_ratio,
        sensor_mass,
        is_strut=is_strut,
        tube_data=tube_data,
    )
    wing_nodes = distribute_mass_over_nodes(
        le_node_masses,
        strut_node_masses,
        le_tip_te_masses,
        sensor_mass,
        panel_canopy_mass_list,
        sensor_points_indices,
        LE_points,
        TE_points,
    )
    nodes = list(wing_nodes)

    bridle_mass_source = None
    total_bridle_mass = 0.0
    n_bridle_segments = 0
    if include_bridle_mass:
        bridle_config, bridle_mass_source = _select_bridle_source_config(
            config, yaml_file_path
        )
        bridle_nodes, total_bridle_mass, n_bridle_segments = _extract_bridle_mass_nodes(
            bridle_config
        )
        nodes.extend(bridle_nodes)

    x_cg, y_cg, z_cg = calculate_cg(nodes)
    inertia_tensor = calculate_inertia(nodes, desired_point)

    # printing
    print(f"\n--- INPUT ---")
    print(f"total_wing_mass: {total_wing_mass}")
    print(f"canopy_kg_p_sqm: {canopy_kg_p_sqm}")
    ratio_source = (
        "auto (surface area)" if le_to_strut_mass_ratio is None else "user-specified"
    )
    print(f"le_to_strut_mass_ratio: {used_le_to_strut_ratio:.4f} ({ratio_source})")
    print(f"sensor_mass: {sensor_mass}")
    print(f"include_bridle_mass: {include_bridle_mass}")
    print(
        f"tube_data: {'loaded from struc_geometry_all_in_surfplan.yaml' if tube_data is not None else 'not available (uniform fallback)'}"
    )

    print(f"\n--- OUTPUT --- ")
    wing_node_mass = sum([node[1] for node in wing_nodes])
    total_node_mass = sum([node[1] for node in nodes])
    print(
        f"Wing node mass:         {wing_node_mass:.2f} kg (target total_wing_mass={total_wing_mass:.2f} kg)"
    )
    print(
        f"Bridle line mass:       {total_bridle_mass:.3f} kg ({n_bridle_segments} bridle segments)"
    )
    if include_bridle_mass:
        source_label = (
            bridle_mass_source if bridle_mass_source is not None else "not found"
        )
        print(f"Bridle source YAML:     {source_label}")
    print(f"Total node mass:        {total_node_mass:.2f} kg (wing + optional bridle)")
    print(f"center of gravity: [{x_cg:.2f}, {y_cg:.2f}, {z_cg:.2f}] [m]")
    print(f"point around intertia is calculated: {desired_point} [m]")
    print("Inertia tensor:")
    print("Ixx: {:.2f}".format(inertia_tensor[0, 0]))
    print("Iyy: {:.2f}".format(inertia_tensor[1, 1]))
    print("Izz: {:.2f}".format(inertia_tensor[2, 2]))
    print("Ixy: {:.2f}".format(inertia_tensor[0, 1]))
    print("Ixz: {:.2f}".format(inertia_tensor[0, 2]))
    print("Iyz: {:.2f}".format(inertia_tensor[1, 2]))

    if is_show_plot:
        plot_nodes(
            nodes,
            x_cg,
            y_cg,
            z_cg,
            desired_point,
            LE_points=LE_points,
            TE_points=TE_points,
            is_strut=is_strut,  # so we can draw strut lines
        )
