import { ChangeDetectionStrategy, Component, computed, DestroyRef, HostListener, inject, signal, OnInit } from '@angular/core';
import { DecimalPipe, NgClass } from '@angular/common';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { forkJoin, interval, map, switchMap } from 'rxjs';
import { CdkDragDrop, CdkDrag, CdkDropList, CdkDragHandle, CdkDragPreview } from '@angular/cdk/drag-drop';
import { OverlayModule, type ConnectedPosition } from '@angular/cdk/overlay';
import { ApiService } from '../../core/services/api.service';
import { NotificationService } from '../../core/services/notification.service';
import { ConfirmService } from '../../core/services/confirm.service';
import { ActionResponse, CategoriesResponse, Torrent } from '../../shared/models';
import { SelectOption } from '../../core/services/confirm.service';
import { LoadingContainerComponent } from '../../shared/ui/loading-container/loading-container.component';

interface ActiveFilter {
  type: 'state' | 'category' | 'type' | 'blacklist' | 'tracker' | 'unregistered';
  value: string;
  label: string;
}

export interface ColumnDef {
  id: string;
  label: string;
  sortField?: keyof Torrent;
  cssClass: string;
  defaultWidth: number;   // percentage (e.g., 22 = 22%)
  minWidthPct: number;    // minimum percentage (e.g., 8 = 8%)
}

const COLUMN_ORDER_KEY = 'qbt-torrents-column-order';
const COLUMN_WIDTHS_KEY = 'qbt-torrents-column-widths';
const COLUMN_WIDTHS_VERSION_KEY = 'qbt-torrents-column-widths-v';
const COLUMN_WIDTHS_VERSION = 2;

const DEFAULT_COLUMNS: ColumnDef[] = [
  { id: 'select', label: '', cssClass: 'col-select', defaultWidth: 3, minWidthPct: 2 },
  { id: 'name', label: 'Name', sortField: 'name', cssClass: 'col-name', defaultWidth: 27, minWidthPct: 10 },
  { id: 'state', label: 'State', sortField: 'state', cssClass: 'col-state', defaultWidth: 10, minWidthPct: 6 },
  { id: 'ratio', label: 'Ratio', sortField: 'ratio', cssClass: 'col-ratio', defaultWidth: 7, minWidthPct: 4 },
  { id: 'seedTime', label: 'Seeding Time', sortField: 'seeding_time', cssClass: 'col-seed-time', defaultWidth: 9, minWidthPct: 5 },
  { id: 'type', label: 'Type', sortField: 'is_private', cssClass: 'col-type', defaultWidth: 7, minWidthPct: 4 },
  { id: 'size', label: 'Size', sortField: 'size', cssClass: 'col-size', defaultWidth: 7, minWidthPct: 4 },
  { id: 'progress', label: 'Progress', sortField: 'progress', cssClass: 'col-progress', defaultWidth: 8, minWidthPct: 5 },
  { id: 'location', label: 'Location', sortField: 'save_path', cssClass: 'col-location', defaultWidth: 10, minWidthPct: 5 },
  { id: 'blacklist', label: 'Blacklisted', sortField: 'is_blacklisted', cssClass: 'col-blacklist', defaultWidth: 8, minWidthPct: 4 },
  { id: 'actions', label: 'Actions', cssClass: 'col-actions', defaultWidth: 6, minWidthPct: 3 },
];

/** CDK overlay positions for universal actions menu: below-start, below-end, above-start, above-end. */
const UNIVERSAL_ACTIONS_POSITIONS: ConnectedPosition[] = [
  { originX: 'start', originY: 'bottom', overlayX: 'start', overlayY: 'top', offsetY: 4 },
  { originX: 'end', originY: 'bottom', overlayX: 'end', overlayY: 'top', offsetY: 4 },
  { originX: 'start', originY: 'top', overlayX: 'start', overlayY: 'bottom', offsetY: -4 },
  { originX: 'end', originY: 'top', overlayX: 'end', overlayY: 'bottom', offsetY: -4 },
];

@Component({
  selector: 'app-torrents',
  standalone: true,
  imports: [
    DecimalPipe,
    NgClass,
    LoadingContainerComponent,
    CdkDropList,
    CdkDrag,
    CdkDragHandle,
    CdkDragPreview,
    OverlayModule,
  ],
  templateUrl: './torrents.component.html',
  styleUrl: './torrents.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class TorrentsComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly notifications = inject(NotificationService);
  private readonly confirmService = inject(ConfirmService);
  private readonly destroyRef = inject(DestroyRef);

  readonly universalActionsOverlayPositions = UNIVERSAL_ACTIONS_POSITIONS;

  readonly torrents = signal<Torrent[]>([]);
  readonly loading = signal<boolean>(true);

  // Column ordering & sizing
  readonly columnOrder = signal<ColumnDef[]>(this.loadColumnOrder());
  readonly columnWidths = signal<Record<string, number>>(this.loadColumnWidths());
  readonly isResizing = signal<boolean>(false);

  readonly isColumnsCustomized = computed<boolean>(() => {
    const currentOrder = this.columnOrder();
    const orderChanged = currentOrder.length !== DEFAULT_COLUMNS.length
      || currentOrder.some((col: ColumnDef, index: number) => col.id !== DEFAULT_COLUMNS[index].id);
    const widthsChanged = Object.keys(this.columnWidths()).length > 0;
    return orderChanged || widthsChanged;
  });

  readonly effectiveWidths = computed<Record<string, number>>(() => {
    const stored = this.columnWidths();
    const columns = this.columnOrder();
    const result: Record<string, number> = {};
    let total = 0;
    for (const col of columns) {
      const width = stored[col.id] ?? col.defaultWidth;
      result[col.id] = width;
      total += width;
    }
    // Normalize to exactly 100% if drift occurred
    if (Math.abs(total - 100) > 0.01) {
      const scale = 100 / total;
      for (const col of columns) {
        result[col.id] = result[col.id] * scale;
      }
    }
    return result;
  });

  // Resize tracking (neighbor-steal model)
  private resizeColumnId = '';
  private resizeRightColumnId = '';
  private resizeStartX = 0;
  private resizeStartLeftPct = 0;
  private resizeStartRightPct = 0;
  private resizeContainerWidth = 0;

  // Filter signals
  readonly searchText = signal<string>('');
  readonly stateFilter = signal<string>('');
  readonly categoryFilter = signal<string>('');
  readonly typeFilter = signal<'all' | 'private' | 'public'>('all');
  readonly blacklistFilter = signal<'all' | 'yes' | 'no'>('all');
  readonly unregisteredFilter = signal<'all' | 'yes' | 'no'>('all');
  readonly trackerFilter = signal<string>('');

  // Layout
  readonly compactMode = signal<boolean>(false);

  // Row selection (for universal actions)
  readonly selectedHashes = signal<Set<string>>(new Set());
  readonly universalActionsOpen = signal<boolean>(false);

  // Dropdown state
  readonly openDropdown = signal<string>('');
  readonly actionMenuHash = signal<string>('');
  readonly actionMenuPos = signal<{ top: number; left: number }>({ top: 0, left: 0 });
  readonly recyclingHash = signal<string>('');
  readonly movingHash = signal<string>('');

  // Sorting & pagination
  readonly sortField = signal<keyof Torrent>('name');
  readonly sortDirection = signal<'asc' | 'desc'>('asc');
  readonly currentPage = signal<number>(0);
  readonly pageSize = signal<number>(25);

  readonly availableStates = computed<string[]>(() => {
    const states = new Set(this.torrents().map((t: Torrent) => t.state));
    return Array.from(states).sort();
  });

  readonly availableCategories = computed<string[]>(() => {
    const categories = new Set(
      this.torrents()
        .map((t: Torrent) => t.category)
        .filter((c: string) => c.length > 0),
    );
    return Array.from(categories).sort();
  });

  readonly availableTrackers = computed<string[]>(() => {
    const trackers = new Set<string>();
    for (const t of this.torrents()) {
      if (t.tracker) {
        try {
          trackers.add(new URL(t.tracker).hostname);
        } catch {
          trackers.add(t.tracker);
        }
      }
    }
    return Array.from(trackers).sort();
  });

  readonly activeFilters = computed<ActiveFilter[]>(() => {
    const filters: ActiveFilter[] = [];
    const state = this.stateFilter();
    if (state) {
      filters.push({ type: 'state', value: state, label: `State: ${this.getStateLabel(state)}` });
    }
    const category = this.categoryFilter();
    if (category) {
      filters.push({ type: 'category', value: category, label: `Category: ${category}` });
    }
    const type = this.typeFilter();
    if (type !== 'all') {
      filters.push({ type: 'type', value: type, label: `Type: ${type === 'private' ? 'Private' : 'Public'}` });
    }
    const blacklist = this.blacklistFilter();
    if (blacklist !== 'all') {
      filters.push({ type: 'blacklist', value: blacklist, label: `Blacklisted: ${blacklist === 'yes' ? 'Yes' : 'No'}` });
    }
    const unreg = this.unregisteredFilter();
    if (unreg !== 'all') {
      filters.push({ type: 'unregistered', value: unreg, label: `Unregistered: ${unreg === 'yes' ? 'Yes' : 'No'}` });
    }
    const tracker = this.trackerFilter();
    if (tracker) {
      filters.push({ type: 'tracker', value: tracker, label: `Tracker: ${tracker}` });
    }
    return filters;
  });

  readonly hasActiveFilters = computed<boolean>(() => this.activeFilters().length > 0);

  // Dropdown display labels
  readonly stateFilterLabel = computed<string>(() =>
    this.stateFilter() ? this.getStateLabel(this.stateFilter()) + ' (' + this.stateFilter() + ')' : 'All States',
  );

  readonly categoryFilterLabel = computed<string>(() =>
    this.categoryFilter() || 'All Categories',
  );

  readonly typeFilterLabel = computed<string>(() => {
    const v = this.typeFilter();
    return v === 'all' ? 'All Types' : v === 'private' ? 'Private' : 'Public';
  });

  readonly blacklistFilterLabel = computed<string>(() => {
    const v = this.blacklistFilter();
    return v === 'all' ? 'All Blacklist' : v === 'yes' ? 'Blacklisted' : 'Not Blacklisted';
  });

  readonly unregisteredFilterLabel = computed<string>(() => {
    const v = this.unregisteredFilter();
    return v === 'all' ? 'Tracker Status' : v === 'yes' ? 'Unregistered' : 'Registered';
  });

  readonly trackerFilterLabel = computed<string>(() =>
    this.trackerFilter() || 'All Trackers',
  );

  readonly filteredTorrents = computed<Torrent[]>(() => {
    let result = this.torrents();

    const search = this.searchText().toLowerCase().trim();
    if (search) {
      result = result.filter((t: Torrent) => t.name.toLowerCase().includes(search));
    }

    const state = this.stateFilter();
    if (state) {
      result = result.filter((t: Torrent) => t.state === state);
    }

    const category = this.categoryFilter();
    if (category) {
      result = result.filter((t: Torrent) => t.category === category);
    }

    const type = this.typeFilter();
    if (type === 'private') {
      result = result.filter((t: Torrent) => t.is_private);
    } else if (type === 'public') {
      result = result.filter((t: Torrent) => !t.is_private);
    }

    const blacklist = this.blacklistFilter();
    if (blacklist === 'yes') {
      result = result.filter((t: Torrent) => t.is_blacklisted);
    } else if (blacklist === 'no') {
      result = result.filter((t: Torrent) => !t.is_blacklisted);
    }

    const unreg = this.unregisteredFilter();
    if (unreg === 'yes') {
      result = result.filter((t: Torrent) => t.is_unregistered);
    } else if (unreg === 'no') {
      result = result.filter((t: Torrent) => !t.is_unregistered);
    }

    const tracker = this.trackerFilter();
    if (tracker) {
      result = result.filter((t: Torrent) => {
        if (!t.tracker) return false;
        try {
          return new URL(t.tracker).hostname === tracker;
        } catch {
          return t.tracker === tracker;
        }
      });
    }

    return result;
  });

  readonly sortedTorrents = computed<Torrent[]>(() => {
    const items = [...this.filteredTorrents()];
    const field = this.sortField();
    const direction = this.sortDirection();

    items.sort((a: Torrent, b: Torrent) => {
      const aValue = a[field];
      const bValue = b[field];

      let comparison = 0;
      if (typeof aValue === 'string' && typeof bValue === 'string') {
        comparison = aValue.localeCompare(bValue);
      } else if (typeof aValue === 'number' && typeof bValue === 'number') {
        comparison = aValue - bValue;
      } else if (typeof aValue === 'boolean' && typeof bValue === 'boolean') {
        comparison = (aValue === bValue) ? 0 : aValue ? 1 : -1;
      }

      return direction === 'asc' ? comparison : -comparison;
    });

    return items;
  });

  readonly totalPages = computed<number>(() => {
    const total = this.sortedTorrents().length;
    const size = this.pageSize();
    return Math.max(1, Math.ceil(total / size));
  });

  readonly paginatedTorrents = computed<Torrent[]>(() => {
    const start = this.currentPage() * this.pageSize();
    return this.sortedTorrents().slice(start, start + this.pageSize());
  });

  readonly paginationInfo = computed<string>(() => {
    const total = this.sortedTorrents().length;
    if (total === 0) return 'No torrents';
    const start = this.currentPage() * this.pageSize() + 1;
    const end = Math.min(start + this.pageSize() - 1, total);
    return `Showing ${start}-${end} of ${total} torrents`;
  });

  readonly selectedCount = computed<number>(() => this.selectedHashes().size);
  readonly selectedTorrents = computed<Torrent[]>(() => {
    const hashes = this.selectedHashes();
    if (hashes.size === 0) return [];
    const list = this.torrents();
    return list.filter((t: Torrent) => hashes.has(t.hash));
  });
  readonly isAllOnPageSelected = computed<boolean>(() => {
    const page = this.paginatedTorrents();
    if (page.length === 0) return false;
    const set = this.selectedHashes();
    return page.every((t: Torrent) => set.has(t.hash));
  });
  readonly isSomeOnPageSelected = computed<boolean>(() => {
    const page = this.paginatedTorrents();
    const set = this.selectedHashes();
    return page.some((t: Torrent) => set.has(t.hash));
  });
  readonly selectedAllPaused = computed<boolean>(() => {
    const list = this.selectedTorrents();
    return list.length > 0 && list.every((t: Torrent) => t.is_paused);
  });
  readonly selectedAllBlacklisted = computed<boolean>(() => {
    const list = this.selectedTorrents();
    return list.length > 0 && list.every((t: Torrent) => t.is_blacklisted);
  });

  private readonly stateColors: Record<string, string> = {
    downloading: 'state-downloading',
    uploading: 'state-seeding',
    seeding: 'state-seeding',
    pausedUP: 'state-paused',
    pausedDL: 'state-paused',
    stoppedUP: 'state-paused',
    stoppedDL: 'state-paused',
    stalledUP: 'state-seeding',
    stalledDL: 'state-stalled',
    error: 'state-error',
    queuedUP: 'state-queued',
    queuedDL: 'state-queued',
    checkingUP: 'state-checking',
    checkingDL: 'state-checking',
    forcedUP: 'state-seeding',
    forcedDL: 'state-downloading',
    forcedMetaDL: 'state-downloading',
    missingFiles: 'state-error',
    moving: 'state-checking',
    allocating: 'state-checking',
    metaDL: 'state-downloading',
    checkingResumeData: 'state-checking',
    unknown: 'state-default',
  };

  private readonly stateLabels: Record<string, string> = {
    downloading: 'Downloading',
    uploading: 'Seeding',
    seeding: 'Seeding',
    pausedUP: 'Paused (S)',
    pausedDL: 'Paused (D)',
    stoppedUP: 'Completed',
    stoppedDL: 'Stopped',
    stalledUP: 'Seeding',
    stalledDL: 'Stalled',
    error: 'Error',
    queuedUP: 'Queued (S)',
    queuedDL: 'Queued (D)',
    checkingUP: 'Checking',
    checkingDL: 'Checking',
    forcedUP: 'Forced Seed',
    forcedDL: 'Forced DL',
    forcedMetaDL: 'Fetching Metadata',
    metaDL: 'Fetching Metadata',
    missingFiles: 'Missing Files',
    moving: 'Moving',
    allocating: 'Allocating',
    checkingResumeData: 'Checking',
    unknown: 'Unknown',
  };

  constructor() {
    this.destroyRef.onDestroy(() => {
      document.removeEventListener('mousemove', this.onResizeMove);
      document.removeEventListener('mouseup', this.onResizeEnd);
    });
  }

  @HostListener('document:click', ['$event'])
  onDocumentClick(event: Event): void {
    const target = event.target as HTMLElement;
    if (!target.closest('.custom-dropdown')) {
      this.closeDropdowns();
    }
    // Overlay is portaled to body so also allow clicks inside the overlay pane
    if (!target.closest('.universal-actions-wrap') && !target.closest('.universal-action-menu-pane')) {
      this.closeUniversalActions();
    }
  }

  ngOnInit(): void {
    this.loadTorrents();
    this.startAutoRefresh();
  }

  loadTorrents(): void {
    this.loading.set(true);
    this.api.getTorrents()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (torrents: Torrent[]) => {
          this.torrents.set(torrents);
          this.loading.set(false);
        },
        error: () => {
          this.loading.set(false);
          this.notifications.error('Failed to load torrents');
        },
      });
  }

  private startAutoRefresh(): void {
    interval(10_000).pipe(
      switchMap(() => this.api.getTorrents()),
      takeUntilDestroyed(this.destroyRef),
    ).subscribe((torrents: Torrent[]) => this.torrents.set(torrents));
  }

  // Column ordering: swap semantics — dropped column lands where you put it.
  // CDK reports previousIndex/currentIndex in FULL list space (disabled items included).
  onColumnDrop(event: CdkDragDrop<ColumnDef[]>): void {
    const draggedCol = event.item?.data as ColumnDef | undefined;
    if (!draggedCol || draggedCol.id === 'select') return;

    const from = event.previousIndex;
    const to = event.currentIndex;
    if (from === to) return;

    const columns = [...this.columnOrder()];
    if (to < 0 || to >= columns.length) return;
    if (columns[to]?.id === 'select') return;

    [columns[from], columns[to]] = [columns[to], columns[from]];

    this.columnOrder.set(columns);
    this.saveColumnOrder();
    this.saveColumnWidths();
  }

  resetColumns(): void {
    this.columnOrder.set([...DEFAULT_COLUMNS]);
    this.columnWidths.set({});
    localStorage.removeItem(COLUMN_ORDER_KEY);
    localStorage.removeItem(COLUMN_WIDTHS_KEY);
    localStorage.removeItem(COLUMN_WIDTHS_VERSION_KEY);
  }

  onHeaderClick(col: ColumnDef): void {
    if (col.sortField) {
      this.sort(col.sortField);
    }
  }

  // Column resizing (percentage-based, neighbor-steal model)
  getColumnWidthPct(col: ColumnDef): number {
    return this.effectiveWidths()[col.id];
  }

  onResizeStart(event: MouseEvent, col: ColumnDef): void {
    event.preventDefault();
    event.stopPropagation();

    const columns = this.columnOrder();
    const colIndex = columns.findIndex((c: ColumnDef) => c.id === col.id);

    // Rightmost column has no right neighbor - cannot resize
    if (colIndex >= columns.length - 1) return;

    const rightCol = columns[colIndex + 1];
    const widths = this.effectiveWidths();

    this.resizeColumnId = col.id;
    this.resizeRightColumnId = rightCol.id;
    this.resizeStartX = event.clientX;
    this.resizeStartLeftPct = widths[col.id];
    this.resizeStartRightPct = widths[rightCol.id];
    this.isResizing.set(true);

    // Capture container width for px-to-% conversion
    const container = (event.target as HTMLElement).closest('.table-container');
    this.resizeContainerWidth = container ? container.clientWidth : 0;

    document.addEventListener('mousemove', this.onResizeMove);
    document.addEventListener('mouseup', this.onResizeEnd);
  }

  private readonly onResizeMove = (event: MouseEvent): void => {
    if (!this.resizeContainerWidth) return;

    const pxDelta = event.clientX - this.resizeStartX;
    const pctDelta = (pxDelta / this.resizeContainerWidth) * 100;

    const columns = this.columnOrder();
    const leftCol = columns.find((c: ColumnDef) => c.id === this.resizeColumnId);
    const rightCol = columns.find((c: ColumnDef) => c.id === this.resizeRightColumnId);
    if (!leftCol || !rightCol) return;

    let newLeftPct = this.resizeStartLeftPct + pctDelta;
    let newRightPct = this.resizeStartRightPct - pctDelta;

    // Enforce minimum widths
    if (newLeftPct < leftCol.minWidthPct) {
      newLeftPct = leftCol.minWidthPct;
      newRightPct = this.resizeStartLeftPct + this.resizeStartRightPct - newLeftPct;
    }
    if (newRightPct < rightCol.minWidthPct) {
      newRightPct = rightCol.minWidthPct;
      newLeftPct = this.resizeStartLeftPct + this.resizeStartRightPct - newRightPct;
    }

    this.columnWidths.update((widths: Record<string, number>) => ({
      ...widths,
      [this.resizeColumnId]: newLeftPct,
      [this.resizeRightColumnId]: newRightPct,
    }));
  };

  private readonly onResizeEnd = (): void => {
    document.removeEventListener('mousemove', this.onResizeMove);
    document.removeEventListener('mouseup', this.onResizeEnd);
    this.isResizing.set(false);
    this.resizeColumnId = '';
    this.resizeRightColumnId = '';
    this.saveColumnWidths();
  };

  toggleDropdown(name: string): void {
    if (this.openDropdown() === name) {
      this.openDropdown.set('');
    } else {
      this.openDropdown.set(name);
    }
  }

  closeDropdowns(): void {
    this.openDropdown.set('');
  }

  sort(field: keyof Torrent): void {
    if (this.sortField() === field) {
      this.sortDirection.set(this.sortDirection() === 'asc' ? 'desc' : 'asc');
    } else {
      this.sortField.set(field);
      this.sortDirection.set('asc');
    }
    this.currentPage.set(0);
  }

  onSearchChange(event: Event): void {
    const value = (event.target as HTMLInputElement).value;
    this.searchText.set(value);
    this.currentPage.set(0);
  }

  onStateFilterChange(value: string): void {
    this.stateFilter.set(value);
    this.currentPage.set(0);
    this.closeDropdowns();
  }

  onCategoryFilterChange(value: string): void {
    this.categoryFilter.set(value);
    this.currentPage.set(0);
    this.closeDropdowns();
  }

  onTypeFilterChange(value: 'all' | 'private' | 'public'): void {
    this.typeFilter.set(value);
    this.currentPage.set(0);
    this.closeDropdowns();
  }

  onBlacklistFilterChange(value: 'all' | 'yes' | 'no'): void {
    this.blacklistFilter.set(value);
    this.currentPage.set(0);
    this.closeDropdowns();
  }

  onUnregisteredFilterChange(value: 'all' | 'yes' | 'no'): void {
    this.unregisteredFilter.set(value);
    this.currentPage.set(0);
    this.closeDropdowns();
  }

  onTrackerFilterChange(value: string): void {
    this.trackerFilter.set(value);
    this.currentPage.set(0);
    this.closeDropdowns();
  }

  removeFilter(filter: ActiveFilter): void {
    switch (filter.type) {
      case 'state':
        this.stateFilter.set('');
        break;
      case 'category':
        this.categoryFilter.set('');
        break;
      case 'type':
        this.typeFilter.set('all');
        break;
      case 'blacklist':
        this.blacklistFilter.set('all');
        break;
      case 'unregistered':
        this.unregisteredFilter.set('all');
        break;
      case 'tracker':
        this.trackerFilter.set('');
        break;
    }
    this.currentPage.set(0);
  }

  clearAllFilters(): void {
    this.searchText.set('');
    this.stateFilter.set('');
    this.categoryFilter.set('');
    this.typeFilter.set('all');
    this.blacklistFilter.set('all');
    this.unregisteredFilter.set('all');
    this.trackerFilter.set('');
    this.currentPage.set(0);
  }

  isSelected(hash: string): boolean {
    return this.selectedHashes().has(hash);
  }

  toggleSelect(hash: string, event?: Event): void {
    if (event) {
      (event as MouseEvent).stopPropagation();
    }
    this.selectedHashes.update((set) => {
      const next = new Set(set);
      if (next.has(hash)) {
        next.delete(hash);
      } else {
        next.add(hash);
      }
      return next;
    });
  }

  toggleSelectAllOnPage(event?: Event): void {
    if (event) {
      (event as MouseEvent).stopPropagation();
    }
    const page = this.paginatedTorrents();
    const set = this.selectedHashes();
    const allSelected = page.every((t: Torrent) => set.has(t.hash));
    this.selectedHashes.update((prev) => {
      const next = new Set(prev);
      for (const t of page) {
        if (allSelected) {
          next.delete(t.hash);
        } else {
          next.add(t.hash);
        }
      }
      return next;
    });
  }

  clearSelection(): void {
    this.selectedHashes.set(new Set());
  }

  toggleUniversalActions(event?: MouseEvent): void {
    if (event) {
      event.stopPropagation();
    }
    if (this.selectedCount() === 0) return;
    this.universalActionsOpen.update((v) => !v);
  }

  /** Position dropdown so it stays inside viewport and doesn't cause overflow/scroll. */
  private constrainMenuToViewport(triggerRect: DOMRect): { top: number; left: number } {
    const MENU_WIDTH = 220;
    const MENU_HEIGHT = 240;
    const GAP = 4;
    const PADDING = 12;
    // clientWidth excludes scrollbar — safer than window.innerWidth on Windows
    const w = document.documentElement.clientWidth;
    const h = document.documentElement.clientHeight;

    // Always right-align menu to the trigger button so it doesn't overflow right
    let left = triggerRect.right - MENU_WIDTH;
    if (left + MENU_WIDTH > w - PADDING) {
      left = w - MENU_WIDTH - PADDING;
    }
    if (left < PADDING) {
      left = PADDING;
    }

    let top = triggerRect.bottom + GAP;
    if (top + MENU_HEIGHT > h - PADDING) {
      top = triggerRect.top - MENU_HEIGHT - GAP;
    }
    if (top < PADDING) {
      top = PADDING;
    }

    return { top, left };
  }

  closeUniversalActions(): void {
    this.universalActionsOpen.set(false);
  }

  toggleCompactMode(): void {
    this.compactMode.update((v: boolean) => !v);
  }

  goToPage(page: number): void {
    if (page >= 0 && page < this.totalPages()) {
      this.currentPage.set(page);
    }
  }

  nextPage(): void {
    this.goToPage(this.currentPage() + 1);
  }

  prevPage(): void {
    this.goToPage(this.currentPage() - 1);
  }

  formatSeedingTime(seconds: number): string {
    if (!seconds || seconds <= 0) return '--';
    const days = Math.floor(seconds / 86400);
    const hours = Math.floor((seconds % 86400) / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);

    if (days > 0) return `${days}d ${hours}h`;
    if (hours > 0) return `${hours}h ${minutes}m`;
    return `${minutes}m`;
  }

  formatSize(bytes: number): string {
    if (!bytes || bytes <= 0) return '--';
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    let unitIndex = 0;
    let size = bytes;
    while (size >= 1024 && unitIndex < units.length - 1) {
      size /= 1024;
      unitIndex++;
    }
    return `${size.toFixed(1)} ${units[unitIndex]}`;
  }

  formatProgress(progress: number): string {
    return `${(progress * 100).toFixed(1)}%`;
  }

  getStateColor(state: string, progress?: number): string {
    const color = this.stateColors[state];
    if (color) return color;
    if (progress !== undefined && progress >= 1) return 'state-seeding';
    return 'state-default';
  }

  getStateLabel(state: string, progress?: number): string {
    const label = this.stateLabels[state];
    if (label) return label;
    if (progress !== undefined && progress >= 1) return 'Seeding';
    return state;
  }

  openActionMenu(event: MouseEvent, hash: string): void {
    event.stopPropagation();
    if (this.actionMenuHash() === hash) {
      this.actionMenuHash.set('');
      return;
    }
    const btn = (event.target as HTMLElement).closest('button')!;
    const rect = btn.getBoundingClientRect();
    this.actionMenuPos.set(this.constrainMenuToViewport(rect));
    this.actionMenuHash.set(hash);
  }

  getMenuTorrent(hash: string): Torrent[] {
    const torrent = this.torrents().find((t: Torrent) => t.hash === hash);
    return torrent ? [torrent] : [];
  }

  togglePause(torrent: Torrent): void {
    this.actionMenuHash.set('');
    const wasPaused = torrent.is_paused;
    const newState = wasPaused ? 'uploading' : 'pausedUP';

    // Optimistic update
    this.torrents.update((list: Torrent[]) =>
      list.map((t: Torrent) => t.hash === torrent.hash
        ? { ...t, is_paused: !wasPaused, state: newState }
        : t
      ),
    );

    const action$ = wasPaused
      ? this.api.resumeTorrent(torrent.hash)
      : this.api.pauseTorrent(torrent.hash);

    action$
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (response: ActionResponse) => {
          if (response.success) {
            this.notifications.success(wasPaused ? 'Torrent resumed' : 'Torrent paused');
          } else {
            this.notifications.error(response.message);
            this.loadTorrents();
          }
        },
        error: () => {
          this.notifications.error(`Failed to ${wasPaused ? 'resume' : 'pause'} torrent`);
          this.loadTorrents();
        },
      });
  }

  toggleBlacklist(torrent: Torrent): void {
    this.actionMenuHash.set('');
    const wasBlacklisted = torrent.is_blacklisted;

    if (wasBlacklisted) {
      this.confirmService.confirm({
        header: 'Remove from Blacklist',
        message: `Remove "${torrent.name}" from the blacklist?`,
        accept: () => {
          this.torrents.update((list: Torrent[]) =>
            list.map((t: Torrent) => t.hash === torrent.hash ? { ...t, is_blacklisted: false } : t),
          );
          this.api.removeFromBlacklist(torrent.hash)
            .pipe(takeUntilDestroyed(this.destroyRef))
            .subscribe({
              next: () => this.notifications.success('Removed from blacklist'),
              error: () => {
                this.notifications.error('Failed to remove from blacklist');
                this.loadTorrents();
              },
            });
        },
      });
    } else {
      this.confirmService.confirm({
        header: 'Add to Blacklist',
        message: `Add "${torrent.name}" to the blacklist? It will be protected from cleanup.`,
        accept: () => {
          this.torrents.update((list: Torrent[]) =>
            list.map((t: Torrent) => t.hash === torrent.hash ? { ...t, is_blacklisted: true } : t),
          );
          this.api.addToBlacklist({ hash: torrent.hash, name: torrent.name, reason: 'Added from web UI' })
            .pipe(takeUntilDestroyed(this.destroyRef))
            .subscribe({
              next: () => this.notifications.success('Added to blacklist'),
              error: () => {
                this.notifications.error('Failed to add to blacklist');
                this.loadTorrents();
              },
            });
        },
      });
    }
  }

  moveTorrent(torrent: Torrent): void {
    this.actionMenuHash.set('');
    this.api.getCategories()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (response: CategoriesResponse) => {
          const selectOptions: SelectOption[] = response.categories.map(
            (cat: { name: string; save_path: string }) => ({
              label: cat.name,
              value: `category:${cat.name}`,
              description: cat.save_path,
            }),
          );
          this.confirmService.confirm({
            header: 'Move Torrent',
            message: `Move "${torrent.name}"\nCurrent path: ${torrent.save_path}`,
            selectOptions,
            selectPlaceholder: 'Select a category...',
            inputPlaceholder: 'Or enter a custom path...',
            accept: (inputValue?: string) => {
              if (!inputValue) return;
              const isCategory = inputValue.startsWith('category:');
              const newCategory = isCategory ? inputValue.replace('category:', '') : torrent.category;
              const newPath = !isCategory ? inputValue : torrent.save_path;
              const request = isCategory
                ? { hash: torrent.hash, category: newCategory }
                : { hash: torrent.hash, location: inputValue };

              // Optimistic update
              this.movingHash.set(torrent.hash);
              this.torrents.update((list: Torrent[]) =>
                list.map((t: Torrent) => t.hash === torrent.hash
                  ? { ...t, category: newCategory, save_path: newPath, is_moving: true }
                  : t
                ),
              );

              this.api.moveTorrent(request)
                .pipe(takeUntilDestroyed(this.destroyRef))
                .subscribe({
                  next: (moveResponse: ActionResponse) => {
                    this.movingHash.set('');
                    if (moveResponse.success) {
                      this.notifications.success(moveResponse.message);
                      this.torrents.update((list: Torrent[]) =>
                        list.map((t: Torrent) => t.hash === torrent.hash ? { ...t, is_moving: false } : t),
                      );
                    } else {
                      this.notifications.error(moveResponse.message);
                      this.loadTorrents();
                    }
                  },
                  error: () => {
                    this.movingHash.set('');
                    this.notifications.error('Failed to move torrent');
                    this.loadTorrents();
                  },
                });
            },
          });
        },
        error: () => this.notifications.error('Failed to load categories'),
      });
  }

  recycleTorrent(torrent: Torrent): void {
    this.actionMenuHash.set('');
    this.confirmService.confirm({
      header: 'Recycle Torrent',
      message: `Recycle "${torrent.name}"? Files will be moved to the recycle bin and the torrent removed from qBittorrent.`,
      accept: () => {
        this.recyclingHash.set(torrent.hash);

        // Optimistic remove
        this.torrents.update((list: Torrent[]) => list.filter((t: Torrent) => t.hash !== torrent.hash));

        this.api.deleteTorrent(torrent.hash, true, true)
          .pipe(takeUntilDestroyed(this.destroyRef))
          .subscribe({
            next: (response: ActionResponse) => {
              this.recyclingHash.set('');
              if (response.success) {
                const recycledName = response.data?.['recycled_name'];
                this.notifications.success(
                  'Torrent recycled',
                  recycledName
                    ? {
                        label: 'Undo',
                        callback: (complete: () => void) => this.undoRecycle(recycledName, complete),
                      }
                    : undefined,
                );
              } else {
                this.notifications.error(response.message);
                this.loadTorrents();
              }
            },
            error: () => {
              this.recyclingHash.set('');
              this.notifications.error('Failed to recycle torrent');
              this.loadTorrents();
            },
          });
      },
    });
  }

  private undoRecycle(recycledName: string, complete: () => void): void {
    this.api.restoreRecycleBinItem(recycledName)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (response: ActionResponse) => {
          complete();
          if (response.success) {
            this.notifications.success('Torrent restored from recycle bin');
            this.loadTorrents();
          } else {
            this.notifications.error(response.message);
          }
        },
        error: () => {
          complete();
          this.notifications.error('Failed to restore torrent');
        },
      });
  }

  deleteTorrent(torrent: Torrent): void {
    this.actionMenuHash.set('');
    this.confirmService.confirm({
      header: 'Delete Torrent',
      message: `Permanently delete "${torrent.name}"? This will remove the torrent and delete its files from disk. This cannot be undone.`,
      accept: () => {
        // Optimistic remove
        this.torrents.update((list: Torrent[]) => list.filter((t: Torrent) => t.hash !== torrent.hash));

        this.api.deleteTorrent(torrent.hash, true)
          .pipe(takeUntilDestroyed(this.destroyRef))
          .subscribe({
            next: () => this.notifications.success('Torrent deleted'),
            error: () => {
              this.notifications.error('Failed to delete torrent');
              this.loadTorrents();
            },
          });
      },
    });
  }

  // Bulk actions (universal actions for selected torrents)
  bulkTogglePause(): void {
    const list = this.selectedTorrents();
    if (list.length === 0) return;
    this.closeUniversalActions();
    const anyRunning = list.some((t: Torrent) => !t.is_paused);
    const actions = list.map((t: Torrent) =>
      anyRunning ? this.api.pauseTorrent(t.hash) : this.api.resumeTorrent(t.hash),
    );
    forkJoin(actions)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (responses: ActionResponse[]) => {
          const failed = responses.filter((r: ActionResponse) => !r.success);
          if (failed.length === 0) {
            this.torrents.update((torrents: Torrent[]) =>
              torrents.map((t: Torrent) =>
                list.some((s: Torrent) => s.hash === t.hash)
                  ? { ...t, is_paused: !anyRunning, state: anyRunning ? 'pausedUP' : 'uploading' }
                  : t,
              ),
            );
            this.notifications.success(
              anyRunning ? `Paused ${list.length} torrent(s)` : `Resumed ${list.length} torrent(s)`,
            );
          } else {
            this.notifications.error(failed[0].message || 'Action failed');
            this.loadTorrents();
          }
          this.clearSelection();
        },
        error: () => {
          this.notifications.error(`Failed to ${anyRunning ? 'pause' : 'resume'} torrents`);
          this.loadTorrents();
          this.clearSelection();
        },
      });
  }

  bulkToggleBlacklist(): void {
    const list = this.selectedTorrents();
    if (list.length === 0) return;
    this.closeUniversalActions();
    const allBlacklisted = list.every((t: Torrent) => t.is_blacklisted);
    const actionLabel = allBlacklisted ? 'Remove from Blacklist' : 'Add to Blacklist';
    const message = allBlacklisted
      ? `Remove ${list.length} torrent(s) from the blacklist?`
      : `Add ${list.length} torrent(s) to the blacklist? They will be protected from cleanup.`;
    this.confirmService.confirm({
      header: actionLabel,
      message,
      accept: () => {
        const actions = list.map((t: Torrent) =>
          allBlacklisted
            ? this.api.removeFromBlacklist(t.hash).pipe(map(() => ({ success: true } as ActionResponse)))
            : this.api.addToBlacklist({ hash: t.hash, name: t.name, reason: 'Bulk add from web UI' }),
        );
        forkJoin(actions)
          .pipe(takeUntilDestroyed(this.destroyRef))
          .subscribe({
            next: (responses: ActionResponse[]) => {
              const failed = responses.filter((r: ActionResponse) => !r.success);
              if (failed.length === 0) {
                this.torrents.update((torrents: Torrent[]) =>
                  torrents.map((t: Torrent) =>
                    list.some((s: Torrent) => s.hash === t.hash)
                      ? { ...t, is_blacklisted: !allBlacklisted }
                      : t,
                  ),
                );
                this.notifications.success(
                  allBlacklisted ? `Removed ${list.length} from blacklist` : `Added ${list.length} to blacklist`,
                );
              } else {
                this.notifications.error(failed[0].message || 'Action failed');
                this.loadTorrents();
              }
              this.clearSelection();
            },
            error: () => {
              this.notifications.error('Failed to update blacklist');
              this.loadTorrents();
              this.clearSelection();
            },
          });
      },
    });
  }

  bulkMove(): void {
    const list = this.selectedTorrents();
    if (list.length === 0) return;
    this.closeUniversalActions();
    this.api.getCategories()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (response: CategoriesResponse) => {
          const selectOptions: SelectOption[] = response.categories.map(
            (cat: { name: string; save_path: string }) => ({
              label: cat.name,
              value: `category:${cat.name}`,
              description: cat.save_path,
            }),
          );
          const first = list[0];
          this.confirmService.confirm({
            header: 'Move Torrents',
            message: `Move ${list.length} torrent(s)\nExample: "${first.name}"\nCurrent path: ${first.save_path}`,
            selectOptions,
            selectPlaceholder: 'Select a category...',
            inputPlaceholder: 'Or enter a custom path...',
            accept: (inputValue?: string) => {
              if (!inputValue) return;
              const isCategory = inputValue.startsWith('category:');
              const newCategory = isCategory ? inputValue.replace('category:', '') : first.category;
              const actions = list.map((t: Torrent) =>
                this.api.moveTorrent(
                  isCategory ? { hash: t.hash, category: newCategory } : { hash: t.hash, location: inputValue },
                ),
              );
              forkJoin(actions)
                .pipe(takeUntilDestroyed(this.destroyRef))
                .subscribe({
                  next: (responses: ActionResponse[]) => {
                    const failed = responses.filter((r: ActionResponse) => !r.success);
                    if (failed.length === 0) {
                      this.notifications.success(`Moved ${list.length} torrent(s)`);
                      this.loadTorrents();
                    } else {
                      this.notifications.error(failed[0].message || 'Move failed');
                      this.loadTorrents();
                    }
                    this.clearSelection();
                  },
                  error: () => {
                    this.notifications.error('Failed to move torrents');
                    this.loadTorrents();
                    this.clearSelection();
                  },
                });
            },
          });
        },
        error: () => this.notifications.error('Failed to load categories'),
      });
  }

  bulkRecycle(): void {
    const list = this.selectedTorrents();
    if (list.length === 0) return;
    this.closeUniversalActions();
    this.confirmService.confirm({
      header: 'Recycle Torrents',
      message: `Recycle ${list.length} torrent(s)? Files will be moved to the recycle bin and the torrents removed from qBittorrent.`,
      accept: () => {
        this.torrents.update((torrents: Torrent[]) => torrents.filter((t: Torrent) => !list.some((s: Torrent) => s.hash === t.hash)));
        const actions = list.map((t: Torrent) => this.api.deleteTorrent(t.hash, true, true));
        forkJoin(actions)
          .pipe(takeUntilDestroyed(this.destroyRef))
          .subscribe({
            next: (responses: ActionResponse[]) => {
              const failed = responses.filter((r: ActionResponse) => !r.success);
              if (failed.length === 0) {
                this.notifications.success(`Recycled ${list.length} torrent(s)`);
              } else {
                this.notifications.error(failed[0].message || 'Recycle failed');
                this.loadTorrents();
              }
              this.clearSelection();
            },
            error: () => {
              this.notifications.error('Failed to recycle torrents');
              this.loadTorrents();
              this.clearSelection();
            },
          });
      },
    });
  }

  bulkDelete(): void {
    const list = this.selectedTorrents();
    if (list.length === 0) return;
    this.closeUniversalActions();
    this.confirmService.confirm({
      header: 'Delete Torrents',
      message: `Permanently delete ${list.length} torrent(s)? This will remove the torrents and delete their files from disk. This cannot be undone.`,
      accept: () => {
        this.torrents.update((torrents: Torrent[]) => torrents.filter((t: Torrent) => !list.some((s: Torrent) => s.hash === t.hash)));
        const actions = list.map((t: Torrent) => this.api.deleteTorrent(t.hash, true));
        forkJoin(actions)
          .pipe(takeUntilDestroyed(this.destroyRef))
          .subscribe({
            next: () => {
              this.notifications.success(`Deleted ${list.length} torrent(s)`);
              this.clearSelection();
            },
            error: () => {
              this.notifications.error('Failed to delete torrents');
              this.loadTorrents();
              this.clearSelection();
            },
          });
      },
    });
  }

  private loadColumnOrder(): ColumnDef[] {
    try {
      const stored = localStorage.getItem(COLUMN_ORDER_KEY);
      if (stored) {
        const ids: string[] = JSON.parse(stored);
        const colMap = new Map<string, ColumnDef>(DEFAULT_COLUMNS.map((c: ColumnDef) => [c.id, c]));
        let ordered = ids
          .map((id: string) => colMap.get(id))
          .filter((c: ColumnDef | undefined): c is ColumnDef => c !== undefined);
        for (const col of DEFAULT_COLUMNS) {
          if (!ordered.some((o: ColumnDef) => o.id === col.id)) {
            ordered.push(col);
          }
        }
        // Ensure select column is always first
        const selectCol = ordered.find((c: ColumnDef) => c.id === 'select');
        if (selectCol && ordered[0]?.id !== 'select') {
          ordered = [selectCol, ...ordered.filter((c: ColumnDef) => c.id !== 'select')];
        }
        return ordered;
      }
    } catch {
      // Ignore parse errors
    }
    return [...DEFAULT_COLUMNS];
  }

  private saveColumnOrder(): void {
    const ids = this.columnOrder().map((c: ColumnDef) => c.id);
    localStorage.setItem(COLUMN_ORDER_KEY, JSON.stringify(ids));
  }

  private loadColumnWidths(): Record<string, number> {
    try {
      const version = localStorage.getItem(COLUMN_WIDTHS_VERSION_KEY);

      // If old version or no version, discard stored widths (they're pixel values)
      if (!version || parseInt(version, 10) < COLUMN_WIDTHS_VERSION) {
        localStorage.removeItem(COLUMN_WIDTHS_KEY);
        localStorage.removeItem(COLUMN_WIDTHS_VERSION_KEY);
        return {};
      }

      const stored = localStorage.getItem(COLUMN_WIDTHS_KEY);
      if (stored) {
        const widths: Record<string, number> = JSON.parse(stored);

        // Validate all values are in sane percentage range (1-80)
        const currentIds = new Set(DEFAULT_COLUMNS.map((c: ColumnDef) => c.id));
        for (const [id, value] of Object.entries(widths)) {
          if (!currentIds.has(id) || value < 1 || value > 80) {
            localStorage.removeItem(COLUMN_WIDTHS_KEY);
            localStorage.removeItem(COLUMN_WIDTHS_VERSION_KEY);
            return {};
          }
        }

        return widths;
      }
    } catch {
      // Ignore parse errors
    }
    return {};
  }

  private saveColumnWidths(): void {
    const widths = this.columnWidths();
    if (Object.keys(widths).length > 0) {
      localStorage.setItem(COLUMN_WIDTHS_KEY, JSON.stringify(widths));
      localStorage.setItem(COLUMN_WIDTHS_VERSION_KEY, String(COLUMN_WIDTHS_VERSION));
    } else {
      localStorage.removeItem(COLUMN_WIDTHS_KEY);
      localStorage.removeItem(COLUMN_WIDTHS_VERSION_KEY);
    }
  }
}
