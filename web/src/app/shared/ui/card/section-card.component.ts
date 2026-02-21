import { Component, ViewEncapsulation } from '@angular/core';

@Component({
  selector: 'app-section-card',
  standalone: true,
  encapsulation: ViewEncapsulation.None,
  template: `
    <div class="section-card">
      <ng-content select="[cardheader]"></ng-content>
      <ng-content></ng-content>
    </div>
  `,
  styleUrls: ['section-card.component.scss'],
})
export class SectionCardComponent {}
