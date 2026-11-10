# frontend/CLAUDE.md — Next.js frontend memory

Loaded automatically when working under `frontend/`. Root `CLAUDE.md` rules still apply.

> **Next.js 16.4** (App Router, Turbopack, **Cache Components** + Partial Prefetching enabled). APIs differ from
> older versions — read `node_modules/next/dist/docs/` (see `AGENTS.md`) before using unfamiliar APIs.
> Key consequences: request APIs (`cookies()`, `headers()`, `params`) are async; dynamic data must be inside
> `<Suspense>` or a `"use cache"` function; `new Date()` in a Server Component needs `"use cache"`;
> `middleware` is now `proxy`.

## Layout (as built in Phase 01)

- `src/app/layout.tsx` (Inter, next-intl provider, skip link), `providers.tsx` (TanStack Query),
  `not-found.tsx`, `error.tsx` (500), `global-error.tsx`
- Route groups: `(public)` (header/footer), `(candidate)/candidate`, `(hr)/hr`, `(admin)/admin` (each uses
  `AppShell`), later `apply/[jobId]`
- `src/components/ui` (shadcn, style `radix-nova`; `cn` comes from the `cn` package)
- `src/components/layout` — `Brand`, `PublicHeader`, `PublicFooter`, `AppShell`, `SidebarNav`,
  `OrgSwitcher`/`NotificationBell` (placeholders), `navigation.ts` (nav items per area)
- `src/components/states` — `EmptyState`, `ErrorState` (request id + retry), `ForbiddenState`,
  `PageSkeleton`, `StatusBadge`
- `src/features/<domain>/{components,hooks,api.ts,schemas.ts}` — domain logic (later phases)
- `src/lib/api-client.ts` (`api.get/post/…`, `ApiError`, CSRF, `X-Org-Id`, `Idempotency-Key`),
  `src/types/api.d.ts` (GENERATED — `npm run gen:api` from `../backend/schema.yml`)
- `src/i18n/request.ts` (locale `en`, TZ `Africa/Harare`), `messages/en.json`
- `tests/` (Vitest + Testing Library, jsdom), `e2e/` (Playwright + axe; projects `chromium`, `mobile`)
- `next.config.ts`: `/api/*` rewrites to `API_INTERNAL_URL` (trailing slash preserved), `skipTrailingSlashRedirect`,
  `output: "standalone"`, security headers

## Rules

1. TypeScript strict; no `any`; API types only from generated `api.d.ts`.
2. Server Components by default; `"use client"` only for interactivity. Public pages SSR/ISR for SEO & low bandwidth.
3. Data: TanStack Query in client components; query keys `[domain, id, params]`; invalidate after mutations.
4. Forms: React Hook Form + Zod; map server `details` (`ApiError.fieldErrors()`) to fields; error summary on
   submit; labels + descriptions.
5. Auth: same-origin cookies via rewrites; never store tokens in localStorage; send `X-CSRFToken`; send `X-Org-Id`
   for staff calls from the org context provider.
6. UI never decides permissions — it only hides; server enforces. Always handle 403/404/409/422/423 gracefully.
7. Every view: loading skeleton, empty state, error state (show request_id), permission state.
8. AI content always labelled "AI-assisted suggestion — requires human review". Never use the word "rejected"
   for candidates (a unit test enforces this for `messages/en.json`).
9. Accessibility: keyboard, focus management, 24 px targets, contrast, aria-live for dynamic changes; axe in Playwright.
10. All user-visible strings via next-intl.
11. Client messages: the root layout ships only `PUBLIC_NAMESPACES` (`src/i18n/client-messages.tsx`); signed-in
    areas wrap their tree in `<AreaMessages>`. A public client component needing a new namespace must add it there.
12. Public data: server-side `"use cache"` helpers in `src/features/jobs/public-api.ts` (60 s `cacheLife`), never fetched at
    build time (CI has no backend). Detail pages render blocking (`export const instant = false`, no Suspense) so
    metadata is in `<head>`; do NOT set `htmlLimitedBots: /.*/` (it makes browser prefetches hang).
13. Area layouts wrap `AuthGate` in `<Suspense>`; client hooks reading the URL (`usePathname`, `useSearchParams`) in
    shared layouts must sit under Suspense or dynamic routes fail to build.
14. Dynamic signed-in pages follow `candidate/applications/[id]`: a sync page with `<Suspense>` around a client
    `…Route` wrapper that reads the segment via `useParams` (an `async` page awaiting `params` inside the area's
    AuthGate hung on full loads). Never render `<noscript>` inside these trees (React #418 hydration mismatch).
15. Mutations that change an object's `lock_version` server-side (e.g. attaching documents/answers to a draft) must
    feed the returned object back into the cache before the next optimistic-locked PATCH.

## Commands

```
npm run dev | build | lint | typecheck (next typegen + tsc) | test | format | format:check | gen:api
npx playwright test  |  npx playwright test e2e/apply.spec.ts --project=mobile
DEMO_PASSWORD=... npx playwright test e2e/jobs.spec.ts   # needs `manage.py seed_demo`
../scripts/lighthouse.sh 3 <urls>   # mobile Lighthouse medians (production build)
```

Docker: the `frontend` service runs `next dev` with `API_INTERNAL_URL=http://backend:8000`.
