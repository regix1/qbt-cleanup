import { Injectable, signal } from '@angular/core';

export interface ConfirmState {
  readonly header: string;
  readonly message: string;
  readonly accept: () => void;
}

@Injectable({ providedIn: 'root' })
export class ConfirmService {
  private readonly _state = signal<ConfirmState | null>(null);
  readonly state = this._state.asReadonly();

  confirm(options: ConfirmState): void {
    this._state.set(options);
  }

  accept(): void {
    const current = this._state();
    if (current) {
      current.accept();
      this._state.set(null);
    }
  }

  reject(): void {
    this._state.set(null);
  }
}
