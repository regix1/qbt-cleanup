# Plan: Reusable UI folder (shared/ui)

## Goal

Extract buttons, tables, dropdowns, action menus, and other recurring UI patterns into a dedicated **ui** folder (`web/src/app/shared/ui/`) so they can be reused across the app. Use the structure and component patterns from **lancache-manager** (`h:\_git\lancache-manager\Web\src\components\ui`) as reference for API design; qbt-cleanup is Angular standalone and already has `shared/ui` with `number-input`, `password-input`, `toggle-switch`, `loading-container`.

---

## Current state

| What | Where | Notes |
|------|-------|-------|
| Buttons | Global [`styles.scss`](web/src/styles.scss) (`.btn`, `.btn-primary`, `.btn-secondary`, `.btn-danger`, `.btn-text`, `.btn-icon`, `.btn-sm`, `.count-badge`) | Used everywhere via class names |
| `.btn-ghost` | [`torrents.component.scss`](web/src/app/features/torrents/torrents.component.scss) lines 666-681 | Unlisted button variant (Clear All filters) |
| Data table | Global `styles.scss` (`.data-table`) + overrides in [`torrents.component.scss`](web/src/app/features/torrents/torrents.component.scss) | Used in torrents, blacklist, recycle-bin |
| `.table-container` | Duplicated in [`torrents.component.scss`](web/src/app/features/torrents/torrents.component.scss) lines 223-273, [`blacklist.component.scss`](web/src/app/features/blacklist/blacklist.component.scss) lines 61-66, [`recycle-bin.component.scss`](web/src/app/features/recycle-bin/recycle-bin.component.scss) lines 37-42 | All share: `overflow-x: auto; background: var(--bg-surface); border; border-radius: 12px` |
| `.name-cell` | Duplicated in torrents (line 412), blacklist (line 68), recycle-bin (line 44) | All: `overflow: hidden; text-overflow: ellipsis; white-space: nowrap` |
| `.no-data-cell` | Duplicated in torrents (line 520), blacklist (line 83) | Same: `text-align: center; padding: 40px; color: var(--text-secondary)` |
| Custom dropdown | [`torrents.component.scss`](web/src/app/features/torrents/torrents.component.scss) (`.custom-dropdown`, `.dropdown-trigger`, `.dropdown-panel`, `.dropdown-option`) | Duplicated in [`confirm-dialog.component.scss`](web/src/app/shared/components/confirm-dialog/confirm-dialog.component.scss) as `.confirm-dropdown` + same trigger/panel/option classes |
| Action menu | Torrents: CDK overlay + [`torrents.component.scss`](web/src/app/features/torrents/torrents.component.scss) (`.action-menu`, `.action-menu-item`) | Row menu + universal actions panel; global [`styles.scss`](web/src/styles.scss) has `.universal-action-menu-pane` |
| Custom checkbox | [`torrents.component.scss`](web/src/app/features/torrents/torrents.component.scss) lines 587-629 (`.custom-checkbox`, `.checked`, `.indeterminate`) | Used for table row selection + select-all header |
| Search field | [`torrents.component.scss`](web/src/app/features/torrents/torrents.component.scss) lines 24-46, nearly identical in [`blacklist.component.scss`](web/src/app/features/blacklist/blacklist.component.scss) lines 123-140 | Icon-over-input pattern |
| Pagination | [`torrents.component.scss`](web/src/app/features/torrents/torrents.component.scss) lines 526-551 (`.pagination-bar`, `.pagination-info`, `.pagination-controls`) | Only in torrents, but generic |
| Filter chips | [`torrents.component.scss`](web/src/app/features/torrents/torrents.component.scss) lines 177-221 (`.filter-chips-row`, `.filter-chip`, `.chip-dismiss`) | Active-filter pills with dismiss |
| Badges (5 variants) | `.state-badge` (torrents 419-472), `.type-badge` (torrents 482-498, recycle-bin 68-84), `.status-chip` (styles.scss 136-170), `.modified-badge` (config 111-122), `.unregistered-badge` (torrents 474-480) | All share `inline-block; padding; border-radius; font-size 11-12px; font-weight 500` — should be one component |
| Empty/error state | `.empty-state-global` (styles.scss 195-221), `.empty-state` (fileflows 124-142), `.error-card` (fileflows 31-57) | Duplicated flex-column centered pattern |
| Card header | `.card-header-content` duplicated in blacklist (9-26), dashboard (23-40), fileflows (59-84) | `display: flex; gap: 12px; padding: 16px; border-bottom` with icon + text |
| Header actions | `.header-actions` duplicated in 5 feature components with slightly different gaps (8px vs 12px) | Should be standardized in `.page-header` |
| Stat card variants | `.stat-card` (global styles.scss), `.summary-stat` (recycle-bin 1-35), `.mini-stat` (dashboard 70-103) | Same pattern at different sizes |
| Accordion | [`config.component.scss`](web/src/app/features/config/config.component.scss) lines 38-99 | Only in config, but generic collapsible panel |
| Icon color utilities | `.icon-yellow`, `.icon-gold`, etc. in dashboard (105-110) and fileflows (1-3) | Duplicated; should be global |
| Monospace utility | `font-family: 'Roboto Mono', monospace` in blacklist (76), config (165, 201), fileflows (120) | Should be a `.font-mono` utility class |
| Form group | `.form-group` in blacklist (40-53), similar in config `.field-row` | Label + input column pattern |
| Page layout | Global `styles.scss` (`.page-container`, `.page-header`, `.card-grid`) | Used by every page |
| Hash dropdown | [`blacklist.component.scss`](web/src/app/features/blacklist/blacklist.component.scss) (`.hash-dropdown`, search + list) | Searchable dropdown variant |
| Inline styles | `blacklist.component.html` (lines 20, 106), `recycle-bin.component.html` (lines 65, 70) | Should be CSS classes |

### Duplicated animation keyframes

| Keyframe | Definitions | Issue |
|----------|-------------|-------|
| `@keyframes dropdown-open` | `styles.scss` (619-628), `torrents.component.scss` (137-146), `confirm-dialog.component.scss` (216-225) | 3 slightly different versions |
| `@keyframes accordion-open` | `styles.scss` (630-638), `config.component.scss` (88-99) | Config version adds `max-height` |
| `@keyframes slide-up` | `styles.scss` line 650 AND line 747 | **Bug**: second definition silently overrides the first (loses opacity transition) |
| `@keyframes card-fade-in` | `dashboard.component.scss` (134-143) | Essentially identical to first `slide-up` with 12px instead of 16px |

### Unused global styles

`.section-card-header` in `styles.scss` lines 174-191 is never used; all templates use `.card-header-content` instead.

---

### Reference (lancache-manager)

| Component | Key patterns to adopt |
|-----------|----------------------|
| **Button** | 4 variants, 8 colors, 4 sizes, `leftSection`/`rightSection` slots, `loading` spinner, extends native attributes |
| **ActionMenu** | Portal rendering, rAF layout-shift detection (closes if trigger moves >2px), Escape to close, scroll-to-close (exempts internal scroll), `ActionMenuItem` / `ActionMenuDangerItem` / `ActionMenuDivider` sub-components |
| **EnhancedDropdown** | Typed option model (icon, description, tooltip, submenu, disabled), viewport-aware direction (opens up if no space below), post-render position clamping, custom scrollbar |
| **MultiSelectDropdown** | Checkbox options, selection count badge, min/max constraints, `pointerdown` for touch support |
| **Modal** | Global modal stack with z-index, scroll lock with scrollbar compensation, animated transitions, backdrop click close |
| **Checkbox** | `stopPropagation` on input + label (prevents row-click in tables), variant (default/rounded) |
| **Pagination** | Page numbers with ellipsis, first/prev/next/last, compact mode, page-jump dropdown, `aria-current="page"` |
| **Tooltip** | Position flipping, viewport clamping, mobile tap-to-toggle, show delay (150ms), scroll-to-dismiss |
| **Alert** | Color variants with default icons, optional close, title |
| **AccordionSection** | Keyboard handling (Enter/Space), interactive-element detection in header, max-h animation |
| **SegmentedControl** | Multi-option tab bar, responsive label hiding, tooltips per option |
| **Card** | `CardHeader` / `CardTitle` / `CardContent` sub-component composition |
| **CustomScrollbar** | Drag support, ResizeObserver, rAF throttling |
| **ManagerCard** | Exports generic `EmptyState` and `LoadingState` |

---

## Target structure

```
web/src/app/shared/ui/
├── button/              # Variants, sizes, loading, badge
├── checkbox/            # Styled checkbox with checked/indeterminate states
├── dropdown/            # Single-select filter dropdown (trigger + panel + options)
├── action-menu/         # Overlay action menu (trigger + items + divider)
├── data-table/          # Table styles (table + container + name-cell + no-data)
├── badge/               # Unified badge/chip (state, type, status, modified variants)
├── search-input/        # Icon-over-input search field
├── pagination/          # Page navigation bar
├── filter-chip/         # Removable filter tag
├── empty-state/         # Centered empty/error state with icon + text
├── card/                # Section card + card header + stat card variants
├── accordion/           # Collapsible panel with chevron
├── number-input/        # (existing)
├── password-input/      # (existing)
├── toggle-switch/       # (existing — consider adding loading + color variants)
└── loading-container/   # (existing)
```

---

## Implementation steps

### 1. Button component (`shared/ui/button/`)

- **Create** `button.component.ts` (standalone): inputs for `variant` (primary | secondary | danger | text | icon | ghost), `size` (default | sm), `loading` (shows spinner, disables), `badge` (count number). Projects content via `<ng-content>`.
- **Markup**: `<button>` with computed class list (`.btn`, `.btn-{variant}`); optional spinner icon when loading; optional `<span class="count-badge">` when badge > 0.
- **Styles**: move `.btn`, `.btn-primary`, `.btn-secondary`, `.btn-danger`, `.btn-text`, `.btn-icon`, `.btn-sm`, `.btn-ghost`, `.count-badge` from `styles.scss` + `torrents.component.scss` into `button.component.scss`. Use `ViewEncapsulation.None` so existing class-based usage keeps working during migration.
- **Migration approach**: create component, keep global class names working. Migrate templates to `<app-button>` incrementally.

### 2. Checkbox component (`shared/ui/checkbox/`)

- **Create** `checkbox.component.ts` (standalone): inputs for `checked`, `indeterminate`, `disabled`; output `checkedChange`. Calls `$event.stopPropagation()` to prevent row-click interference in tables.
- **Styles**: move `.custom-checkbox`, `.checked`, `.indeterminate` from `torrents.component.scss` lines 587-629.
- **Migrate**: torrents header select-all and row checkboxes.

### 3. Dropdown component (`shared/ui/dropdown/`)

- **Create** `dropdown.component.ts` (standalone): trigger slot (via `<ng-content select="[trigger]">`), panel with projected option list, `isOpen` / `isOpenChange`, click-outside close, Escape to close, scroll-to-close (exempting internal scroll).
- **Viewport-aware positioning**: use CDK `FlexibleConnectedPositionStrategy` to open upward when insufficient space below.
- **Styles**: consolidate `.custom-dropdown`, `.dropdown-trigger`, `.dropdown-panel`, `.dropdown-option`, `.dropdown-chevron` from torrents and confirm-dialog; reconcile minor differences (bg color, font size) via inputs or CSS custom properties.
- **Migrate**: torrents filter dropdowns (6 instances) and confirm-dialog dropdown.

### 4. Action menu component (`shared/ui/action-menu/`)

- **Create** `action-menu.component.ts` (standalone): trigger slot + CDK overlay panel. Projected content for menu items.
- **Sub-components**: `ActionMenuItemComponent` (icon + label), `ActionMenuDangerItemComponent` (danger variant), optionally a divider directive.
- **Behavior**: CDK overlay with `FlexibleConnectedPositionStrategy`; close on backdrop click, Escape, outside scroll. Emit `closed` event.
- **Styles**: move `.action-menu`, `.action-menu-item`, `.action-menu-backdrop`, `.universal-action-menu-pane`, `.universal-actions-backdrop` from torrents + global styles.
- **Migrate**: torrents row action menu and universal actions overlay.

### 5. Data table styles (`shared/ui/data-table/`)

- **Create** `_data-table.scss` partial containing `.data-table` (from global), `.table-container` (from 3 feature files), `.name-cell` (from 3 features), `.no-data-cell` (from 2 features).
- **Import** partial from `styles.scss`. No component yet (keep `<table class="data-table">`).
- **Remove** duplicated `.table-container`, `.name-cell`, `.no-data-cell` from torrents, blacklist, recycle-bin component styles.

### 6. Badge component (`shared/ui/badge/`)

- **Create** `badge.component.ts` (standalone): input `variant` (state-downloading | state-uploading | state-paused | ... | type-private | type-public | type-folder | type-file | status-success | status-error | status-warning | modified | unregistered), or simpler `color` + `label` inputs.
- **Styles**: unify base from `.state-badge`, `.type-badge`, `.status-chip`, `.modified-badge`, `.unregistered-badge`. Common base: `display: inline-block; padding: 3px 10px; border-radius: 12px; font-size: 12px; font-weight: 500; text-transform: uppercase;`. Color via variant classes.
- **Remove** per-feature badge styles from torrents, recycle-bin, config, global `styles.scss`.

### 7. Search input component (`shared/ui/search-input/`)

- **Create** `search-input.component.ts` (standalone): wraps an input with a magnifying-glass icon overlay. Inputs: `placeholder`, `value`; output: `valueChange`.
- **Styles**: consolidate from torrents `.search-field` and blacklist `.hash-dropdown-search`.
- **Migrate**: torrents search and blacklist hash search.

### 8. Pagination component (`shared/ui/pagination/`)

- **Create** `pagination.component.ts` (standalone): inputs for `currentPage`, `totalPages`, `pageSize`, `totalItems`; output `pageChange`.
- **Markup**: prev/next buttons, page info text, optional page-number buttons. Include `aria-label` and `aria-current="page"`.
- **Styles**: move `.pagination-bar`, `.pagination-info`, `.pagination-controls`, `.page-info` from torrents.
- **Migrate**: torrents pagination bar.

### 9. Filter chip component (`shared/ui/filter-chip/`)

- **Create** `filter-chip.component.ts` (standalone): inputs for `label`; output `dismissed`.
- **Styles**: move `.filter-chip`, `.chip-dismiss` from torrents. Optionally include `.filter-chips-row` as a layout wrapper.
- **Migrate**: torrents active filter chips.

### 10. Empty state component (`shared/ui/empty-state/`)

- **Create** `empty-state.component.ts` (standalone): inputs for `icon`, `title`, `message`. Projects optional action content.
- **Styles**: consolidate `.empty-state-global` (styles.scss), `.empty-state` (fileflows), `.error-card .error-content` (fileflows) into one component.
- **Migrate**: recycle-bin empty state, fileflows empty state, fileflows error card. Remove duplicates from styles.scss and fileflows.

### 11. Card / section card (`shared/ui/card/`)

- **Create** `section-card.component.ts` (standalone) with sub-components `CardHeaderComponent` (icon + title) and projected `<ng-content>` for body.
- **Consolidate**: `.section-card`, `.card-header-content` (from blacklist, dashboard, fileflows), `.card-body`. Remove unused `.section-card-header`.
- **Stat card**: Add `stat-card.component.ts` (standalone) unifying `.stat-card`, `.summary-stat`, `.mini-stat` with a `size` input (sm | md | lg).

### 12. Accordion component (`shared/ui/accordion/`)

- **Create** `accordion.component.ts` (standalone): inputs for `title`, `icon`, `expanded`; output `expandedChange`. Keyboard handling: Enter/Space to toggle.
- **Styles**: move from config lines 38-99.
- **Migrate**: config page accordion panels.

### 13. Global cleanup

- **Deduplicate `@keyframes`**: keep one canonical `dropdown-open`, `accordion-open`, `slide-up` in `styles.scss`. Remove from torrents, confirm-dialog, config.
- **Fix `@keyframes slide-up` bug**: rename the second definition (line 747, used for universal-action mobile bottom-sheet) to `@keyframes slide-up-full` or `@keyframes bottom-sheet-enter`.
- **Add icon color utilities** to `styles.scss`: `.icon-yellow`, `.icon-gold`, `.icon-teal`, `.icon-amber`, `.icon-red`, `.icon-copper`, `.icon-active`, `.icon-inactive`. Remove from dashboard and fileflows.
- **Add `.font-mono`** utility to `styles.scss`. Replace 4 inline `font-family: 'Roboto Mono'` usages.
- **Add `.form-group`** to `styles.scss` (or `shared/ui/`). Standardize label + input column pattern from blacklist + config.
- **Standardize `.header-actions`** gap in `.page-header` rules. Remove per-feature overrides.
- **Replace inline styles** in blacklist.component.html and recycle-bin.component.html with CSS classes.

### 14. Shared UI barrel export

- **Add** `shared/ui/index.ts` exporting all components for easy imports.

---

## Cross-cutting patterns to adopt (from lancache-manager)

These should be applied consistently across all new shared UI components:

| Pattern | How to implement in Angular |
|---------|----------------------------|
| **Keyboard dismissal** (Escape) | `@HostListener('document:keydown.escape')` on overlay components |
| **Scroll-to-close** with internal scroll exemption | Listen on `window:scroll` (capture), check if event target is inside the overlay before closing |
| **Viewport-aware positioning** | CDK `FlexibleConnectedPositionStrategy` with preferred + fallback positions |
| **Click-outside with trigger exemption** | CDK backdrop or manual `document:click` handler that checks `.closest()` |
| **Accessibility** | `aria-label` on interactive elements, `aria-current="page"` on pagination, `role="button"` + `tabIndex` + Enter/Space on non-button interactive elements |
| **Loading state on buttons** | `loading` input that shows spinner + disables button |
| **Sub-component composition** | Export related standalone components from the same folder (e.g. `ActionMenuComponent` + `ActionMenuItemComponent` + `ActionMenuDividerDirective`) |
| **Animations** | Canonical keyframes in one place; CSS transitions for enter/exit on overlays |

---

## File checklist

| Action | File(s) |
|--------|---------|
| Create | `shared/ui/button/button.component.{ts,html,scss}` |
| Create | `shared/ui/checkbox/checkbox.component.{ts,scss}` |
| Create | `shared/ui/dropdown/dropdown.component.{ts,html,scss}` |
| Create | `shared/ui/action-menu/action-menu.component.{ts,html,scss}`, `action-menu-item.component.ts` |
| Create | `shared/ui/data-table/_data-table.scss` |
| Create | `shared/ui/badge/badge.component.{ts,scss}` |
| Create | `shared/ui/search-input/search-input.component.{ts,html,scss}` |
| Create | `shared/ui/pagination/pagination.component.{ts,html,scss}` |
| Create | `shared/ui/filter-chip/filter-chip.component.{ts,scss}` |
| Create | `shared/ui/empty-state/empty-state.component.{ts,html,scss}` |
| Create | `shared/ui/card/section-card.component.{ts,html,scss}`, `stat-card.component.{ts,html,scss}` |
| Create | `shared/ui/accordion/accordion.component.{ts,html,scss}` |
| Create | `shared/ui/index.ts` |
| Move | Button styles from `styles.scss` + `.btn-ghost` from torrents -> `button/` |
| Move | Checkbox styles from torrents -> `checkbox/` |
| Move | Dropdown styles from torrents + confirm-dialog -> `dropdown/` |
| Move | Action menu styles from torrents + global overlay -> `action-menu/` |
| Move | `.data-table`, `.table-container`, `.name-cell`, `.no-data-cell` -> `data-table/` |
| Move | `.state-badge`, `.type-badge`, `.status-chip`, `.modified-badge`, `.unregistered-badge` -> `badge/` |
| Move | `.search-field` from torrents + `.hash-dropdown-search` from blacklist -> `search-input/` |
| Move | `.pagination-bar` etc. from torrents -> `pagination/` |
| Move | `.filter-chip` etc. from torrents -> `filter-chip/` |
| Move | `.empty-state-global`, `.empty-state`, `.error-card` -> `empty-state/` |
| Move | `.section-card`, `.card-header-content`, `.stat-card` etc. -> `card/` |
| Move | Accordion styles from config -> `accordion/` |
| Fix | Rename duplicate `@keyframes slide-up` (line 747 in styles.scss) |
| Fix | Deduplicate `@keyframes dropdown-open` (3 definitions) |
| Fix | Deduplicate `@keyframes accordion-open` (2 definitions) |
| Add | `.icon-yellow`, `.icon-gold`, etc. utilities to `styles.scss`; remove from dashboard + fileflows |
| Add | `.font-mono` utility to `styles.scss`; replace 4 inline font-family usages |
| Add | `.form-group` to `styles.scss`; standardize from blacklist + config |
| Fix | Standardize `.header-actions` gap in `.page-header`; remove per-feature overrides |
| Fix | Replace inline `style=""` in blacklist + recycle-bin templates with CSS classes |
| Remove | Unused `.section-card-header` from `styles.scss` |
| Update | `styles.scss` to import new partials / remove moved sections |
| Migrate | Feature templates to use new shared UI components |

---

## Priority order

1. **Button** + **Checkbox** -- foundational; used everywhere
2. **Dropdown** + **Action menu** -- eliminate the largest style duplication
3. **Data table** styles + **Badge** -- consolidate 5 badge variants + 3 table duplications
4. **Search input** + **Pagination** + **Filter chip** -- extract from torrents
5. **Empty state** + **Card** + **Accordion** -- consolidate remaining patterns
6. **Global cleanup** -- keyframes, utilities, inline styles, unused rules

---

## Verification

- All existing pages (dashboard, torrents, blacklist, recycle-bin, config, fileflows) look and behave identically.
- No duplicate styles between feature components and shared UI.
- Keyboard navigation works: Escape closes overlays, Enter/Space toggles accordion.
- Viewport-aware dropdown positioning works (opens upward near bottom of screen).
- `@keyframes slide-up` bug is fixed (two definitions no longer collide).
- New features can import and reuse all shared UI components from `shared/ui/`.
