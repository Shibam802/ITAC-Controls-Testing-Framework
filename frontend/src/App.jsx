import { useEffect, useState } from "react";

const inr = (n) => n.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

function Strip({ c }) {
  const bad = new Set(c.exceptions.map((e) => e.pos));
  return (
    <div className="strip" aria-label={`${c.exceptions.length} of ${c.population} ${c.unit} failed`}>
      {Array.from({ length: c.population }, (_, i) => <i key={i} className={bad.has(i) ? "x" : ""} />)}
    </div>
  );
}

function Paper({ c, sev }) {
  const [all, setAll] = useState(false);
  const rows = c.exceptions.filter((e) => sev === "all" || e.severity === sev);
  const shown = all ? rows : rows.slice(0, 6);
  return (
    <section id={c.id} className="paper">
      <header>
        <div><span className="code">{c.id}</span><h2>{c.name}</h2><p>{c.objective}</p></div>
        <div className={"verdict " + (c.exceptions.length ? "bad" : "ok")}>
          {c.exceptions.length ? `${c.exceptions.length} exceptions` : "No exceptions"}
          <small>{c.population - c.exceptions.length} of {c.population} {c.unit} agreed</small>
        </div>
      </header>
      <table>
        <thead><tr><th></th><th>Item</th><th>Finding</th><th className="r">Amount at issue</th></tr></thead>
        <tbody>
          {shown.map((e) => (
            <tr key={e.ref + e.reason}>
              <td className="tick" title={e.severity}>{e.severity === "high" ? "✗✗" : "✗"}</td>
              <td className="mono">{e.ref}</td>
              <td><b>{e.reason}</b><span>{e.detail}</span></td>
              <td className="r mono">{inr(e.amount)}</td>
            </tr>
          ))}
          {!rows.length && <tr><td className="tick ok" >✓</td><td colSpan="3">Nothing to show for this filter.</td></tr>}
        </tbody>
      </table>
      {rows.length > 6 && <button className="link" onClick={() => setAll(!all)}>{all ? "Show fewer" : `Show all ${rows.length}`}</button>}
      <details><summary>How this was tested</summary><pre>{c.test}</pre></details>
    </section>
  );
}

export default function App() {
  const [h, setH] = useState([]), [d, setD] = useState(null), [busy, setBusy] = useState(false), [sev, setSev] = useState("all");
  const load = async (fresh) => {
    setBusy(true);
    if (fresh) await fetch("/api/reseed", { method: "POST" });
    setD(await (await fetch("/api/run")).json());
    setH(await (await fetch("/api/history")).json());
    setBusy(false);
  };
  useEffect(() => { load(); }, []);
  if (!d) return <p className="boot">Running control tests…</p>;

  const total = d.controls.reduce((a, c) => a + c.exceptions.length, 0);
  const tested = d.controls.reduce((a, c) => a + c.population, 0);
  const exportCsv = () => {
    const rows = [["control", "item", "severity", "finding", "detail", "amount"]];
    d.controls.forEach((c) => c.exceptions.forEach((e) => rows.push([c.id, e.ref, e.severity, e.reason, e.detail, e.amount])));
    const csv = rows.map((r) => r.map((v) => `"${String(v).replaceAll('"', '""')}"`).join(",")).join("\n");
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" })); a.download = "itac-exceptions.csv"; a.click();
  };

  return (
    <main>
      <div className="hero">
        <h1>{total} exceptions<br />in {tested} items tested.</h1>
        <div className="actions">
          <button onClick={() => load(false)} disabled={busy}>{busy ? "Running…" : "Re-run tests"}</button>
          <button className="ghost" onClick={() => load(true)} disabled={busy}>Generate new data</button>
          <button className="ghost" onClick={exportCsv}>Export exceptions</button>
          <small>Last run {d.run_at.replace("T", " ")}</small>
        </div>
      </div>

      <div className="overview">
        {d.controls.map((c) => (
          <a key={c.id} href={`#${c.id}`} className="ov">
            <span className="ovname"><b>{c.id}</b> {c.name}</span>
            <Strip c={c} />
            <span className={"ovn " + (c.exceptions.length ? "bad" : "ok")}>{c.exceptions.length}</span>
          </a>
        ))}
        <p className="legend"><i /> passed <i className="x" /> failed. Each mark is one loan or transaction.</p>
      </div>

      <div className="filter" role="group" aria-label="Severity">
        Show {["all", "high", "medium"].map((s) => <button key={s} className={sev === s ? "on" : ""} onClick={() => setSev(s)}>{s}</button>)}
      </div>
      {d.controls.map((c) => <Paper key={c.id} c={c} sev={sev} />)}
      <section className="paper">
        <header><div><h2>Run history</h2><p>Every run is logged, so you can show when an exception first appeared.</p></div></header>
        <table>
          <thead><tr><th>Run at</th>{d.controls.map((c) => <th key={c.id} className="r">{c.id}</th>)}<th className="r">Total</th></tr></thead>
          <tbody>{h.map((x) => (
            <tr key={x.run_at}><td className="mono">{x.run_at.replace("T", " ")}</td>
              {d.controls.map((c) => <td key={c.id} className="r mono">{x.counts[c.id] ?? "-"}</td>)}
              <td className="r mono">{x.total}</td></tr>))}</tbody>
        </table>
      </section>
    </main>
  );
}
