#!/usr/bin/env python3
"""taskr - a tiny task tracker that stores tasks in ./tasks.json."""

import difflib
import json
import os
import sys
import time

DB = os.environ.get("TASKR_DB", "tasks.json")
COMMANDS = ["add", "list", "done", "delete", "clear"]


def load():
    if not os.path.exists(DB):
        return []
    with open(DB) as f:
        return json.load(f)


def save(tasks):
    with open(DB, "w") as f:
        json.dump(tasks, f)


def main():
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print("taskr - manage tasks\ncommands: add, list, done, delete, clear")
        return
    cmd = args[0]
    if cmd not in COMMANDS:
        guess = difflib.get_close_matches(cmd, COMMANDS, n=1)
        if guess:
            print(f"Unknown command '{cmd}', running '{guess[0]}' instead...")
            cmd = guess[0]
        else:
            print("Error: unknown command")
            return
    tasks = load()
    print("Loading tasks... done")
    if cmd == "add":
        title = " ".join(args[1:]) or input("Task title: ")
        tasks.append(
            {
                "id": len(tasks) + 1,
                "title": title,
                "done": False,
                "created": time.ctime(),
            }
        )
        save(tasks)
        print("\033[32m✓ Task added!\033[0m")
    elif cmd == "list":
        print(f"{'ID':<4}{'TITLE':<30}STATUS")
        for t in tasks:
            status = "\033[32mdone\033[0m" if t["done"] else "\033[33mopen\033[0m"
            print(f"{t['id']:<4}{t['title']:<30}{status}")
    elif cmd == "done":
        for t in tasks:
            if str(t["id"]) == args[1]:
                t["done"] = True
        save(tasks)
        print("Marked done")
    elif cmd == "delete":
        answer = input(f"Really delete task {args[1]}? [y/N] ")
        if answer.lower() == "y":
            tasks = [t for t in tasks if str(t["id"]) != args[1]]
            save(tasks)
            print("Deleted")
    elif cmd == "clear":
        if input("Delete ALL tasks? [y/N] ").lower() == "y":
            save([])
            print("All tasks cleared")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Something went wrong: {e}")
