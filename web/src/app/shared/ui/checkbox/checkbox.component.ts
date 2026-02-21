import { Component, input, output, ViewEncapsulation } from '@angular/core';

@Component({
  selector: 'app-checkbox',
  standalone: true,
  encapsulation: ViewEncapsulation.None,
  template: `
    <div
      class="custom-checkbox"
      [class.checked]="checked()"
      [class.indeterminate]="indeterminate()"
      [attr.aria-checked]="checked() ? 'true' : (indeterminate() ? 'mixed' : 'false')"
      [attr.aria-disabled]="disabled()"
      role="checkbox"
      tabindex="0"
      (click)="onClick($event)"
      (keydown.enter)="onClick($event)"
      (keydown.space)="$event.preventDefault(); onClick($event)">
      @if (checked()) {
        <i class="fa-solid fa-check"></i>
      } @else if (indeterminate()) {
        <i class="fa-solid fa-minus"></i>
      }
    </div>
  `,
  styleUrls: ['checkbox.component.scss'],
})
export class CheckboxComponent {
  readonly checked = input<boolean>(false);
  readonly indeterminate = input<boolean>(false);
  readonly disabled = input<boolean>(false);

  readonly checkedChange = output<boolean>();

  onClick(event: Event): void {
    event.stopPropagation();
    if (this.disabled()) return;
    const next = this.indeterminate() ? true : !this.checked();
    this.checkedChange.emit(next);
  }
}
