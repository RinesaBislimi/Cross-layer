import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ApiService } from '../../core/services/api.service';
import { Incident } from '../../shared/models/incident';
import { LogEvent } from '../../shared/models/log-event';

@Component({
  selector: 'app-incidents',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './incidents.component.html',
  styleUrls: ['./incidents.component.css'],
})
export class IncidentsComponent implements OnInit {
  allIncidents: Incident[] = [];
  loading = false;
  error: string | null = null;
  selected: Incident | null = null;
  selectedEvents: LogEvent[] = [];
  loadingEvents = false;
  searchText = '';
  severityFilter = '';
  copied = false;

  severities = ['critical', 'high', 'medium', 'low'];

  constructor(private api: ApiService) {}

  ngOnInit(): void { this.load(); }

  load(): void {
    this.loading = true;
    this.error = null;
    this.api.getIncidents(200).subscribe({
      next: (list) => { this.allIncidents = list; this.loading = false; },
      error: (err) => { this.error = err?.message || 'Failed to load incidents'; this.loading = false; },
    });
  }

  get filteredIncidents(): Incident[] {
    let list = this.allIncidents;
    if (this.severityFilter) {
      list = list.filter(i => (i.severity || '').toLowerCase() === this.severityFilter);
    }
    if (this.searchText.trim()) {
      const q = this.searchText.toLowerCase();
      list = list.filter(i =>
        (i.entity || '').toLowerCase().includes(q) ||
        (i.type || '').toLowerCase().includes(q)
      );
    }
    return list;
  }

  countBySeverity(sev: string): number {
    return this.allIncidents.filter(i => (i.severity || '').toLowerCase() === sev).length;
  }

  selectIncident(inc: Incident): void {
    if (this.selected?.id === inc.id) { this.selected = null; return; }
    this.selected = inc;
    this.selectedEvents = [];
    if (!inc.id) return;
    this.loadingEvents = true;
    this.api.getIncidentEvents(inc.id).subscribe({
      next: (events) => { this.selectedEvents = events; this.loadingEvents = false; },
      error: () => { this.loadingEvents = false; },
    });
  }

  durationLabel(inc: Incident): string {
    if (!inc.end_time) return 'open';
    const ms = new Date(inc.end_time).getTime() - new Date(inc.start_time).getTime();
    if (ms < 60000) return `${Math.round(ms / 1000)}s`;
    if (ms < 3600000) return `${Math.round(ms / 60000)}m`;
    return `${Math.round(ms / 3600000)}h`;
  }

  copyEntity(entity: string | null): void {
    if (!entity) return;
    navigator.clipboard.writeText(entity).then(() => {
      this.copied = true;
      setTimeout(() => (this.copied = false), 1500);
    });
  }

  layersAttr(inc: Incident): string[] {
    const layers = inc.attributes?.['layers'];
    if (Array.isArray(layers)) return layers as string[];
    return [];
  }

  formatDate(s: string): string { return new Date(s).toLocaleString(); }

  severityClass(severity: string | null): string {
    if (!severity) return 'badge-medium';
    const s = severity.toLowerCase();
    if (s === 'critical' || s === 'high') return 'badge-high';
    if (s === 'low') return 'badge-low';
    return 'badge-medium';
  }

  eventsByLayer(layer: string): LogEvent[] {
    return this.selectedEvents.filter(e => e.layer === layer).slice(0, 100);
  }

  scoreAttr(inc: Incident): number | null {
    const s = inc.attributes?.['max_score'];
    return typeof s === 'number' ? s : null;
  }

  numEventsAttr(inc: Incident): number {
    const n = inc.attributes?.['num_events'];
    return typeof n === 'number' ? n : (inc.events?.length ?? 0);
  }

  /** Human-readable description stored in attributes, or derived from type as fallback. */
  descriptionLabel(inc: Incident): string {
    const stored = inc.attributes?.['description'];
    if (typeof stored === 'string' && stored.trim()) return stored;

    // Fallback: derive a readable label from the type field
    const t = inc.type || '';
    if (t.startsWith('ML:')) {
      const src = t.replace('ML:', '');
      return `ML-detected anomaly cluster in ${src} — ${this.numEventsAttr(inc)} flagged events.`;
    }
    if (t.startsWith('Cross-layer[')) {
      const layers = this.layersAttr(inc).map(l => l.charAt(0).toUpperCase() + l.slice(1)).join(' + ');
      return `Cross-layer correlation across ${layers || 'multiple layers'}.`;
    }
    if (t.startsWith('Cross-layer time window')) {
      const layers = this.layersAttr(inc).map(l => l.charAt(0).toUpperCase() + l.slice(1)).join(' + ');
      return `Simultaneous activity in ${layers || 'multiple layers'} within the same time window.`;
    }
    if (t.startsWith('Cross-layer incident')) {
      const layers = this.layersAttr(inc).map(l => l.charAt(0).toUpperCase() + l.slice(1)).join(' + ');
      return `Correlated alert across ${layers || 'multiple layers'}${inc.entity ? ' for entity "' + inc.entity + '"' : ''}.`;
    }
    return t;
  }

  correlationModeLabel(inc: Incident): string {
    const mode = inc.attributes?.['generated_from'] as string | undefined;
    const map: Record<string, string> = {
      ml_incidents: 'ML model',
      positional_bucket: 'Positional',
      time_cooccurrence: 'Time window',
      log_events: 'Entity',
    };
    return map[mode ?? ''] ?? mode ?? '';
  }

  // ── AI explain ────────────────────────────────────────────────────────────
  aiExplanation: string | null = null;
  aiLoading = false;
  aiError: string | null = null;

  explainWithAi(inc: Incident): void {
    if (!inc.id) return;
    this.aiExplanation = null;
    this.aiError = null;
    this.aiLoading = true;
    this.api.analyzeIncident(inc.id).subscribe({
      next: (res) => { this.aiExplanation = res.explanation; this.aiLoading = false; },
      error: (err) => {
        const detail: string = err?.error?.detail || err?.message || '';
        this.aiError = detail.includes('credit balance') || detail.includes('billing')
          ? 'Insufficient credits. Go to console.anthropic.com/settings/billing to add credits.'
          : detail.includes('ANTHROPIC_API_KEY') || detail.includes('api_key') || detail.includes('auth')
          ? 'API key not configured. Add ANTHROPIC_API_KEY to backend/.env and restart.'
          : detail || 'AI analysis failed.';
        this.aiLoading = false;
      },
    });
  }
}
