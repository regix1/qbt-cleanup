import { Component, computed, effect, inject, signal } from '@angular/core';
import { ConfirmService } from '../../../core/services/confirm.service';

@Component({
  selector: 'app-confirm-dialog',
  standalone: true,
  templateUrl: './confirm-dialog.component.html',
  styleUrl: './confirm-dialog.component.scss',
})
export class ConfirmDialogComponent {
  private readonly confirmService = inject(ConfirmService);

  readonly state = this.confirmService.state;
  readonly inputValue = signal('');

  constructor() {
    effect(() => {
      const s = this.state();
      this.inputValue.set(s?.inputDefault ?? '');
    });
  }

  onInputChange(event: Event): void {
    this.inputValue.set((event.target as HTMLInputElement).value);
  }

  accept(): void {
    this.confirmService.accept(this.inputValue());
  }

  reject(): void {
    this.confirmService.reject();
  }
}
