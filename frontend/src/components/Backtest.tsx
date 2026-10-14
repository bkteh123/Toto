import { useState } from "react";
import { useTranslation } from "react-i18next";
import { CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ApiError } from "../api/client";
import { useBacktest, useStartBacktest } from "../api/hooks";
import { METHODS, type BacktestResult, type Method, type ScoreParams } from "../api/types";
import { curveData, curveDomain, flagFor, METHOD_COLORS } from "../lib/backtest";
import { fmtP, fmtPct, fmtSignedPct } from "../lib/format";
import { Empty, Field, Panel, Status } from "./ui";

const MIN_WARMUP = 10;
const MIN_TESTED = 5;

function Results({ r, seed, lang }: { r: BacktestResult; seed: unknown; lang: string }) {
  const { t } = useTranslation();
  const data = curveData(r);
  const [lo, hi] = curveDomain(r);
  const verdictText = lang === "zh" ? r.verdict.text_zh : r.verdict.text_en;
  const first = r.labels[0];
  const last = r.labels[r.labels.length - 1];

  return (
    <div className="stack">
      <p className="note" style={{ color: "var(--ink)" }}>
        {t("backtest.summary", {
          tested: r.tested_draws,
          from: first ?? r.warmup + 1,
          to: last ?? r.warmup + r.tested_draws,
          tickets: r.tickets_per_draw,
          seed: String(seed ?? "—"),
          mean: r.expected_mean.toFixed(4),
          ge3: fmtPct(r.expected_ge3, 2),
        })}
      </p>
      <div className="tablewrap tall" tabIndex={0} role="region" aria-label={t("backtest.title")}>
        <table>
          <thead>
            <tr>
              <th className="l">{t("backtest.columns.method")}</th>
              <th>{t("backtest.columns.tickets")}</th>
              <th>{t("backtest.columns.avg")}</th>
              <th>{t("backtest.columns.vs")}</th>
              <th>{t("backtest.columns.ge3")}</th>
              <th>{t("backtest.columns.ge3exp")}</th>
              <th>{t("backtest.columns.z")}</th>
              <th>{t("backtest.columns.p")}</th>
              <th>{t("backtest.columns.pDraw")}</th>
              <th className="l">{t("backtest.columns.result")}</th>
            </tr>
          </thead>
          <tbody>
            {r.methods.map((m) => {
              const flag = m.method === "random" ? "control" : flagFor(m);
              return (
                <tr key={m.method}>
                  <td className="l">
                    <span style={{ color: METHOD_COLORS[m.method] }} aria-hidden="true">■ </span>
                    {t(`methods.${m.method}`)}
                  </td>
                  <td>{m.tickets}</td>
                  <td>{m.avg_matches.toFixed(4)}</td>
                  <td className={m.pct_vs_expected >= 0 ? "pos" : "neg"}>{fmtSignedPct(m.pct_vs_expected)}</td>
                  <td>{fmtPct(m.rate_ge3, 2)}</td>
                  <td>{fmtPct(m.expected_ge3, 2)}</td>
                  <td>{m.z.toFixed(2)}</td>
                  <td>{fmtP(m.p_value)}</td>
                  <td>{fmtP(m.p_by_draw)}</td>
                  <td className="l"><span className={`pill ${flag}`}>{t(`backtest.flags.${flag}`)}</span></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <small className="note">{t("backtest.pExplain")}</small>

      <h3>{t("backtest.chartTitle")}</h3>
      <div className="chart">
        <div className="inner" role="img" aria-label={t("backtest.chartAria")}>
          <ResponsiveContainer width="100%" height={250}>
            <LineChart data={data} margin={{ top: 12, right: 12, bottom: 4, left: 0 }}>
              <CartesianGrid stroke="#4a3a14" vertical={false} />
              <XAxis dataKey="label" tickLine={false} axisLine={{ stroke: "#4a3a14" }} minTickGap={24} />
              <YAxis domain={[lo, hi]} tickFormatter={(v: number) => v.toFixed(2)} tickLine={false} axisLine={false} width={44} />
              <Tooltip
                contentStyle={{ background: "#251c0b", border: "1px solid #4a3a14", borderRadius: 6, fontFamily: "DM Mono, monospace", fontSize: 12 }}
                labelStyle={{ color: "#b9a679" }}
                formatter={(v: number, name: string) => [v.toFixed(3), t(`methods.${name}`)]}
              />
              <ReferenceLine
                y={r.expected_mean}
                stroke="#f6ecd0"
                strokeDasharray="4 4"
                label={{ value: t("backtest.expectation", { value: r.expected_mean.toFixed(2) }), position: "insideTopRight", fill: "#b9a679", fontSize: 11 }}
              />
              <Legend formatter={(v: string) => t(`methods.${v}`)} />
              {r.methods.map((m) => (
                <Line key={m.method} type="monotone" dataKey={m.method} stroke={METHOD_COLORS[m.method]}
                  strokeWidth={m.method === "random" ? 1.2 : 1.8} dot={false} isAnimationActive={false} />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      <h3>{t("backtest.verdictTitle")}</h3>
      <div className={`verdict${r.verdict.kind === "some_significant" ? " warn" : ""}`}>{verdictText}</div>
    </div>
  );
}

export function Backtest({
  code,
  params,
  drawCount,
  lang,
}: {
  code: string;
  params: ScoreParams;
  drawCount: number;
  lang: string;
}) {
  const { t } = useTranslation();
  const [warmup, setWarmup] = useState(30);
  const [tickets, setTickets] = useState(5);
  const [methods, setMethods] = useState<Method[]>([...METHODS]);
  const [seed, setSeed] = useState("");
  const [jobId, setJobId] = useState<number | null>(null);
  const start = useStartBacktest(code);
  const job = useBacktest(jobId);

  const need = warmup + MIN_TESTED;
  const tooFew = drawCount < need;
  const active = start.isPending || job.data?.status === "queued" || job.data?.status === "running";
  const toggle = (m: Method) =>
    setMethods((cur) => (cur.includes(m) ? cur.filter((x) => x !== m) : METHODS.filter((x) => x === m || cur.includes(x))));

  const run = () => {
    setJobId(null);
    start.mutate(
      {
        warmup,
        tickets,
        methods,
        ...(seed.trim() !== "" ? { seed: Math.max(0, Math.round(Number(seed))) } : {}),
        ...params,
      },
      { onSuccess: (r) => setJobId(r.id) },
    );
  };

  const j = job.data;
  const pct = Math.round((j?.progress ?? 0) * 100);

  return (
    <Panel title={t("backtest.title")}>
      <small className="note">{t("backtest.help")}</small>
      <small className="note"><strong>{t("app.scoresNote")}</strong></small>
      <div className="row">
        <Field label={t("backtest.warmup")}>
          {(id) => (
            <input id={id} type="number" min={MIN_WARMUP} value={warmup}
              onChange={(e) => setWarmup(Math.max(MIN_WARMUP, Math.round(Number(e.target.value)) || MIN_WARMUP))} />
          )}
        </Field>
        <Field label={t("backtest.tickets")}>
          {(id) => (
            <input id={id} type="number" min={1} max={50} value={tickets}
              onChange={(e) => setTickets(Math.min(50, Math.max(1, Math.round(Number(e.target.value)) || 1)))} />
          )}
        </Field>
        <Field label={t("backtest.seed")}>
          {(id) => (
            <input id={id} type="number" min={0} max={4294967295} value={seed} placeholder="—"
              onChange={(e) => setSeed(e.target.value)} aria-describedby={`${id}-hint`} />
          )}
        </Field>
        <button type="button" className="primary" onClick={run} disabled={active || tooFew || methods.length === 0}>
          {active ? t("backtest.running") : t("backtest.run")}
        </button>
      </div>
      <fieldset style={{ border: "none", padding: 0, margin: 0 }}>
        <legend className="lbl">{t("backtest.methods")}</legend>
        <div className="row" style={{ marginTop: 6 }}>
          {METHODS.map((m) => (
            <label key={m} className="row" style={{ gap: 6, textTransform: "none", letterSpacing: 0, fontSize: 13, color: "var(--ink)" }}>
              <input type="checkbox" checked={methods.includes(m)} onChange={() => toggle(m)} />
              <span style={{ color: METHOD_COLORS[m] }} aria-hidden="true">■</span> {t(`methods.${m}`)}
            </label>
          ))}
        </div>
      </fieldset>
      <small className="note">{t("backtest.seedHint")}</small>
      {tooFew && <Status kind="err">{t("backtest.needMore", { count: need, have: drawCount })}</Status>}
      {start.isError && (
        <Status kind="err">
          {t("backtest.error", { message: start.error instanceof ApiError ? start.error.message : t("errors.network") })}
        </Status>
      )}

      {j && (j.status === "queued" || j.status === "running") && (
        <div className="stack" aria-live="polite">
          <progress max={100} value={pct} aria-label={t("backtest.progress", { pct })} />
          <Status>{j.status === "queued" ? t("backtest.queued") : t("backtest.progress", { pct })}</Status>
        </div>
      )}
      {j?.status === "error" && <Status kind="err">{t("backtest.error", { message: j.error ?? "" })}</Status>}
      {j?.status === "done" && j.result ? (
        <Results r={j.result} seed={j.params.seed} lang={lang} />
      ) : !j && !start.isPending ? (
        <Empty>{t("generator.empty")}</Empty>
      ) : null}
    </Panel>
  );
}
