import { Component, ViewEncapsulation, input } from '@angular/core';

@Component({
  selector: 'app-empty-state',
  standalone: true,
  encapsulation: ViewEncapsulation.None,
  template: `
    <div
      class="empty-state empty-state-global"
      [class.empty-state-error]="variant() === 'error'"
    >
      @if (icon()) {
        <i [class]="icon()" [class.error-icon]="variant() === 'error'"></i>
      }
      @if (title()) {
        <h3>{{ title() }}</h3>
      }
      @if (message()) {
        <p>{{ message() }}</p>
      }
      <ng-content></ng-content>
    </div>
  `,
  styleUrls: ['empty-state.component.scss'],
})
export class EmptyStateComponent {
  readonly icon = input<string>('');
  readonly title = input<string>('');
  readonly message = input<string>('');
  readonly variant = input<'empty' | 'error'>('empty');
}
