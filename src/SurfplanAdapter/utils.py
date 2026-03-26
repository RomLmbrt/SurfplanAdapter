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


PALETTE = {
    "Black": "#000000",
    "Orange": "#E69F00",
    "Sky Blue": "#56B4E9",
    "Bluish Green": "#009E73",
    "Yellow": "#F0E442",
    "Blue": "#0072B2",
    "Vermillion": "#D55E00",
    "Reddish Purple": "#CC79A7",
}


def hex_to_rgba(hex_color, alpha=1.0):
    """Convert a hex color to RGBA values in [0, 1]."""
    hex_color = hex_color.lstrip("#")
    value_len = len(hex_color)
    rgb = tuple(
        int(hex_color[i : i + value_len // 3], 16) / 255.0
        for i in range(0, value_len, value_len // 3)
    )
    return rgb + (alpha,)


def get_color(color_name, alpha=1.0):
    """Return RGBA for a named palette color (defaults to black)."""
    return hex_to_rgba(PALETTE.get(color_name, "#000000"), alpha)


def get_color_list():
    """Return the default plotting palette as hex strings."""
    return list(PALETTE.values())


def visualize_palette():
    """Show the configured color palette."""
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(20, 2))
    for i, (color_name, color_hex) in enumerate(PALETTE.items()):
        ax.add_patch(plt.Rectangle((i * 2, 0), 2, 2, color=color_hex))
        ax.text(
            i * 2 + 1,
            1,
            color_name,
            color="white",
            ha="center",
            va="center",
            fontsize=12,
            fontweight="bold",
        )
    ax.set_xlim(0, 2 * len(PALETTE))
    ax.set_ylim(0, 2)
    ax.axis("off")
    plt.show()


def set_plot_style(use_latex=False):
    """
    Set matplotlib defaults for SurfplanAdapter plots.

    By default this keeps LaTeX disabled so new users do not need a TeX installation.
    Set ``use_latex=True`` to enable TeX rendering when available.
    """
    import matplotlib.pyplot as plt
    from cycler import cycler

    color_cycle = [
        PALETTE["Black"],
        PALETTE["Orange"],
        PALETTE["Sky Blue"],
        PALETTE["Bluish Green"],
        PALETTE["Yellow"],
        PALETTE["Blue"],
        PALETTE["Vermillion"],
        PALETTE["Reddish Purple"],
    ]

    plt.rcParams.update(
        {
            "text.usetex": bool(use_latex),
            "font.family": "serif",
            "font.serif": (
                ["Computer Modern Roman"] if use_latex else ["DejaVu Serif"]
            ),
            "axes.titlesize": 15,
            "axes.labelsize": 13,
            "axes.linewidth": 1.0,
            "axes.edgecolor": "#C5C5C5",
            "axes.labelcolor": "black",
            "axes.autolimit_mode": "round_numbers",
            "axes.xmargin": 0,
            "axes.ymargin": 0,
            "axes.grid": True,
            "axes.grid.axis": "both",
            "grid.alpha": 0.5,
            "grid.color": "#C5C5C5",
            "grid.linestyle": "-",
            "grid.linewidth": 1.0,
            "lines.linewidth": 1,
            "lines.markersize": 6,
            "figure.titlesize": 15,
            "pgf.texsystem": "pdflatex",
            "pgf.rcfonts": False,
            "figure.figsize": (15, 5),
            "axes.prop_cycle": cycler("color", color_cycle),
            "xtick.color": "#C5C5C5",
            "ytick.color": "#C5C5C5",
            "xtick.labelcolor": "black",
            "ytick.labelcolor": "black",
            "xtick.labelsize": 13,
            "ytick.labelsize": 13,
            "xtick.top": True,
            "xtick.bottom": True,
            "ytick.left": True,
            "ytick.right": True,
            "xtick.direction": "in",
            "ytick.direction": "in",
            "legend.fontsize": 15,
        }
    )


def set_plot_style_no_latex():
    """Convenience wrapper for style without TeX dependency."""
    set_plot_style(use_latex=False)


def apply_palette(ax, colors=None):
    """Apply a sequence of colors to existing lines on a matplotlib axis."""
    if colors is None:
        colors = get_color_list()
    for line, color in zip(ax.get_lines(), colors):
        line.set_color(color)
    ax.figure.canvas.draw_idle()
