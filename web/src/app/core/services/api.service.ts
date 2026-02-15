import { inject, Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import {
  HealthResponse,
  StatusResponse,
  Torrent,
  BlacklistEntry,
  BlacklistAddRequest,
  ActionResponse,
  ConfigResponse,
  ConfigUpdateRequest,
  FileFlowsStatus,
  NotificationTestResponse,
  RecycleBinResponse,
  CategoriesResponse,
  TorrentMoveRequest,
} from '../../shared/models';

@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly baseUrl = '/api';
  private readonly http = inject(HttpClient);

  getHealth(): Observable<HealthResponse> {
    return this.http.get<HealthResponse>(`${this.baseUrl}/health`);
  }

  getStatus(): Observable<StatusResponse> {
    return this.http.get<StatusResponse>(`${this.baseUrl}/status`);
  }

  getTorrents(): Observable<Torrent[]> {
    return this.http.get<Torrent[]>(`${this.baseUrl}/torrents`);
  }

  deleteTorrent(hash: string, deleteFiles: boolean, recycle: boolean = false): Observable<ActionResponse> {
    return this.http.request<ActionResponse>('DELETE', `${this.baseUrl}/torrents`, {
      body: { hash, delete_files: deleteFiles, recycle },
    });
  }

  getBlacklist(): Observable<BlacklistEntry[]> {
    return this.http.get<BlacklistEntry[]>(`${this.baseUrl}/blacklist`);
  }

  addToBlacklist(request: BlacklistAddRequest): Observable<ActionResponse> {
    return this.http.post<ActionResponse>(`${this.baseUrl}/blacklist`, request);
  }

  removeFromBlacklist(hash: string): Observable<ActionResponse> {
    return this.http.delete<ActionResponse>(`${this.baseUrl}/blacklist/${hash}`);
  }

  clearBlacklist(): Observable<ActionResponse> {
    return this.http.delete<ActionResponse>(`${this.baseUrl}/blacklist`);
  }

  getConfig(): Observable<ConfigResponse> {
    return this.http.get<ConfigResponse>(`${this.baseUrl}/config`);
  }

  updateConfig(request: ConfigUpdateRequest): Observable<ActionResponse> {
    return this.http.put<ActionResponse>(`${this.baseUrl}/config`, request);
  }

  runScan(): Observable<ActionResponse> {
    return this.http.post<ActionResponse>(`${this.baseUrl}/actions/scan`, {});
  }

  runOrphanedScan(): Observable<ActionResponse> {
    return this.http.post<ActionResponse>(`${this.baseUrl}/actions/orphaned-scan`, {});
  }

  getFileFlowsStatus(): Observable<FileFlowsStatus> {
    return this.http.get<FileFlowsStatus>(`${this.baseUrl}/fileflows/status`);
  }

  testNotification(): Observable<NotificationTestResponse> {
    return this.http.post<NotificationTestResponse>(`${this.baseUrl}/actions/test-notification`, {});
  }

  getRecycleBin(): Observable<RecycleBinResponse> {
    return this.http.get<RecycleBinResponse>(`${this.baseUrl}/recycle-bin`);
  }

  deleteRecycleBinItem(itemName: string): Observable<ActionResponse> {
    return this.http.delete<ActionResponse>(`${this.baseUrl}/recycle-bin/${encodeURIComponent(itemName)}`);
  }

  restoreRecycleBinItem(itemName: string, targetPath?: string): Observable<ActionResponse> {
    const body = targetPath ? { target_path: targetPath } : {};
    return this.http.post<ActionResponse>(
      `${this.baseUrl}/recycle-bin/${encodeURIComponent(itemName)}/restore`,
      body,
    );
  }

  emptyRecycleBin(): Observable<ActionResponse> {
    return this.http.delete<ActionResponse>(`${this.baseUrl}/recycle-bin`);
  }

  getCategories(): Observable<CategoriesResponse> {
    return this.http.get<CategoriesResponse>(`${this.baseUrl}/torrents/categories`);
  }

  pauseTorrent(hash: string): Observable<ActionResponse> {
    return this.http.post<ActionResponse>(`${this.baseUrl}/torrents/pause`, { hash });
  }

  resumeTorrent(hash: string): Observable<ActionResponse> {
    return this.http.post<ActionResponse>(`${this.baseUrl}/torrents/resume`, { hash });
  }

  moveTorrent(request: TorrentMoveRequest): Observable<ActionResponse> {
    return this.http.post<ActionResponse>(`${this.baseUrl}/torrents/move`, request);
  }
}
