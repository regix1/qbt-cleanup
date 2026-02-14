import { Routes } from '@angular/router';

export const routes: Routes = [
  { path: '', loadComponent: () => import('./features/dashboard/dashboard.component').then((m) => m.DashboardComponent) },
  { path: 'torrents', loadComponent: () => import('./features/torrents/torrents.component').then((m) => m.TorrentsComponent) },
  { path: 'blacklist', loadComponent: () => import('./features/blacklist/blacklist.component').then((m) => m.BlacklistComponent) },
  { path: 'config', loadComponent: () => import('./features/config/config.component').then((m) => m.ConfigComponent) },
  { path: 'fileflows', loadComponent: () => import('./features/fileflows/fileflows.component').then((m) => m.FileFlowsComponent) },
  { path: 'recycle-bin', loadComponent: () => import('./features/recycle-bin/recycle-bin.component').then((m) => m.RecycleBinComponent) },
  { path: '**', redirectTo: '' },
];
