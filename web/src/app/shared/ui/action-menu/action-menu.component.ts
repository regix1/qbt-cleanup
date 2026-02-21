import {
  Component,
  ElementRef,
  ViewEncapsulation,
  input,
  output,
  HostListener,
} from '@angular/core';
import { OverlayModule, type ConnectedPosition } from '@angular/cdk/overlay';

const ACTION_MENU_POSITIONS: ConnectedPosition[] = [
  { originX: 'start', originY: 'bottom', overlayX: 'start', overlayY: 'top', offsetY: 4 },
  { originX: 'end', originY: 'bottom', overlayX: 'end', overlayY: 'top', offsetY: 4 },
  { originX: 'start', originY: 'top', overlayX: 'start', overlayY: 'bottom', offsetY: -4 },
  { originX: 'end', originY: 'top', overlayX: 'end', overlayY: 'bottom', offsetY: -4 },
];

@Component({
  selector: 'app-action-menu',
  standalone: true,
  imports: [OverlayModule],
  encapsulation: ViewEncapsulation.None,
  styleUrls: ['action-menu.component.scss'],
  template: `
    <ng-template
      cdkConnectedOverlay
      [cdkConnectedOverlayOrigin]="triggerOrigin()"
      [cdkConnectedOverlayOpen]="isOpen()"
      [cdkConnectedOverlayPositions]="positions"
      [cdkConnectedOverlayWidth]="220"
      cdkConnectedOverlayPanelClass="action-menu-pane"
      [cdkConnectedOverlayHasBackdrop]="true"
      cdkConnectedOverlayBackdropClass="action-menu-backdrop"
      (backdropClick)="closed.emit()"
      (overlayOutsideClick)="closed.emit()"
      (detach)="closed.emit()"
    >
      <div class="action-menu">
        <ng-content></ng-content>
      </div>
    </ng-template>
  `,
})
export class ActionMenuComponent {
  /** Whether the overlay is open. */
  readonly isOpen = input.required<boolean>();
  /** Reference to the trigger element (pass ElementRef<HTMLElement> from a template #triggerRef). */
  readonly triggerOrigin = input.required<ElementRef<HTMLElement>>();
  /** Emitted when the overlay closes (backdrop click, Escape, or detach). */
  readonly closed = output<void>();

  protected readonly positions: ConnectedPosition[] = ACTION_MENU_POSITIONS;

  @HostListener('document:keydown.escape')
  onEscape(): void {
    if (this.isOpen()) {
      this.closed.emit();
    }
  }
}
