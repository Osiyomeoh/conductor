// Conductor's mark: three streams (humans and agents) converging to one
// verified node. It is the product's own merge/branch geometry, distilled —
// ownable, meaningful, and legible down to a favicon.

export function Glyph({ color = "#04191b" }: { color?: string }) {
  return (
    <svg viewBox="0 0 24 24" width="100%" height="100%" fill="none" aria-hidden>
      <path d="M4 6.5C9 6.5 10.5 12 15 12" stroke={color} strokeWidth="1.9" strokeLinecap="round" opacity=".55" />
      <path d="M4 12h11" stroke={color} strokeWidth="1.9" strokeLinecap="round" />
      <path d="M4 17.5C9 17.5 10.5 12 15 12" stroke={color} strokeWidth="1.9" strokeLinecap="round" opacity=".55" />
      <circle cx="17.4" cy="12" r="3.1" fill={color} />
    </svg>
  );
}

// The chip form: the glyph on the teal brand square, used as the logo mark.
export function Mark({ size = 24 }: { size?: number }) {
  return (
    <span style={{
      width: size, height: size, borderRadius: size * 0.29, background: "var(--accent)",
      display: "inline-grid", placeItems: "center", flex: "none",
    }}>
      <span style={{ width: size * 0.72, height: size * 0.72, display: "block" }}><Glyph /></span>
    </span>
  );
}
