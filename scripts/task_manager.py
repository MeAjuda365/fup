#!/usr/bin/env python3
"""
FUP Task Manager — CLI tool for managing FUP tasks stored in ~/.fup/tasks.json

Usage:
    python task_manager.py create --title "..." [--description "..."] [--due "2026-04-01"] [--priority normal] [--owner user]
    python task_manager.py list [--status pending,in_progress] [--all]
    python task_manager.py get --id fup-XXXX
    python task_manager.py update --id fup-XXXX [--status in_progress] [--add-missing "info"] [--remove-missing "info"] [--add-response "text"]
    python task_manager.py complete --id fup-XXXX
    python task_manager.py escalate --id fup-XXXX --to "Apex"
    python task_manager.py log --id fup-XXXX --event "reminder_sent" --channel "gmail" [--note "..."]
    python task_manager.py delete --id fup-XXXX
    python task_manager.py overdue
    python task_manager.py stats
"""

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path


# Storage

def get_tasks_path():
    tasks_dir = Path.home() / ".fup"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    return tasks_dir / "tasks.json"


def load_tasks():
    path = get_tasks_path()
    if not path.exists():
        return {"tasks": [], "meta": {"created_at": now_iso(), "total_created": 0}}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_tasks(data):
    path = get_tasks_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def short_id():
    return str(uuid.uuid4())[:8]


# CRUD

def cmd_create(args):
    data = load_tasks()
    task_id = f"fup-{short_id()}"
    task = {
        "task_id": task_id,
        "title": args.title,
        "description": args.description or args.title,
        "owner": args.owner or "user",
        "status": "pending",
        "priority": args.priority or "normal",
        "created_at": now_iso(),
        "last_updated": now_iso(),
        "due_date": args.due or None,
        "missing_info": [m.strip() for m in args.missing.split(",") if m.strip()] if args.missing else [],
        "reminders_sent": [],
        "responses_received": [],
        "escalated_to": None,
        "completed_at": None,
        "metadata": {}
    }
    if task["missing_info"]:
        task["status"] = "waiting_for_input"
    data["tasks"].append(task)
    data["meta"]["total_created"] = data["meta"].get("total_created", 0) + 1
    save_tasks(data)
    print(json.dumps({"ok": True, "task_id": task_id, "task": task}, indent=2))


def cmd_list(args):
    data = load_tasks()
    tasks = data["tasks"]
    if not args.all:
        active_statuses = set(
            args.status.split(",") if args.status
            else ["pending", "in_progress", "waiting_for_input", "blocked"]
        )
        tasks = [t for t in tasks if t["status"] in active_statuses]

    def sort_key(t):
        priority_rank = {"urgent": 0, "high": 1, "normal": 2, "low": 3}
        status_rank = {"blocked": 0, "waiting_for_input": 1, "in_progress": 2,
                       "pending": 3, "escalated": 4, "completed": 5}
        return (status_rank.get(t["status"], 9), priority_rank.get(t["priority"], 9), t["created_at"])

    tasks = sorted(tasks, key=sort_key)
    print(json.dumps({"ok": True, "count": len(tasks), "tasks": tasks}, indent=2))


def cmd_get(args):
    data = load_tasks()
    task = next((t for t in data["tasks"] if t["task_id"] == args.id), None)
    if not task:
        print(json.dumps({"ok": False, "error": f"Task {args.id} not found"}))
        sys.exit(1)
    print(json.dumps({"ok": True, "task": task}, indent=2))


def cmd_update(args):
    data = load_tasks()
    task = next((t for t in data["tasks"] if t["task_id"] == args.id), None)
    if not task:
        print(json.dumps({"ok": False, "error": f"Task {args.id} not found"}))
        sys.exit(1)
    if args.status: task["status"] = args.status
    if args.title: task["title"] = args.title
    if args.description: task["description"] = args.description
    if args.priority: task["priority"] = args.priority
    if args.due: task["due_date"] = args.due
    if args.owner: task["owner"] = args.owner
    if args.add_missing:
        for item in [x.strip() for x in args.add_missing.split(",") if x.strip()]:
            if item not in task["missing_info"]:
                task["missing_info"].append(item)
        task["status"] = "waiting_for_input"
    if args.remove_missing:
        to_remove = {x.strip() for x in args.remove_missing.split(",") if x.strip()}
        task["missing_info"] = [m for m in task["missing_info"] if m not in to_remove]
        if not task["missing_info"] and task["status"] == "waiting_for_input":
            task["status"] = "in_progress"
    if args.add_response:
        task["responses_received"].append({"received_at": now_iso(), "content": args.add_response})
    if args.metadata_key and args.metadata_value:
        task["metadata"][args.metadata_key] = args.metadata_value
    task["last_updated"] = now_iso()
    save_tasks(data)
    print(json.dumps({"ok": True, "task": task}, indent=2))


def cmd_complete(args):
    data = load_tasks()
    task = next((t for t in data["tasks"] if t["task_id"] == args.id), None)
    if not task:
        print(json.dumps({"ok": False, "error": f"Task {args.id} not found"}))
        sys.exit(1)
    task["status"] = "completed"
    task["completed_at"] = now_iso()
    task["last_updated"] = now_iso()
    save_tasks(data)
    print(json.dumps({"ok": True, "task": task}, indent=2))


def cmd_escalate(args):
    data = load_tasks()
    task = next((t for t in data["tasks"] if t["task_id"] == args.id), None)
    if not task:
        print(json.dumps({"ok": False, "error": f"Task {args.id} not found"}))
        sys.exit(1)
    task["status"] = "escalated"
    task["escalated_to"] = args.to
    task["last_updated"] = now_iso()
    task["metadata"]["escalation_target"] = args.to
    task["metadata"]["escalated_at"] = now_iso()
    save_tasks(data)
    print(json.dumps({"ok": True, "task": task}, indent=2))


def cmd_log(args):
    data = load_tasks()
    task = next((t for t in data["tasks"] if t["task_id"] == args.id), None)
    if not task:
        print(json.dumps({"ok": False, "error": f"Task {args.id} not found"}))
        sys.exit(1)
    entry = {"sent_at": now_iso(), "event": args.event,
             "channel": args.channel or "chat", "message_preview": (args.note or "")[:100]}
    task["reminders_sent"].append(entry)
    task["last_updated"] = now_iso()
    save_tasks(data)
    print(json.dumps({"ok": True, "logged": entry}, indent=2))


def cmd_delete(args):
    data = load_tasks()
    before = len(data["tasks"])
    data["tasks"] = [t for t in data["tasks"] if t["task_id"] != args.id]
    if len(data["tasks"]) == before:
        print(json.dumps({"ok": False, "error": f"Task {args.id} not found"}))
        sys.exit(1)
    save_tasks(data)
    print(json.dumps({"ok": True, "deleted": args.id}))


def cmd_overdue(args):
    data = load_tasks()
    now = datetime.now(timezone.utc)
    overdue = []
    for t in data["tasks"]:
        if t["status"] in ("completed", "escalated"): continue
        if t.get("due_date"):
            try:
                due = datetime.fromisoformat(t["due_date"])
                if due.tzinfo is None: due = due.replace(tzinfo=timezone.utc)
                if due < now: overdue.append(t)
            except ValueError: pass
    print(json.dumps({"ok": True, "count": len(overdue), "overdue_tasks": overdue}, indent=2))


def cmd_stats(args):
    data = load_tasks()
    tasks = data["tasks"]
    by_status = {}
    for t in tasks:
        by_status[t["status"]] = by_status.get(t["status"], 0) + 1
    completed = [t for t in tasks if t["status"] == "completed"]
    avg_hours = None
    if completed:
        durations = []
        for t in completed:
            if t.get("completed_at") and t.get("created_at"):
                try:
                    s = datetime.fromisoformat(t["created_at"])
                    e = datetime.fromisoformat(t["completed_at"])
                    durations.append((e - s).total_seconds() / 3600)
                except: pass
        if durations: avg_hours = round(sum(durations) / len(durations), 1)
    print(json.dumps({"ok": True, "total_tasks": len(tasks),
                      "by_status": by_status, "avg_completion_hours": avg_hours}, indent=2))


# CLI

def main():
    parser = argparse.ArgumentParser(description="FUP Task Manager")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("create")
    p.add_argument("--title", required=True)
    p.add_argument("--description")
    p.add_argument("--due")
    p.add_argument("--priority", choices=["low", "normal", "high", "urgent"], default="normal")
    p.add_argument("--owner", default="user")
    p.add_argument("--missing")

    p = sub.add_parser("list")
    p.add_argument("--status")
    p.add_argument("--all", action="store_true")

    p = sub.add_parser("get")
    p.add_argument("--id", required=True)

    p = sub.add_parser("update")
    p.add_argument("--id", required=True)
    p.add_argument("--status")
    p.add_argument("--title")
    p.add_argument("--description")
    p.add_argument("--priority")
    p.add_argument("--due")
    p.add_argument("--owner")
    p.add_argument("--add-missing")
    p.add_argument("--remove-missing")
    p.add_argument("--add-response")
    p.add_argument("--metadata-key")
    p.add_argument("--metadata-value")

    p = sub.add_parser("complete")
    p.add_argument("--id", required=True)

    p = sub.add_parser("escalate")
    p.add_argument("--id", required=True)
    p.add_argument("--to", required=True)

    p = sub.add_parser("log")
    p.add_argument("--id", required=True)
    p.add_argument("--event", required=True)
    p.add_argument("--channel")
    p.add_argument("--note")

    p = sub.add_parser("delete")
    p.add_argument("--id", required=True)

    sub.add_parser("overdue")
    sub.add_parser("stats")

    args = parser.parse_args()
    commands = {
        "create": cmd_create, "list": cmd_list, "get": cmd_get,
        "update": cmd_update, "complete": cmd_complete, "escalate": cmd_escalate,
        "log": cmd_log, "delete": cmd_delete, "overdue": cmd_overdue, "stats": cmd_stats,
    }
    if args.command not in commands:
        parser.print_help()
        sys.exit(1)
    commands[args.command](args)


if __name__ == "__main__":
    main()
