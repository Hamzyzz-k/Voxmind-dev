export default function ToneToggle({ tone, onChange, disabled }) {
  return (
    <div className="tone-toggle">
      <button
        type="button"
        className={tone === "friendly" ? "active" : ""}
        disabled={disabled}
        onClick={() => onChange("friendly")}
      >
        Friendly
      </button>
      <button
        type="button"
        className={tone === "official" ? "active" : ""}
        disabled={disabled}
        onClick={() => onChange("official")}
      >
        Official
      </button>
    </div>
  );
}
