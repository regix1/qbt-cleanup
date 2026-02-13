import { Component, computed, DestroyRef, inject, signal, OnInit } from '@angular/core';
import { DecimalPipe, NgClass } from '@angular/common';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ApiService } from '../../core/services/api.service';
import { NotificationService } from '../../core/services/notification.service';
import { ConfirmService } from '../../core/services/confirm.service';
import { Torrent } from '../../shared/models';
import { LoadingContainerComponent } from '../../shared/ui/loading-container/loading-container.component';

interface ActiveFilter {
  type: 'state' | 'category' | 'type' | 'blacklist' | 'tracker';
  value: string;
  label: string;
}

@Component({
  selector: 'app-torrents',
  standalone: true,
  imports: [
    DecimalPipe,
    NgClass,
    LoadingContainerComponent,
  ],
  templateUrl: './torrents.component.html',
  styleUrl: './torrents.component.scss',
})
export class TorrentsComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly notifications = inject(NotificationService);
  private readonly confirmService = inject(ConfirmService);
  private readonly destroyRef = inject(DestroyRef);

  readonly torrents = signal<Torrent[]>([]);
  readonly loading = signal<boolean>(true);

  // Filter signals
  readonly searchText = signal<string>('');
  readonly stateFilter = signal<string>('');
  readonly categoryFilter = signal<string>('');
  readonly typeFilter = signal<'all' | 'private' | 'public'>('all');
  readonly blacklistFilter = signal<'all' | 'yes' | 'no'>('all');
  readonly trackerFilter = signal<string>('');

  // Layout
  readonly compactMode = signal<boolean>(false);

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
    const tracker = this.trackerFilter();
    if (tracker) {
      filters.push({ type: 'tracker', value: tracker, label: `Tracker: ${tracker}` });
    }
    return filters;
  });

  readonly hasActiveFilters = computed<boolean>(() => this.activeFilters().length > 0);

  readonly filteredTorrents = computed<Torrent[]>(() => {
    let result = this.torrents();

    // Search text — name only
    const search = this.searchText().toLowerCase().trim();
    if (search) {
      result = result.filter((t: Torrent) => t.name.toLowerCase().includes(search));
    }

    // State filter
    const state = this.stateFilter();
    if (state) {
      result = result.filter((t: Torrent) => t.state === state);
    }

    // Category filter
    const category = this.categoryFilter();
    if (category) {
      result = result.filter((t: Torrent) => t.category === category);
    }

    // Type filter
    const type = this.typeFilter();
    if (type === 'private') {
      result = result.filter((t: Torrent) => t.is_private);
    } else if (type === 'public') {
      result = result.filter((t: Torrent) => !t.is_private);
    }

    // Blacklist filter
    const blacklist = this.blacklistFilter();
    if (blacklist === 'yes') {
      result = result.filter((t: Torrent) => t.is_blacklisted);
    } else if (blacklist === 'no') {
      result = result.filter((t: Torrent) => !t.is_blacklisted);
    }

    // Tracker filter
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
    stalledUP: 'state-seeding',
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
    pausedUP: 'Paused',
    pausedDL: 'Paused',
    stalledUP: 'Seeding',
    stalledDL: 'Stalled',
    error: 'Error',
    queuedUP: 'Queued',
    queuedDL: 'Queued',
    checkingUP: 'Checking',
    checkingDL: 'Checking',
    forcedUP: 'Seeding',
    forcedDL: 'Downloading',
    missingFiles: 'Missing Files',
    moving: 'Moving',
    allocating: 'Allocating',
    checkingResumeData: 'Checking',
    unknown: 'Unknown',
  };

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

  onStateFilterChange(event: Event): void {
    const value = (event.target as HTMLSelectElement).value;
    this.stateFilter.set(value);
    this.currentPage.set(0);
  }

  onCategoryFilterChange(event: Event): void {
    const value = (event.target as HTMLSelectElement).value;
    this.categoryFilter.set(value);
    this.currentPage.set(0);
  }

  onTypeFilterChange(event: Event): void {
    const value = (event.target as HTMLSelectElement).value as 'all' | 'private' | 'public';
    this.typeFilter.set(value);
    this.currentPage.set(0);
  }

  onBlacklistFilterChange(event: Event): void {
    const value = (event.target as HTMLSelectElement).value as 'all' | 'yes' | 'no';
    this.blacklistFilter.set(value);
    this.currentPage.set(0);
  }

  onTrackerFilterChange(event: Event): void {
    const value = (event.target as HTMLSelectElement).value;
    this.trackerFilter.set(value);
    this.currentPage.set(0);
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

  toggleBlacklist(torrent: Torrent): void {
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
}
