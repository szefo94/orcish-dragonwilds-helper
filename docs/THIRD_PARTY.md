# Third-party dependencies

Dependencies are installed from PyPI by Setup.cmd and are not bundled in source releases. Requirements are in `src/requirements.txt`; optional DirectML installation is managed by Setup.cmd. Transitive dependencies and OCR model notices must also be checked before distributing a binary/model bundle.

Primary projects: NumPy, OpenCV, RapidOCR/ONNX Runtime, MSS, psutil, Pillow and DXcam. Consult each installed distribution's license metadata for the exact version in use. This source review does not certify the licensing of a future bundled executable.

Fishing implementation was written for this project. Public examples informed the architecture; no third-party fishing bot source or game artwork was copied.
