import { Component, computed, effect, HostListener, inject, signal } from '@angular/core';
import { ConfirmService, SelectOption } from '../../../core/services/confirm.service';

@Component({
  selector: 'app-confirm-dialog',
  standalone: true,
  templateUrl: './confirm-dialog.component.html',
  styleUrl: './confirm-dialog.component.scss',
})
export class ConfirmDialogComponent {
  private readonly confirmService = inject(ConfirmService);

  readonly state = this.confirmService.state;
  readonly inputValue = signal<string>('');
  readonly selectValue = signal<string>('');
  readonly isDropdownOpen = signal<boolean>(false);

  readonly resolvedValue = computed<string>(() => {
    const select = this.selectValue();
    const input = this.inputValue();
    return select || input;
  });

  readonly hasValue = computed<boolean>(() => this.resolvedValue().length > 0);

  readonly selectedOptionLabel = computed<string>(() => {
    const value = this.selectValue();
    const s = this.state();
    if (!value || !s?.selectOptions) {
      return s?.selectPlaceholder ?? 'Select an option...';
    }
    const option = s.selectOptions.find((opt: SelectOption) => opt.value === value);
    return option?.label ?? s.selectPlaceholder ?? 'Select an option...';
  });

  constructor() {
    effect(() => {
      const s = this.state();
      this.inputValue.set(s?.inputDefault ?? '');
      this.selectValue.set('');
      this.isDropdownOpen.set(false);
    });
  }

  @HostListener('document:click', ['$event'])
  onDocumentClick(event: Event): void {
    const target = event.target as HTMLElement;
    if (!target.closest('.confirm-dropdown')) {
      this.isDropdownOpen.set(false);
    }
  }

  onInputChange(event: Event): void {
    this.inputValue.set((event.target as HTMLInputElement).value);
    if ((event.target as HTMLInputElement).value) {
      this.selectValue.set('');
    }
  }

  toggleDropdown(): void {
    this.isDropdownOpen.update((open: boolean) => !open);
  }

  selectOption(option: SelectOption): void {
    this.selectValue.set(option.value);
    this.inputValue.set('');
    this.isDropdownOpen.set(false);
  }

  accept(): void {
    this.confirmService.accept(this.resolvedValue());
  }

  reject(): void {
    this.confirmService.reject();
  }
}
