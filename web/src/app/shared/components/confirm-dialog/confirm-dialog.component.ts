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
  readonly selectValue = signal('');

  readonly resolvedValue = computed<string>(() => {
    const select = this.selectValue();
    const input = this.inputValue();
    return select || input;
  });

  readonly hasValue = computed<boolean>(() => this.resolvedValue().length > 0);

  constructor() {
    effect(() => {
      const s = this.state();
      this.inputValue.set(s?.inputDefault ?? '');
      this.selectValue.set('');
    });
  }

  onInputChange(event: Event): void {
    this.inputValue.set((event.target as HTMLInputElement).value);
    if ((event.target as HTMLInputElement).value) {
      this.selectValue.set('');
    }
  }

  onSelectChange(event: Event): void {
    const value = (event.target as HTMLSelectElement).value;
    this.selectValue.set(value);
    if (value) {
      this.inputValue.set('');
    }
  }

  accept(): void {
    this.confirmService.accept(this.resolvedValue());
  }

  reject(): void {
    this.confirmService.reject();
  }
}
