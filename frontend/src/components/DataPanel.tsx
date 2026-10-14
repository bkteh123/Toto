import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { ApiError } from "../api/client";
import { useCollect, useCollectLogs, useConflicts, useImportDraws, useInvalidateGameData, useMissing } from "../api/hooks";
import type { CollectLog, Game } from "../api/types";
import { fmtDate, pad } from "../lib/format";
import { Field, Panel, Status } from "./ui";

const MISSING_SHOWN = 60;

function logMessage(t: (k: string, o?: Record<string, unknown>) => string, log: CollectLog): { text: string; kind?: "ok" | "err" } {
  switch (log.status) {
    case "ok":
      return { text: t("data.collect.ok", { added: log.added }), kind: "ok" };
    case "conflict":
      return { text: t("data.collect.conflict", { count: log.conflicts }), kind: "err" };
    case "error":
      return { text: t("data.collect.error"), kind: "err" };
    case "unreachable":
      return { text: t("data.collect.unreachable"), kind: "err" };
    default:
      return { text: t("data.collect.running") };
  }
}

export function DataPanel({ game, drawCount }: { game: Game; drawCount: number | undefined }) {
  const { t, i18n } = useTranslation();
  const code = game.code;
  const logs = useCollectLogs(code);
  const missing = useMissing(code);
  const conflicts = useConflicts(code);
  const importer = useImportDraws(code);
  const collect = useCollect(code);
  const invalidate = useInvalidateGameData(code);

  const [file, setFile] = useState<File | null>(null);
  const [skip, setSkip] = useState(0);

  const latest = logs.data?.[0];
  const running = collect.isPending || latest?.status === "running";

  // When a run finishes, everything derived from the draws is stale.
  const wasRunning = useRef(false);
  useEffect(() => {
    if (wasRunning.current && !running) void invalidate();
    wasRunning.current = running;
  }, [running]); // eslint-disable-line react-hooks/exhaustive-deps

  const lastOk = logs.data?.find((l) => l.status === "ok" && l.finished_at);
  const fmtTime = (iso: string) =>
    new Date(iso).toLocaleString(i18n.language === "zh" ? "zh-CN" : "en-GB", { dateStyle: "medium", timeStyle: "short" });

  const imp = importer.data;
  const missingList = missing.data?.missing ?? [];

  return (
    <Panel title={t("data.title")}>
      <div className="row">
        <span className="status">
          {t("data.draws", { count: drawCount ?? 0 })} · {t("data.latestUpdate")}:{" "}
          {lastOk?.finished_at ? fmtTime(lastOk.finished_at) : t("data.never")}
        </span>
        <button type="button" className="primary" onClick={() => collect.mutate()} disabled={running}>
          {running ? t("data.updating") : t("data.updateNow")}
        </button>
        {collect.isError &&
          (collect.error instanceof ApiError && collect.error.status === 501 ? (
            <Status>{t("data.noCollector")}</Status>
          ) : (
            <Status kind="err">
              {collect.error instanceof ApiError && collect.error.status === 409
                ? collect.error.message
                : t("errors.generic", { message: (collect.error as Error).message })}
            </Status>
          ))}
        {latest && !collect.isError && latest.kind === "collector" && (
          <Status kind={logMessage(t, latest).kind}>{logMessage(t, latest).text}</Status>
        )}
      </div>

      <form
        className="row"
        onSubmit={(e) => {
          e.preventDefault();
          if (file) importer.mutate({ file, skipLeading: skip });
        }}
      >
        <Field label={t("data.upload")}>
          {(id) => (
            <input id={id} type="file" accept=".csv,.txt,.xlsx,.xlsm" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          )}
        </Field>
        <Field label={t("data.skip")}>
          {(id) => (
            <input id={id} type="number" min={0} max={20} value={skip} onChange={(e) => setSkip(Math.max(0, Number(e.target.value) | 0))} />
          )}
        </Field>
        <button type="submit" disabled={!file || importer.isPending}>
          {importer.isPending ? t("data.importing") : t("data.import")}
        </button>
        <small className="note">{t("data.skipHint")}</small>
      </form>

      {importer.isError && (
        <Status kind="err">
          {importer.error instanceof ApiError ? importer.error.message : t("errors.network")}
        </Status>
      )}
      {imp && (
        <div className="card stack" aria-live="polite">
          <Status kind={imp.status === "ok" ? "ok" : "err"}>
            {imp.status === "ok"
              ? t("data.result.ok", { added: imp.added, skipped: imp.skipped })
              : t("data.result.conflict", { count: imp.conflicts.length })}
          </Status>
          {imp.rejected_count > 0 && <span className="status">{t("data.result.rejected", { count: imp.rejected_count })}</span>}
          {imp.missing_rows.length > 0 && <span className="status">{t("data.result.missing", { count: imp.missing_rows.length })}</span>}
          {imp.warnings.length > 0 && (
            <span className="status">{t("data.result.warnings")}: {imp.warnings.join("; ")}</span>
          )}
          {imp.rejected.length > 0 && (
            <details>
              <summary>{t("data.result.rejected", { count: imp.rejected_count })}</summary>
              <ul className="note">
                {imp.rejected.slice(0, 20).map((r) => (
                  <li key={r.line_no}>#{r.line_no}: {r.reason}</li>
                ))}
              </ul>
            </details>
          )}
        </div>
      )}

      <details>
        <summary>
          {t("data.missingTitle")} ({missingList.length})
        </summary>
        <div className="stack" style={{ marginTop: 8 }}>
          {missingList.length === 0 ? (
            <span className="status">{t("data.missingNone")}</span>
          ) : (
            <>
              <div className="chips">
                {missingList.slice(0, MISSING_SHOWN).map((n) => (
                  <span key={n} className="chip">{n}</span>
                ))}
                {missingList.length > MISSING_SHOWN && <span className="chip">+{missingList.length - MISSING_SHOWN}</span>}
              </div>
              <small className="note">{t("data.missingNote")}</small>
            </>
          )}
        </div>
      </details>

      <details open={(conflicts.data?.length ?? 0) > 0}>
        <summary>
          {t("data.conflictsTitle")} ({conflicts.data?.length ?? 0})
        </summary>
        <div className="stack" style={{ marginTop: 8 }}>
          {(conflicts.data?.length ?? 0) === 0 ? (
            <span className="status">{t("data.conflictsNone")}</span>
          ) : (
            <>
              <div className="tablewrap">
                <table>
                  <thead>
                    <tr>
                      <th className="l">#</th>
                      <th className="l">{t("bao.laterColumns.date")}</th>
                      <th className="l">{t("data.conflictStored")}</th>
                      <th className="l">{t("data.conflictIncoming")}</th>
                      <th className="l">{t("data.conflictSource")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {conflicts.data!.map((c) => (
                      <tr key={c.id}>
                        <td className="l">{c.draw_no ?? "—"}</td>
                        <td className="l">{fmtDate(c.draw_date)}</td>
                        <td className="l">{c.existing_numbers?.map(pad).join(" ") ?? "—"}</td>
                        <td className="l">{c.incoming_numbers.map(pad).join(" ")}</td>
                        <td className="l">{c.source}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <small className="note">{t("data.conflictNote")}</small>
            </>
          )}
        </div>
      </details>
    </Panel>
  );
}
