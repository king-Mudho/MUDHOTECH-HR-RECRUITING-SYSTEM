# frontend/CLAUDE.md — Next.js frontend memory

Loaded automatically when working under `frontend/`. Root `CLAUDE.md` rules still apply.

> Scaffolding note (Phase 1): `create-next-app` refuses a non-empty directory. Scaffold into a temp folder
> (e.g. `../_tmp_next`), then move its contents into `frontend/` keeping this file.

## Layout
- `src/app/(public)`, `(candidate)/candidate`, `(hr)/hr`, `(admin)/admin`, `apply/[jobId]`
- `src/features/<domain>/{components,hooks,api.ts,schemas.ts}` — domain logic lives here, not in route files
- `src/components/ui` (shadcn), `src/components/{layout,forms,data-table,evidence-viewer}`
- `src/lib/api-client.ts` (fetch + CSRF + envelope errors), `src/types/api.d.ts` (GENERATED — `npm run gen:api`)
- `messages/en.json` (next-intl), `tests/` (Vitest), `e2e/` (Playwright)

## Rules
1. TypeScript strict; no `any`; API types only from generated `api.d.ts`.
2. Server Components by default; `"use client"` only for interactivity. Public pages SSR/ISR for SEO & low bandwidth.
3. Data: TanStack Query in client components; query keys `[domain, id, params]`; invalidate after mutations.
4. Forms: React Hook Form + Zod; map server `details` to fields; error summary on submit; labels + descriptions.
5. Auth: same-origin cookies via rewrites; never store tokens in localStorage; send `X-CSRFToken`; send `X-Org-Id` for staff calls from the org context provider.
6. UI never decides permissions — it only hides; server enforces. Always handle 403/404/409/422/423 gracefully.
7. Every view: loading skeleton, empty state, error state (show request_id), permission state.
8. AI content always labelled "AI-assisted suggestion — requires human review". Never use the word "rejected" for candidates.
9. Accessibility: keyboard, focus management, 24 px targets, contrast, aria-live for dynamic changes; run axe in Playwright.
10. All user-visible strings via next-intl.

## Commands
```
npm run dev | build | lint | typecheck | test | gen:api
npx playwright test  |  npx playwright test e2e/apply.spec.ts --project=mobile
```
