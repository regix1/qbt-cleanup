export interface HealthResponse {
  status: string;
  version: string;
  uptime_seconds: number;
}

export interface StatusResponse {
  version: string;
  state_enabled: boolean;
  db_path: string;
  torrent_count: number;
  blacklist_count: number;
  stalled_count: number;
  unregistered_count: number;
  private_count: number;
  public_count: number;
  last_run_time: string | null;
  last_run_success: boolean | null;
  last_run_stats: LastRunStats | null;
  scheduler_running: boolean;
  schedule_hours: number;
  dry_run: boolean;
  delete_files: boolean;
}

export interface LastRunStats {
  total_checked: number;
  total_removed: number;
  private_removed: number;
  public_removed: number;
  stalled_removed: number;
  blacklisted_skipped: number;
  errors: number;
}

export interface Torrent {
  hash: string;
  name: string;
  state: string;
  ratio: number;
  seeding_time: number;
  is_private: boolean;
  is_paused: boolean;
  is_downloading: boolean;
  is_stalled: boolean;
  is_blacklisted: boolean;
  is_unregistered: boolean;
  size: number;
  progress: number;
  category: string;
  tracker: string;
  added_on: number;
  save_path: string;
}

export interface BlacklistEntry {
  hash: string;
  name: string;
  added_at: string;
  reason: string;
}

export interface BlacklistAddRequest {
  hash: string;
  name?: string;
  reason?: string;
}

export interface ActionResponse {
  success: boolean;
  message: string;
}

export type ConfigSectionValues = Record<string, string | number | boolean>;

export interface ConfigResponse {
  connection: ConfigSectionValues;
  limits: ConfigSectionValues;
  behavior: ConfigSectionValues;
  schedule: ConfigSectionValues;
  fileflows: ConfigSectionValues;
  orphaned: ConfigSectionValues;
  notifications: ConfigSectionValues;
  recycle_bin: ConfigSectionValues;
  web: ConfigSectionValues;
  [section: string]: ConfigSectionValues;
}

export interface ConfigUpdateRequest {
  overrides: Record<string, ConfigSectionValues>;
}

export interface FileFlowsProcessingFile {
  name: string;
  relativePath: string;
}

export interface FileFlowsStatus {
  enabled: boolean;
  connected: boolean;
  processing: number;
  queue: number;
  processing_files: FileFlowsProcessingFile[];
}

export interface NotificationTestResponse {
  success: boolean;
  message: string;
  services_notified: number;
}

export interface RecycleBinItem {
  name: string;
  path: string;
  size: number;
  is_dir: boolean;
  modified_time: number;
  age_days: number;
}

export interface RecycleBinResponse {
  enabled: boolean;
  path: string;
  items: RecycleBinItem[];
  total_size: number;
  purge_after_days: number;
}
