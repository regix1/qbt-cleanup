import { ChangeDetectionStrategy, Component, computed, DestroyRef, HostListener, inject, signal, OnInit } from '@angular/core';
import { DecimalPipe, NgClass } from '@angular/common';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CdkDragDrop, CdkDrag, CdkDropList, CdkDragHandle, CdkDragPreview, moveItemInArray } from '@angular/cdk/drag-drop';
import { ApiService } from '../../core/services/api.service';
import { NotificationService } from '../../core/services/notification.service';
import { ConfirmService } from '../../core/services/confirm.service';
import { ActionResponse, Torrent } from '../../shared/models';
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
  minWidth: number;
}

const COLUMN_ORDER_KEY = 'qbt-torrents-column-order';
const COLUMN_WIDTHS_KEY = 'qbt-torrents-column-widths';

const DEFAULT_COLUMNS: ColumnDef[] = [
  { id: 'name', label: 'Name', sortField: 'name', cssClass: 'col-name', minWidth: 120 },
  { id: 'state', label: 'State', sortField: 'state', cssClass: 'col-state', minWidth: 70 },
  { id: 'ratio', label: 'Ratio', sortField: 'ratio', cssClass: 'col-ratio', minWidth: 60 },
  { id: 'seedTime', label: 'Seeding Time', sortField: 'seeding_time', cssClass: 'col-seed-time', minWidth: 80 },
  { id: 'type', label: 'Type', sortField: 'is_private', cssClass: 'col-type', minWidth: 70 },
  { id: 'size', label: 'Size', sortField: 'size', cssClass: 'col-size', minWidth: 60 },
  { id: 'progress', label: 'Progress', sortField: 'progress', cssClass: 'col-progress', minWidth: 70 },
  { id: 'blacklist', label: 'Blacklisted', sortField: 'is_blacklisted', cssClass: 'col-blacklist', minWidth: 60 },
  { id: 'actions', label: 'Actions', cssClass: 'col-actions', minWidth: 50 },
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

  readonly hasCustomWidths = computed<boolean>(() =>
    Object.keys(this.columnWidths()).length > 0,
  );

  // Resize tracking
  private resizeColumnId = '';
  private resizeStartX = 0;
  private resizeStartWidth = 0;
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

  // Dropdown state
  readonly openDropdown = signal<string>('');
  readonly actionMenuHash = signal<string>('');
  readonly actionMenuPos = signal<{ top: number; left: number }>({ top: 0, left: 0 });

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

  private readonly stateColors: Record<string, string> = {
    downloading: 'state-downloading',
    uploading: 'state-seeding',
    seeding: 'state-seeding',
    pausedUP: 'state-paused',
    pausedDL: 'state-paused',
    stalledUP: 'state-idle',
    stalledDL: 'state-stalled',
    error: 'state-error',
    queuedUP: 'state-queued',
    queuedDL: 'state-queued',
    checkingUP: 'state-checking',
    checkingDL: 'state-checking',
    forcedUP: 'state-seeding',
    forcedDL: 'state-downloading',
    missingFiles: 'state-error',
    moving: 'state-checking',
    allocating: 'state-checking',
    checkingResumeData: 'state-checking',
    unknown: 'state-default',
  };

  private readonly stateLabels: Record<string, string> = {
    downloading: 'Downloading',
    uploading: 'Seeding',
    seeding: 'Seeding',
    pausedUP: 'Paused (S)',
    pausedDL: 'Paused (D)',
    stalledUP: 'Idle',
    stalledDL: 'Stalled',
    error: 'Error',
    queuedUP: 'Queued (S)',
    queuedDL: 'Queued (D)',
    checkingUP: 'Checking',
    checkingDL: 'Checking',
    forcedUP: 'Forced Seed',
    forcedDL: 'Forced DL',
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
  }

  ngOnInit(): void {
    this.loadTorrents();
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

  // Column ordering
  onColumnDrop(event: CdkDragDrop<string[]>): void {
    // Snapshot current widths before reordering so columns keep their sizes
    if (!this.hasCustomWidths()) {
      this.snapshotColumnWidths();
    }
    const columns = [...this.columnOrder()];
    moveItemInArray(columns, event.previousIndex, event.currentIndex);
    this.columnOrder.set(columns);
    this.saveColumnOrder();
    this.saveColumnWidths();
  }

  resetColumns(): void {
    this.columnOrder.set([...DEFAULT_COLUMNS]);
    this.columnWidths.set({});
    localStorage.removeItem(COLUMN_ORDER_KEY);
    localStorage.removeItem(COLUMN_WIDTHS_KEY);
  }

  onHeaderClick(col: ColumnDef): void {
    if (col.sortField) {
      this.sort(col.sortField);
    }
  }

  // Column resizing
  getColumnWidth(col: ColumnDef): number | null {
    const widths = this.columnWidths();
    return widths[col.id] ?? null;
  }

  onResizeStart(event: MouseEvent, col: ColumnDef): void {
    event.preventDefault();
    event.stopPropagation();

    this.resizeColumnId = col.id;
    this.resizeStartX = event.clientX;
    this.isResizing.set(true);

    // Snapshot current width from DOM
    const th = (event.target as HTMLElement).closest('th');
    if (th) {
      this.resizeStartWidth = th.getBoundingClientRect().width;
    }

    // Capture container width for max constraint
    const container = (event.target as HTMLElement).closest('.table-container');
    this.resizeContainerWidth = container ? container.clientWidth : 0;

    // If no custom widths yet, snapshot all column widths from DOM
    if (!this.hasCustomWidths()) {
      this.snapshotColumnWidths();
    }

    document.addEventListener('mousemove', this.onResizeMove);
    document.addEventListener('mouseup', this.onResizeEnd);
  }

  private readonly onResizeMove = (event: MouseEvent): void => {
    const delta = event.clientX - this.resizeStartX;
    const col = this.columnOrder().find((c: ColumnDef) => c.id === this.resizeColumnId);
    const minWidth = col?.minWidth ?? 50;

    // Cap so total columns don't exceed container width
    let maxWidth = Infinity;
    if (this.resizeContainerWidth > 0) {
      const widths = this.columnWidths();
      let otherColumnsWidth = 0;
      for (const c of this.columnOrder()) {
        if (c.id !== this.resizeColumnId) {
          otherColumnsWidth += widths[c.id] ?? c.minWidth;
        }
      }
      maxWidth = this.resizeContainerWidth - otherColumnsWidth;
    }

    const newWidth = Math.min(maxWidth, Math.max(minWidth, this.resizeStartWidth + delta));
    this.columnWidths.update((widths: Record<string, number>) => ({
      ...widths,
      [this.resizeColumnId]: newWidth,
    }));
  };

  private readonly onResizeEnd = (): void => {
    document.removeEventListener('mousemove', this.onResizeMove);
    document.removeEventListener('mouseup', this.onResizeEnd);
    this.isResizing.set(false);
    this.resizeColumnId = '';
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
    this.actionMenuPos.set({ top: rect.bottom + 4, left: rect.right - 180 });
    this.actionMenuHash.set(hash);
  }

  getMenuTorrent(hash: string): Torrent[] {
    const torrent = this.torrents().find((t: Torrent) => t.hash === hash);
    return torrent ? [torrent] : [];
  }

  toggleBlacklist(torrent: Torrent): void {
    this.actionMenuHash.set('');
    if (torrent.is_blacklisted) {
      this.confirmService.confirm({
        header: 'Remove from Blacklist',
        message: `Remove "${torrent.name}" from the blacklist?`,
        accept: () => {
          this.api.removeFromBlacklist(torrent.hash)
            .pipe(takeUntilDestroyed(this.destroyRef))
            .subscribe({
              next: () => {
                this.notifications.success('Removed from blacklist');
                this.loadTorrents();
              },
              error: () => this.notifications.error('Failed to remove from blacklist'),
            });
        },
      });
    } else {
      this.confirmService.confirm({
        header: 'Add to Blacklist',
        message: `Add "${torrent.name}" to the blacklist? It will be protected from cleanup.`,
        accept: () => {
          this.api.addToBlacklist({ hash: torrent.hash, name: torrent.name, reason: 'Added from web UI' })
            .pipe(takeUntilDestroyed(this.destroyRef))
            .subscribe({
              next: () => {
                this.notifications.success('Added to blacklist');
                this.loadTorrents();
              },
              error: () => this.notifications.error('Failed to add to blacklist'),
            });
        },
      });
    }
  }

  recycleTorrent(torrent: Torrent): void {
    this.actionMenuHash.set('');
    this.confirmService.confirm({
      header: 'Recycle Torrent',
      message: `Recycle "${torrent.name}"? Files will be moved to the recycle bin and the torrent removed from qBittorrent.`,
      accept: () => {
        this.api.deleteTorrent(torrent.hash, true, true)
          .pipe(takeUntilDestroyed(this.destroyRef))
          .subscribe({
            next: (response: ActionResponse) => {
              if (response.success) {
                const recycledName = response.data?.['recycled_name'];
                this.notifications.success(
                  'Torrent recycled',
                  recycledName
                    ? {
                        label: 'Undo',
                        callback: () => this.undoRecycle(recycledName),
                      }
                    : undefined,
                );
                this.loadTorrents();
              } else {
                this.notifications.error(response.message);
              }
            },
            error: () => this.notifications.error('Failed to recycle torrent'),
          });
      },
    });
  }

  private undoRecycle(recycledName: string): void {
    this.api.restoreRecycleBinItem(recycledName)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (response: ActionResponse) => {
          if (response.success) {
            this.notifications.success('Torrent restored from recycle bin');
          } else {
            this.notifications.error(response.message);
          }
        },
        error: () => this.notifications.error('Failed to restore torrent'),
      });
  }

  deleteTorrent(torrent: Torrent): void {
    this.actionMenuHash.set('');
    this.confirmService.confirm({
      header: 'Delete Torrent',
      message: `Permanently delete "${torrent.name}"? This will remove the torrent and delete its files from disk. This cannot be undone.`,
      accept: () => {
        this.api.deleteTorrent(torrent.hash, true)
          .pipe(takeUntilDestroyed(this.destroyRef))
          .subscribe({
            next: () => {
              this.notifications.success('Torrent deleted');
              this.loadTorrents();
            },
            error: () => this.notifications.error('Failed to delete torrent'),
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
        const ordered = ids
          .map((id: string) => colMap.get(id))
          .filter((c: ColumnDef | undefined): c is ColumnDef => c !== undefined);
        for (const col of DEFAULT_COLUMNS) {
          if (!ordered.some((o: ColumnDef) => o.id === col.id)) {
            ordered.push(col);
          }
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
      const stored = localStorage.getItem(COLUMN_WIDTHS_KEY);
      if (stored) {
        return JSON.parse(stored);
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
    } else {
      localStorage.removeItem(COLUMN_WIDTHS_KEY);
    }
  }

  private snapshotColumnWidths(): void {
    const headerRow = document.querySelector('.data-table thead tr');
    if (!headerRow) return;
    const ths = headerRow.querySelectorAll('th');
    const widths: Record<string, number> = {};
    const columns = this.columnOrder();
    ths.forEach((th: Element, index: number) => {
      if (index < columns.length) {
        widths[columns[index].id] = (th as HTMLElement).getBoundingClientRect().width;
      }
    });
    this.columnWidths.set(widths);
  }
}
