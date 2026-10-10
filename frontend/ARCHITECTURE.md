# Frontend architecture

Frontend changes should follow a small set of layers. Keep components in their own files and import each module directly; do not add barrel files.

UI rules, numeric precision, component states, and the visual checklist are in [DESIGN.md](DESIGN.md). The local interactive catalogue is `/design-system.html` under the Vite development server; it is deliberately excluded from the production entrypoint.

```text
src/
  app/                  application composition and shell
    components/         app-only shell components
    navigation.mjs      route/navigation metadata
  features/             domain workflows composed from shared UI
    analysis-context/    date selection and measurement context
    auth/                authentication flow
    losses/              loss structure and explanations
    metrics/             efficiency and URE presentations
    overview/            overview dashboard sections
    scheme/              equipment scheme and topology helpers
  pages/                 route-level pages and their private helpers
  shared/
    api.ts                API transport and resource hooks
    types.ts              API/domain contracts
    metrics/              domain-neutral metric assessment helpers
    styles/              design tokens and global style foundations
    ui/                  reusable, domain-neutral controls and display components
  charts/                chart renderers, chart models, and chart-specific styles
  main.tsx               React bootstrap only
```

## Dependency direction

- `app` composes `pages`, `features`, and `shared`; it owns navigation and application state.
- `pages` and `features` may use `shared/ui`, `charts`, `api`, and domain types.
- `shared/ui` must not import from `app`, `pages`, or `features`.
- `charts` owns rendering and chart presentation; pages/features pass typed chart models or data into it.
- Keep API transport in `shared/api.ts`; keep response contracts in `shared/types.ts`.

## Design system

- Use semantic CSS variables from `shared/styles/tokens.css` for surfaces, text, borders, status, spacing, shape, shadows, and motion. Add a token when a repeated UI role needs one; avoid one-off hex colors in component styles.
- Reusable controls and presentation patterns live under `shared/ui`, one component per file. Keep feature-specific compositions under that feature.
- Component styles should live beside the component or in the stylesheet for their layer. `style.css` is for global shell/layout rules; shared page styles live in `shared/styles/pages.css` and feature styles live beside their feature.
- Import concrete modules directly. This keeps module dependencies visible and avoids pulling unrelated UI into a page bundle.

## Verification

- Run `npm run build` after frontend changes; it includes TypeScript checking and the production bundle.
- Add or update a focused test for user-visible behavior changes. Browser layout behavior belongs in `e2e/`; pure data/formatting behavior belongs in colocated `*.test.mjs` files.
