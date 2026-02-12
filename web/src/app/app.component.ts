import { Component, inject, signal } from '@angular/core';
import { RouterOutlet, RouterLink, RouterLinkActive } from '@angular/router';
import { toSignal } from '@angular/core/rxjs-interop';
import { map, catchError, of } from 'rxjs';
import { Toast } from 'primeng/toast';
import { ConfirmDialog } from 'primeng/confirmdialog';
import { ButtonModule } from 'primeng/button';
import { Toolbar } from 'primeng/toolbar';
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
    Toast,
    ConfirmDialog,
    ButtonModule,
    Toolbar,
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
    { path: '/', label: 'Dashboard', icon: 'pi pi-home' },
    { path: '/torrents', label: 'Torrents', icon: 'pi pi-download' },
    { path: '/blacklist', label: 'Blacklist', icon: 'pi pi-ban' },
    { path: '/config', label: 'Config', icon: 'pi pi-cog' },
    { path: '/fileflows', label: 'FileFlows', icon: 'pi pi-sync' },
  ] as const;

  toggleSidenav(): void {
    this.sidenavOpen.update((open) => !open);
  }
}
