import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ApiError } from "../api/client";
import { useGenerate } from "../api/hooks";
import { METHODS, type Method, type ScoreParams } from "../api/types";
import { combosCsv } from "../lib/bao";
import { CopyButton, Empty, ExportButtons, Field, Panel, Status } from "./ui";
import { Balls } from "./ui";

export function Generator({
  code,
  params,
  drawCount,
}: {
  code: string;
  params: ScoreParams;
  drawCount: number;
}) {
  const { t } = useTranslation();
  const [method, setMethod] = useState<Method>("weighted");
  const [count, setCount] = useState(5);
  const gen = useGenerate(code);
  const result = gen.data;
  const needsData = method !== "random" && drawCount === 0;

  return (
    <Panel title={t("generator.title")}>
      <div className="row">
        <Field label={t("generator.method")}>
          {(id) => (
            <select id={id} value={method} onChange={(e) => setMethod(e.target.value as Method)}>
              {METHODS.map((m) => (
                <option key={m} value={m}>{t(`generator.methods.${m}`)}</option>
              ))}
            </select>
          )}
        </Field>
        <Field label={t("generator.count")}>
          {(id) => (
            <input id={id} type="number" min={1} max={50} value={count}
              onChange={(e) => setCount(Math.min(50, Math.max(1, Math.round(Number(e.target.value)) || 1)))} />
          )}
        </Field>
        <button type="button" className="primary" disabled={gen.isPending || needsData}
          onClick={() => gen.mutate({ method, count, ...params })}>
          {gen.isPending ? t("generator.generating") : t("generator.generate")}
        </button>
        {result && <CopyButton text={() => combosCsv(result.combinations, t(`generator.methodShort.${result.method}`))} />}
        {result && (
          <ExportButtons
            game={code}
            kind="combos"
            body={{ method: result.method, combinations: result.combinations }}
          />
        )}
      </div>
      {needsData && <Status>{t("generator.needData")}</Status>}
      {gen.isError && (
        <Status kind="err">{gen.error instanceof ApiError ? gen.error.message : t("errors.network")}</Status>
      )}
      <small className="note">{t("app.scoresNote")} {t("generator.note")}</small>

      {result ? (
        <div className="stack" aria-live="polite">
          {result.shortfall > 0 && (
            <Status>{t("generator.shortfall", { got: result.combinations.length, want: result.requested })}</Status>
          )}
          {result.combinations.map((c, i) => (
            <div className="combo" key={c.join("-")}>
              <span className="tag">
                {String(i + 1).padStart(2, "0")} · {t(`generator.methodShort.${result.method}`)}
              </span>
              <Balls numbers={c} sm />
            </div>
          ))}
        </div>
      ) : (
        <Empty>{t("generator.empty")}</Empty>
      )}
    </Panel>
  );
}
