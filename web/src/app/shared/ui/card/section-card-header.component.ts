import { Component, ViewEncapsulation } from '@angular/core';

@Component({
  selector: 'app-section-card-header',
  standalone: true,
  encapsulation: ViewEncapsulation.None,
  template: `
    <div class="card-header-content">
      <ng-content></ng-content>
    </div>
  `,
  styleUrls: ['section-card-header.component.scss'],
  host: {
    '[attr.cardheader]': '""',
  },
})
export class SectionCardHeaderComponent {}
