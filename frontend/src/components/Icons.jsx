/** Small, hand-drawn stroke icons — deliberately not emoji.
 *
 * The header used 🏠 and 🧪 originally, which render differently across
 * platforms (different weight, different color treatment, some systems
 * showing them in full color) in a UI that otherwise commits to a
 * consistent dark, cyan/magenta palette. A plain 24x24 stroke icon inherits
 * `currentColor`, so it always matches the button text around it exactly —
 * the same reason `.icon-button` already resets font/color for these.
 *
 * No icon library pulled in for two glyphs: these are drawn directly as
 * plain geometry rather than reproducing a specific library's icon set.
 */

const BASE_PROPS = {
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.75,
  strokeLinecap: "round",
  strokeLinejoin: "round",
  "aria-hidden": "true",
  focusable: "false",
};

export function HomeIcon({ size = 18, className }) {
  return (
    <svg {...BASE_PROPS} width={size} height={size} className={className}>
      <path d="M4 12 L12 4 L20 12" />
      <path d="M6 11 V20 H18 V11" />
      <rect x="10" y="14" width="4" height="6" rx="0.5" />
    </svg>
  );
}

/** A simple isometric box/cube — stands in for "3D model" without reusing
 * the goggles glyph the Devices button already owns, which points at real
 * registered hardware rather than the design-and-demo showcase this links to. */
export function SimulatorIcon({ size = 18, className }) {
  return (
    <svg {...BASE_PROPS} width={size} height={size} className={className}>
      <path d="M4 9 L4 20 L16 20 L16 9 Z" />
      <path d="M4 9 L8 4 L20 4 L16 9 Z" />
      <path d="M16 9 L20 4 L20 15 L16 20" />
    </svg>
  );
}
