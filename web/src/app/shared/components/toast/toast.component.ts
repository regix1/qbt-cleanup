import { Component, inject, signal } from '@angular/core';
import { NotificationService, ToastMessage } from '../../../core/services/notification.service';

@Component({
  selector: 'app-toast',
  standalone: true,
  templateUrl: './toast.component.html',
  styleUrl: './toast.component.scss',
})
export class ToastComponent {
  private readonly notificationService = inject(NotificationService);

  readonly toasts = this.notificationService.toasts;
  readonly processingIds = signal<Set<number>>(new Set());

  getIcon(severity: ToastMessage['severity']): string {
    switch (severity) {
      case 'success':
        return 'fa-solid fa-circle-check';
      case 'error':
        return 'fa-solid fa-circle-xmark';
      case 'info':
        return 'fa-solid fa-circle-info';
      case 'warn':
        return 'fa-solid fa-triangle-exclamation';
    }
  }

  isProcessing(id: number): boolean {
    return this.processingIds().has(id);
  }

  onAction(toast: ToastMessage): void {
    if (!toast.action || this.isProcessing(toast.id)) return;

    this.processingIds.update((ids: Set<number>) => {
      const next = new Set(ids);
      next.add(toast.id);
      return next;
    });

    toast.action.callback(() => {
      this.processingIds.update((ids: Set<number>) => {
        const next = new Set(ids);
        next.delete(toast.id);
        return next;
      });
      this.notificationService.remove(toast.id);
    });
  }

  dismiss(id: number): void {
    this.processingIds.update((ids: Set<number>) => {
      const next = new Set(ids);
      next.delete(id);
      return next;
    });
    this.notificationService.remove(id);
  }

  trackById(_index: number, toast: ToastMessage): number {
    return toast.id;
  }
}
