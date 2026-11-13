# Deploying the website to Blazer Cloud

Status: **plan, not done.** Nothing here has been run. Direction agreed verbally between Panashe and Takudzwa on 11 November 2026; get it in writing before the first deploy. Owner: Takudzwa.

The site is one static file with no scripts, no cookies and no personal data, so this is the lowest-risk thing to host first. Rolling back means putting the previous copy of the folder back.

## Before the first deploy

Every box in `website/README.md` "Not publishable yet" must be ticked. In particular: domain bought, `CONTACT_EMAIL_TBD` replaced (two places), real photographs, figures and wording signed off.

Also settle, and record in `docs/PROGRESS_LOG.md`:

- **Who owns the registrar account and the server account**, with two administrators and a documented recovery path (STACK.md: accounts are Panashe's, Takudzwa second administrator).
- **The server is operated by Takudzwa's own business.** Disclose that to Cimas and any research partner, and put it in the founders agreement.
- **Location.** A Johannesburg server is outside Zimbabwe. For a static page with no personal data this does not matter; it matters for the backend (`docs/SECURITY.md`, §14.5).

## Layout on the server

Keep releases side by side so rollback is one command:

```
/var/www/silicaguard/
  releases/2026-11-20-1/index.html
  releases/2026-11-27-1/index.html
  current -> releases/2026-11-27-1      # symlink the web server serves
```

Deploy: copy `website/index.html` into a new dated folder, check it in a browser at the staging address, then repoint `current`. Rollback: repoint `current` to the previous folder.

## Web server settings (nginx shown; adapt to whatever Blazer Cloud runs)

- HTTPS only, certificate from Let's Encrypt, HTTP redirected to HTTPS, renewal tested.
- Serve only the `current` folder. Directory listing off.
- Headers. The page uses inline styles and no scripts, so the policy can be strict:
  - `Content-Security-Policy: default-src 'none'; style-src 'unsafe-inline'; img-src 'self' data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'`
  - `X-Content-Type-Options: nosniff`
  - `Referrer-Policy: strict-origin-when-cross-origin`
  - `Strict-Transport-Security: max-age=31536000` once HTTPS is confirmed working
- If real photographs are added, they are `img-src 'self'` files, not third-party hosts.
- No analytics, no tracking pixels, no third-party fonts. If analytics is ever wanted, it needs the team's agreement first.

## Rules that still apply once it is live

- No USSD shortcode until one is allocated. No partnerships, pricing, formal-sector language, login or live demo (§24.1, §23.5).
- Every number on the page comes from `docs/FIGURES.md`.
- The page says no miner has been screened. Update that sentence only when it stops being true.
- Keep a copy of the deployed file in git; the server is never the only copy.

## Next stages (not part of this document)

1. **Staging** (roadmap 0.5): a copy of the backend with demonstration data only. Production data is never copied to staging.
2. **Backend and database**: only after the data-sovereignty decision, backups, monitoring and a tested restore. Panashe owns this.
