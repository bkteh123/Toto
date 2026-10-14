import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useDraws, useGames, useStats } from "./api/hooks";
import type { Period, ScoreParams } from "./api/types";
import { Backtest } from "./components/Backtest";
import { Bao } from "./components/Bao";
import { DataPanel } from "./components/DataPanel";
import { Footer } from "./components/Footer";
import { Generator } from "./components/Generator";
import { Header } from "./components/Header";
import { Glance, LatestResult } from "./components/Overview";
import { ScoreSection } from "./components/ScoreSection";
import { Empty, Panel, Status } from "./components/ui";
import { savedLang, type Lang } from "./i18n";

const DEFAULT_PARAMS: ScoreParams = { w10: 40, w20: 25, w50: 20, w100: 15, mix: 50 };
const GAME_KEY = "ry_game";

function savedGame(): string | null {
  try {
    return localStorage.getItem(GAME_KEY);
  } catch {
    return null;
  }
}

export default function App() {
  const { t, i18n } = useTranslation();
  const [lang, setLang] = useState<Lang>(savedLang());
  const games = useGames();
  const [chosen, setChosen] = useState<string | null>(savedGame());
  const [params, setParams] = useState<ScoreParams>(DEFAULT_PARAMS);
  const [period, setPeriod] = useState<Period>("10");

  // changeLanguage re-creates `t`, so it must not share an effect that depends on `t`
  // (that re-ran changeLanguage forever) and is skipped when the language already matches.
  // changeLanguage re-creates `t`, so it must not share an effect that depends on `t`
  // (that re-ran changeLanguage forever) and is skipped when the language already matches.
  useEffect(() => {
    if (i18n.language !== lang) void i18n.changeLanguage(lang);
  }, [lang, i18n]);

  useEffect(() => {
    document.documentElement.lang = lang === "zh" ? "zh-CN" : "en";
    document.title = t("app.title");
  }, [lang, t]);

  const list = games.data ?? [];
  const game = useMemo(
    () => list.find((g) => g.code === chosen) ?? list.find((g) => g.is_default) ?? list[0],
    [list, chosen],
  );
  const code = game?.code;

  const chooseGame = (c: string) => {
    setChosen(c);
    try {
      localStorage.setItem(GAME_KEY, c);
    } catch {
      /* per-viewer convenience only */
    }
  };

  const stats = useStats(code, params);
  const latest = useDraws(code, 1);
  const drawCount = stats.data?.draw_count ?? latest.data?.total ?? 0;

  if (games.isLoading) {
    return (
      <div className="wrap">
        <Status>{t("app.loading")}</Status>
      </div>
    );
  }
  if (games.isError || !game) {
    return (
      <div className="wrap">
        <Panel title={t("app.title")}>
          <Status kind="err">{games.isError ? t("app.apiDown") : t("app.noGames")}</Status>
          <div>
            <button type="button" onClick={() => void games.refetch()}>{t("app.retry")}</button>
          </div>
        </Panel>
      </div>
    );
  }

  return (
    <div className="wrap">
      <Header games={list} code={code} onGame={chooseGame} lang={lang} onLang={setLang} />

      <DataPanel game={game} drawCount={stats.data?.draw_count} />

      <div className="grid2">
        <LatestResult game={game} latest={latest.data?.items[0]} />
        <Glance stats={stats.data} />
      </div>

      {stats.isError ? (
        <Panel title={t("scores.title")}>
          <Empty>{t("app.apiDown")}</Empty>
        </Panel>
      ) : (
        <ScoreSection
          code={game.code}
          stats={stats.data}
          applied={params}
          onApply={setParams}
          period={period}
          onPeriod={setPeriod}
        />
      )}

      <Generator code={game.code} params={params} drawCount={drawCount} />
      <Bao game={game} drawCount={drawCount} />
      <Backtest code={game.code} params={params} drawCount={drawCount} lang={lang} />

      <Footer />
    </div>
  );
}
