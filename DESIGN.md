---
version: alpha
name: raguard
description: Evidence-first UI design contract for raguard — self-hosted multi-tenant conversational RAG over internal documents (React + Vite + TanStack Router/Query, apps/web).
colors:
  surface: "#FAF9F5"
  surface-raised: "#FFFFFF"
  surface-muted: "#F0EDE2"
  ink: "#201D17"
  ink-muted: "#57524A"
  ink-faint: "#857F72"
  border: "#DCD7C7"
  primary: "#24507E"
  primary-hover: "#1C3F63"
  primary-active: "#16324E"
  on-primary: "#FBF9F2"
  accent: "#E3B341"
  accent-on: "#3B2F0B"
  danger: "#A63A2B"
  danger-hover: "#8C2F22"
  on-danger: "#FFF6F4"
  warning: "#9A6700"
  on-warning: "#FFFBF0"
  success: "#2F6B4F"
  on-success: "#F2F9F4"
  focus: "#24507E"
typography:
  display-lg:
    fontFamily: IBM Plex Sans
    fontSize: 1.75rem
    fontWeight: 600
    lineHeight: 1.25
    letterSpacing: -0.01em
  display-md:
    fontFamily: IBM Plex Sans
    fontSize: 1.25rem
    fontWeight: 600
    lineHeight: 1.3
    letterSpacing: -0.01em
  title-md:
    fontFamily: IBM Plex Sans
    fontSize: 1rem
    fontWeight: 600
    lineHeight: 1.5
  body-md:
    fontFamily: IBM Plex Sans
    fontSize: 1rem
    fontWeight: 400
    lineHeight: 1.65
  body-sm:
    fontFamily: IBM Plex Sans
    fontSize: 0.875rem
    fontWeight: 400
    lineHeight: 1.5
  mono-sm:
    fontFamily: IBM Plex Mono
    fontSize: 0.8125rem
    fontWeight: 400
    lineHeight: 1.5
    fontFeature: "tnum 1"
  mono-xs:
    fontFamily: IBM Plex Mono
    fontSize: 0.75rem
    fontWeight: 400
    lineHeight: 1.4
    fontFeature: "tnum 1"
rounded:
  sm: 4px
  md: 8px
  lg: 12px
  full: 9999px
spacing:
  xs: 4px
  sm: 8px
  md: 16px
  lg: 24px
  xl: 32px
  xxl: 48px
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    rounded: "{rounded.md}"
    padding: 12px
    height: 40px
  button-primary-hover:
    backgroundColor: "{colors.primary-hover}"
    textColor: "{colors.on-primary}"
    rounded: "{rounded.md}"
    padding: 12px
    height: 40px
  button-primary-active:
    backgroundColor: "{colors.primary-active}"
    textColor: "{colors.on-primary}"
    rounded: "{rounded.md}"
    padding: 12px
    height: 40px
  button-primary-disabled:
    backgroundColor: "{colors.surface-muted}"
    textColor: "{colors.ink-muted}"
    rounded: "{rounded.md}"
    padding: 12px
    height: 40px
  button-secondary:
    backgroundColor: "{colors.surface-raised}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    padding: 12px
    height: 40px
  button-destructive:
    backgroundColor: "{colors.danger}"
    textColor: "{colors.on-danger}"
    rounded: "{rounded.md}"
    padding: 12px
    height: 40px
  button-destructive-hover:
    backgroundColor: "{colors.danger-hover}"
    textColor: "{colors.on-danger}"
    rounded: "{rounded.md}"
    padding: 12px
    height: 40px
  button-ghost:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink-muted}"
    rounded: "{rounded.md}"
    padding: 12px
    height: 40px
  input:
    backgroundColor: "{colors.surface-raised}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    padding: 12px
    height: 40px
  card-surface:
    backgroundColor: "{colors.surface-raised}"
    rounded: "{rounded.lg}"
    padding: 24px
  chip-status-pending:
    backgroundColor: "{colors.warning}"
    textColor: "{colors.on-warning}"
    rounded: "{rounded.full}"
    padding: 4px 10px
  chip-status-indexing:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    rounded: "{rounded.full}"
    padding: 4px 10px
  chip-status-indexed:
    backgroundColor: "{colors.success}"
    textColor: "{colors.on-success}"
    rounded: "{rounded.full}"
    padding: 4px 10px
  chip-status-failed:
    backgroundColor: "{colors.danger}"
    textColor: "{colors.on-danger}"
    rounded: "{rounded.full}"
    padding: 4px 10px
  citation-marker:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.accent-on}"
    rounded: "{rounded.full}"
    size: 18px
  source-highlight:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.ink}"
  skeleton:
    backgroundColor: "{colors.surface-muted}"
    rounded: "{rounded.sm}"
  toast-error:
    backgroundColor: "{colors.danger}"
    textColor: "{colors.on-danger}"
    rounded: "{rounded.md}"
    padding: 12px 16px
---

> **Status**: Draft — greenfield UI design contract, not yet implemented &nbsp;|&nbsp; **Last updated**: 2026-08-04 &nbsp;|&nbsp; **Author**: Jonathan Soto (jonasotoaguilar)

This document is the UI design contract for the raguard web app (`apps/web`) as specified by [PRD.md](./PRD.md) and [ARCHITECTURE.md](./ARCHITECTURE.md). The repository is at bootstrap stage: nothing described here exists as code yet, and no API surface beyond the architecture sketch is assumed to exist (see [Data Fetching & Cache](#data-fetching--cache-tanstack-query) for the endpoint contract points to confirm at API build). `DESIGN.md` is owned by the `design-ui` skill; product intent lives in `PRD.md`, system design in `ARCHITECTURE.md` — this document does not restate or replace either.

## Overview

raguard's UI must make one gesture effortless: **verify the answer against the source**. Every surface — chat, citations, document library, admin — exists to support a trust decision. The design is an evidence desk, not a chatbot arcade.

### Product & UI principles

1. **Evidence before fluency** — an answer without an openable source is incomplete, not acceptable. Verification is the default gesture: citations are rendered in the answer flow, never hidden behind menus.
2. **Trust is the product** — the interface is calm, paper-light, and predictable. Density is balanced: quiet for chat, information-dense where admins work. Variance is predictable; nothing decorative surprises the user mid-verification.
3. **Authorization is the floor, not the feature** — the UI presents what the API verified. The retrieval-level authorization invariant ([ADR-0002](docs/adr/0002-retrieval-level-authorization.md)) means the UI never *is* the control: hiding a control client-side is presentation, never enforcement. The UI renders only data the API returned; it never constructs citations, chunk links, or document content on its own.
4. **Document content is untrusted data** — document-derived text is rendered as *text*, never as HTML, never as instructions. Prompt-injection hardening is an API concern; the UI's equivalent is a rendering pipeline that treats every document byte as hostile input (no `dangerouslySetInnerHTML` with document content, sanitized Markdown).
5. **Honest states** — loading, empty, error, and forbidden are first-class designed surfaces with a clear next action. No placeholder content, no fabricated answers, no existence leaks.
6. **Calm motion, no spectacle** — motion only explains state change (message arrival, dialog open, status transition). Restrained values, `prefers-reduced-motion` honored.
7. **One query surface** — the chat composer is the search. There is no parallel global search box in the MVP (no global/public search across tenants is a PRD non-goal).
8. **Tenant clarity** — the active tenant is always visible in the shell, because scope confusion is a security error, not a UX nicety.

### Atmosphere (design direction)

> A compliance officer at her desk at 10:00 AM checks an answer against the actual policy PDF. The app is quiet, paper-light, and every citation opens like a highlighted passage in the original document.

Committed axes: **density** balanced, **variance** predictable, **motion** restrained, **color strategy** restrained (warm paper neutrals + one fountain-ink blue accent ≤ 10% of surfaces; highlighter yellow reserved exclusively for cited passages).

Anti-template check (two altitudes):
- *First-order reflex* ("AI/RAG tool → SaaS cream + purple gradient + chat bubbles"): rejected — warm paper-and-ink neutrals, a single deep fountain-ink primary, and a physical highlighter metaphor for citations.
- *Second-order reflex* ("alternative → terminal-dark hacker tool"): rejected — the design is light-first paper, not dark mode as identity, and mono type is reserved for metadata, not chrome.

### Personas and primary journeys

| Persona | Primary journey | Key surfaces |
|---|---|---|
| Member | Ask → verify → follow up | Chat, citations, source preview |
| Organization admin | Onboard tenant → invite users → assign roles → upload documents | Admin setup, users, roles, documents |
| Organization admin | Monitor ingestion | Document library, statuses, failure reasons |
| Maintainer/evaluator | Check system + evaluation health (conditional) | Admin → System status |
| Security reviewer | Demonstrate isolation | Forbidden states, neutral empty states, status surface |

## Colors

Warm paper-and-ink palette. Semantic roles, never raw hex in components.

- **Surfaces** — `surface` (paper), `surface-raised` (cards/inputs), `surface-muted` (skeleton, disabled fills, hover rows). Warm tinted neutrals, never default-tint cool gray.
- **Ink** — `ink` (near-black with warm cast, body), `ink-muted` (secondary text), `ink-faint` (meta, placeholders, disabled text — never body copy).
- **Primary** — fountain-ink blue `primary` for primary actions, links, active nav, and the `indexing` status chip. Accent coverage stays ≤ 10% of any surface; the product reads as paper and ink, not blue.
- **Accent (citation)** — highlighter yellow `accent`. Used in exactly two places: citation markers and the highlighted chunk passage inside the source preview. Its scarcity is what makes citations findable.
- **Semantic** — `danger` (errors, failures, destructive actions), `warning` (pending/queued status), `success` (indexed/healthy status). Status is never communicated by color alone: chips always pair color with a text label and icon.
- **Focus** — `focus` ring (2px, 3:1 contrast against adjacent surface, `:focus-visible` only). Instant, never animated.
- **Dark mode** — light-first; dark tokens are a follow-up, designed as warm charcoal paper (`surface` ≈ `#17161A`-family with the same warm cast, not inverted light tokens). Tune saturation lower in dark to avoid glare. Not part of the MVP.

## Typography

One humanist family plus its mono sibling — **IBM Plex Sans** (UI and prose) and **IBM Plex Mono** (metadata) — paired on the contrast axis of the same foundry, which keeps the identity coherent and avoids the Inter-default SaaS reflex.

- **Display** — `display-lg` (page titles), `display-md` (section titles). Hierarchy through weight and size, not novelty.
- **Body** — `body-md` (chat answers, prose), `body-sm` (supporting text, tables). Relaxed leading (1.5–1.65); answer text max-width ~65–75ch.
- **Mono** — `mono-sm`/`mono-xs` for chunk positions, timestamps, document names in metadata, status codes, file sizes. Tabular numerals (`tnum`) for all numeric metadata.
- Body minimum `1rem`; never below 14px for text.

## Layout

- **App shell** — sidebar navigation (desktop) + header; main content region. Three primary nav items max: **Chat**, **Documents**, **Admin** (admin only). ≤ 5 nav items at any width.
- **Containment** — layouts use `max-width`; chat thread column caps at ~760px; grids use `repeat(auto-fit, minmax(280px, 1fr))` and `minmax(0, 1fr)` so nothing overflows. No horizontal scroll at any width.
- **Spacing** — scale `xs 4 / sm 8 / md 16 / lg 24 / xl 32 / xxl 48`; tighter inside groups, looser between groups. Rhythm varies; never uniform padding everywhere.
- **Z-index** — semantic scale only: sticky header → drawer → dialog backdrop → dialog → toast → tooltip. No arbitrary values.
- **Full-height** sections use `min-h-[100dvh]`; the chat composer stays pinned to the viewport bottom on mobile (safe-area aware).
- **Grid vs flex** — grid for 2D (document cards, tables), flex for 1D (toolbars, forms).

## Elevation & Depth

The paper metaphor means **flat, bordered surfaces** are the default; shadows are used sparingly, never as decoration.

- Level 0: flat surfaces separated by 1px `border` hairlines.
- Level 1: raised controls and cards — 1px border + soft shadow (e.g., `0 1px 2px rgb(32 29 23 / 0.06)`).
- Level 2: drawers and dialogs — stronger shadow + scrim (`rgb(32 29 23 / 0.4)`).
- Backdrop blur only for the source-preview scrim when it materially improves reading focus; never glassmorphism as decoration.

## Shapes

Small, calm radii. `sm` 4px (chips, skeletons, inline elements), `md` 8px (buttons, inputs, toasts), `lg` 12px (cards, dialogs, dropzone), `full` (status chips, citation markers). Inner elements use a radius slightly smaller than their outer container. Geometry stays constant across states — state is signaled by background, outline, or shadow, never by changing border-width or height.

## Components

### Conventions

- **Taxonomy**: primitive (Button, Input, Dialog) → component (Composer, CitationMarker, StatusChip) → block (AppShell, DocumentQueue) → template (route pages).
- **State contract** for every interactive component: default, hover, `focus-visible`, active, disabled, loading, error (plus selected, invalid, empty where applicable). Styled via `data-state`, `data-disabled`, `data-loading`, `data-invalid`.
- **Tokens only**: components reference semantic tokens (`{colors.*}`, `{typography.*}`); raw hex/fonts at call sites are a review defect. New values are promoted to this document's tokens first.
- **Keyboard behavior documented per component** (below). Semantic HTML first; ARIA only where the pattern requires it (dialog, menu, tabs, combobox).
- **Icons**: one vector icon set (Lucide recommended; confirm at implementation) with accessible names. Emojis are valid as content (e.g., a toast celebration) but **never** as functional icons (nav, settings, status) — they are font-dependent and not themable.
- **Buttons**: one primary per decision area; labels are action phrases ("Save changes", "Upload documents"); icons paired with labels unless universally obvious; subtle press feedback (scale 0.98–1.02) with zero layout shift.

### Registry (MVP)

| Component | Behavior notes | States & a11y |
|---|---|---|
| Button (primary/secondary/destructive/ghost) | Primary = one per decision area | disabled, loading (spinner replaces label, geometry fixed) |
| Input, Textarea, Select | Visible labels always; placeholder is hint only (allowed in search); inline errors via `aria-describedby`; validate on blur, not keystroke | invalid, error, disabled |
| Dropzone | Keyboard-accessible (Enter/Space opens picker); drag-drop is enhancement, not requirement; accepts `.pdf`, `.md`/`.markdown`; client-side type/size pre-validation | dragging, error (unsupported file) |
| StatusChip | Text + icon + color; never color-only | one of: pending, indexing, indexed, failed |
| Table (documents, users) | Real `<table>` with `<th scope>`; rows as cards below 768px | selected, empty, loading (skeleton rows) |
| Dialog (source preview, confirmations) | `role="dialog"`, focus trap, Esc closes, focus returns to trigger | open, loading chunk |
| Menu (user menu, row actions) | Keyboard navigable, correct `menuitem` roles | open, disabled item |
| Toast | Error/success notifications; live region | — |
| Tooltip | Hover/focus triggered, never required to act | — |
| Skeleton | Matches final geometry exactly (CLS-safe); shimmer at restrained speed | — |
| EmptyState | Title + one next action; permission-neutral wording | — |
| ErrorState | Renders `{error: {code, message, details?}}` envelope + retry | — |
| ForbiddenState | 403 surface; no existence disclosure | — |
| Composer | Multiline textarea, autofocused on route enter, Enter sends, Shift+Enter newline | disabled while pending, error (rate limit) |
| Message | User (raised) / assistant (flat paper); assistant carries citations | pending skeleton, error card, ungrounded notice |
| CitationMarker | Superscript button, accent-filled; `aria-label="Source n: <document title>"` | hover/focus shows popover |
| SourcePreview | Dialog: document header, highlighted chunk, position `chunk i of n`, prev/next | loading, missing (chunk revoked/deleted) |
| ConversationList | Sidebar list (drawer on mobile); active conversation highlighted | empty, loading |
| AppShell | Sidebar + header (tenant name, user menu); skip link | — |
| TenantSwitcher | Visible when user has > 1 membership; only tenants the API lists | — |

## Information Architecture & Routes

Route table (TanStack Router; file-based vs code-based routing decided at implementation — the contract below is the stable map):

| Route | Surface | Access |
|---|---|---|
| `/login` | Sign in (email + password; JWT via same-domain cookie per config-time conventions) | public |
| `/chat` | Conversation list + empty thread (or last conversation) | member |
| `/chat/$conversationId` | Thread view; deep-linkable | member (owner) |
| `/documents` | Document library + upload dropzone | member (documents visible = authorized documents only) |
| `/documents/$documentId` | Document detail: metadata, status history, authorized chunk list | member (document grant) |
| `/admin` | Org settings (name, tenant identity) | admin |
| `/admin/users` | Users, invites, role assignment | admin |
| `/admin/roles` | Roles list; permission matrix per role | admin |
| `/admin/roles/$roleId` | Role detail: document grants, capability toggles | admin |
| `/admin/status` | System status + evaluation snapshot (conditional) | admin |
| — (no route) | 403 Forbidden, 404 Not Found, global API-down banner | — |

Rules:

- **Guards** — route `beforeLoad` checks auth (401 → `/login` with return path) and role (403 → ForbiddenState). Guards are UX routing only; every gated capability is re-enforced server-side.
- **Deep links** — conversation threads and document details must be reachable from a URL (refresh-safe). Chat prefill via search param (`/chat?q=…`) for future "ask from document" entry points.
- **Shell** — auth-aware layout providing sidebar, tenant switcher, user menu; focus moves to `<main>` after route change.
- **No self-serve signup** — tenant provisioning is admin-driven (PRD non-goal); `/login` has no sign-up link.
- **SEO** — not applicable: fully authenticated internal tool; no indexable content. Route titles still use real document titles for tab/browser-title clarity.

## Chat & Search Interaction Model

The chat thread is the product's center of gravity.

- **Composer** — "Ask a question about your documents"; Enter sends, Shift+Enter newline; autofocus on thread enter; disabled while a request is in flight; Esc clears nothing destructive. Send is abortable (API non-mutating; the in-flight answer is cancelled and discarded — the user may re-ask).
- **Message flow** — user message is appended optimistically; the assistant reply is rendered from the API response only. Pending state: assistant slot with skeleton + a truthful status line ("Searching your documents…") and no answer text — an answer is *never* shown before it exists. Draft p95 target (< 10 s) informs the status line ("This can take up to ~10 seconds" only if the SLA is confirmed).
- **Answer rendering** — sanitized Markdown-lite (headings, bold, lists, inline code, links). Document-derived text inside the answer is rendered as text; no raw HTML.
- **Grounding honesty (defense-in-depth)** — if the API ever returns an answer with an empty citations array, the UI shows an explicit "No verified sources found" notice with that answer — it does not silently present ungrounded text as normal output. This is presentation-level honesty layered over the API's citation-verification control.
- **No-results** — retrieval-empty and permission-scoped-empty look identical and neutral ("No relevant documents found for this question. Try rephrasing, or ask an admin if you expected access."). The UI never reveals whether un-authorized documents exist.
- **Follow-ups** — context carries within the conversation; each assistant message carries its own citations (no re-use of a previous message's sources).
- **Conversation list** — recent conversations, rename-friendly title from the first question, active-state highlight, delete per product retention decision. History persistence scope follows the open product decision on chat history.
- **Empty conversation state** — starter prompt chips (generic formulations such as "Summarize the runbook for…"), which are guidance, not claims about corpus contents; plus a "no documents yet" card for members when their accessible corpus is empty.
- **Tenant scope** — the active tenant name sits in the shell header on every screen; switching tenants swaps the entire data context (Query cache scoped per tenant key).

## Citations & Source Preview

The citation lifecycle is the trust surface; it is strictly API-driven.

1. **Render** — the API returns the answer plus a `citations` array (chunk ids, document references, excerpt, position). The UI renders inline superscript markers `[1]` `[2]` grouped per claim, plus a collapsible source list at the message footer. The UI never invents, reorders, or reconstructs citations.
2. **Inspect** — hovering or focusing a marker opens a small popover: document title, source type, chunk position, and the excerpt.
3. **Open** — activating a marker opens the **SourcePreview** dialog: document header (title, type, modified/status), the chunk passage highlighted with the accent (the highlighter metaphor), position `chunk 3 of 42`, and prev/next navigation through the document's chunks (only chunks the API returns for that document — paging is authorized per request).
4. **Failure** — if the chunk can no longer be loaded (deleted, revoked mid-session, permission changed), the preview shows an explicit missing/forbidden card. **No cached or partial content is shown**, and the error does not hint at why beyond what the API states (no existence disclosure).
5. **Keyboard** — marker Enter/Space opens preview; dialog traps focus; Esc closes; focus returns to the marker. Screen readers: markers are buttons labelled "Source 1: <document title>"; the answer container announces arrival politely.

## Admin, Documents & Permissions Flows

### Onboarding & org setup

- First admin after tenant provisioning lands on `/admin` with an onboarding checklist (finish org settings → invite users → assign roles → upload first documents) — checklists with honest progress, not a wizard that implies tenant creation.
- Org settings: tenant name and identity. No self-serve provisioning.

### Users & roles

- **Users** — table (email, role, membership status, joined); invite-by-email flow (admin-driven provisioning per PRD); role select per user; remove/disable with confirmation dialog. Invite and membership APIs are contract points to confirm at API build.
- **Roles** — default roles (e.g., `admin`, `member`) plus custom; role detail shows a capability matrix (manage org settings, manage users, manage documents, view document corpus, chat access) and per-document grants. The matrix is a read/edit surface over server-enforced RBAC: toggling a control is a request, never a claim of effect — a failed grant update surfaces the API error inline.
- **Consistency** — permission changes apply to retrieval at query time (authz is resolved fresh per request; see [ADR-0002](docs/adr/0002-retrieval-level-authorization.md)). The UI communicates "permission changes take effect immediately for new questions", not "you were just locked out".

### Documents & ingestion

- **Upload** — Dropzone accepting `.pdf`, `.md`/`.markdown`; multi-file; client-side type check and size pre-validation; per-file queue cards with status. On upload success the file enters `pending`; from then on, status is polled.
- **Status model** — `pending` (queued/waiting), `indexing` (working — indeterminate stage line "Parsing → Embedding → Indexing" only if the API exposes stage), `indexed` (healthy), `failed` (danger + API-provided reason text + retry action). Status chips per the registry; never color-only.
- **Failure handling** — a failed document shows its reason (e.g., unparseable PDF, provider outage) with a Retry action (re-enqueue; API contract point) and a "re-upload replaces" note (ingestion is idempotent by document id).
- **Delete** — delete affordance is spec'd but **gated on the open document-deletion decision** (whether deletion removes embeddings/citations immediately). Until decided, the UI must not imply immediate purge semantics.
- **Library** — table/list with status filter, type filter, and client-side name search; document detail shows metadata, status history, and an authorized chunk list (chunk browsing is itself permission-filtered by the API).
- **Polling** — while any document is `pending`/`indexing`, refetch the list on an interval (5 s draft) with automatic backoff and pause when the tab is hidden; stop polling when no document is active (see Data Fetching).

### System status & evaluation (conditional surface)

`/admin/status` renders: provider health (chat + embedding adapters), ingestion queue depth, recent ingestion failures, and — **only if the evaluation harness ships in-repo** (open decision) — an evaluation snapshot (retrieval precision, citation verifiability, answer acceptance). Until that decision, the surface shows provider/ingestion health only. It is an honest status board: every metric has a source, a timestamp, and an "as of" label; no fabricated gauges.

## Loading, Error, Empty & Forbidden States

Every data surface implements the four-state contract. Skeletons mirror final geometry (CLS-safe); spinners alone are never the loading state.

| State | Contract | Chat specifics | Document/Admin specifics |
|---|---|---|---|
| Loading | Skeleton matching layout; stable height | Assistant slot skeleton + status line | Skeleton table rows / card grid |
| Empty | Title + one next action; permission-neutral copy | Starter prompts; "no documents yet" card | "No documents" → Upload CTA; "No users" → Invite CTA |
| Error | Envelope `{code, message, details?}` + Retry | Answer slot becomes an error card ("Answer generation is temporarily unavailable. Nothing was generated.") — never a fabricated answer | Inline error near the action + Retry; global banner for API-down |
| Forbidden | ForbiddenState screen/card; neutral copy | — | Route guard 403; row-level 403 for revoked grants |

- **Global states** — a single app-level banner for API-unreachable (affects everything); per-surface errors otherwise.
- **Error taxonomy surfaced** — 401 → session-expired notice + redirect to `/login` (return path preserved); 403 → ForbiddenState; 404 → Not Found; 429 → rate-limit message honoring `Retry-After`; 5xx/network → retry-able error card. LLM-provider failure is a chat-surface error, never a documents error.
- **No existence disclosure** — forbidden, empty, and no-results copy must be indistinguishable between "nothing exists" and "you may not see it" (subject to API error codes — if the API's 404 vs 403 distinction is meaningful, the UI follows it verbatim).

## Accessibility

Target WCAG 2.2 AA across the authenticated app.

- **Keyboard model** — full task coverage without a mouse: login → chat (composer autofocus, Enter send / Shift+Enter newline, Esc dismisses open preview) → citation navigation (Tab to markers, Enter/Space opens) → source preview (focus trap, Esc) → dialogs and menus (standard patterns) → tables (scrollable tables keyboard-reachable, row actions operable) → dropzone (Enter/Space opens picker).
- **Focus** — visible `focus-visible` ring on every interactive element (≥ 3:1 contrast, instant); focus moves to `<main>` after route change; skip-to-content link; logical DOM order.
- **Screen readers** — chat: assistant answers announced in a polite live region; message arrival and ingestion status transitions announced (not spammed — batch/polite); citations as labelled buttons; answer claims need no special verbosity mode. Forms: visible labels + `aria-describedby` errors. Tables: `<th scope>`. Status: text + icon, never color alone.
- **Contrast** — text ≥ 4.5:1, UI components ≥ 3:1 (`ink-faint` is meta-only; never body copy).
- **Motion** — `prefers-reduced-motion`: reduce to crossfade/instant; no parallax, no auto-scroll.
- **Touch** — targets ≥ 44×44pt on mobile; no gesture-only critical actions; drag-drop optional.

## Responsive Behavior

Mobile-first; the desktop app shell is the primary target, the mobile layout is the floor.

| Width | Shell | Chat | Admin/Documents |
|---|---|---|---|
| ≥ 1024px | Sidebar (260px) + header | Thread centered, ≤ 760px column | Tables, card grid |
| 768–1024px | Collapsible sidebar | Same column | Tables compress |
| < 768px | Top bar + bottom tab bar (Chat / Documents / Admin ≤ 5 items) | Composer pinned bottom (safe-area inset), conversation list as drawer | Tables → stacked cards; dropzone full-width |

- No horizontal scroll at 360px; grids `minmax(0, 1fr)`; headlines scale via `clamp()`; landscape mobile remains readable.
- Touch targets ≥ 44px; composer pinned with `env(safe-area-inset-bottom)`.

## Data Fetching & Cache (TanStack Query)

TanStack Query is the sole data layer; TanStack Router loads routes.

- **Client defaults** — `staleTime`: 30 s for stable refs (org settings, roles, system status), 0–5 s for dynamic data (documents, conversations); `refetchOnWindowFocus: true`; GET retries 1–2 with backoff, mutations retry 0; 4xx never retried; 429 honors `Retry-After`; `throwOnError: false` — components own their error states (ErrorState).
- **Key taxonomy** — `['org']`, `['users']`, `['roles', id]`, `['documents']`, `['document', id]`, `['document', id, 'chunks']`, `['conversations']`, `['conversation', id]`, `['status']`. Tenant is part of the cache scope (per-tenant isolation of client state; switching tenants swaps the context).
- **Route loading** — `ensureQueryData` in route loaders for shell-critical data (org identity, document list headers); page data stays in component queries so deep links refresh-safe.
- **Polling** — documents list: `refetchInterval` active only while any document is `pending`/`indexing` (5 s draft), pauses on hidden tab, stops when idle. No server push in the MVP.
- **Mutations** — upload (per-file `FormData`), retry/delete document, invite user, role/grant updates, org settings, chat send. Optimistic updates with rollback: role assignment (user row), user message append (replaced by confirmed message on success). Invalidation: documents mutations invalidate `['documents']`; role/grant mutations invalidate `['users']`, `['roles']`, and (importantly) nothing chat-side — chat answers are not cached across sessions and permission changes take effect on the next request by design.
- **Chat** — POST via mutation, abortable; the assistant message is *not* optimistic — it appears only from the API response (grounding honesty). Conversation history is cached per conversation for the session; answers are never persisted client-side beyond the Query cache.
- **API contract points (confirm at API build)** — assumed endpoints the UI design depends on, to be validated against the FastAPI surface: login, chat (answer + citations), conversations list/thread, documents list/detail/status, document upload, document retry (re-enqueue), document delete (gated), chunk paging for preview, users list/invite/update, roles list/update/grants, org settings, system status. Error envelope `{error: {code, message, details?}}` per ARCHITECTURE. UI behavior is designed against this envelope; deviations are implementation-time adjustments, not design changes.

## Security & Privacy UX Constraints

1. **UI hiding is never an authorization control** — every gated capability is re-enforced by the API; the UI treats 403 as a normal, designed state.
2. **Document content is untrusted at render time** — no `dangerouslySetInnerHTML` with document-derived content; Markdown rendered through a sanitizer (e.g., DOMPurify policy); filenames and chunk text rendered as text. A document containing `<script>` or Markdown links to external hosts renders inert. (Testable: see heuristics.)
3. **Citations only from the API** — the UI never assembles citation links or chunk URLs from local state; crafted/guessable chunk URLs yield 403, never content.
4. **No client-supplied tenant identity** — the tenant is resolved from the JWT server-side; the TenantSwitcher only lists memberships the API returns.
5. **No existence disclosure** — empty, no-results, and forbidden copy stays neutral (see states).
6. **Session hygiene** — no conversation content in `localStorage`; sign-out clears the Query cache; session expiry (401) redirects to login preserving the return path.
7. **Rate limits** — 429 surfaces a calm rate-limit notice with `Retry-After`, never a generic error.
8. **Privacy** — no analytics/tracking in the MVP; nothing sensitive is logged client-side; browser autofill disabled on password fields where supported (no credential exfiltration surface beyond the JWT cookie).

## Testable Acceptance Heuristics

Implementation-phase verification anchors (playwright + vitest are the planned tooling; these are the invariants tests must prove):

1. Every rendered citation marker maps 1:1 to an entry in the API response's `citations` array — no client-constructed citations.
2. Source preview shows only chunk content returned by the API for the authorized chunk; a crafted unauthorized chunk URL renders ForbiddenState, never content.
3. Document-derived text renders inert: a PDF/Markdown containing HTML/scripts shows text, never executes or styles beyond the sanitizer.
4. No horizontal scroll at 360px width; composer reachable; touch targets ≥ 44px.
5. Full journeys keyboard-only: login → send question → open citation → close preview → navigate shell.
6. Screen-reader pass: answer arrival announced; citation markers labelled with document titles; status changes announced politely; forms labelled.
7. Text contrast ≥ 4.5:1 and UI components ≥ 3:1 on all tokens used in light mode.
8. `prefers-reduced-motion` honored: no transform/opacity motion beyond crossfade.
9. API-down: global banner + chat error card; no fabricated answer text appears in any state.
10. Ingestion: unsupported file type rejected pre-upload with message; failed document shows API reason; retry re-enqueues; polling stops when idle and pauses when tab hidden.
11. Empty states present on a fresh tenant with a single clear next action; copy identical whether the corpus is empty or merely unauthorized.
12. Session expiry → login redirect with return path; sign-out clears client conversation cache.
13. 429 → rate-limit notice with `Retry-After`, no error spam.
14. Upload of a valid PDF + Markdown reaches `indexed` end-to-end via the status flow; the same file re-uploaded shows idempotent replace semantics.

## Non-Goals & Open Visual/Product Decisions

### Non-goals (UI, MVP)

- No chat streaming (SSE/WebSocket) — request/response with honest pending states; streaming is a later enhancement, not an MVP hole.
- No global/public search, no cross-tenant views, no tenant switcher beyond the API-listed memberships.
- No self-serve signup; no invite-less provisioning.
- No in-browser full-document viewer beyond authorized chunk preview; no annotations.
- No document versioning, folders, or categories UI.
- No dark-mode default (light-first; tokens proposed, validation deferred).
- No i18n, no theming/branding, no analytics, no notification center.
- No admin audit-log surface in the MVP (revisit with product need).
- No evaluation dashboard until the harness in-repo decision resolves; `/admin/status` shows provider/ingestion health regardless.

### Open decisions

| Decision | Working assumption in this contract | Owner |
|---|---|---|
| Chat streaming | Not in MVP; request/response + skeletons | Product, post-MVP |
| Chat history persistence/retention | Persist per tenant; UI supports list/delete | Product (PRD open) |
| Document deletion semantics | Delete affordance spec'd but gated on the decision; no purge promises | Product (PRD open) |
| Evaluation harness in-repo | `/admin/status` evaluation section appears only if in-repo | Product/config phase |
| Dark-mode tokens | Light-first; dark designed with warm charcoal, not inversion | Design, post-MVP |
| Icon set | Lucide recommended; confirm at implementation | Design |
| Routing style | File-based vs code-based TanStack Router; route map above is stable | Implementation |
| Fonts | IBM Plex Sans + Mono committed here; swap requires re-validation of tokens | Design |
| Exact 429/polling values | 5 s polling draft; rate limits set at config phase | Config phase |

## Do's and Don'ts

- **Do** verify claims in the UI: every answer carries citations, every citation opens a source.
- **Don't** ever render, construct, or cache document content or citations the API did not return.
- **Do** treat document text as hostile input in the renderer — text, never HTML.
- **Don't** communicate status or state by color alone — pair color with text and icon.
- **Do** design all four states (loading, empty, error, forbidden) for every surface before shipping it.
- **Don't** reveal whether un-authorized content exists — neutral copy in empty, no-results, and 403 surfaces.
- **Do** keep the chat composer as the single query surface; no parallel search boxes.
- **Don't** use motion without intent, `ease-in`, or animated dimensions; honor `prefers-reduced-motion`.
- **Do** use semantic tokens everywhere; promote new values to this document before use.
- **Don't** use emojis as functional icons, gradient text, glassmorphism decoration, or nested cards.
- **Do** keep the tenant name visible on every screen — scope confusion is a security error.
- **Don't** claim permission effects client-side; a grant toggle is a request the API answers.
