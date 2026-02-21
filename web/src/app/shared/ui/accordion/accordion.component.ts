import {
  Component,
  ViewEncapsulation,
  input,
  output,
} from '@angular/core';

@Component({
  selector: 'app-accordion',
  standalone: true,
  encapsulation: ViewEncapsulation.None,
  template: `
    <div
      class="accordion-panel"
      [class.accordion-panel-open]="expanded()"
    >
      <div
        class="accordion-header"
        (click)="toggle()"
        (keydown.enter)="onKeydown($event)"
        (keydown.space)="onKeydown($event)"
        role="button"
        [attr.aria-expanded]="expanded()"
        [attr.aria-controls]="contentId"
        tabindex="0"
      >
        @if (icon()) {
          <i [class]="icon()" class="section-icon"></i>
        }
        <span class="section-name">{{ title() }}</span>
        <i class="fa-solid fa-chevron-down accordion-chevron" aria-hidden="true"></i>
      </div>
      @if (expanded()) {
        <div class="accordion-content" [id]="contentId">
          <ng-content></ng-content>
        </div>
      }
    </div>
  `,
  styleUrls: ['accordion.component.scss'],
})
export class AccordionComponent {
  readonly title = input<string>('');
  readonly icon = input<string>('');
  readonly expanded = input<boolean>(false);

  readonly expandedChange = output<boolean>();

  readonly contentId = `accordion-content-${Math.random().toString(36).slice(2, 10)}`;

  toggle(): void {
    this.expandedChange.emit(!this.expanded());
  }

  onKeydown(event: Event): void {
    const e = event as KeyboardEvent;
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      this.toggle();
    }
  }
}
