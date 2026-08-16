/**
 * The session cookie's name, in one place.
 *
 * The API sets this cookie from `settings.session_cookie_name`
 * (`SESSION_COOKIE_NAME` in `.env`), so the web tier has to read the same
 * value or a rename silently breaks every authenticated request. The default
 * matches `apps/api/app/config.py`.
 *
 * This module deliberately imports nothing. `proxy.ts` runs in its own
 * execution context ahead of the app and must not pull in `lib/session.ts`,
 * which uses `next/headers` — hence the constant lives here rather than there.
 *
 * `proxy` runs in the Node.js runtime, so `process.env.SESSION_COOKIE_NAME`
 * is read at runtime; a deploy that changes it does not need a web rebuild.
 * (Under the old Edge-runtime `middleware`, Next inlined the value at build
 * time, so a rename there required rebuilding — no longer the case.)
 */
export const SESSION_COOKIE_NAME =
  process.env.SESSION_COOKIE_NAME ?? "jf_session";
