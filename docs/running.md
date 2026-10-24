# Running it

## Offline (the only mode)
```bash
sudo apt-get install -y gnucobol          # Debian/Ubuntu; macOS: brew install gnucobol
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest -q
python scripts/count_tests.py             # prints the real total
legacyagents demo
legacyagents bench --out results.json     # all measurements
legacyagents bench --check results.json   # deterministic numbers must match
python scripts/render_docs.py             # regenerate README block and docs/results.md
```

COBOL programs are compiled into `build/` on first use (`cobc -x -free`). Data files are generated
from fixed seeds into a temporary directory each run, so nothing on disk is reused or shared.

## Environment
| Variable | Purpose | Default |
| --- | --- | --- |
| `LEGACY_DEMO_RO_PASSWORD` | Password for the read-only SQL profile `AGENTRO` | `demo-ro` (demo only) |

## Optional next steps (not built)
- Swap the in-process broker for RabbitMQ (free, `docker run rabbitmq`) behind `MQClient`.
- Point the screen tool at a TN5250 emulator library against a real IBM i test partition.
Neither needs a paid service, but neither is wired up yet.
