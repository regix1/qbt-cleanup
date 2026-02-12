import { Component, model, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

@Component({
  selector: 'app-password-input',
  standalone: true,
  imports: [FormsModule],
  template: `
    <div class="password-input-wrapper">
      <input class="form-input"
             [type]="visible() ? 'text' : 'password'"
             [ngModel]="value()"
             (ngModelChange)="value.set($event)">
      <button class="password-toggle" type="button" (click)="visible.set(!visible())">
        <i [class]="visible() ? 'fa-solid fa-eye-slash' : 'fa-solid fa-eye'"></i>
      </button>
    </div>
  `,
  styleUrl: './password-input.component.scss',
})
export class PasswordInputComponent {
  readonly value = model<string>('');
  readonly visible = signal(false);
}
