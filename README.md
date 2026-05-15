# LUC v0.1.0 — Lead-Lag Analyzer

Desktop GUI analyzer for Binance Spot lead-lag behavior between **BTCUSDT** (leader) and **BTCU** (follower).

## Features
- Binance `bookTicker` websocket for BTCUSDT and BTCU.
- Rolling 5-minute history (`bid`, `ask`, `mid`, `spread`, `timestamp_ms`).
- Price lead-lag table across configured lags.
- Dark compact GUI with statuses, ticks/sec, uptime, START/STOP/CLEAR.
- Event log panel (last 300 lines).

## Run
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

## Notes
- Analysis only. No API keys, no private endpoints, no orders.
