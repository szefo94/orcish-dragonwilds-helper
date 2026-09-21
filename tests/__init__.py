# Test package: make the program modules importable the way app.py imports them.
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src' / 'orcpresser'))
