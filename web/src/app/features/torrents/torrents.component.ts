import { Component, DestroyRef, inject, signal, viewChild, OnInit } from '@angular/core';
import { DecimalPipe } from '@angular/common';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { MatTableModule, MatTableDataSource } from '@angular/material/table';
import { MatSortModule, MatSort } from '@angular/material/sort';
import { MatPaginatorModule, MatPaginator } from '@angular/material/paginator';
import { MatInputModule } from '@angular/material/input';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatChipsModule } from '@angular/material/chips';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MatTooltipModule } from '@angular/material/tooltip';
import { ApiService } from '../../core/services/api.service';
import { Torrent } from '../../shared/models';
import { ConfirmDialogComponent } from './confirm-dialog.component';

@Component({
  selector: 'app-torrents',
  standalone: true,
  imports: [
    DecimalPipe,
    FormsModule,
    MatTableModule,
    MatSortModule,
    MatPaginatorModule,
    MatInputModule,
    MatFormFieldModule,
    MatIconModule,
    MatButtonModule,
    MatChipsModule,
    MatProgressSpinnerModule,
    MatSnackBarModule,
    MatDialogModule,
    MatTooltipModule,
  ],
  templateUrl: './torrents.component.html',
  styleUrl: './torrents.component.scss',
})
export class TorrentsComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly snackBar = inject(MatSnackBar);
  private readonly dialog = inject(MatDialog);
  private readonly destroyRef = inject(DestroyRef);

  readonly sort = viewChild.required(MatSort);
  readonly paginator = viewChild.required(MatPaginator);

  readonly displayedColumns: string[] = ['name', 'state', 'ratio', 'seeding_time', 'type', 'size', 'progress', 'blacklisted', 'actions'];
  readonly dataSource = new MatTableDataSource<Torrent>();
  readonly loading = signal<boolean>(true);
  readonly filterValue = signal<string>('');

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
          this.dataSource.data = torrents;
          this.dataSource.sort = this.sort();
          this.dataSource.paginator = this.paginator();
          this.loading.set(false);
        },
        error: () => {
          this.loading.set(false);
          this.snackBar.open('Failed to load torrents', 'Dismiss', {
            duration: 5000,
            panelClass: ['error-snackbar'],
          });
        },
      });
  }

  applyFilter(event: Event): void {
    const value = (event.target as HTMLInputElement).value;
    this.filterValue.set(value);
    this.dataSource.filter = value.trim().toLowerCase();
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
      const dialogRef = this.dialog.open(ConfirmDialogComponent, {
        data: {
          title: 'Remove from Blacklist',
          message: `Remove "${torrent.name}" from the blacklist?`,
        },
      });

      dialogRef.afterClosed()
        .pipe(takeUntilDestroyed(this.destroyRef))
        .subscribe((confirmed: boolean) => {
          if (confirmed) {
            this.api.removeFromBlacklist(torrent.hash)
              .pipe(takeUntilDestroyed(this.destroyRef))
              .subscribe({
                next: () => {
                  this.snackBar.open('Removed from blacklist', 'OK', { duration: 3000, panelClass: ['success-snackbar'] });
                  this.loadTorrents();
                },
                error: () => this.snackBar.open('Failed to remove from blacklist', 'Dismiss', { duration: 5000, panelClass: ['error-snackbar'] }),
              });
          }
        });
    } else {
      const dialogRef = this.dialog.open(ConfirmDialogComponent, {
        data: {
          title: 'Add to Blacklist',
          message: `Add "${torrent.name}" to the blacklist? It will be protected from cleanup.`,
        },
      });

      dialogRef.afterClosed()
        .pipe(takeUntilDestroyed(this.destroyRef))
        .subscribe((confirmed: boolean) => {
          if (confirmed) {
            this.api.addToBlacklist({ hash: torrent.hash, name: torrent.name, reason: 'Added from web UI' })
              .pipe(takeUntilDestroyed(this.destroyRef))
              .subscribe({
                next: () => {
                  this.snackBar.open('Added to blacklist', 'OK', { duration: 3000, panelClass: ['success-snackbar'] });
                  this.loadTorrents();
                },
                error: () => this.snackBar.open('Failed to add to blacklist', 'Dismiss', { duration: 5000, panelClass: ['error-snackbar'] }),
              });
          }
        });
    }
  }
}
