import { Component, OnInit, inject, signal, DestroyRef } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { interval, switchMap } from 'rxjs';
import { Card } from 'primeng/card';
import { ButtonModule } from 'primeng/button';
import { ProgressSpinner } from 'primeng/progressspinner';
import { ApiService } from '../../core/services/api.service';
import { FileFlowsStatus } from '../../shared/models';

@Component({
  selector: 'app-fileflows',
  standalone: true,
  imports: [
    Card,
    ButtonModule,
    ProgressSpinner,
  ],
  templateUrl: './fileflows.component.html',
  styleUrl: './fileflows.component.scss',
})
export class FileFlowsComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly destroyRef = inject(DestroyRef);

  readonly status = signal<FileFlowsStatus | null>(null);
  readonly loading = signal(true);
  readonly error = signal(false);

  ngOnInit(): void {
    this.loadStatus();
    this.startAutoRefresh();
  }

  private startAutoRefresh(): void {
    interval(15_000).pipe(
      switchMap(() => this.api.getFileFlowsStatus()),
      takeUntilDestroyed(this.destroyRef),
    ).subscribe({
      next: (status: FileFlowsStatus) => {
        this.status.set(status);
        this.error.set(false);
      },
      error: () => this.error.set(true),
    });
  }

  loadStatus(): void {
    this.api.getFileFlowsStatus()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (status: FileFlowsStatus) => {
          this.status.set(status);
          this.loading.set(false);
          this.error.set(false);
        },
        error: () => {
          this.loading.set(false);
          this.error.set(true);
        },
      });
  }

  getFileName(filePath: string): string {
    if (!filePath) return filePath;
    const parts = filePath.replace(/\\/g, '/').split('/');
    return parts[parts.length - 1] || filePath;
  }
}
