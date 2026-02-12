import { Component, computed, DestroyRef, inject, OnInit, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { TableModule } from 'primeng/table';
import { CardModule } from 'primeng/card';
import { ButtonModule } from 'primeng/button';
import { InputTextModule } from 'primeng/inputtext';
import { FloatLabelModule } from 'primeng/floatlabel';
import { ProgressSpinnerModule } from 'primeng/progressspinner';
import { TooltipModule } from 'primeng/tooltip';
import { ConfirmationService } from 'primeng/api';
import { ApiService } from '../../core/services/api.service';
import { ActionResponse, BlacklistEntry } from '../../shared/models';
import { NotificationService } from '../../core/services/notification.service';

@Component({
  selector: 'app-blacklist',
  standalone: true,
  imports: [
    FormsModule,
    TableModule,
    CardModule,
    ButtonModule,
    InputTextModule,
    FloatLabelModule,
    ProgressSpinnerModule,
    TooltipModule,
  ],
  templateUrl: './blacklist.component.html',
  styleUrl: './blacklist.component.scss',
})
export class BlacklistComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly notify = inject(NotificationService);
  private readonly confirmationService = inject(ConfirmationService);
  private readonly destroyRef = inject(DestroyRef);

  readonly displayedColumns: string[] = ['name', 'hash', 'reason', 'added_at', 'actions'];
  readonly loading = signal<boolean>(true);
  readonly entries = signal<BlacklistEntry[]>([]);

  readonly newHash = signal<string>('');
  readonly newName = signal<string>('');
  readonly newReason = signal<string>('');

  readonly canAdd = computed(() => this.newHash().trim().length > 0);

  ngOnInit(): void {
    this.loadBlacklist();
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

  addEntry(): void {
    if (!this.canAdd()) {
      this.notify.warn('Hash is required');
      return;
    }

    this.api.addToBlacklist({
      hash: this.newHash().trim(),
      name: this.newName().trim() || undefined,
      reason: this.newReason().trim() || undefined,
    })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (result: ActionResponse) => {
          result.success ? this.notify.success(result.message) : this.notify.error(result.message);
          if (result.success) {
            this.newHash.set('');
            this.newName.set('');
            this.newReason.set('');
            this.loadBlacklist();
          }
        },
        error: () => {
          this.notify.error('Failed to add to blacklist');
        },
      });
  }

  removeEntry(entry: BlacklistEntry): void {
    this.confirmationService.confirm({
      message: `Remove "${entry.name || entry.hash}" from the blacklist?`,
      header: 'Remove from Blacklist',
      icon: 'pi pi-exclamation-triangle',
      accept: () => {
        this.api.removeFromBlacklist(entry.hash)
          .pipe(takeUntilDestroyed(this.destroyRef))
          .subscribe({
            next: () => {
              this.notify.success('Removed from blacklist');
              this.loadBlacklist();
            },
            error: () => this.notify.error('Failed to remove from blacklist'),
          });
      },
    });
  }

  clearAll(): void {
    this.confirmationService.confirm({
      message: 'Are you sure you want to remove ALL entries from the blacklist? This cannot be undone.',
      header: 'Clear Entire Blacklist',
      icon: 'pi pi-exclamation-triangle',
      accept: () => {
        this.api.clearBlacklist()
          .pipe(takeUntilDestroyed(this.destroyRef))
          .subscribe({
            next: (result: ActionResponse) => {
              result.success ? this.notify.success(result.message) : this.notify.error(result.message);
              this.loadBlacklist();
            },
            error: () => this.notify.error('Failed to clear blacklist'),
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
