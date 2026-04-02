"""Quick test of mass integration in struc_geometry.yaml pipeline."""

import matplotlib

matplotlib.use("Agg")
from pathlib import Path
from SurfplanAdapter.process_wing import main_process_wing
from SurfplanAdapter.process_bridle_lines import main_process_bridle_lines
from SurfplanAdapter.generate_yaml import main_generate_yaml
import yaml

PROJECT_DIR = Path(".")
data_dir = PROJECT_DIR / "data" / "TUDELFT_V3_KITE"
save_dir = PROJECT_DIR / "processed_data" / "TUDELFT_V3_KITE"

print("Processing wing...")
ribs_data = main_process_wing.main(
    surfplan_txt_file_path=data_dir / "TUDELFT_V3_KITE.txt",
    profile_load_dir=data_dir / "profiles",
    profile_save_dir=save_dir / "profiles",
)
print("Processing bridle lines...")
bridle_lines = main_process_bridle_lines.main(data_dir / "TUDELFT_V3_KITE.txt")

print("Generating YAML with mass params...")
main_generate_yaml.main(
    ribs_data=ribs_data,
    bridle_lines=bridle_lines,
    yaml_file_path=save_dir / "config_kite.yaml",
    airfoil_type="masure_regression",
    total_wing_mass=10.0,
    canopy_kg_p_sqm=0.05,
    sensor_mass=0.0,
)

# Validate
print("\n=== VALIDATION ===")
with open(save_dir / "struc_geometry.yaml", "r") as f:
    config = yaml.safe_load(f)

wing_elements = config["wing_elements"]
print(f"Headers: {wing_elements['headers']}")
total_mass = sum(row[4] for row in wing_elements["data"])
print(f"Total element mass: {total_mass:.4f} kg (target: 10.0 kg)")
print(f"Number of elements: {len(wing_elements['data'])}")

# Show first few elements
print("\nFirst 5 elements:")
for row in wing_elements["data"][:5]:
    print(f"  {row}")
print("...")
print("Last 5 elements:")
for row in wing_elements["data"][-5:]:
    print(f"  {row}")

print("\nDONE")
