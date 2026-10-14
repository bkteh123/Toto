import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ApiError } from "../api/client";
import { useCreateGame } from "../api/hooks";
import type { Game } from "../api/types";
import { saveLang, type Lang } from "../i18n";
import { fmtInt } from "../lib/format";
import { Field, Status } from "./ui";

export function gamePriceLabel(g: Game): string {
  return `${fmtInt(Number(g.ticket_price))} ${g.currency}`;
}

function CustomGameForm({ onDone }: { onDone: (code: string) => void }) {
  const { t } = useTranslation();
  const create = useCreateGame();
  const [f, setF] = useState({
    code: "", name: "", max: 49, pick: 6, bonus: false, bonusMax: 49, price: "1", currency: "USD",
  });
  const set = <K extends keyof typeof f>(k: K, v: (typeof f)[K]) => setF((s) => ({ ...s, [k]: v }));

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    create.mutate(
      {
        code: f.code.trim(),
        name: f.name.trim(),
        max_number: f.max,
        pick_count: f.pick,
        has_bonus: f.bonus,
        bonus_max: f.bonus ? f.bonusMax : null,
        ticket_price: f.price,
        currency: f.currency.trim(),
      },
      { onSuccess: (g) => onDone(g.code) },
    );
  };

  return (
    <form className="card stack" onSubmit={submit}>
      <div className="row">
        <Field label={t("game.code")}>
          {(id) => (
            <input id={id} value={f.code} onChange={(e) => set("code", e.target.value)} required
              pattern="[a-z0-9_]+" minLength={2} maxLength={64} placeholder="my_game_649" />
          )}
        </Field>
        <Field label={t("game.name")}>
          {(id) => <input id={id} value={f.name} onChange={(e) => set("name", e.target.value)} required maxLength={200} />}
        </Field>
        <Field label={t("game.max")}>
          {(id) => <input id={id} type="number" min={2} max={500} value={f.max} onChange={(e) => set("max", Number(e.target.value))} required />}
        </Field>
        <Field label={t("game.pick")}>
          {(id) => <input id={id} type="number" min={1} max={20} value={f.pick} onChange={(e) => set("pick", Number(e.target.value))} required />}
        </Field>
        <Field label={t("game.price")}>
          {(id) => <input id={id} type="number" min={0} step="any" value={f.price} onChange={(e) => set("price", e.target.value)} required />}
        </Field>
        <Field label={t("game.currency")}>
          {(id) => <input id={id} value={f.currency} onChange={(e) => set("currency", e.target.value)} required maxLength={8} style={{ width: 90 }} />}
        </Field>
      </div>
      <small className="note">{t("game.codeHint")}</small>
      <div className="row">
        <label className="row" style={{ gap: 6, textTransform: "none", letterSpacing: 0 }}>
          <input type="checkbox" checked={f.bonus} onChange={(e) => set("bonus", e.target.checked)} />
          {t("game.bonus")}
        </label>
        {f.bonus && (
          <Field label={t("game.bonusMax")}>
            {(id) => <input id={id} type="number" min={1} max={500} value={f.bonusMax} onChange={(e) => set("bonusMax", Number(e.target.value))} />}
          </Field>
        )}
        <button className="primary" type="submit" disabled={create.isPending}>{t("game.create")}</button>
      </div>
      {create.isError && (
        <Status kind="err">
          {create.error instanceof ApiError ? create.error.message : t("errors.network")}
        </Status>
      )}
    </form>
  );
}

export function Header({
  games,
  code,
  onGame,
  lang,
  onLang,
}: {
  games: Game[];
  code: string | undefined;
  onGame: (code: string) => void;
  lang: Lang;
  onLang: (l: Lang) => void;
}) {
  const { t } = useTranslation();
  const [adding, setAdding] = useState(false);
  const current = games.find((g) => g.code === code);

  const choose = (l: Lang) => {
    saveLang(l);
    onLang(l);
  };

  return (
    <>
      <header className="top">
        <div>
          <div className="eyebrow">{t("app.eyebrow")}</div>
          <h1>{t("app.title")}</h1>
        </div>
        <p className="disclaimer">{t("app.disclaimer")}</p>
      </header>

      <section className="panel" aria-label={t("game.label")}>
        <div className="row between">
          <div className="row">
            <Field label={t("game.label")}>
              {(id) => (
                <select id={id} value={code ?? ""} onChange={(e) => onGame(e.target.value)}>
                  {games.map((g) => (
                    <option key={g.code} value={g.code}>{g.name}</option>
                  ))}
                </select>
              )}
            </Field>
            {current && (
              <span className="status">
                {t("game.summary", { k: current.pick_count, n: current.max_number, price: gamePriceLabel(current) })}
              </span>
            )}
            <button type="button" className="small" onClick={() => setAdding((v) => !v)} aria-expanded={adding}>
              + {t("game.custom")}
            </button>
          </div>
          <div className="langtoggle" role="group" aria-label={t("app.language")}>
            <button type="button" aria-pressed={lang === "zh"} onClick={() => choose("zh")} lang="zh">简体中文</button>
            <button type="button" aria-pressed={lang === "en"} onClick={() => choose("en")} lang="en">English</button>
          </div>
        </div>
        {adding && (
          <CustomGameForm
            onDone={(c) => {
              setAdding(false);
              onGame(c);
            }}
          />
        )}
      </section>
    </>
  );
}
