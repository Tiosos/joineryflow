/**
 * The session cookie's name, in one place.
 *
 * The API sets this cookie from `settings.session_cookie_name`
 * (`SESSION_COOKIE_NAME` in `.env`), so the web tier has to read the same
 * value or a rename silently breaks every authenticated request. The default
 * matches `apps/api/app/config.py`.
 *
 * This module deliberately imports nothing. `middleware.ts` runs in the Edge
 * runtime and cannot pull in `lib/session.ts`, which uses `next/headers` —
 * hence the constant lives here rather than there.
 *
 * Caveat: Next inlines `process.env` reads in middleware at build time, so a
 * production deploy that changes SESSION_COOKIE_NAME needs a rebuild, not just
 * a restart. The dev loop (`pnpm dev`) reads it at startup.
 */
export const SESSION_COOKIE_NAME =
  process.env.SESSION_COOKIE_NAME ?? "jf_session";
