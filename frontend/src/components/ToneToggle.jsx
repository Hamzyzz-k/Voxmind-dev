/** Friendly / Official as a segmented pair, styled to sit alongside the
 *  Log out button rather than as a separate visual language. */
export default function ToneToggle({ tone, onChange, disabled }) {
  return (
    <div className="tone-toggle" role="group" aria-label="Response tone">
      {[
        { value: "friendly", label: "Friendly" },
        { value: "official", label: "Official" },
      ].map(({ value, label }) => (
        <button
          key={value}
          type="button"
          className={`tone-option${tone === value ? " active" : ""}`}
          aria-pressed={tone === value}
          disabled={disabled}
          onClick={() => tone !== value && onChange(value)}
        >
          {label}
        </button>
      ))}
    </div>
  );
}
