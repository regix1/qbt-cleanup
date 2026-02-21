import {
  Component,
  ViewEncapsulation,
  input,
  output,
  computed,
} from '@angular/core';

@Component({
  selector: 'app-pagination',
  standalone: true,
  encapsulation: ViewEncapsulation.None,
  template: `
    <div class="pagination-bar">
      <div class="pagination-info page-info">
        {{ rangeText() }}
      </div>
      <div class="pagination-controls">
        <button
          type="button"
          class="btn btn-secondary btn-sm"
          [disabled]="currentPage() <= 1"
          (click)="goTo(currentPage() - 1)"
          aria-label="Previous page"
        >
          Prev
        </button>
        <span class="page-info" aria-current="page" aria-label="Page {{ currentPage() }} of {{ totalPages() }}">
          {{ currentPage() }} / {{ totalPages() }}
        </span>
        <button
          type="button"
          class="btn btn-secondary btn-sm"
          [disabled]="currentPage() >= totalPages()"
          (click)="goTo(currentPage() + 1)"
          aria-label="Next page"
        >
          Next
        </button>
      </div>
    </div>
  `,
  styleUrls: ['pagination.component.scss'],
})
export class PaginationComponent {
  readonly currentPage = input<number>(1);
  readonly totalPages = input<number>(1);
  readonly totalItems = input<number>(0);
  readonly pageSize = input<number>(10);

  readonly pageChange = output<number>();

  readonly rangeText = computed(() => {
    const total = this.totalItems();
    if (total === 0) return 'Showing 0–0 of 0';
    const size = this.pageSize();
    const page = this.currentPage();
    const start = (page - 1) * size + 1;
    const end = Math.min(page * size, total);
    return `Showing ${start}–${end} of ${total}`;
  });

  goTo(page: number): void {
    if (page >= 1 && page <= this.totalPages()) {
      this.pageChange.emit(page);
    }
  }
}
