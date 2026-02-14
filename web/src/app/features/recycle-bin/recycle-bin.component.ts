import { ChangeDetectionStrategy, Component, computed, DestroyRef, inject, OnInit, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ApiService } from '../../core/services/api.service';
import { NotificationService } from '../../core/services/notification.service';
import { ConfirmService } from '../../core/services/confirm.service';
import { ActionResponse, RecycleBinItem, RecycleBinResponse } from '../../shared/models';
import { LoadingContainerComponent } from '../../shared/ui/loading-container/loading-container.component';

@Component({
  selector: 'app-recycle-bin',
  standalone: true,
  imports: [LoadingContainerComponent],
  templateUrl: './recycle-bin.component.html',
  styleUrl: './recycle-bin.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class RecycleBinComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly notify = inject(NotificationService);
  private readonly confirmService = inject(ConfirmService);
  private readonly destroyRef = inject(DestroyRef);

  readonly data = signal<RecycleBinResponse | null>(null);
  readonly loading = signal(true);

  readonly isEmpty = computed(() => {
    const d = this.data();
    return !d || d.items.length === 0;
  });

  ngOnInit(): void {
    this.loadRecycleBin();
  }

  loadRecycleBin(): void {
    this.loading.set(true);
    this.api.getRecycleBin()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (response: RecycleBinResponse) => {
          this.data.set(response);
          this.loading.set(false);
        },
        error: () => {
          this.loading.set(false);
          this.notify.error('Failed to load recycle bin');
        },
      });
  }

  deleteItem(item: RecycleBinItem): void {
    this.confirmService.confirm({
      header: 'Delete Permanently',
      message: `Permanently delete "${item.name}"? This cannot be undone.`,
      accept: () => {
        this.api.deleteRecycleBinItem(item.name)
          .pipe(takeUntilDestroyed(this.destroyRef))
          .subscribe({
            next: () => {
              this.notify.success(`Deleted ${item.name}`);
              this.loadRecycleBin();
            },
            error: () => this.notify.error('Failed to delete item'),
          });
      },
    });
  }

  restoreItem(item: RecycleBinItem): void {
    const hasMetadata = !!item.original_path;
    this.confirmService.confirm({
      header: 'Restore Item',
      message: hasMetadata
        ? `Restore "${item.name}" to its original location?`
        : `No original path metadata found. Enter the destination directory to restore "${item.name}":`,
      inputPlaceholder: hasMetadata ? undefined : '/path/to/restore/directory',
      inputDefault: item.original_path || '',
      accept: (inputValue?: string) => {
        const targetPath = hasMetadata ? undefined : inputValue;
        this.api.restoreRecycleBinItem(item.name, targetPath)
          .pipe(takeUntilDestroyed(this.destroyRef))
          .subscribe({
            next: (response: ActionResponse) => {
              if (response.success) {
                this.notify.success(`Restored ${item.name}`);
              } else {
                this.notify.error(response.message);
              }
              this.loadRecycleBin();
            },
            error: () => this.notify.error('Failed to restore item'),
          });
      },
    });
  }

  emptyBin(): void {
    this.confirmService.confirm({
      header: 'Empty Recycle Bin',
      message: 'Permanently delete all items in the recycle bin? This cannot be undone.',
      accept: () => {
        this.api.emptyRecycleBin()
          .pipe(takeUntilDestroyed(this.destroyRef))
          .subscribe({
            next: () => {
              this.notify.success('Recycle bin emptied');
              this.loadRecycleBin();
            },
            error: () => this.notify.error('Failed to empty recycle bin'),
          });
      },
    });
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

  formatAge(days: number): string {
    if (days < 1) return 'Today';
    if (days < 2) return '1 day ago';
    return `${Math.floor(days)} days ago`;
  }
}
