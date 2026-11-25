"""Milestone theo title."""
from . import client


def _find(cfg, title):
    for m in client.rest("GET", f"{client.repo_path(cfg)}/milestones?state=all&per_page=100"):
        if m["title"] == title:
            return m
    raise client.GhError(f"Milestone '{title}' không tồn tại")


def milestone_number(cfg, title):
    return _find(cfg, title)["number"]


def milestone_open_issues(cfg, title):
    return _find(cfg, title)["open_issues"]


def ensure_milestone(cfg, title):
    try:
        return milestone_number(cfg, title)
    except client.GhError:
        return client.rest("POST", f"{client.repo_path(cfg)}/milestones", {"title": title})["number"]


def set_milestone(cfg, n, title):
    client.rest("PATCH", f"{client.repo_path(cfg)}/issues/{n}", {"milestone": milestone_number(cfg, title)})
