# ITAC Automated Controls Testing Framework
Simulated core banking database (users, accounts, loans, transactions) with four automated control tests and a review dashboard.

| Control | Test |
|---|---|
| ITAC-01 | Recompute loan interest independently (Decimal, 0.01 tolerance) and compare to system value |
| ITAC-02 | Input validation: zero, negative and above-cap amounts |
| ITAC-03 | Segregation of duties: maker != approver |
| ITAC-04 | Authorization limits: amount <= approver limit, approver required above 100,000 |

Data is seeded with planted exceptions so every control has something to find. Tolerance-band cases are also planted to show correct passes.

## Run
    cd backend && pip install -r requirements.txt && uvicorn main:app --reload
    cd frontend && npm install && npm run dev      # http://localhost:5173

API: `GET /api/run` runs and logs all controls, `GET /api/history` lists past runs, `POST /api/reseed` regenerates the database.

Tests: `cd backend && pytest`. Loans support `simple` and `emi` (reducing-balance) interest methods.
