import { Component, computed, DestroyRef, inject, OnInit, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { MatTableModule, MatTableDataSource } from '@angular/material/table';
import { MatInputModule } from '@angular/material/input';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatDividerModule } from '@angular/material/divider';
import { ApiService } from '../../core/services/api.service';
import { ActionResponse, BlacklistEntry } from '../../shared/models';
import { ConfirmDialogComponent } from '../torrents/confirm-dialog.component';

@Component({
  selector: 'app-blacklist',
  standalone: true,
  imports: [
    FormsModule,
    MatTableModule,
    MatInputModule,
    MatFormFieldModule,
    MatIconModule,
    MatButtonModule,
    MatCardModule,
    MatProgressSpinnerModule,
    MatSnackBarModule,
    MatDialogModule,
    MatTooltipModule,
    MatDividerModule,
  ],
  templateUrl: './blacklist.component.html',
  styleUrl: './blacklist.component.scss',
})
export class BlacklistComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly snackBar = inject(MatSnackBar);
  private readonly dialog = inject(MatDialog);
  private readonly destroyRef = inject(DestroyRef);

  readonly displayedColumns: string[] = ['name', 'hash', 'reason', 'added_at', 'actions'];
  readonly dataSource = new MatTableDataSource<BlacklistEntry>();
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
          this.dataSource.data = entries;
          this.loading.set(false);
        },
        error: () => {
          this.loading.set(false);
          this.snackBar.open('Failed to load blacklist', 'Dismiss', {
            duration: 5000,
            panelClass: ['error-snackbar'],
          });
        },
      });
  }

  addEntry(): void {
    if (!this.canAdd()) {
      this.snackBar.open('Hash is required', 'Dismiss', { duration: 3000 });
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
          this.snackBar.open(result.message, 'OK', {
            duration: 3000,
            panelClass: [result.success ? 'success-snackbar' : 'error-snackbar'],
          });
          if (result.success) {
            this.newHash.set('');
            this.newName.set('');
            this.newReason.set('');
            this.loadBlacklist();
          }
        },
        error: () => {
          this.snackBar.open('Failed to add to blacklist', 'Dismiss', {
            duration: 5000,
            panelClass: ['error-snackbar'],
          });
        },
      });
  }

  removeEntry(entry: BlacklistEntry): void {
    const dialogRef = this.dialog.open(ConfirmDialogComponent, {
      data: {
        title: 'Remove from Blacklist',
        message: `Remove "${entry.name || entry.hash}" from the blacklist?`,
      },
    });

    dialogRef.afterClosed()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((confirmed: boolean) => {
        if (confirmed) {
          this.api.removeFromBlacklist(entry.hash)
            .pipe(takeUntilDestroyed(this.destroyRef))
            .subscribe({
              next: () => {
                this.snackBar.open('Removed from blacklist', 'OK', {
                  duration: 3000,
                  panelClass: ['success-snackbar'],
                });
                this.loadBlacklist();
              },
              error: () => {
                this.snackBar.open('Failed to remove from blacklist', 'Dismiss', {
                  duration: 5000,
                  panelClass: ['error-snackbar'],
                });
              },
            });
        }
      });
  }

  clearAll(): void {
    const dialogRef = this.dialog.open(ConfirmDialogComponent, {
      data: {
        title: 'Clear Entire Blacklist',
        message: 'Are you sure you want to remove ALL entries from the blacklist? This cannot be undone.',
      },
    });

    dialogRef.afterClosed()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((confirmed: boolean) => {
        if (confirmed) {
          this.api.clearBlacklist()
            .pipe(takeUntilDestroyed(this.destroyRef))
            .subscribe({
              next: (result: ActionResponse) => {
                this.snackBar.open(result.message, 'OK', {
                  duration: 3000,
                  panelClass: [result.success ? 'success-snackbar' : 'error-snackbar'],
                });
                this.loadBlacklist();
              },
              error: () => {
                this.snackBar.open('Failed to clear blacklist', 'Dismiss', {
                  duration: 5000,
                  panelClass: ['error-snackbar'],
                });
              },
            });
        }
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
