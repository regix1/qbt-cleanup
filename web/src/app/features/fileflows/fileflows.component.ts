import { ChangeDetectionStrategy, Component, OnInit, inject, signal, DestroyRef } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { interval, switchMap } from 'rxjs';
import { ApiService } from '../../core/services/api.service';
import { LoadingContainerComponent } from '../../shared/ui/loading-container/loading-container.component';
import { FileFlowsStatus, FileFlowsProcessingFile } from '../../shared/models';

@Component({
  selector: 'app-fileflows',
  standalone: true,
  imports: [LoadingContainerComponent],
  templateUrl: './fileflows.component.html',
  styleUrl: './fileflows.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
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

  getFileName(file: FileFlowsProcessingFile): string {
    const fullPath = file.name || file.relativePath || '';
    if (!fullPath) return 'Unknown file';
    const parts = fullPath.replace(/\\/g, '/').split('/');
    return parts[parts.length - 1] || fullPath;
  }

  getFilePath(file: FileFlowsProcessingFile): string {
    return file.name || file.relativePath || '';
  }
}
