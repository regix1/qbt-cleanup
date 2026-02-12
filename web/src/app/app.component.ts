import { Component, inject, signal } from '@angular/core';
import { RouterOutlet, RouterLink, RouterLinkActive } from '@angular/router';
import { toSignal } from '@angular/core/rxjs-interop';
import { map, catchError, of } from 'rxjs';
import { ToastComponent } from './shared/components/toast/toast.component';
import { ConfirmDialogComponent } from './shared/components/confirm-dialog/confirm-dialog.component';
import { ApiService } from './core/services/api.service';

interface NavItem {
  readonly path: string;
  readonly label: string;
  readonly icon: string;
}

@Component({
  selector: 'app-root',
  imports: [
    RouterOutlet,
    RouterLink,
    RouterLinkActive,
    ToastComponent,
    ConfirmDialogComponent,
  ],
  templateUrl: './app.component.html',
  styleUrl: './app.component.scss',
})
export class AppComponent {
  private readonly api = inject(ApiService);

  readonly sidenavOpen = signal(true);

  readonly version = toSignal(
    this.api.getHealth().pipe(
      map((health) => health.version),
      catchError(() => of('unknown'))
    ),
    { initialValue: '' }
  );

  readonly navItems: readonly NavItem[] = [
    { path: '/', label: 'Dashboard', icon: 'fa-solid fa-house' },
    { path: '/torrents', label: 'Torrents', icon: 'fa-solid fa-download' },
    { path: '/blacklist', label: 'Blacklist', icon: 'fa-solid fa-ban' },
    { path: '/config', label: 'Config', icon: 'fa-solid fa-gear' },
    { path: '/fileflows', label: 'FileFlows', icon: 'fa-solid fa-rotate' },
  ] as const;

  toggleSidenav(): void {
    this.sidenavOpen.update((open: boolean) => !open);
  }

  closeSidenavOnMobile(): void {
    if (window.innerWidth <= 768) {
      this.sidenavOpen.set(false);
    }
  }
}
