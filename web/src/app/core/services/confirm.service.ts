import { Injectable, signal } from '@angular/core';

export interface SelectOption {
  readonly label: string;
  readonly value: string;
  readonly description?: string;
}

export interface ConfirmState {
  readonly header: string;
  readonly message: string;
  readonly accept: (inputValue?: string) => void;
  readonly inputPlaceholder?: string;
  readonly inputDefault?: string;
  readonly selectOptions?: SelectOption[];
  readonly selectPlaceholder?: string;
}

@Injectable({ providedIn: 'root' })
export class ConfirmService {
  private readonly _state = signal<ConfirmState | null>(null);
  readonly state = this._state.asReadonly();

  confirm(options: ConfirmState): void {
    this._state.set(options);
  }

  accept(inputValue?: string): void {
    const current = this._state();
    if (current) {
      current.accept(inputValue);
      this._state.set(null);
    }
  }

  reject(): void {
    this._state.set(null);
  }
}
