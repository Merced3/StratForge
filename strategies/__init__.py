# strategies package

# How many trades to know if a strategy is good or not?
#   - **To call a strategy bad:** 50–100 trades is often enough to flag negative EV if the average is meaningfully below 0.
#   - **To call a strategy good:** usually **200–500 trades** minimum. Options strategies are noisy; 300–1000 is safer.
#   - **To call it robust:** 500+ trades across different days/conditions (trend, chop, high/low vol).
