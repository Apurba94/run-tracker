import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout

from run_tracker.cli import main
from run_tracker.core import Tracker


class TrackerTests(unittest.TestCase):
    def setUp(self):
        self.t = Tracker(":memory:")

    def test_params_metrics_and_tags(self):
        rid = self.t.start("cnn", {"lr": 0.01, "layers": [64, 32]}, name="baseline", tags=["gpu"], git=False)
        for step, loss in enumerate([0.9, 0.5, 0.3]):
            self.t.log(rid, step, loss=loss)
        self.t.log(rid, acc=0.91)
        self.t.finish(rid, notes="converged")
        r = self.t.run(rid)
        self.assertEqual(r["params"], {"lr": 0.01, "layers": [64, 32]})
        self.assertEqual(r["metrics"], {"loss": 0.3, "acc": 0.91})
        self.assertEqual((r["status"], r["notes"], r["tags"]), ("finished", "converged", ["gpu"]))
        self.assertEqual(self.t.history(rid, "loss"), [(0, 0.9), (1, 0.5), (2, 0.3)])

    def test_best_and_filters(self):
        a = self.t.start("exp", {"lr": 0.1}, git=False)
        b = self.t.start("exp", {"lr": 0.01}, tags=["final"], git=False)
        self.t.start("other", git=False)
        self.t.log(a, acc=0.8)
        self.t.log(b, acc=0.9)
        self.assertEqual(self.t.best("exp", "acc")["id"], b)
        self.assertEqual(self.t.best("exp", "acc", "min")["id"], a)
        self.assertEqual([r["id"] for r in self.t.runs(tag="final")], [b])
        self.assertIsNone(self.t.best("exp", "f1"))

    def test_compare_shows_varying_params(self):
        a = self.t.start("exp", {"lr": 0.1, "seed": 1}, git=False)
        b = self.t.start("exp", {"lr": 0.01, "seed": 1}, git=False)
        self.t.log(a, acc=0.8)
        header, rows = self.t.compare([a, b])
        self.assertEqual(header, ["run", "lr", "acc"])
        self.assertEqual(rows[1], [str(b), "0.01", ""])

    def test_delete_cascades(self):
        rid = self.t.start("x", {"a": 1}, git=False)
        self.t.log(rid, m=1)
        self.t.delete(rid)
        self.assertEqual(self.t.db.execute("SELECT COUNT(*) FROM metrics").fetchone()[0], 0)
        with self.assertRaises(KeyError):
            self.t.run(rid)

    def test_cli(self):
        with tempfile.TemporaryDirectory() as d:
            db = os.path.join(d, "r.sqlite")
            with redirect_stdout(io.StringIO()) as buf:
                main(["--db", db, "start", "exp", "lr=0.1", "opt=adam"])
            rid = buf.getvalue().strip()
            main(["--db", db, "log", rid, "acc=0.75", "--step", "1"])
            main(["--db", db, "finish", rid])
            with redirect_stdout(io.StringIO()) as buf:
                main(["--db", db, "show", rid])
            r = json.loads(buf.getvalue())
            self.assertEqual(r["params"], {"lr": 0.1, "opt": "adam"})
            self.assertEqual(r["metrics"]["acc"], 0.75)


if __name__ == "__main__":
    unittest.main()
