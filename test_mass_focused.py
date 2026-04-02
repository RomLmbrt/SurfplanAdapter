"""Focused test of mass integration via create_struc_geometry_yaml."""

import matplotlib

matplotlib.use("Agg")
import yaml
from pathlib import Path
from SurfplanAdapter.process_wing import main_process_wing
from SurfplanAdapter.process_bridle_lines import main_process_bridle_lines
from SurfplanAdapter.generate_yaml.create_struc_geometry_yaml import (
    main as create_struc_main,
)

PROJECT_DIR = Path(".")
data_dir = PROJECT_DIR / "data" / "TUDELFT_V3_KITE"
save_dir = PROJECT_DIR / "processed_data" / "TUDELFT_V3_KITE"

print("Step 1: Processing wing...", flush=True)
ribs_data = main_process_wing.main(
    surfplan_txt_file_path=data_dir / "TUDELFT_V3_KITE.txt",
    profile_load_dir=data_dir / "profiles",
    profile_save_dir=save_dir / "profiles",
)
print(f"  Got {len(ribs_data)} ribs", flush=True)

print("Step 2: Processing bridle lines...", flush=True)
bridle_lines = main_process_bridle_lines.main(data_dir / "TUDELFT_V3_KITE.txt")
print(f"  Got {len(bridle_lines)} bridle lines", flush=True)

print("Step 3: Creating struc_geometry.yaml WITH mass params...", flush=True)
create_struc_main(
    ribs_data=ribs_data,
    bridle_lines=bridle_lines,
    yaml_file_path=save_dir / "config_kite.yaml",
    airfoil_type="masure_regression",
    total_wing_mass=10.0,
    canopy_kg_p_sqm=0.05,
    le_to_strut_mass_ratio=None,
    sensor_mass=0.0,
)
print("  Done!", flush=True)

print("\nStep 4: Validating struc_geometry.yaml...", flush=True)
with open(save_dir / "struc_geometry.yaml") as f:
    config = yaml.safe_load(f)

elems = config["wing_elements"]
total_m = sum(row[4] for row in elems["data"])
n_elems = len(elems["data"])
print(f"  Elements: {n_elems}")
print(f"  Total element mass: {total_m:.4f} kg (target: 10.0 kg)")

print("\n  Element breakdown:")
for row in elems["data"]:
    print(f"    {row[0]:12s}  l0={row[1]:.4f}  m={row[4]:.6f}")

print("\nALL DONE")
