// Security headers (SPEC-FE-047 G1). The basic headers apply everywhere. HSTS and
// the Content-Security-Policy apply only to production builds, because `next dev`
// needs eval and plain http. The CSP allows the backend origin from
// NEXT_PUBLIC_API_BASE_URL, data:/blob: images and media (branding, ad previews),
// inline styles (the shell uses style props) and Next's inline bootstrap scripts.
// SPEC-FE-076: Meta's JS SDK for WhatsApp Embedded Signup (connect.facebook.net,
// its facebook.com frames and calls) — only those Meta hosts.
const isProd = process.env.NODE_ENV === "production";

function apiOrigin() {
  try {
    return new URL(process.env.NEXT_PUBLIC_API_BASE_URL ?? "").origin;
  } catch {
    return "";
  }
}

function securityHeaders() {
  const headers = [
    { key: "X-Frame-Options", value: "DENY" },
    { key: "X-Content-Type-Options", value: "nosniff" },
    { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
    // Microphone for this site only: Command Chat voice commands (SPEC-FE-062).
    { key: "Permissions-Policy", value: "camera=(), microphone=(self), geolocation=()" },
  ];
  if (isProd) {
    const api = apiOrigin();
    const csp = [
      "default-src 'self'",
      "script-src 'self' 'unsafe-inline' https://connect.facebook.net",
      // The PilotSonic font (SPEC-FE-072) from Google Fonts: its stylesheet and font files.
      "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
      `img-src 'self' data: blob: https:${api ? ` ${api}` : ""}`,
      `media-src 'self' data: blob: https:${api ? ` ${api}` : ""}`,
      "font-src 'self' data: https://fonts.gstatic.com",
      `connect-src 'self'${api ? ` ${api}` : ""} https://*.facebook.com https://connect.facebook.net`,
      "frame-src https://*.facebook.com",
      "frame-ancestors 'none'",
      "base-uri 'self'",
      "form-action 'self'",
      "object-src 'none'",
    ].join("; ");
    headers.push(
      { key: "Strict-Transport-Security", value: "max-age=31536000; includeSubDomains" },
      { key: "Content-Security-Policy", value: csp },
    );
  }
  return headers;
}

/** @type {import('next').NextConfig} */
const nextConfig = {
  poweredByHeader: false,
  // Self-contained server bundle (.next/standalone/server.js) for the cPanel
  // "Setup Node.js App" host, which runs it under Passenger with its own PORT.
  output: "standalone",
  // Lets a production build be checked without touching the dev server's .next
  // (SPEC-FE-047 G4). Unset = the default ".next".
  ...(process.env.NEXT_BUILD_DIR ? { distDir: process.env.NEXT_BUILD_DIR } : {}),
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders() }];
  },
  // Campaigns moved under Marketing › Paid Marketing (SPEC-FE-049); old
  // bookmarks and links keep working (308).
  async redirects() {
    return [
      { source: "/campaigns", destination: "/marketing/paid", permanent: true },
      { source: "/campaigns/:path*", destination: "/marketing/paid/:path*", permanent: true },
    ];
  },
};

export default nextConfig;
