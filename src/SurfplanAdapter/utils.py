import numpy as np


def clean_numeric_line(line, delimiter=None):
    """
    Clean a line containing numeric data by handling multiple periods, converting commas to periods,
    and automatically detecting delimiters.

    Args:
        line (str): The input line to clean
        delimiter (str, optional): The delimiter used to split the line.
                                 If None, automatically detects between ";" and ","

    Returns:
        list: List of cleaned string parts that can be converted to float
    """
    # Auto-detect delimiter if not provided
    if delimiter is None:
        # Count occurrences of potential delimiters
        semicolon_count = line.count(";")

        # If we have semicolons, this is likely TUDELFT format (semicolon delimited, comma decimals)
        if semicolon_count > 0:
            delimiter = ";"
        # Otherwise use commas as delimiter (default_kite format)
        else:
            delimiter = ","

    # Split the line by the delimiter first
    parts = line.split(delimiter)
    cleaned_parts = []

    for part in parts:
        part = part.strip()
        if part and any(char.isdigit() for char in part):
            # For semicolon-delimited format, convert commas to periods for decimal numbers
            if delimiter == ";":
                part = part.replace(",", ".")

            # Handle multiple periods in numbers (malformed floats)
            if part.count(".") > 1:
                first_period = part.find(".")
                if first_period != -1:
                    before_period = part[: first_period + 1]
                    after_period = part[first_period + 1 :].replace(".", "")
                    part = before_period + after_period
            cleaned_parts.append(part)
        elif part:  # Keep non-empty non-numeric parts as is
            cleaned_parts.append(part)

    return cleaned_parts


def line_parser(line):
    """
    Parse a line from the .txt file from Surfplan.

    Parameters:
        line (str): The line to parse.

    Returns:
        list: A list of floats containing the parsed values.
    """
    cleaned_parts = clean_numeric_line(line)
    return list(map(float, cleaned_parts))


def transform_coordinate_system_surfplan_to_VSM(coord_surfplan):
    """
    Transform coordinate from Surfplan reference frame to VSM reference frame

    Surfplan reference frame :
    # z: along the chord / parallel to flow direction
    # x: left
    # y: upwards

    VSM reference frame :
    # Body EastNorthUp (ENU) Reference Frame (aligned with Earth direction)
    # x: along the chord / parallel to flow direction
    # y: left
    # z: upwards

    Parameters:
    coord_surfplan (tuple): a tuple of three floats representing the x, y, and z coordinates of the rib endpoint in Surfplan reference frame.

    Returns:
    coord_vsm (tuple): a tuple of three floats representing the x, y, and z coordinates of the rib endpoint in VSM reference frame.
    """

    # Rotation matrix
    R = np.array([[0, 0, -1], [-1, 0, 0], [0, 1, 0]])
    coord_vsm = np.dot(R, coord_surfplan)

    return coord_vsm


def rotate_coordinate_around_y_vsm(coord_vsm, angle_rad):
    """
    Rotate a VSM coordinate around the global y-axis by angle_rad.

    This is a pure rotation (no translation), so y remains unchanged while
    x and z are rotated in the x-z plane.
    """
    c = np.cos(angle_rad)
    s = np.sin(angle_rad)
    R_y = np.array([[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]])
    return np.dot(R_y, np.asarray(coord_vsm, dtype=float))


def _interpolated_midspan_le_te_points(ribs_data, tol=1e-9):
    """
    Get LE/TE points at y=0 using interpolation between closest negative and
    positive spanwise ribs when an exact mid-span rib is not present.
    """
    samples = []
    for rib in ribs_data:
        if "LE" not in rib or "TE" not in rib:
            continue
        le = np.asarray(rib["LE"], dtype=float)
        te = np.asarray(rib["TE"], dtype=float)
        if le.shape != (3,) or te.shape != (3,):
            continue
        y_span = 0.5 * (le[1] + te[1])
        samples.append((float(y_span), le, te))

    if not samples:
        return None, None

    closest = min(samples, key=lambda item: abs(item[0]))
    if abs(closest[0]) <= tol:
        return closest[1], closest[2]

    negatives = [item for item in samples if item[0] < 0.0]
    positives = [item for item in samples if item[0] > 0.0]

    if negatives and positives:
        y_neg, le_neg, te_neg = max(negatives, key=lambda item: item[0])
        y_pos, le_pos, te_pos = min(positives, key=lambda item: item[0])
        denom = y_pos - y_neg
        if abs(denom) > tol:
            t = -y_neg / denom
            le_mid = le_neg + t * (le_pos - le_neg)
            te_mid = te_neg + t * (te_pos - te_neg)
            return le_mid, te_mid

    # Fallback for one-sided or pathological data: use nearest available rib.
    return closest[1], closest[2]


def compute_midspan_chord_alignment_rotation_about_y(ribs_data, tol=1e-9):
    """
    Compute a yaw angle around y_vsm that aligns +x_vsm with the mid-span chord
    direction (LE->TE) projected onto the x-z plane.
    """
    le_mid, te_mid = _interpolated_midspan_le_te_points(ribs_data, tol=tol)
    if le_mid is None or te_mid is None:
        return 0.0

    chord = np.asarray(te_mid - le_mid, dtype=float)
    chord_x = chord[0]
    chord_z = chord[2]
    if np.hypot(chord_x, chord_z) <= tol:
        return 0.0

    # After rotation by theta about y:
    # z' = -sin(theta)*x + cos(theta)*z = 0  -> theta = atan2(z, x)
    return float(np.arctan2(chord_z, chord_x))
