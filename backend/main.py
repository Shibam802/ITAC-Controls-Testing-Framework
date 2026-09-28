"""ITAC Automated Controls Testing Framework - simulated core banking DB + control tests."""
import os, random, sqlite3, datetime as dt
from decimal import Decimal, ROUND_HALF_UP
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

DB = os.path.join(os.path.dirname(__file__), "bank.db")
HARD_CAP = 5_000_000      # max single-transaction amount (input control)
AUTO_LIMIT = 100_000      # above this, a transaction must carry an approver
TOL = Decimal("0.01")     # rounding tolerance for interest recompute

app = FastAPI(title="ITAC Controls Testing")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

SCHEMA = """
DROP TABLE IF EXISTS transactions; DROP TABLE IF EXISTS loans;
DROP TABLE IF EXISTS accounts; DROP TABLE IF EXISTS users;
CREATE TABLE users(id INTEGER PRIMARY KEY, name TEXT, role TEXT, approval_limit REAL);
CREATE TABLE accounts(id INTEGER PRIMARY KEY, holder TEXT, balance REAL);
CREATE TABLE loans(id INTEGER PRIMARY KEY, account_id INT, principal REAL, annual_rate REAL,
                   months_elapsed INT, system_interest REAL, method TEXT, term_months INT);
CREATE TABLE transactions(id INTEGER PRIMARY KEY, account_id INT, amount REAL, kind TEXT,
                          maker_id INT, approver_id INT, created TEXT);
"""

def conn():
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE IF NOT EXISTS control_runs(run_at TEXT, control_id TEXT, population INT, exceptions INT)")
    return c

CENT = Decimal("0.01")

def expected_interest(p, rate, months, method="simple", term=None):
    """Independent recompute. simple: P x r x t. emi: interest accrued over `months` instalments on a reducing balance."""
    p, r = Decimal(str(p)), Decimal(str(rate))
    if method == "simple":
        return (p * r / 100 * months / 12).quantize(CENT, ROUND_HALF_UP)
    i = r / 1200
    emi = (p * i * (1 + i) ** term / ((1 + i) ** term - 1)).quantize(CENT, ROUND_HALF_UP)
    bal, total = p, Decimal(0)
    for _ in range(months):
        intr = (bal * i).quantize(CENT, ROUND_HALF_UP); total += intr; bal -= emi - intr
    return total

def seed(seed_val=7):
    r = random.Random(seed_val); c = conn(); c.executescript(SCHEMA)
    c.executemany("INSERT INTO users VALUES(?,?,?,?)", [
        (1, "Anita Rao", "maker", 0), (2, "Karan Mehta", "maker", 0),
        (3, "Priya Nair", "branch manager", 250000), (4, "Vikram Shah", "branch manager", 250000),
        (5, "Sunita Iyer", "regional head", 2000000), (6, "Dev Malhotra", "auditor", 0)])
    for i in range(1, 41):
        c.execute("INSERT INTO accounts VALUES(?,?,?)", (i, f"Customer {i:03d}", round(r.uniform(5e3, 9e5), 2)))
        p, rate, term = r.choice([200000, 500000, 750000, 1200000, 2500000]), r.choice([8.5, 9.25, 10.5, 11.75, 12.0]), r.choice([12, 24, 36])
        m, meth = r.randint(3, term), ("emi" if i % 2 == 0 else "simple")
        s = expected_interest(p, rate, m, meth, term)
        if i % 9 == 0: s += Decimal(r.randint(60, 900))      # planted: system overstates interest
        elif i % 14 == 0: s -= Decimal(r.randint(20, 300))   # planted: system understates
        elif i % 7 == 0: s += Decimal("0.01")                # within rounding tolerance -> passes
        elif i % 11 == 0 and meth == "emi": s = expected_interest(p, rate, m)  # planted: flat interest used on a reducing-balance loan
        c.execute("INSERT INTO loans VALUES(?,?,?,?,?,?,?,?)", (i, i, p, rate, m, float(s), meth, term))
    base = dt.date(2026, 6, 1)
    for i in range(1, 321):
        maker = r.choice([1, 2, 3]); amt = round(r.uniform(500, 180000), 2)
        appr = r.choice([a for a in (3, 4, 5) if a != maker])
        if amt <= AUTO_LIMIT and r.random() < .3: appr = None
        if i % 37 == 0: amt = -round(r.uniform(500, 90000), 2)           # negative amount
        if i % 53 == 0: amt = r.choice([0.0, 7_500_000.0])              # zero / above hard cap
        if i % 29 == 0: maker, appr = 3, 3                              # self-approval
        if i % 41 == 0: amt, appr = round(r.uniform(300000, 900000), 2), r.choice([3, 4])  # above approver limit
        if i % 61 == 0: amt, appr = round(r.uniform(150000, 400000), 2), None              # no approver
        c.execute("INSERT INTO transactions VALUES(?,?,?,?,?,?,?)", (i, r.randint(1, 40), amt,
                  r.choice(["deposit", "withdrawal", "transfer"]), maker, appr,
                  (base + dt.timedelta(days=i // 3)).isoformat()))
    c.commit(); c.close()

def sev_amt(a): return "high" if abs(a) >= 500000 else "medium"

SQL_C2 = f"SELECT id, amount FROM transactions WHERE amount <= 0 OR amount > {HARD_CAP}"
SQL_C3 = "SELECT id, maker_id, approver_id FROM transactions WHERE approver_id IS NOT NULL AND approver_id = maker_id"
SQL_C4 = f"""SELECT t.id, t.amount, t.approver_id, u.name, u.approval_limit
FROM transactions t LEFT JOIN users u ON u.id = t.approver_id
WHERE t.amount > 0 AND ((t.approver_id IS NOT NULL AND t.amount > u.approval_limit)
   OR (t.approver_id IS NULL AND t.amount > {AUTO_LIMIT}))"""

def run_controls(log=False):
    c = conn(); n_loans = c.execute("SELECT COUNT(*) FROM loans").fetchone()[0]
    n_txn = c.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    ex1 = []
    for l in c.execute("SELECT * FROM loans ORDER BY id"):
        exp = expected_interest(l["principal"], l["annual_rate"], l["months_elapsed"], l["method"], l["term_months"])
        diff = Decimal(str(l["system_interest"])) - exp
        if abs(diff) > TOL:
            ex1.append(dict(ref=f"LN-{l['id']:04d}", pos=l["id"] - 1, amount=float(abs(diff)),
                severity="high" if abs(diff) >= 500 else "medium",
                reason="System interest does not match recompute",
                detail=f"system {l['system_interest']:,.2f} vs recomputed {exp:,.2f} ({l['method']}, {l['annual_rate']}% on {l['principal']:,.0f}, {l['months_elapsed']} of {l['term_months']} mo)"))
    ex2 = [dict(ref=f"TXN-{t['id']:04d}", pos=t["id"] - 1, amount=abs(t["amount"]), severity="high",
                reason="Negative amount accepted" if t["amount"] < 0 else "Zero amount accepted" if t["amount"] == 0 else "Amount exceeds hard cap",
                detail=f"recorded amount {t['amount']:,.2f}; allowed range 0 to {HARD_CAP:,}")
           for t in c.execute(SQL_C2)]
    ex3 = [dict(ref=f"TXN-{t['id']:04d}", pos=t["id"] - 1, amount=t["amount"], severity="high",
                reason="Maker approved own transaction",
                detail=f"user #{t['maker_id']} is both maker and approver")
           for t in c.execute("SELECT id, maker_id, amount FROM transactions WHERE approver_id IS NOT NULL AND approver_id = maker_id")]
    ex4 = [dict(ref=f"TXN-{t['id']:04d}", pos=t["id"] - 1, amount=t["amount"], severity=sev_amt(t["amount"]),
                reason="Approved above authority limit" if t["approver_id"] else "No approver on high-value item",
                detail=(f"{t['name']} limit {t['approval_limit']:,.0f}" if t["approver_id"] else f"items above {AUTO_LIMIT:,} need an approver"))
           for t in c.execute(SQL_C4)]
    c.close()
    spec = [("ITAC-01", "Loan interest recomputation", "System-calculated interest agrees to an independent recompute.", n_loans, "loans", ex1,
             "Recompute per loan method in Python (Decimal): simple = P x r x t; emi = month-by-month reducing balance. Compare to loans.system_interest, tolerance 0.01."),
            ("ITAC-02", "Input validation", "The system rejects zero, negative and above-cap amounts.", n_txn, "transactions", ex2, SQL_C2),
            ("ITAC-03", "Segregation of duties", "A maker never approves their own transaction.", n_txn, "transactions", ex3, SQL_C3),
            ("ITAC-04", "Authorization limits", "Every transaction is approved by someone with enough authority.", n_txn, "transactions", ex4, SQL_C4)]
    res = dict(run_at=dt.datetime.now().isoformat(timespec="seconds"), controls=[
        dict(id=i, name=n, objective=o, population=p, unit=u, exceptions=e, test=s) for i, n, o, p, u, e, s in spec])
    if log:
        h = conn(); h.executemany("INSERT INTO control_runs VALUES(?,?,?,?)", [(res['run_at'], k['id'], k['population'], len(k['exceptions'])) for k in res['controls']]); h.commit(); h.close()
    return res

@app.on_event("startup")
def _init():
    if not os.path.exists(DB): seed()

@app.get("/api/run")
def run(): return run_controls(log=True)

@app.get("/api/history")
def history():
    c = conn(); rows = c.execute("SELECT run_at, control_id, exceptions FROM control_runs ORDER BY run_at DESC, control_id LIMIT 80").fetchall(); c.close()
    runs = {}
    for r in rows: runs.setdefault(r["run_at"], {})[r["control_id"]] = r["exceptions"]
    return [dict(run_at=k, counts=v, total=sum(v.values())) for k, v in list(runs.items())[:10]]

@app.post("/api/reseed")
def reseed(): seed(random.randint(1, 10_000)); return {"ok": True}
