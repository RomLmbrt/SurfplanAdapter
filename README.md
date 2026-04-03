# SurfplanAdapter: Kite Design Processing and Analysis Tool

[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Purpose

SurfplanAdapter converts design files from [SurfPlan](http://www.surfplan.com.au/sp/) to yaml format, designed for use in aerodynamic and structural analysis of kites. The yaml files are used in:
- [Vortex-Step-Method](https://github.com/awegroup/Vortex-Step-Method) for aerodynamic simulations.
- [kite_fem](https://github.com/awegroup/kite_fem) for structural analysis.
- [Particle_System_Simulator](https://github.com/awegroup/Particle_System_Simulator) for structural analysis.
- [ASKITE](https://github.com/awegroup/ASKITE) for coupled aero-structural analysis, integrating the toolchains mentioned above.
  
## Installation Instructions

   Linux: 
    ```bash
    git clone git@github.com:jellepoland/SurfplanAdapter.git && \
    cd SurfplanAdapter && \
    python3 -m venv venv && \
    source venv/bin/activate && \
    pip install -e .[dev]
    ```
    Windows:
    ```bash
    git clone git@github.com:jellepoland/SurfplanAdapter.git; `
    cd SurfplanAdapter; `
    python -m venv venv; `
    .\venv\Scripts\Activate.ps1; `
    pip install -e .[dev]
    ```

## Quick-test-run
Run the following from the repository root, to test the workflow with the [TUDELFT_V3_KITE](https://awegroup.github.io/TUDELFT_V3_KITE/)
```bash
    python -m scripts.process_surfplan_files --kite_name=TUDELFT_V3_KITE
```

## Processing your Surfplan Design

1. Export your kite design from SurfPlan:
   - Export the main design as a `.txt` file.
   - Export each airfoil profile as a `.dat` file (through the XFLR5 output).

2. Create a new kite folder in `data/` (e.g., `data/MY_NEW_KITE`) and place your exported files

3. Adjust the `config.yaml` in your kite folder to specify any custom settings, e.g. canopy density.

4. Run the processing pipeline from the repository root:

    ```bash
    python -m scripts.process_surfplan_files --kite_name=MY_NEW_KITE
    ```

## Dependencies

Core dependencies (see [pyproject.toml](pyproject.toml) for complete list):
- **numpy**: Numerical computations and array operations
- **matplotlib**: Plotting and visualization
- **pyyaml**: YAML file handling
- **scipy**: Scientific computing utilities

Optional dependencies:
- **VSM** (Vortex-Step-Method): For aerodynamic analysis
- **pytest**: For running tests (dev)

## LEI Airfoil Parametrization

The tool uses a 6-parameter model for leading-edge inflatable (LEI) airfoils, based on the work of [K.R.G. Masure](https://resolver.tudelft.nl/uuid:865d59fc-ccff-462e-9bac-e81725f1c0c9):

- **t**: Leading edge tube diameter (normalized by chord)
- **η**: Chordwise camber position (0 to 1)
- **κ**: Maximum camber height (normalized by chord)
- **δ**: Trailing edge reflex angle (degrees)
- **λ**: Trailing edge camber tension (0 to 1)
- **φ**: Leading edge curvature tension (0 to 1)

These parameters are automatically fitted to CAD-sliced profiles from Surfplan.


## Citation

If you use this project in your research, please cite:
```bibtex
@software{surfplanadapter2025,
  author = {Poland, Jelle and Mooijman, Tom and Tan, Corentin},
  title = {SurfplanAdapter},
  year = {2026},
  url = {https://github.com/jellepoland/SurfplanAdapter}
}
```

Citation details can also be found in [CITATION.cff](CITATION.cff).

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## WAIVER

Technische Universiteit Delft hereby disclaims all copyright interest in the package written by the Author(s).

Prof.dr. H.G.C. (Henri) Werij, Dean of Aerospace Engineering

### Copyright

Copyright (c) 2024-2025-2026 Jelle Poland (TU Delft)

Copyright (c) 2024 Tom Mooijman (Kitepower)

Copyright (c) 2024 Corentin Tan (BeyondTheSea)

## Help and Documentation

- [AWE Group Developer Guide](https://awegroup.github.io/developer-guide/)
- [Changelog](changelog.md)
- [Implementation Summary](IMPLEMENTATION_SUMMARY.md)
