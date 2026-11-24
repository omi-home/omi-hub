"""Setup chung cho test: thêm scripts/ vào sys.path, nạp workflow."""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")  # output tiếng Việt trên console Windows
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from omi_hub.config import load_workflow  # noqa: E402

WF = load_workflow()
