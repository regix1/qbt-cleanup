import {
  Component,
  ViewEncapsulation,
  input,
  output,
} from '@angular/core';

@Component({
  selector: 'app-filter-chip',
  standalone: true,
  encapsulation: ViewEncapsulation.None,
  template: `
    <span class="filter-chip">
      {{ label() }}
      <button
        type="button"
        class="chip-dismiss"
        (click)="dismissed.emit()"
        aria-label="Remove filter"
      >
        <i class="fa-solid fa-times"></i>
      </button>
    </span>
  `,
  styleUrls: ['filter-chip.component.scss'],
})
export class FilterChipComponent {
  readonly label = input.required<string>();
  readonly dismissed = output<void>();
}
