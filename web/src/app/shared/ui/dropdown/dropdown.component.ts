import {
  Component,
  ElementRef,
  EventEmitter,
  HostListener,
  Input,
  Output,
  ViewChild,
  ViewEncapsulation,
} from '@angular/core';

@Component({
  selector: 'app-dropdown',
  standalone: true,
  template: `
    <div
      class="custom-dropdown"
      (click)="$event.stopPropagation()"
      [class.open]="isOpen"
    >
      <div class="dropdown-trigger-wrapper" [class.open]="isOpen">
        <ng-content select="[dropdownTrigger]"></ng-content>
      </div>
      @if (isOpen) {
        <div
          #dropdownPanel
          class="dropdown-panel"
          role="listbox"
        >
          <ng-content select="[dropdownOptions]"></ng-content>
        </div>
      }
    </div>
  `,
  styleUrls: ['dropdown.component.scss'],
  encapsulation: ViewEncapsulation.None,
})
export class DropdownComponent {
  @Input() isOpen = false;

  /** Optional value indicating which option is selected (for parent to use when projecting options). */
  @Input() selected?: unknown;

  @Output() isOpenChange = new EventEmitter<boolean>();

  @ViewChild('dropdownPanel') panelRef?: ElementRef<HTMLElement>;

  constructor(private readonly host: ElementRef<HTMLElement>) {}

  @HostListener('document:click', ['$event'])
  onDocumentClick(event: MouseEvent): void {
    if (!this.isOpen) return;
    const target = event.target as Node;
    if (target && !this.host.nativeElement.contains(target)) {
      this.isOpenChange.emit(false);
    }
  }

  @HostListener('document:keydown.escape')
  onEscape(): void {
    if (this.isOpen) {
      this.isOpenChange.emit(false);
    }
  }

  @HostListener('window:scroll', ['$event'])
  onScroll(event: Event): void {
    if (!this.isOpen) return;
    const target = event.target as Node;
    const panel = this.panelRef?.nativeElement;
    if (panel && target && !panel.contains(target)) {
      this.isOpenChange.emit(false);
    }
  }
}
