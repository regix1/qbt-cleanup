import { Component, computed, DestroyRef, inject, signal, OnInit } from '@angular/core';
import { DecimalPipe, NgClass } from '@angular/common';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { ApiService } from '../../core/services/api.service';
import { NotificationService } from '../../core/services/notification.service';
import { ConfirmService } from '../../core/services/confirm.service';
import { Torrent } from '../../shared/models';

@Component({
  selector: 'app-torrents',
  standalone: true,
  imports: [
    DecimalPipe,
    NgClass,
    FormsModule,
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

  readonly filterText = signal<string>('');
  readonly sortField = signal<string>('name');
  readonly sortDirection = signal<'asc' | 'desc'>('asc');
  readonly currentPage = signal<number>(0);
  readonly pageSize = signal<number>(25);

  readonly filteredTorrents = computed<Torrent[]>(() => {
    const filter = this.filterText().toLowerCase().trim();
    const all = this.torrents();
    if (!filter) return all;
    return all.filter((torrent: Torrent) =>
      torrent.name.toLowerCase().includes(filter) ||
      torrent.state.toLowerCase().includes(filter) ||
      torrent.category.toLowerCase().includes(filter),
    );
  });

  readonly sortedTorrents = computed<Torrent[]>(() => {
    const items = [...this.filteredTorrents()];
    const field = this.sortField();
    const direction = this.sortDirection();

    items.sort((a: Torrent, b: Torrent) => {
      const aValue = a[field as keyof Torrent];
      const bValue = b[field as keyof Torrent];

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

  private readonly stateColors: Record<string, string> = {
    downloading: 'state-downloading',
    uploading: 'state-seeding',
    seeding: 'state-seeding',
    pausedUP: 'state-paused',
    pausedDL: 'state-paused',
    stalledUP: 'state-stalled',
    stalledDL: 'state-stalled',
    error: 'state-error',
    queuedUP: 'state-queued',
    queuedDL: 'state-queued',
    checkingUP: 'state-checking',
    checkingDL: 'state-checking',
  };

  private readonly stateLabels: Record<string, string> = {
    downloading: 'Downloading',
    uploading: 'Seeding',
    seeding: 'Seeding',
    pausedUP: 'Paused',
    pausedDL: 'Paused',
    stalledUP: 'Stalled',
    stalledDL: 'Stalled',
    error: 'Error',
    queuedUP: 'Queued',
    queuedDL: 'Queued',
    checkingUP: 'Checking',
    checkingDL: 'Checking',
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

  sort(field: string): void {
    if (this.sortField() === field) {
      this.sortDirection.set(this.sortDirection() === 'asc' ? 'desc' : 'asc');
    } else {
      this.sortField.set(field);
      this.sortDirection.set('asc');
    }
    this.currentPage.set(0);
  }

  onFilterChange(event: Event): void {
    const value = (event.target as HTMLInputElement).value;
    this.filterText.set(value);
    this.currentPage.set(0);
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

  getStateColor(state: string): string {
    return this.stateColors[state] ?? 'state-default';
  }

  getStateLabel(state: string): string {
    return this.stateLabels[state] ?? state;
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
