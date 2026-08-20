import type { NextConfig } from "next";

/**
 * Deux projets Vercel (frontend / backend) reliés par un proxy same-origin.
 * Le navigateur n'appelle jamais le backend directement : il appelle
 * /api/backend/v1/... sur son propre domaine, ce qui rend le cookie de
 * session httpOnly utilisable sans CORS (plan.md § 3.8).
 *
 * En dev local, `next dev` applique aussi ce rewrite : BACKEND_ORIGIN doit
 * pointer vers http://localhost:8000 (uvicorn).
 */
const BACKEND_ORIGIN = process.env.BACKEND_ORIGIN ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/backend/:path*",
        destination: `${BACKEND_ORIGIN}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
