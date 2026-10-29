"""Command-line interface for run-tracker."""
import argparse
import csv
import json
import sys

from .core import Tracker


def _kv(pairs):
    out = {}
    for p in pairs:
        k, _, v = p.partition("=")
        try:
            out[k] = json.loads(v)
        except ValueError:
            out[k] = v
    return out


def _table(header, rows):
    widths = [max(len(str(x)) for x in col) for col in zip(header, *rows)]
    lines = ["  ".join(str(h).ljust(w) for h, w in zip(header, widths))]
    lines += ["  ".join(str(c).ljust(w) for c, w in zip(r, widths)) for r in rows]
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="run-tracker", description="Track experiment runs in SQLite.")
    ap.add_argument("--db", help="database file (default runs.sqlite or $RUN_TRACKER_DB)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("start")
    s.add_argument("experiment")
    s.add_argument("params", nargs="*", help="key=value")
    s.add_argument("--name")
    s.add_argument("-t", "--tag", action="append", default=[])
    lg = sub.add_parser("log")
    lg.add_argument("run_id", type=int)
    lg.add_argument("metrics", nargs="+", help="key=value")
    lg.add_argument("--step", type=int)
    f = sub.add_parser("finish")
    f.add_argument("run_id", type=int)
    f.add_argument("--status", default="finished", choices=["finished", "failed", "killed"])
    f.add_argument("--notes")
    ls = sub.add_parser("list")
    ls.add_argument("-e", "--experiment")
    ls.add_argument("-t", "--tag")
    cmp_ = sub.add_parser("compare")
    cmp_.add_argument("run_ids", type=int, nargs="+")
    cmp_.add_argument("--csv", action="store_true")
    b = sub.add_parser("best")
    b.add_argument("experiment")
    b.add_argument("metric")
    b.add_argument("--min", action="store_true")
    sh = sub.add_parser("show")
    sh.add_argument("run_id", type=int)
    args = ap.parse_args(argv)

    t = Tracker(args.db)
    try:
        if args.cmd == "start":
            print(t.start(args.experiment, _kv(args.params), args.name, args.tag))
        elif args.cmd == "log":
            t.log(args.run_id, args.step, **{k: float(v) for k, v in _kv(args.metrics).items()})
        elif args.cmd == "finish":
            t.finish(args.run_id, args.status, args.notes)
        elif args.cmd == "list":
            rows = [[r["id"], r["experiment"], r["name"] or "", r["status"], r["started"], r["git_commit"] or "",
                     " ".join("%s=%.4g" % kv for kv in r["metrics"].items())] for r in t.runs(args.experiment, args.tag)]
            print(_table(["id", "experiment", "name", "status", "started", "commit", "metrics"], rows))
        elif args.cmd == "compare":
            header, rows = t.compare(args.run_ids)
            if args.csv:
                w = csv.writer(sys.stdout)
                w.writerow(header)
                w.writerows(rows)
            else:
                print(_table(header, rows))
        elif args.cmd == "best":
            r = t.best(args.experiment, args.metric, "min" if args.min else "max")
            print(json.dumps(r, indent=2) if r else "no runs with metric %s" % args.metric)
        elif args.cmd == "show":
            print(json.dumps(t.run(args.run_id), indent=2))
    except KeyError as exc:
        print("unknown run %s" % exc, file=sys.stderr)
        return 1
    finally:
        t.close()
    return 0
