BTC Race 24h bot

Files:
- main.py: deterministic cbBTC strategy
- vendor/makefun_bars.py: unmodified SDK shim from the competition kit

Run the official local grader from the extracted competition kit:
node cli/makefun.mjs grade-local --kit . --bot /path/to/btc-race-bot --driver docker

The final race prices are unknown, so this strategy cannot guarantee a profit or prize.
