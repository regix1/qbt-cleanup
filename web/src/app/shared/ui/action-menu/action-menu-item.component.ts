import { Component, ViewEncapsulation, input } from '@angular/core';

@Component({
  selector: 'app-action-menu-item',
  standalone: true,
  encapsulation: ViewEncapsulation.None,
  template: `
    <button type="button" class="action-menu-item" [class.danger]="danger()">
      <ng-content></ng-content>
    </button>
  `,
})
export class ActionMenuItemComponent {
  /** When true, applies danger styling (e.g. red text for delete). */
  readonly danger = input<boolean>(false);
}
