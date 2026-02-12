import { Component, computed, DestroyRef, inject, OnInit, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { AccordionModule } from 'primeng/accordion';
import { InputTextModule } from 'primeng/inputtext';
import { ButtonModule } from 'primeng/button';
import { ToggleSwitch } from 'primeng/toggleswitch';
import { ProgressSpinnerModule } from 'primeng/progressspinner';
import { TooltipModule } from 'primeng/tooltip';
import { ApiService } from '../../core/services/api.service';
import { ConfigResponse, ConfigSectionValues } from '../../shared/models';
import { NotificationService } from '../../core/services/notification.service';

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
    AccordionModule,
    InputTextModule,
    ButtonModule,
    ToggleSwitch,
    ProgressSpinnerModule,
    TooltipModule,
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

  private readonly sectionMeta: Readonly<Record<string, SectionMeta>> = {
    connection: { name: 'Connection', icon: 'pi pi-link' },
    limits: { name: 'Limits', icon: 'pi pi-sliders-h' },
    behavior: { name: 'Behavior', icon: 'pi pi-cog' },
    schedule: { name: 'Schedule', icon: 'pi pi-clock' },
    fileflows: { name: 'FileFlows', icon: 'pi pi-sync' },
    orphaned: { name: 'Orphaned', icon: 'pi pi-folder' },
    web: { name: 'Web', icon: 'pi pi-globe' },
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

  onFieldChange(_section: ConfigSection, field: ConfigField): void {
    field.modified = field.editValue !== field.value;
  }

  sectionHasModifications(section: ConfigSection): boolean {
    return section.fields.some((field: ConfigField) => field.modified);
  }

  resetField(field: ConfigField): void {
    field.editValue = field.value;
    field.modified = false;
  }

  formatFieldName(key: string): string {
    return key
      .replace(/_/g, ' ')
      .replace(/\b\w/g, (char: string) => char.toUpperCase());
  }

  private buildSections(config: ConfigResponse): void {
    const sections: ConfigSection[] = [];

    for (const [sectionKey, sectionData] of Object.entries(config) as [string, ConfigSectionValues][]) {
      const meta = this.sectionMeta[sectionKey] ?? { name: sectionKey, icon: 'pi pi-cog' };
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
          overrides[section.key][field.key] = field.editValue;
        }
      }
    }
    return overrides;
  }
}
