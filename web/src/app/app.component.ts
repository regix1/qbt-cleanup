import { Component, computed, inject, signal } from '@angular/core';
import { RouterOutlet, RouterLink, RouterLinkActive } from '@angular/router';
import { toSignal } from '@angular/core/rxjs-interop';
import { MatSidenavModule } from '@angular/material/sidenav';
import { MatToolbarModule } from '@angular/material/toolbar';
import { MatListModule } from '@angular/material/list';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { map, catchError, of } from 'rxjs';
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
    MatSidenavModule,
    MatToolbarModule,
    MatListModule,
    MatIconModule,
    MatButtonModule,
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
    { path: '/', label: 'Dashboard', icon: 'dashboard' },
    { path: '/torrents', label: 'Torrents', icon: 'download' },
    { path: '/blacklist', label: 'Blacklist', icon: 'block' },
    { path: '/config', label: 'Config', icon: 'settings' },
    { path: '/fileflows', label: 'FileFlows', icon: 'sync' },
  ] as const;

  toggleSidenav(): void {
    this.sidenavOpen.update((open) => !open);
  }
}
