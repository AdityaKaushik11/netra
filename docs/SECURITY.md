# Security

Netra handles CCTV video, vehicle movements and watchlists, so it is built to be secure by
default: nothing is reachable from the network unless you opt in, every request is
authenticated, and every important action is audited.

## 1. Controls

### Access & sessions
| Control | Detail |
|---|---|
| Authentication | JWT (HS256, 8 h) with required `exp`/`sub`/`typ` claims and a unique `jti`; tokens of one type (e.g. a camera stream token) are rejected where another is expected. |
| Real logout | `POST /auth/logout` revokes the token server-side (Redis deny-list); the WebSocket checks revocation too. |
| Password change | `python -m app.manage set-password <user>` signs out every existing session of that user. |
| Brute force | Per-IP rate limit (10/min) **and** per-account lockout: 5 failures → 15 min lock, regardless of source IP. Unknown usernames lock the same way (no user enumeration). |
| Passwords | bcrypt cost 12; 72-byte maximum enforced (never silently truncated); constant-time path for unknown users. |
| Roles | ADMIN / OPERATOR / VIEWER checked on every route; tested. |
| Machine identities | Random 256-bit API keys, shown once, stored only as HMAC-SHA256; scopes restricted to `events:write`, `cameras:heartbeat`, `cameras:write`; revocable; per-key rate limit. |

### Video & camera credentials
| Control | Detail |
|---|---|
| Credentials at rest | Camera passwords / vendor API keys encrypted with Fernet (AES-128-CBC + HMAC); never returned by the API; URLs with inline `user:pass@` are refused. |
| Stream access | Browsers get a 5-minute token scoped to **one camera**; the video gateway asks the backend to verify it for every HLS, WebRTC and recording request. |
| Gateway control API | Requires the backend's own secret (`GATEWAY_API_SECRET`), so no other container can re-point or delete streams. |
| SSRF protection | Camera endpoints may not target the platform's own services, loopback, link-local (incl. cloud metadata `169.254.169.254`) or reserved addresses. Checked when saved **and** after DNS resolution before every outbound request, including each redirect hop. The snapshot proxy only relays images. |
| XML | ONVIF responses parsed with `defusedxml` (no XXE / billion-laughs). |

### Web & transport
| Control | Detail |
|---|---|
| TLS | Caddy terminates HTTPS (automatic Let's Encrypt with a real domain); HSTS. |
| Content-Security-Policy | Console runs only its own scripts; external origins limited to map tiles and the configured HLS source. Fonts are bundled, so no third-party font requests. |
| Other headers | `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy: no-referrer` (map tiles alone send the site's origin, which OpenStreetMap's usage policy requires; never a path or query), COOP, restrictive `Permissions-Policy`. |
| Request limits | 2 MB API bodies, 64 KB WebRTC offers; validated schemas with length limits on every field. |
| Internal endpoints | `/api/v1/internal/*` and `/api/metrics` are not routed by the edge proxy. |
| Errors | Generic 500 responses; stack traces only in server logs. |

### Infrastructure
| Control | Detail |
|---|---|
| Exposure | Ports bind to `127.0.0.1` by default; set `BIND_ADDRESS=0.0.0.0` only when you deliberately serve other machines. MySQL and Redis publish no ports at all. |
| Network segmentation | Separate `cameras`, `app` and `data` networks. |
| Containers | `no-new-privileges` everywhere; application containers drop **all** Linux capabilities (web keeps only `NET_BIND_SERVICE`); backend and simulator run as non-root users. |
| Secrets | Only in `.env` (git-ignored, `chmod 600`), generated randomly by `make env`; the backend refuses to start in `ENVIRONMENT=production` with the default JWT secret. |
| API docs | `API_DOCS_ENABLED=false` hides Swagger/OpenAPI on internet-facing deployments. |
| Dependencies | Pinned versions; `pip-audit` and `npm audit` report **0 known vulnerabilities** (checked 26 Sep 2026). |
| Audit trail | Logins (success, failure, lockout), logout, onboarding, edits (field-level diff, secrets masked), status changes, stream/recording access, alert handling, watchlist and API-key changes. No endpoint deletes audit records. |

## 2. How it was verified

* 37 automated tests, including `tests/test_security.py`: lockout, server-side logout, forged and
  wrong-type tokens, seven SSRF payloads (Redis, MySQL, localhost, IPv6 loopback, cloud metadata),
  private camera VLANs still allowed, API-key scope validation, over-long passwords, security headers.
* Live checks against the running stack: requests without or with the wrong camera's stream token
  are refused (401); internal endpoints return 404 through the proxy; the gateway API refuses
  calls without the backend secret; ports are bound to localhost only.

## 3. Cost: ₹0

Everything is free and open source; no paid service, API key or subscription is required.

| Component | Licence / terms |
|---|---|
| FastAPI, SQLAlchemy, Pydantic, Redis client, httpx, bcrypt, cryptography | MIT / BSD / Apache-2.0 |
| MySQL Community 8.4 | GPLv2 (free) |
| Redis 7.4 | BSD-3 (free) |
| MediaMTX, FFmpeg | MIT, LGPL/GPL (free) |
| Caddy (incl. Let's Encrypt certificates) | Apache-2.0; certificates are free |
| React, Vite, Tailwind, Leaflet, hls.js, Recharts, Inter & JetBrains Mono fonts | MIT / BSD / OFL |
| Map tiles | OpenStreetMap (free, attribution shown; for heavy production use, self-host tiles) |
| Demo HLS feed | Mux public test stream (free); any legal footage can replace it |
| Docker Desktop / Engine, GitHub, GitHub Actions | Free for personal use and public repositories |

## 4. Residual risks and recommendations

* **Demo passwords.** A short, memorable admin password is easy to guess. The lockout blunts online
  guessing, but set a strong password (`python -m app.manage set-password admin`) before exposing the platform beyond
  your own computer.
* **Lockout abuse.** Anyone can lock an account for 15 minutes by failing five logins. Standard
  trade-off; production would add SSO + MFA (Keycloak / state IdP), which also removes passwords here.
* **Local certificate.** Caddy's internal CA triggers a one-time browser warning on `localhost`;
  use a real domain for trusted certificates.
* **Token storage.** The session token lives in `sessionStorage`; the strict CSP is the defence
  against script injection. Moving to HttpOnly cookies + CSRF tokens is a further hardening step.
* **Map tiles.** Browsers fetch tiles from openstreetmap.org, which sees operators' IPs and the
  map area. Self-host a tile server for an air-gapped deployment.
* **Secrets in environment variables** are visible to anyone with Docker access on the host; use
  Docker/Kubernetes secrets or Vault in production.
