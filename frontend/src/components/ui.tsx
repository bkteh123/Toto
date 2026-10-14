import { useId, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { ApiError, downloadFile, exportUrl, type ExportFormat, type ExportKind } from "../api/client";
import { pad } from "../lib/format";

export function Ball({ n, sm, bonus }: { n: number; sm?: boolean; bonus?: boolean }) {
  return <span className={`ball${sm ? " sm" : ""}${bonus ? " bonus" : ""}`}>{pad(n)}</span>;
}

export function Balls({
  numbers,
  sm,
  bonus,
  label,
}: {
  numbers: number[];
  sm?: boolean;
  bonus?: number | null;
  label?: string;
}) {
  return (
    <div className="balls" role="group" aria-label={label ?? numbers.map(pad).join(" ")}>
      {numbers.map((n) => (
        <Ball key={n} n={n} sm={sm} />
      ))}
      {bonus !== null && bonus !== undefined && (
        <>
          <span className="plus" aria-hidden="true">+</span>
          <Ball n={bonus} sm={sm} bonus />
        </>
      )}
    </div>
  );
}

/** A panel whose heading names it for assistive technology. */
export function Panel({ title, children, extra }: { title: string; children: ReactNode; extra?: ReactNode }) {
  const id = useId();
  return (
    <section className="panel" aria-labelledby={id}>
      <div className="row between">
        <h2 id={id}>{title}</h2>
        {extra}
      </div>
      {children}
    </section>
  );
}

export function Field({ label, children }: { label: string; children: (id: string) => ReactNode }) {
  const id = useId();
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      {children(id)}
    </div>
  );
}

/** Copies text and tells the user what happened; clipboard access can be refused. */
export function CopyButton({ text, disabled }: { text: () => string; disabled?: boolean }) {
  const { t } = useTranslation();
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text());
      setMsg({ ok: true, text: t("app.copied") });
    } catch {
      setMsg({ ok: false, text: t("app.copyFailed") });
    }
  };
  return (
    <>
      <button type="button" className="small" onClick={copy} disabled={disabled}>
        {t("app.copyCsv")}
      </button>
      <span className={`status${msg && !msg.ok ? " err" : ""}`} role="status">
        {msg?.text}
      </span>
    </>
  );
}

/**
 * CSV / Excel downloads. `query` carries the on-screen parameters for the deterministic exports;
 * `body` (combos only) is POSTed because generated picks are random and cannot be recomputed.
 */
export function ExportButtons({
  game,
  kind,
  query,
  body,
}: {
  game: string;
  kind: ExportKind;
  query?: Record<string, string | number | undefined | null>;
  body?: unknown;
}) {
  const { t } = useTranslation();
  const [busy, setBusy] = useState<ExportFormat | null>(null);
  const [error, setError] = useState<string | null>(null);

  const run = async (f: ExportFormat) => {
    setBusy(f);
    setError(null);
    try {
      const url = exportUrl(game, kind, f, query);
      const init: RequestInit | undefined =
        body === undefined
          ? undefined
          : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
      await downloadFile(url, init, `${game}-${kind}.${f}`);
    } catch (e) {
      setError(
        e instanceof ApiError && e.status !== 0 ? e.message : t("errors.network"),
      );
    } finally {
      setBusy(null);
    }
  };

  return (
    <>
      <span className="row" role="group" aria-label={t("export.label")}>
        {(["csv", "xlsx"] as const).map((f) => (
          <button key={f} type="button" className="small" disabled={busy !== null} onClick={() => run(f)}>
            {t(`export.${f}`)}
          </button>
        ))}
      </span>
      {error && (
        <span className="status err" role="alert">
          {error}
        </span>
      )}
    </>
  );
}

export function Status({ kind, children }: { kind?: "err" | "ok"; children?: ReactNode }) {
  return (
    <span className={`status${kind ? ` ${kind}` : ""}`} role={kind === "err" ? "alert" : "status"}>
      {children}
    </span>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>;
}
