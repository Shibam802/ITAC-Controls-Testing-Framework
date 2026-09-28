import pytest, main
from decimal import Decimal

@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB", str(tmp_path / "t.db")); return main

def refs(res, cid):
    return {e["ref"] for c in res["controls"] if c["id"] == cid for e in c["exceptions"]}

def tiny(db, amount, maker, approver):
    c = db.conn(); c.executescript(db.SCHEMA)
    c.executemany("INSERT INTO users VALUES(?,?,?,?)", [(1, "M", "maker", 0), (2, "A", "branch manager", 250000)])
    c.execute("INSERT INTO loans VALUES(1,1,100000,12,6,6000.0,'simple',12)")
    c.execute("INSERT INTO transactions VALUES(1,1,?,?,?,?,'2026-06-01')", (amount, "deposit", maker, approver))
    c.commit(); c.close(); return db.run_controls()

def test_simple_interest_known_value():
    assert main.expected_interest(100000, 12, 6) == Decimal("6000.00")

def test_emi_interest_over_full_term():
    assert Decimal("6618") < main.expected_interest(100000, 12, 12, "emi", 12) < Decimal("6619")

def test_clean_data_has_no_exceptions(db):
    assert all(not c["exceptions"] for c in tiny(db, 5000, 1, 2)["controls"])

def test_self_approval_flagged(db):
    assert "TXN-0001" in refs(tiny(db, 5000, 2, 2), "ITAC-03")

def test_over_authority_flagged(db):
    assert "TXN-0001" in refs(tiny(db, 300000, 1, 2), "ITAC-04")

def test_negative_amount_flagged(db):
    assert "TXN-0001" in refs(tiny(db, -10, 1, 2), "ITAC-02")

def test_seeded_planted_exceptions(db):
    db.seed(); res = db.run_controls()
    r1 = refs(res, "ITAC-01")
    assert {"LN-0009", "LN-0022"} <= r1     # overstated interest; flat interest on EMI loan
    assert "LN-0007" not in r1              # 0.01 difference is inside tolerance
    assert "TXN-0037" in refs(res, "ITAC-02") and "TXN-0029" in refs(res, "ITAC-03") and "TXN-0041" in refs(res, "ITAC-04")

def test_runs_are_logged(db):
    db.seed(); db.run_controls(log=True)
    c = db.conn(); n = c.execute("SELECT COUNT(*) FROM control_runs").fetchone()[0]; c.close()
    assert n == 4
