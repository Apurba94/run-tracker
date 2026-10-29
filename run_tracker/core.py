"""Runs with parameters, metrics (optionally per step), tags, notes and git state, in one SQLite file."""
import datetime
import json
import os
import sqlite3
import subprocess

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (id INTEGER PRIMARY KEY AUTOINCREMENT, experiment TEXT NOT NULL, name TEXT,
    started TEXT NOT NULL, finished TEXT, status TEXT NOT NULL DEFAULT 'running', git_commit TEXT, notes TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS params (run_id INTEGER REFERENCES runs(id) ON DELETE CASCADE, key TEXT, value TEXT,
    PRIMARY KEY (run_id, key));
CREATE TABLE IF NOT EXISTS metrics (run_id INTEGER REFERENCES runs(id) ON DELETE CASCADE, key TEXT, step INTEGER,
    value REAL, logged TEXT);
CREATE TABLE IF NOT EXISTS tags (run_id INTEGER REFERENCES runs(id) ON DELETE CASCADE, tag TEXT, PRIMARY KEY (run_id, tag));
CREATE INDEX IF NOT EXISTS metrics_run ON metrics(run_id, key);
"""


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _git_commit():
    try:
        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=5)
        if r.returncode == 0:
            dirty = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, timeout=5).stdout
            return r.stdout.strip() + ("+dirty" if dirty.strip() else "")
    except (OSError, subprocess.SubprocessError):
        pass
    return None


class Tracker:
    def __init__(self, path=None):
        self.db = sqlite3.connect(path or os.environ.get("RUN_TRACKER_DB", "runs.sqlite"))
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.executescript(SCHEMA)

    def close(self):
        self.db.close()

    def start(self, experiment, params=None, name=None, tags=(), git=True):
        with self.db:
            cur = self.db.execute("INSERT INTO runs (experiment, name, started, git_commit) VALUES (?, ?, ?, ?)",
                                  (experiment, name, _now(), _git_commit() if git else None))
            rid = cur.lastrowid
            for k, v in (params or {}).items():
                self.db.execute("INSERT INTO params VALUES (?, ?, ?)", (rid, k, json.dumps(v)))
            for t in tags:
                self.db.execute("INSERT OR IGNORE INTO tags VALUES (?, ?)", (rid, t))
        return rid

    def log(self, run_id, step=None, **metrics):
        with self.db:
            for k, v in metrics.items():
                self.db.execute("INSERT INTO metrics VALUES (?, ?, ?, ?, ?)", (run_id, k, step, float(v), _now()))

    def finish(self, run_id, status="finished", notes=None):
        with self.db:
            self.db.execute("UPDATE runs SET finished = ?, status = ? WHERE id = ?", (_now(), status, run_id))
            if notes:
                self.db.execute("UPDATE runs SET notes = TRIM(notes || char(10) || ?, char(10) || ' ') WHERE id = ?", (notes, run_id))

    def run(self, run_id):
        r = self.db.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if not r:
            raise KeyError(run_id)
        d = dict(r)
        d["params"] = {k: json.loads(v) for k, v in self.db.execute("SELECT key, value FROM params WHERE run_id = ?", (run_id,))}
        d["metrics"] = self.final_metrics(run_id)
        d["tags"] = [t for (t,) in self.db.execute("SELECT tag FROM tags WHERE run_id = ? ORDER BY tag", (run_id,))]
        return d

    def final_metrics(self, run_id):
        """Last logged value of each metric."""
        rows = self.db.execute("SELECT key, value FROM metrics WHERE run_id = ? ORDER BY COALESCE(step, -1), rowid",
                               (run_id,))
        out = {}
        for k, v in rows:
            out[k] = v
        return out

    def history(self, run_id, key):
        return [(s, v) for s, v in self.db.execute("SELECT step, value FROM metrics WHERE run_id = ? AND key = ? "
                                                   "ORDER BY COALESCE(step, -1), rowid", (run_id, key))]

    def runs(self, experiment=None, tag=None, status=None):
        sql = "SELECT DISTINCT r.id FROM runs r LEFT JOIN tags t ON t.run_id = r.id WHERE 1=1"
        args = []
        for cond, val in (("r.experiment = ?", experiment), ("t.tag = ?", tag), ("r.status = ?", status)):
            if val:
                sql += " AND " + cond
                args.append(val)
        return [self.run(rid) for (rid,) in self.db.execute(sql + " ORDER BY r.id", args)]

    def best(self, experiment, metric, mode="max"):
        rs = [r for r in self.runs(experiment) if metric in r["metrics"]]
        if not rs:
            return None
        return (max if mode == "max" else min)(rs, key=lambda r: r["metrics"][metric])

    def compare(self, run_ids):
        """Table of params and final metrics that differ (or are present) across runs."""
        runs = [self.run(i) for i in run_ids]
        pkeys = sorted({k for r in runs for k in r["params"]})
        mkeys = sorted({k for r in runs for k in r["metrics"]})
        varying = [k for k in pkeys if len({json.dumps(r["params"].get(k)) for r in runs}) > 1]
        header = ["run"] + varying + mkeys
        rows = [[str(r["id"])] + [str(r["params"].get(k, "")) for k in varying] +
                ["%.4g" % r["metrics"][k] if k in r["metrics"] else "" for k in mkeys] for r in runs]
        return header, rows

    def delete(self, run_id):
        with self.db:
            self.db.execute("DELETE FROM runs WHERE id = ?", (run_id,))
