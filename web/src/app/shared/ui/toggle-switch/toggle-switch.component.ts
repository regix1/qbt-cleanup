import { Component, input, model } from '@angular/core';
import { FormsModule } from '@angular/forms';

@Component({
  selector: 'app-toggle-switch',
  standalone: true,
  imports: [FormsModule],
  template: `
    <div class="toggle-row">
      <label class="toggle-switch">
        <input type="checkbox"
               [ngModel]="checked()"
               (ngModelChange)="checked.set($event)"
               [disabled]="disabled()">
        <span class="toggle-slider"></span>
      </label>
      <span class="toggle-label">{{ checked() ? enabledText() : disabledText() }}</span>
    </div>
  `,
  styleUrl: './toggle-switch.component.scss',
})
export class ToggleSwitchComponent {
  readonly checked = model<boolean>(false);
  readonly disabled = input<boolean>(false);
  readonly enabledText = input<string>('Enabled');
  readonly disabledText = input<string>('Disabled');
}
