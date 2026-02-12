import { Component, input } from '@angular/core';

@Component({
  selector: 'app-loading-container',
  standalone: true,
  template: `
    <div class="loading-container">
      <div class="spinner" [class.spinner-sm]="size() === 'sm'" [class.spinner-lg]="size() === 'lg'"></div>
    </div>
  `,
})
export class LoadingContainerComponent {
  readonly size = input<'sm' | 'md' | 'lg'>('md');
}
