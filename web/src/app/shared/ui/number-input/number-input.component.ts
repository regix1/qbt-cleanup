import { Component, input, model } from '@angular/core';
import { FormsModule } from '@angular/forms';

@Component({
  selector: 'app-number-input',
  standalone: true,
  imports: [FormsModule],
  templateUrl: './number-input.component.html',
  styleUrl: './number-input.component.scss',
})
export class NumberInputComponent {
  readonly value = model<number>(0);
  readonly step = input<number>(1);
  readonly min = input<number | null>(null);
  readonly max = input<number | null>(null);

  decrement(): void {
    const next = +this.value() - this.step();
    const minVal = this.min();
    this.value.set(minVal !== null ? Math.max(minVal, next) : next);
  }

  increment(): void {
    const next = +this.value() + this.step();
    const maxVal = this.max();
    this.value.set(maxVal !== null ? Math.min(maxVal, next) : next);
  }
}
