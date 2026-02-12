import { Component, inject } from '@angular/core';
import { NotificationService, ToastMessage } from '../../../core/services/notification.service';

@Component({
  selector: 'app-toast',
  templateUrl: './toast.component.html',
  styleUrl: './toast.component.scss',
})
export class ToastComponent {
  private readonly notificationService = inject(NotificationService);

  readonly toasts = this.notificationService.toasts;

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

  dismiss(id: number): void {
    this.notificationService.remove(id);
  }

  trackById(_index: number, toast: ToastMessage): number {
    return toast.id;
  }
}
