import { useTranslation } from "react-i18next";

/** "codencode" in black and ".my" in mint, on a light chip so the black stays legible on the dark page. */
export function Wordmark() {
  return (
    <span className="wordmark" aria-label="codencode.my">
      <span className="a">codencode</span>
      <span className="b">.my</span>
    </span>
  );
}

export function Footer() {
  const { t } = useTranslation();
  return (
    <footer className="site">
      <Wordmark />
      <p>{t("app.footer")}</p>
    </footer>
  );
}
