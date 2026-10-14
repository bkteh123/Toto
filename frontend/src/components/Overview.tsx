import { useTranslation } from "react-i18next";
import type { Game, StatsResponse, Draw } from "../api/types";
import { fmtDate, pad } from "../lib/format";
import { Balls, Empty, Panel } from "./ui";

export function LatestResult({ game, latest }: { game: Game; latest: Draw | undefined }) {
  const { t } = useTranslation();
  return (
    <Panel title={t("latest.title")}>
      {latest ? (
        <div className="stack">
          <div className="lbl">
            {latest.draw_no !== null ? t("latest.draw", { no: latest.draw_no }) : ""}
            {latest.draw_no !== null && latest.draw_date ? " · " : ""}
            {fmtDate(latest.draw_date)}
          </div>
          <Balls numbers={latest.numbers} bonus={game.has_bonus ? latest.bonus : null} label={t("latest.title")} />
        </div>
      ) : (
        <Empty>{t("latest.empty")}</Empty>
      )}
    </Panel>
  );
}

export function Glance({ stats }: { stats: StatsResponse | undefined }) {
  const { t } = useTranslation();
  return (
    <Panel title={t("glance.title")}>
      {stats && stats.draw_count > 0 ? (
        <>
          <div className="lbl">{t("glance.hottest")}</div>
          <div className="chips">
            {stats.hottest_10.map((c) => (
              <span key={c.number} className="chip">
                {pad(c.number)} <b>{t("glance.times", { count: c.appearances })}</b>
              </span>
            ))}
          </div>
          <div className="lbl">{t("glance.coldest")}</div>
          <div className="chips">
            {stats.coldest.map((c) => (
              <span key={c.number} className="chip">
                {pad(c.number)} <b>{t("glance.drawsSince", { count: c.gap })}</b>
              </span>
            ))}
          </div>
        </>
      ) : (
        <Empty>{t("latest.empty")}</Empty>
      )}
    </Panel>
  );
}
