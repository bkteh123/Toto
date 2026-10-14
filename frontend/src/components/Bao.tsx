import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { ApiError } from "../api/client";
import { useBao, useDraws } from "../api/hooks";
import type { Game } from "../api/types";
import { baoCsv, baoSizes, ruleVerdict } from "../lib/bao";
import { fmtDate, fmtInt, fmtMoney, fmtOneIn, pad } from "../lib/format";
import { Balls, CopyButton, Empty, ExportButtons, Field, Panel, Status } from "./ui";

export function Bao({ game, drawCount }: { game: Game; drawCount: number }) {
  const { t } = useTranslation();
  const sizes = baoSizes(game.max_number, game.pick_count);
  const defaultSize = sizes.includes(8) ? 8 : sizes[0];
  const [size, setSize] = useState(defaultSize);
  const [windowSize, setWindowSize] = useState(10);
  const [end, setEnd] = useState<string>(""); // "" = latest
  const draws = useDraws(game.code, 1000);
  const bao = useBao(game.code);

  // A different game has different valid sizes and different draws.
  useEffect(() => {
    setSize(sizes.includes(8) ? 8 : sizes[0]);
    setEnd("");
    bao.reset();
  }, [game.code]); // eslint-disable-line react-hooks/exhaustive-deps

  const items = draws.data?.items ?? [];
  const r = bao.data;

  const build = () =>
    bao.mutate({ size, window: windowSize, end_draw_no: end === "" ? null : Number(end) });

  const rc = r?.rule_check;
  const verdict = rc ? ruleVerdict(rc.avg_hits, rc.expected_hits) : null;

  return (
    <Panel title={t("bao.title")}>
      <small className="note">{t("bao.help")}</small>
      <small className="note"><strong>{t("app.scoresNote")}</strong></small>
      <div className="row">
        <Field label={t("bao.size")}>
          {(id) => (
            <select id={id} value={size} onChange={(e) => setSize(Number(e.target.value))}>
              {sizes.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          )}
        </Field>
        <Field label={t("bao.window")}>
          {(id) => (
            <input id={id} type="number" min={1} max={500} value={windowSize}
              onChange={(e) => setWindowSize(Math.max(1, Math.round(Number(e.target.value)) || 1))} />
          )}
        </Field>
        <Field label={t("bao.end")}>
          {(id) => (
            <select id={id} value={end} onChange={(e) => setEnd(e.target.value)} style={{ maxWidth: "100%" }}>
              <option value="">{t("bao.latest")}</option>
              {items
                .filter((d) => d.draw_no !== null)
                .map((d) => (
                  <option key={d.draw_no} value={d.draw_no!}>
                    #{d.draw_no} · {fmtDate(d.draw_date)} · {d.numbers.map(pad).join(" ")}
                  </option>
                ))}
            </select>
          )}
        </Field>
        <button type="button" className="primary" disabled={bao.isPending || drawCount === 0} onClick={build}>
          {t("bao.generate")}
        </button>
        {r && <CopyButton text={() => baoCsv(r.numbers, r.counts)} />}
        {r && (
          <ExportButtons
            game={game.code}
            kind="bao"
            query={{ size: r.size, window: r.window, end_draw_no: r.end_draw_no }}
          />
        )}
      </div>
      {drawCount === 0 && <Status>{t("bao.noData")}</Status>}
      {bao.isError && (
        <Status kind="err">{bao.error instanceof ApiError ? bao.error.message : t("errors.network")}</Status>
      )}

      {!r ? (
        <Empty>{t("generator.empty")}</Empty>
      ) : (
        <div className="stack" aria-live="polite">
          <div className="lbl">
            {t("bao.set", { size: r.size, no: r.end_draw_no ?? "—", date: fmtDate(r.end_draw_date), window: r.window })}
          </div>
          <Balls numbers={r.numbers} label={t("bao.title")} />
          <div className="chips">
            {r.numbers.map((n) => (
              <span key={n} className="chip">
                {pad(n)} <b>{t("glance.times", { count: r.counts[String(n)] })}</b>
              </span>
            ))}
          </div>
          {r.tied_alternatives.length > 0 && (
            <small className="note">
              {t("bao.tied", {
                numbers: r.tied_alternatives.map((x) => pad(x.number)).join("、"),
                count: r.cut_count,
              })}
            </small>
          )}
          {r.unseen_filler && <small className="note">{t("bao.filler", { size: r.size })}</small>}
          <div className="chips">
            <span className="chip">{t("bao.linesChip", { size: r.size, lines: fmtInt(r.lines) })}</span>
            <span className="chip">
              {t("bao.costChip", { price: fmtMoney(r.ticket_price, r.currency), cost: fmtMoney(r.cost, r.currency) })}
            </span>
            <span className="chip">{t("bao.oddsChip", { odds: fmtOneIn(r.jackpot_one_in) })}</span>
          </div>
          {r.special_bao && (
            <small className="note">
              {t("bao.special", {
                size: r.size,
                rest: game.max_number - r.size,
                lines: r.lines,
                k: game.pick_count,
              })}
            </small>
          )}

          {r.later_draws.length > 0 && (
            <>
              <h3>{t("bao.later")}</h3>
              <div className="tablewrap tall" tabIndex={0} role="region" aria-label={t("bao.later")}>
                <table>
                  <thead>
                    <tr>
                      <th className="l">{t("bao.laterColumns.draw")}</th>
                      <th className="l">{t("bao.laterColumns.date")}</th>
                      <th className="l">{t("bao.laterColumns.numbers")}</th>
                      <th className="l">{t("bao.laterColumns.hits")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {r.later_draws.map((d) => (
                      <tr key={d.draw_no ?? d.draw_date}>
                        <td className="l">{d.draw_no ?? "—"}</td>
                        <td className="l">{fmtDate(d.draw_date)}</td>
                        <td className="l">{d.numbers.map(pad).join(" ")}</td>
                        <td className="l">
                          {d.hits.length}
                          {d.hits.length > 0 && ` (${d.hits.map(pad).join(", ")})`}
                          {d.jackpot && <span className="pill beats" style={{ marginLeft: 6 }}>{t("bao.jackpotRow")}</span>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}

          <div className="verdict">
            {rc ? (
              <>
                {t("bao.rule", {
                  window: r.window,
                  size: r.size,
                  n: rc.draws_tested,
                  avg: rc.avg_hits.toFixed(2),
                  exp: rc.expected_hits.toFixed(2),
                  ge3: rc.draws_with_3_plus,
                })}{" "}
                {verdict === "same" && t("bao.ruleSame")}
                {verdict === "above" && t("bao.ruleAbove")}
                {verdict === "below" && t("bao.ruleBelow")}
              </>
            ) : (
              t("bao.ruleNone")
            )}
          </div>
        </div>
      )}
    </Panel>
  );
}
