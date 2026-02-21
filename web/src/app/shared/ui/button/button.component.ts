import { Component, ViewEncapsulation, input } from '@angular/core';

@Component({
  selector: 'app-button',
  standalone: true,
  encapsulation: ViewEncapsulation.None,
  template: `
    <button
      type="button"
      [class]="buttonClasses"
      [disabled]="loading()"
    >
      @if (loading()) {
        <i class="fa-solid fa-spinner fa-spin"></i>
      }
      @if (badge() !== undefined && badge()! > 0) {
        <span class="count-badge">{{ badge() }}</span>
      }
      <ng-content></ng-content>
    </button>
  `,
  styleUrls: ['button.component.scss'],
})
export class ButtonComponent {
  readonly variant = input<
    'primary' | 'secondary' | 'danger' | 'text' | 'icon' | 'ghost'
  >('primary');
  readonly size = input<'default' | 'sm'>('default');
  readonly loading = input<boolean>(false);
  readonly badge = input<number | undefined>(undefined);

  get buttonClasses(): string {
    const v = this.variant();
    const sizeClass = this.size() === 'sm' ? ' btn-sm' : '';
    return `btn btn-${v}${sizeClass}`;
  }
}
