import { Component, ViewEncapsulation, input } from '@angular/core';

@Component({
  selector: 'app-badge',
  standalone: true,
  encapsulation: ViewEncapsulation.None,
  template: `
    <span class="badge" [class]="'badge-' + variant()">{{ label() }}</span>
  `,
  styleUrls: ['badge.component.scss'],
})
export class BadgeComponent {
  /** Variant for styling: state-*, type-*, status-*, modified, unregistered */
  readonly variant = input<string>('status-inactive');
  readonly label = input<string>('');
}
