import { ChangeDetectionStrategy, Component, computed, DestroyRef, HostListener, inject, OnInit, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { interval, switchMap } from 'rxjs';
import { FormsModule } from '@angular/forms';
import { ApiService } from '../../core/services/api.service';
import { ActionResponse, BlacklistEntry, Torrent } from '../../shared/models';
import { NotificationService } from '../../core/services/notification.service';
import { ConfirmService } from '../../core/services/confirm.service';
import { LoadingContainerComponent } from '../../shared/ui/loading-container/loading-container.component';

@Component({
  selector: 'app-blacklist',
  standalone: true,
  imports: [
    FormsModule,
    LoadingContainerComponent,
  ],
  templateUrl: './blacklist.component.html',
  styleUrl: './blacklist.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class BlacklistComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly notify = inject(NotificationService);
  private readonly confirmService = inject(ConfirmService);
  private readonly destroyRef = inject(DestroyRef);

  readonly displayedColumns: string[] = ['name', 'hash', 'reason', 'added_at', 'actions'];
  readonly loading = signal<boolean>(true);
  readonly entries = signal<BlacklistEntry[]>([]);

  readonly newHash = signal<string>('');
  readonly newName = signal<string>('');
  readonly newReason = signal<string>('');

  readonly torrents = signal<Torrent[]>([]);
  readonly showHashDropdown = signal(false);
  readonly hashSearch = signal('');

  readonly canAdd = computed(() => this.newHash().trim().length > 0);

  readonly filteredTorrents = computed(() => {
    const search = this.hashSearch().toLowerCase().trim();
    const blacklisted = new Set(this.entries().map((e: BlacklistEntry) => e.hash));
    const available = this.torrents().filter((t: Torrent) => !blacklisted.has(t.hash));
    if (!search) return available;
    return available.filter((t: Torrent) =>
      t.name.toLowerCase().includes(search) || t.hash.toLowerCase().includes(search)
    );
  });

  @HostListener('document:click', ['$event'])
  onDocumentClick(event: Event): void {
    const target = event.target as HTMLElement;
    if (!target.closest('.hash-dropdown') && !target.closest('.hash-picker-btn')) {
      this.showHashDropdown.set(false);
    }
  }

  ngOnInit(): void {
    this.loadBlacklist();
    this.loadTorrents();
    this.startAutoRefresh();
  }

  private startAutoRefresh(): void {
    interval(30_000).pipe(
      switchMap(() => this.api.getBlacklist()),
      takeUntilDestroyed(this.destroyRef),
    ).subscribe((entries: BlacklistEntry[]) => this.entries.set(entries));
  }

  loadBlacklist(): void {
    this.loading.set(true);
    this.api.getBlacklist()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (entries: BlacklistEntry[]) => {
          this.entries.set(entries);
          this.loading.set(false);
        },
        error: () => {
          this.loading.set(false);
          this.notify.error('Failed to load blacklist');
        },
      });
  }

  loadTorrents(): void {
    this.api.getTorrents()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (torrents: Torrent[]) => this.torrents.set(torrents),
      });
  }

  toggleHashDropdown(): void {
    this.showHashDropdown.update((v: boolean) => !v);
    this.hashSearch.set('');
  }

  selectTorrent(torrent: Torrent): void {
    this.newHash.set(torrent.hash);
    this.newName.set(torrent.name);
    this.showHashDropdown.set(false);
  }

  onHashSearchChange(event: Event): void {
    this.hashSearch.set((event.target as HTMLInputElement).value);
  }

  addEntry(): void {
    if (!this.canAdd()) {
      this.notify.warn('Hash is required');
      return;
    }

    const hash = this.newHash().trim();
    const name = this.newName().trim() || undefined;
    const reason = this.newReason().trim() || undefined;

    // Optimistic: add to list and clear form immediately
    const optimisticEntry: BlacklistEntry = {
      hash,
      name: name || '',
      reason: reason || '',
      added_at: new Date().toISOString(),
    };
    this.entries.update((list: BlacklistEntry[]) => [optimisticEntry, ...list]);
    this.newHash.set('');
    this.newName.set('');
    this.newReason.set('');
    this.notify.success('Added to blacklist');

    this.api.addToBlacklist({ hash, name, reason })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (result: ActionResponse) => {
          if (!result.success) {
            this.notify.error(result.message);
            this.loadBlacklist();
          }
        },
        error: () => {
          this.notify.error('Failed to add to blacklist');
          this.loadBlacklist();
        },
      });
  }

  removeEntry(entry: BlacklistEntry): void {
    this.confirmService.confirm({
      message: `Remove "${entry.name || entry.hash}" from the blacklist?`,
      header: 'Remove from Blacklist',
      accept: () => {
        // Optimistic: remove from list immediately
        this.entries.update((list: BlacklistEntry[]) =>
          list.filter((e: BlacklistEntry) => e.hash !== entry.hash),
        );
        this.notify.success('Removed from blacklist');

        this.api.removeFromBlacklist(entry.hash)
          .pipe(takeUntilDestroyed(this.destroyRef))
          .subscribe({
            error: () => {
              this.notify.error('Failed to remove from blacklist');
              this.loadBlacklist();
            },
          });
      },
    });
  }

  clearAll(): void {
    this.confirmService.confirm({
      message: 'Are you sure you want to remove ALL entries from the blacklist? This cannot be undone.',
      header: 'Clear Entire Blacklist',
      accept: () => {
        // Optimistic: clear list immediately
        const previousEntries = this.entries();
        this.entries.set([]);
        this.notify.success('Blacklist cleared');

        this.api.clearBlacklist()
          .pipe(takeUntilDestroyed(this.destroyRef))
          .subscribe({
            next: (result: ActionResponse) => {
              if (!result.success) {
                this.notify.error(result.message);
                this.entries.set(previousEntries);
              }
            },
            error: () => {
              this.notify.error('Failed to clear blacklist');
              this.entries.set(previousEntries);
            },
          });
      },
    });
  }

  formatDate(dateStr: string): string {
    if (!dateStr) return '--';
    const date = new Date(dateStr);
    return date.toLocaleString();
  }

  truncateHash(hash: string): string {
    if (!hash) return '--';
    return hash.length > 12 ? `${hash.substring(0, 12)}...` : hash;
  }
}
