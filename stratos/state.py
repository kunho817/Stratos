"""Project state on disk: .stratos/tasks.json (the task list) and .stratos/decisions.jsonl (what was decided, why)."""
import json
import time
from pathlib import Path


class Store:
    def __init__(self, state_dir):
        self.dir = Path(state_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.tasks_path = self.dir / "tasks.json"
        self.decisions_path = self.dir / "decisions.jsonl"

    def tasks(self):
        if not self.tasks_path.exists():
            return []
        return json.loads(self.tasks_path.read_text(encoding="utf-8"))

    def _save(self, tasks):
        tmp = self.tasks_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(tasks, ensure_ascii=False, indent=1), encoding="utf-8")
        # Windows refuses the replace while another program (antivirus, indexer) still reads the file: retry briefly
        for wait in (0.05, 0.1, 0.2, 0.4, 0.8, 1.6):
            try:
                tmp.replace(self.tasks_path)
                return
            except PermissionError:
                time.sleep(wait)
        tmp.replace(self.tasks_path)

    def add_task(self, title, goal, files, protected, tests, role='coder', after=(), output=None, replace=()):
        """files: paths shown to the model (it may rewrite them); protected: paths shown read-only (the tests);
        tests: pytest targets that must pass. role: which model plays this task. after: task ids that must be
        done before this one runs. output: a search task's path; the generator's stdout is written there.
        replace: paths this task may replace wholesale with a shorter whole file."""
        tasks = self.tasks()
        task = {"id": f"T{len(tasks) + 1:03d}", "title": title, "goal": goal, "files": list(files),
                "protected": list(protected), "tests": list(tests), "role": role, "after": list(after),
                "status": "todo", "created": time.time()}
        if output is not None:
            task["output"] = output
        if replace:
            task["replace"] = list(replace)
        tasks.append(task)
        self._save(tasks)
        return task

    def get(self, task_id):
        for t in self.tasks():
            if t["id"] == task_id:
                return t
        raise KeyError(task_id)

    def update(self, task_id, **fields):
        tasks = self.tasks()
        for t in tasks:
            if t["id"] == task_id:
                t.update(fields)
                self._save(tasks)
                return t
        raise KeyError(task_id)

    def decide(self, **fields):
        with self.decisions_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": round(time.time(), 3), **fields}, ensure_ascii=False) + "\n")
