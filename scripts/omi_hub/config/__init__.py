"""Nạp cấu hình khai báo đi kèm plugin."""
import json
from pathlib import Path

WORKFLOW_PATH = Path(__file__).with_name("workflow.json")
TEMPLATES_PATH = Path(__file__).with_name("templates.json")
PR_TEMPLATE_PATH = Path(__file__).with_name("pr_template.json")


def load_workflow(path=WORKFLOW_PATH):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_templates(path=TEMPLATES_PATH):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_pr_template(path=PR_TEMPLATE_PATH):
    return json.loads(Path(path).read_text(encoding="utf-8"))
