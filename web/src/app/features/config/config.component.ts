import { Component, computed, DestroyRef, inject, OnInit, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ApiService } from '../../core/services/api.service';
import { ConfigResponse, ConfigSectionValues } from '../../shared/models';
import { NotificationService } from '../../core/services/notification.service';
import { LoadingContainerComponent } from '../../shared/ui/loading-container/loading-container.component';
import { ToggleSwitchComponent } from '../../shared/ui/toggle-switch/toggle-switch.component';
import { NumberInputComponent } from '../../shared/ui/number-input/number-input.component';
import { PasswordInputComponent } from '../../shared/ui/password-input/password-input.component';

interface ConfigField {
  key: string;
  value: string | number | boolean;
  type: 'string' | 'number' | 'boolean';
  editValue: string | number | boolean;
  modified: boolean;
}

interface ConfigSection {
  name: string;
  icon: string;
  key: string;
  fields: ConfigField[];
  expanded: boolean;
}

interface SectionMeta {
  name: string;
  icon: string;
}

@Component({
  selector: 'app-config',
  standalone: true,
  imports: [
    FormsModule,
    LoadingContainerComponent,
    ToggleSwitchComponent,
    NumberInputComponent,
    PasswordInputComponent,
  ],
  templateUrl: './config.component.html',
  styleUrl: './config.component.scss',
})
export class ConfigComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly notify = inject(NotificationService);
  private readonly destroyRef = inject(DestroyRef);

  readonly sections = signal<ConfigSection[]>([]);
  readonly loading = signal(true);
  readonly saving = signal(false);
  readonly hasModifications = computed(() =>
    this.sections().some((section: ConfigSection) =>
      section.fields.some((field: ConfigField) => field.modified)
    )
  );

  private readonly fieldDescriptions: Readonly<Record<string, Record<string, string>>> = {
    connection: {
      host: 'qBittorrent WebUI hostname or IP address',
      port: 'qBittorrent WebUI port number',
      username: 'qBittorrent login username',
      password: 'qBittorrent login password',
      verify_ssl: 'Verify SSL certificate when connecting',
    },
    limits: {
      fallback_ratio: 'Default ratio limit if not set per tracker type',
      fallback_days: 'Default seeding days if not set per tracker type',
      private_ratio: 'Ratio limit for private tracker torrents',
      private_days: 'Max seeding days for private tracker torrents',
      public_ratio: 'Ratio limit for public tracker torrents',
      public_days: 'Max seeding days for public tracker torrents',
      ignore_qbt_ratio_private: 'Ignore qBittorrent ratio limits for private torrents',
      ignore_qbt_ratio_public: 'Ignore qBittorrent ratio limits for public torrents',
      ignore_qbt_time_private: 'Ignore qBittorrent time limits for private torrents',
      ignore_qbt_time_public: 'Ignore qBittorrent time limits for public torrents',
    },
    behavior: {
      delete_files: 'Delete files from disk when removing torrents',
      dry_run: 'Log actions without actually deleting anything',
      schedule_hours: 'Hours between automatic cleanup runs',
      run_once: 'Run a single cleanup cycle and exit',
      check_paused_only: 'Only delete torrents that qBittorrent has paused',
      check_private_paused_only: 'Only delete paused private torrents',
      check_public_paused_only: 'Only delete paused public torrents',
      force_delete_after_hours: 'Force delete after criteria met for this many hours',
      force_delete_private_after_hours: 'Force delete threshold for private torrents',
      force_delete_public_after_hours: 'Force delete threshold for public torrents',
      cleanup_stale_downloads: 'Enable cleanup of stalled downloads',
      max_stalled_days: 'Max days a download can be stalled before removal',
      max_stalled_private_days: 'Max stalled days for private torrents',
      max_stalled_public_days: 'Max stalled days for public torrents',
    },
    orphaned: {
      enabled: 'Enable orphaned file cleanup',
      scan_dirs: 'Directories to scan for orphaned files (comma-separated)',
      min_age_hours: 'Minimum file age in hours before removal',
      schedule_days: 'Days between orphaned cleanup runs',
    },
    fileflows: {
      enabled: 'Enable FileFlows processing protection',
      host: 'FileFlows server hostname or IP address',
      port: 'FileFlows server port number',
      timeout: 'API timeout in seconds',
    },
  };

  private readonly sectionMeta: Readonly<Record<string, SectionMeta>> = {
    connection: { name: 'Connection', icon: 'fa-solid fa-link' },
    limits: { name: 'Limits', icon: 'fa-solid fa-sliders' },
    behavior: { name: 'Behavior', icon: 'fa-solid fa-gear' },
    schedule: { name: 'Schedule', icon: 'fa-solid fa-clock' },
    fileflows: { name: 'FileFlows', icon: 'fa-solid fa-arrows-rotate' },
    orphaned: { name: 'Orphaned', icon: 'fa-solid fa-folder' },
    web: { name: 'Web', icon: 'fa-solid fa-globe' },
  };

  ngOnInit(): void {
    this.loadConfig();
  }

  loadConfig(): void {
    this.loading.set(true);
    this.api.getConfig()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (config: ConfigResponse) => {
          this.buildSections(config);
          this.loading.set(false);
        },
        error: () => {
          this.loading.set(false);
          this.notify.error('Failed to load configuration');
        },
      });
  }

  saveConfig(): void {
    const overrides = this.getModifiedFields();
    if (Object.keys(overrides).length === 0) {
      this.notify.info('No changes to save');
      return;
    }

    this.saving.set(true);
    this.api.updateConfig({ overrides })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (result) => {
          this.saving.set(false);
          result.success ? this.notify.success(result.message) : this.notify.error(result.message);
          if (result.success) {
            this.loadConfig();
          }
        },
        error: () => {
          this.saving.set(false);
          this.notify.error('Failed to save configuration');
        },
      });
  }

  toggleSection(section: ConfigSection): void {
    section.expanded = !section.expanded;
  }

  onFieldChange(_section: ConfigSection, field: ConfigField): void {
    field.modified = field.editValue !== field.value;
    this.sections.update((sections: ConfigSection[]) => [...sections]);
  }

  sectionHasModifications(section: ConfigSection): boolean {
    return section.fields.some((field: ConfigField) => field.modified);
  }

  resetField(field: ConfigField): void {
    field.editValue = field.value;
    field.modified = false;
  }

  isPasswordField(sectionKey: string, fieldKey: string): boolean {
    return sectionKey === 'connection' && fieldKey === 'password';
  }

  getFieldDescription(sectionKey: string, fieldKey: string): string {
    return this.fieldDescriptions[sectionKey]?.[fieldKey] ?? '';
  }

  isScanDirsField(sectionKey: string, fieldKey: string): boolean {
    return sectionKey === 'orphaned' && fieldKey === 'scan_dirs';
  }

  getScanDirs(field: ConfigField): string[] {
    const value = String(field.editValue || '');
    if (!value) return [];
    return value.split(',').map((s: string) => s.trim());
  }

  addScanDir(section: ConfigSection, field: ConfigField): void {
    const dirs = this.getScanDirs(field);
    dirs.push('');
    field.editValue = dirs.join(',');
    this.onFieldChange(section, field);
  }

  removeScanDir(section: ConfigSection, field: ConfigField, index: number): void {
    const dirs = this.getScanDirs(field);
    dirs.splice(index, 1);
    field.editValue = dirs.join(',');
    this.onFieldChange(section, field);
  }

  updateScanDir(section: ConfigSection, field: ConfigField, index: number, value: string): void {
    const dirs = this.getScanDirs(field);
    dirs[index] = value;
    field.editValue = dirs.join(',');
    this.onFieldChange(section, field);
  }

  formatFieldName(key: string): string {
    return key
      .replace(/_/g, ' ')
      .replace(/\b\w/g, (char: string) => char.toUpperCase());
  }

  private buildSections(config: ConfigResponse): void {
    const sections: ConfigSection[] = [];

    for (const [sectionKey, sectionData] of Object.entries(config) as [string, ConfigSectionValues][]) {
      const meta = this.sectionMeta[sectionKey] ?? { name: sectionKey, icon: 'fa-solid fa-gear' };
      const fields: ConfigField[] = [];

      for (const [fieldKey, fieldValue] of Object.entries(sectionData)) {
        const fieldType = this.detectType(fieldValue);
        fields.push({
          key: fieldKey,
          value: fieldValue,
          type: fieldType,
          editValue: fieldValue,
          modified: false,
        });
      }

      sections.push({
        name: meta.name,
        icon: meta.icon,
        key: sectionKey,
        fields,
        expanded: false,
      });
    }

    this.sections.set(sections);
  }

  private detectType(value: string | number | boolean): 'string' | 'number' | 'boolean' {
    if (typeof value === 'boolean') return 'boolean';
    if (typeof value === 'number') return 'number';
    return 'string';
  }

  private getModifiedFields(): Record<string, Record<string, string | number | boolean>> {
    const overrides: Record<string, Record<string, string | number | boolean>> = {};
    for (const section of this.sections()) {
      for (const field of section.fields) {
        if (field.modified) {
          if (!overrides[section.key]) {
            overrides[section.key] = {};
          }
          let value = field.editValue;
          if (this.isScanDirsField(section.key, field.key)) {
            value = String(value).split(',').map((s: string) => s.trim()).filter((s: string) => s.length > 0).join(',');
          }
          overrides[section.key][field.key] = value;
        }
      }
    }
    return overrides;
  }
}
