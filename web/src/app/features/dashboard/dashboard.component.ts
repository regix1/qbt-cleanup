import { Component, OnInit, inject, signal, DestroyRef } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { interval, switchMap } from 'rxjs';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatDividerModule } from '@angular/material/divider';
import { ApiService } from '../../core/services/api.service';
import { ActionResponse, StatusResponse } from '../../shared/models';

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [
    MatCardModule,
    MatButtonModule,
    MatIconModule,
    MatProgressSpinnerModule,
    MatSnackBarModule,
    MatDividerModule,
  ],
  templateUrl: './dashboard.component.html',
  styleUrl: './dashboard.component.scss',
})
export class DashboardComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly snackBar = inject(MatSnackBar);
  private readonly destroyRef = inject(DestroyRef);

  readonly status = signal<StatusResponse | null>(null);
  readonly loading = signal(true);
  readonly scanning = signal(false);
  readonly orphanScanning = signal(false);

  ngOnInit(): void {
    this.loadStatus();
    this.startAutoRefresh();
  }

  private startAutoRefresh(): void {
    interval(30_000).pipe(
      switchMap(() => this.api.getStatus()),
      takeUntilDestroyed(this.destroyRef),
    ).subscribe((status: StatusResponse) => this.status.set(status));
  }

  loadStatus(): void {
    this.api.getStatus()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (status: StatusResponse) => {
          this.status.set(status);
          this.loading.set(false);
        },
        error: () => {
          this.loading.set(false);
          this.snackBar.open('Failed to load status', 'Dismiss', {
            duration: 5000,
            panelClass: ['error-snackbar'],
          });
        },
      });
  }

  runScan(): void {
    this.scanning.set(true);
    this.api.runScan()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (result: ActionResponse) => {
          this.scanning.set(false);
          this.snackBar.open(result.message, 'OK', {
            duration: 5000,
            panelClass: [result.success ? 'success-snackbar' : 'error-snackbar'],
          });
          setTimeout(() => this.loadStatus(), 2000);
        },
        error: () => {
          this.scanning.set(false);
          this.snackBar.open('Failed to trigger scan', 'Dismiss', {
            duration: 5000,
            panelClass: ['error-snackbar'],
          });
        },
      });
  }

  runOrphanedScan(): void {
    this.orphanScanning.set(true);
    this.api.runOrphanedScan()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (result: ActionResponse) => {
          this.orphanScanning.set(false);
          this.snackBar.open(result.message, 'OK', {
            duration: 5000,
            panelClass: [result.success ? 'success-snackbar' : 'error-snackbar'],
          });
        },
        error: () => {
          this.orphanScanning.set(false);
          this.snackBar.open('Failed to trigger orphaned scan', 'Dismiss', {
            duration: 5000,
            panelClass: ['error-snackbar'],
          });
        },
      });
  }

  formatDate(dateStr: string | null): string {
    if (!dateStr) return 'Never';
    const date = new Date(dateStr);
    return date.toLocaleString();
  }
}
