/* =========================================================
   BRAND MARK — the NyayMitra shield with the scales of
   justice, drawn as inline SVG so it is crisp at any size,
   needs no image asset, and inherits nothing that could
   break between the light and dark themes.

   The palette here is fixed on purpose: a logo is a logo in
   both themes (deep indigo shield, white scales), matching
   the brand tiles used across the product.
   ========================================================= */

type BrandLogoProps = {
  /** Rendered width/height in px. */
  size?: number;
  className?: string;
};

function BrandLogo({ size = 46, className }: BrandLogoProps) {
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      role="img"
      aria-label="NyayMitra"
    >
      {/* Shield body */}
      <path
        d="M12 1.8 L20.4 4.7 V11.4 C20.4 16.9 16.9 20.9 12 22.2 C7.1 20.9 3.6 16.9 3.6 11.4 V4.7 Z"
        fill="#3730a3"
      />
      {/* Inner hairline for depth */}
      <path
        d="M12 3.5 L18.9 5.9 V11.4 C18.9 15.9 16 19.4 12 20.6 C8 19.4 5.1 15.9 5.1 11.4 V5.9 Z"
        stroke="rgba(255,255,255,0.28)"
        strokeWidth="0.7"
      />
      {/* Scales: centre post, beam, pans, base */}
      <g
        stroke="#ffffff"
        strokeWidth="1.25"
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="none"
      >
        {/* finial */}
        <circle cx="12" cy="6.1" r="0.85" fill="#ffffff" stroke="none" />
        {/* post */}
        <path d="M12 7.2 V17.1" />
        {/* beam */}
        <path d="M7.3 9.4 H16.7" />
        {/* left pan */}
        <path d="M5.6 12.2 A3.2 3.2 0 0 0 9 12.2" />
        <path d="M7.3 9.4 V10.4" />
        {/* right pan */}
        <path d="M15 12.2 A3.2 3.2 0 0 0 18.4 12.2" />
        <path d="M16.7 9.4 V10.4" />
        {/* base */}
        <path d="M9.6 17.3 H14.4" />
      </g>
    </svg>
  );
}

export default BrandLogo;
