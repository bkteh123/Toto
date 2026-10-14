import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Bar, BarChart, CartesianGrid, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { PERIODS, type NumberClass, type Period, type ScoreParams, type StatsResponse } from "../api/types";
import { fmtPct, pad } from "../lib/format";
import {
  defaultSortDir,
  expectedAppearances,
  normalisedWeightPercents,
  rowsForPeriod,
  scoresCsv,
  sortRows,
  spanFor,
  type SortKey,
} from "../lib/scores";
import { CopyButton, Empty, ExportButtons, Field, Panel } from "./ui";

const CLASS_COLOR: Record<NumberClass, string> = { Hot: "#ff8a3d", Cold: "#6fb7ff", Neutral: "#f2c230" };

const COLUMNS: SortKey[] = ["number", "appearances", "frequency", "gap", "rank", "hot", "cold", "combined", "cls"];

export function ScoreSection({
  code,
  stats,
  applied,
  onApply,
  period,
  onPeriod,
}: {
  code: string;
  stats: StatsResponse | undefined;
  applied: ScoreParams;
  onApply: (p: ScoreParams) => void;
  period: Period;
  onPeriod: (p: Period) => void;
}) {
  const { t } = useTranslation();
  const [draft, setDraft] = useState<ScoreParams>(applied);
  const [sortKey, setSortKey] = useState<SortKey>("number");
  const [sortDir, setSortDir] = useState<1 | -1>(1);

  const rows = useMemo(() => (stats ? rowsForPeriod(stats, period) : []), [stats, period]);
  const sorted = useMemo(() => sortRows(rows, sortKey, sortDir), [rows, sortKey, sortDir]);
  const span = stats ? spanFor(period, stats.draw_count) : 0;
  const expected = stats ? expectedAppearances(span, stats.k, stats.n) : 0;
  const pct = normalisedWeightPercents([applied.w10, applied.w20, applied.w50, applied.w100]);

  const clickSort = (k: SortKey) => {
    if (k === sortKey) setSortDir((d) => (d === 1 ? -1 : 1));
    else {
      setSortKey(k);
      setSortDir(defaultSortDir(k));
    }
  };
  const num = (v: string) => (v === "" ? 0 : Number(v));
  const allZero = draft.w10 + draft.w20 + draft.w50 + draft.w100 <= 0;

  return (
    <>
      <Panel
        title={t("scores.title")}
        extra={
          <div className="tabs" role="group" aria-label={t("scores.title")}>
            {PERIODS.map((p) => (
              <button key={p} type="button" aria-pressed={p === period} onClick={() => onPeriod(p)}>
                {t(`scores.tabs.${p}`)}
              </button>
            ))}
          </div>
        }
      >
        <form
          className="row"
          onSubmit={(e) => {
            e.preventDefault();
            if (!allZero) onApply(draft);
          }}
        >
          {([["w10", 10], ["w20", 20], ["w50", 50], ["w100", 100]] as const).map(([k, n]) => (
            <Field key={k} label={t("scores.weight", { n })}>
              {(id) => (
                <input id={id} type="number" min={0} value={draft[k]} onChange={(e) => setDraft({ ...draft, [k]: num(e.target.value) })} />
              )}
            </Field>
          ))}
          <Field label={t("scores.mix")}>
            {(id) => (
              <input id={id} type="number" min={0} max={100} value={draft.mix}
                onChange={(e) => setDraft({ ...draft, mix: Math.min(100, Math.max(0, num(e.target.value))) })} />
            )}
          </Field>
          <button type="submit" disabled={allZero}>{t("scores.recompute")}</button>
        </form>
        <small className="note">{t("scores.help")}</small>
        <small className="note">
          {t("scores.applied", {
            w10: pct[0].toFixed(0), w20: pct[1].toFixed(0), w50: pct[2].toFixed(0), w100: pct[3].toFixed(0),
            mix: applied.mix,
          })}
        </small>
        <small className="note"><strong>{t("app.scoresNote")}</strong></small>

        {stats && stats.draw_count > 0 ? (
          <>
            <small className="note">
              {t("scores.expectation", { value: expected.toFixed(2), span, k: stats.k, n: stats.n })}
            </small>
            <div className="tablewrap" tabIndex={0} role="region" aria-label={t("scores.title")}>
              <table>
                <thead>
                  <tr>
                    {COLUMNS.map((k) => (
                      <th
                        key={k}
                        className={`sortable${k === "number" || k === "cls" ? " c" : ""}`}
                        tabIndex={0}
                        aria-sort={k === sortKey ? (sortDir === 1 ? "ascending" : "descending") : undefined}
                        onClick={() => clickSort(k)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault();
                            clickSort(k);
                          }
                        }}
                      >
                        {t(`scores.columns.${k}`)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {sorted.map((r) => (
                    <tr key={r.number}>
                      <td className="c"><span className="ball sm">{pad(r.number)}</span></td>
                      <td>{r.appearances}</td>
                      <td>{fmtPct(r.frequency)}</td>
                      <td>{r.gap}</td>
                      <td>{r.rank}</td>
                      <td>{r.hot.toFixed(3)}</td>
                      <td>{r.cold.toFixed(3)}</td>
                      <td>{r.combined.toFixed(3)}</td>
                      <td className="c"><span className={`pill ${r.cls}`}>{t(`scores.classes.${r.cls}`)}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="row">
              <small className="note">{t("scores.sortHint")}</small>
              <CopyButton text={() => scoresCsv(rows)} />
              <ExportButtons game={code} kind="stats" query={{ period, ...applied }} />
            </div>
          </>
        ) : (
          <Empty>{t("scores.empty")}</Empty>
        )}
      </Panel>

      <Panel title={t("chart.title")}>
        {stats && stats.draw_count > 0 ? (
          <>
            <div className="chart">
              <div className="inner" style={{ minWidth: Math.max(600, stats.n * 20) }} role="img" aria-label={t("chart.aria")}>
                <ResponsiveContainer width="100%" height={240}>
                  <BarChart data={rows} margin={{ top: 16, right: 8, bottom: 4, left: 0 }}>
                    <CartesianGrid stroke="#4a3a14" vertical={false} />
                    <XAxis dataKey="number" interval={stats.n > 60 ? 4 : 0} tickLine={false} axisLine={{ stroke: "#4a3a14" }} />
                    <YAxis allowDecimals={false} tickLine={false} axisLine={false} width={32} />
                    <Tooltip
                      cursor={{ fill: "#f2c23014" }}
                      content={({ active, payload }) =>
                        active && payload && payload.length ? (
                          <div className="chart-tip">
                            {t("chart.tooltip", { n: pad(payload[0].payload.number), count: payload[0].payload.appearances })}
                          </div>
                        ) : null
                      }
                    />
                    <ReferenceLine
                      y={expected}
                      stroke="#f6ecd0"
                      strokeDasharray="4 4"
                      label={{ value: t("chart.expectation", { value: expected.toFixed(1) }), position: "insideTopRight", fill: "#b9a679", fontSize: 11 }}
                    />
                    <Bar dataKey="appearances" radius={[2, 2, 0, 0]} isAnimationActive={false}>
                      {rows.map((r) => (
                        <Cell key={r.number} fill={CLASS_COLOR[r.cls]} fillOpacity={0.88} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
            <small className="note">{t("chart.help")}</small>
          </>
        ) : (
          <Empty>{t("scores.empty")}</Empty>
        )}
      </Panel>
    </>
  );
}
