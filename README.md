# run-tracker

**Track every experiment run (parameters, metrics over time, tags, notes and the exact git
commit) in a single SQLite file, then list, compare and pick the best run.**

Part of the *Research Automation Toolkit*: 100 open tools for daily research work.

## Why

Simulation sweeps, model training and parameter studies produce dozens of runs. Results end up in
file names like `results_lr001_final2.csv` and nobody remembers which settings produced the figure in
the paper. Hosted trackers require accounts and send data off-site. `run-tracker` is a dependency-free
local alternative whose database you can archive with the project.

## Features

- Runs with experiment name, display name, status, timestamps, tags, notes
- Parameters of any JSON type; metrics as scalars or per step (learning curves) with full history
- Automatic git commit (marked `+dirty` with uncommitted changes)
- `compare` shows only the parameters that differ plus final metrics; `best` by any metric (max or min)
- Python API for use inside scripts, CLI for shell pipelines

## Usage

```python
from run_tracker import Tracker
t = Tracker("runs.sqlite")
rid = t.start("cnn-cifar", {"lr": 1e-3, "batch": 64}, tags=["gpu"])
for epoch in range(10):
    t.log(rid, epoch, loss=..., val_acc=...)
t.finish(rid)
```

```bash
pip install .
run-tracker --db runs.sqlite list -e cnn-cifar
run-tracker --db runs.sqlite compare 3 4 7
run-tracker --db runs.sqlite best cnn-cifar val_acc
```

## Testing

```bash
python -m unittest discover -s tests -t .
```

## License

MIT (c) JANIN A APURBA
