"""Đọc các node GraphQL dùng chung (item Project, field value, issue type)."""


def in_project(nodes, project_id):
    return next((x for x in nodes if x["project"]["id"] == project_id), None)


def field_value(it, key, sub):
    v = (it or {}).get(key)
    return v.get(sub) if v else None


def type_name(node):
    return (node.get("issueType") or {}).get("name")


def status_of(node, project_id):
    return field_value(in_project(node["projectItems"]["nodes"], project_id), "status", "name")
