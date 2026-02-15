import { Injectable, signal } from '@angular/core';

export interface ToastAction {
  readonly label: string;
  readonly callback: (complete: () => void) => void;
}

export interface ToastMessage {
  readonly id: number;
  readonly severity: 'success' | 'error' | 'info' | 'warn';
  readonly summary: string;
  readonly detail: string;
  readonly action?: ToastAction;
}

@Injectable({ providedIn: 'root' })
export class NotificationService {
  private readonly _toasts = signal<ToastMessage[]>([]);
  readonly toasts = this._toasts.asReadonly();
  private nextId = 0;
  private readonly timers = new Map<number, ReturnType<typeof setTimeout>>();

  success(message: string, action?: ToastAction): void {
    this.add('success', 'Success', message, action ? 15_000 : 3000, action);
  }

  error(message: string): void {
    this.add('error', 'Error', message, 5000);
  }

  info(message: string): void {
    this.add('info', 'Info', message, 3000);
  }

  warn(message: string): void {
    this.add('warn', 'Warning', message, 4000);
  }

  remove(id: number): void {
    this.clearTimer(id);
    this._toasts.update((toasts: ToastMessage[]) => toasts.filter((toast: ToastMessage) => toast.id !== id));
  }

  cancelAutoDismiss(id: number): void {
    this.clearTimer(id);
  }

  private clearTimer(id: number): void {
    const timer = this.timers.get(id);
    if (timer) {
      clearTimeout(timer);
      this.timers.delete(id);
    }
  }

  private add(severity: ToastMessage['severity'], summary: string, detail: string, life: number, action?: ToastAction): void {
    const id = this.nextId++;
    this._toasts.update((toasts: ToastMessage[]) => [...toasts, { id, severity, summary, detail, action }]);
    if (life > 0) {
      this.timers.set(id, setTimeout(() => this.remove(id), life));
    }
  }
}
