import { Component, OnInit, inject, signal, DestroyRef } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { interval, switchMap } from 'rxjs';
import { Card } from 'primeng/card';
import { ButtonModule } from 'primeng/button';
import { ProgressSpinner } from 'primeng/progressspinner';
import { Divider } from 'primeng/divider';
import { ApiService } from '../../core/services/api.service';
import { NotificationService } from '../../core/services/notification.service';
import { ActionResponse, StatusResponse } from '../../shared/models';

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [
    Card,
    ButtonModule,
    ProgressSpinner,
    Divider,
  ],
  templateUrl: './dashboard.component.html',
  styleUrl: './dashboard.component.scss',
})
export class DashboardComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly notifications = inject(NotificationService);
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
          this.notifications.error('Failed to load status');
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
          if (result.success) {
            this.notifications.success(result.message);
          } else {
            this.notifications.error(result.message);
          }
          setTimeout(() => this.loadStatus(), 2000);
        },
        error: () => {
          this.scanning.set(false);
          this.notifications.error('Failed to trigger scan');
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
          if (result.success) {
            this.notifications.success(result.message);
          } else {
            this.notifications.error(result.message);
          }
        },
        error: () => {
          this.orphanScanning.set(false);
          this.notifications.error('Failed to trigger orphaned scan');
        },
      });
  }

  formatDate(dateStr: string | null): string {
    if (!dateStr) return 'Never';
    const date = new Date(dateStr);
    return date.toLocaleString();
  }
}
