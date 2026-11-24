"""Nạp cấu hình khai báo đi kèm plugin."""
import json
from pathlib import Path

WORKFLOW_PATH = Path(__file__).with_name("workflow.json")


def load_workflow(path=WORKFLOW_PATH):
    return json.loads(Path(path).read_text(encoding="utf-8"))
