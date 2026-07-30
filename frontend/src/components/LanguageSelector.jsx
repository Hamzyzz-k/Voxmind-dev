import { LANG_LABELS } from "../services/speech";

export default function LanguageSelector({ lang, onChange, disabled }) {
  return (
    <select className="lang-select" value={lang} onChange={(e) => onChange(e.target.value)} disabled={disabled}>
      {Object.entries(LANG_LABELS).map(([code, label]) => (
        <option key={code} value={code}>
          {label}
        </option>
      ))}
    </select>
  );
}
