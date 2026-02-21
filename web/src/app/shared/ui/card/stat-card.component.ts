import { Component, ViewEncapsulation, input } from '@angular/core';

@Component({
  selector: 'app-stat-card',
  standalone: true,
  encapsulation: ViewEncapsulation.None,
  template: `
    <div
      class="stat-card"
      [class.stat-card-sm]="size() === 'sm'"
      [class.stat-card-md]="size() === 'md'"
      [class.stat-card-lg]="size() === 'lg'"
    >
      @if (icon()) {
        <span class="stat-icon"><i [class]="icon()"></i></span>
      }
      <span class="stat-value">{{ value() }}</span>
      <span class="stat-label">{{ label() }}</span>
    </div>
  `,
  styleUrls: ['stat-card.component.scss'],
})
export class StatCardComponent {
  readonly value = input<string | number>('');
  readonly label = input<string>('');
  readonly icon = input<string>('');
  readonly size = input<'sm' | 'md' | 'lg'>('md');
}
