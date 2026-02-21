import {
  Component,
  ViewEncapsulation,
  input,
  output,
} from '@angular/core';

@Component({
  selector: 'app-search-input',
  standalone: true,
  encapsulation: ViewEncapsulation.None,
  template: `
    <div class="search-field">
      <i class="fa-solid fa-magnifying-glass"></i>
      <input
        class="form-input"
        [value]="value()"
        (input)="valueChange.emit($any($event.target).value)"
        [placeholder]="placeholder()"
      />
    </div>
  `,
  styleUrls: ['search-input.component.scss'],
})
export class SearchInputComponent {
  readonly placeholder = input<string>('');
  readonly value = input<string>('');
  readonly valueChange = output<string>();
}
