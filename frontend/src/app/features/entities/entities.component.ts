import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { HttpClient } from '@angular/common/http';

interface EntitySummary {
  entity: string;
  incident_count: number;
  max_risk: number;
  avg_risk: number;
  last_seen: string;
  severities: string[];
  layers: string[];
}

interface EntityIncident {
  id: string;
  incident_type: string;
  severity: string;
  layer: string;
  risk_score: number;
  start_time: string;
  description: string;
}

interface EntityDetail {
  entity: string;
  incidents: EntityIncident[];
}

@Component({
  selector: 'app-entities',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './entities.component.html',
  styleUrls: ['./entities.component.css'],
})
export class EntitiesComponent implements OnInit {
  entities: EntitySummary[] = [];
  loading = true;
  error: string | null = null;

  selectedEntity: string | null = null;
  entityDetail: EntityDetail | null = null;
  detailLoading = false;
  detailError: string | null = null;

  constructor(private http: HttpClient) {}

  ngOnInit() {
    this.http
      .get<{ entities: EntitySummary[] }>('http://127.0.0.1:8000/analytics/entities')
      .subscribe({
        next: (res) => {
          this.entities = res.entities;
          this.loading = false;
        },
        error: (e) => {
          this.error = e.message || 'Failed to load entities';
          this.loading = false;
        },
      });
  }

  selectEntity(name: string) {
    if (this.selectedEntity === name) {
      this.selectedEntity = null;
      this.entityDetail = null;
      return;
    }
    this.selectedEntity = name;
    this.entityDetail = null;
    this.detailError = null;
    this.detailLoading = true;

    this.http
      .get<EntityDetail>(`http://127.0.0.1:8000/analytics/entity/${encodeURIComponent(name)}`)
      .subscribe({
        next: (res) => {
          this.entityDetail = res;
          this.detailLoading = false;
        },
        error: (e) => {
          this.detailError = e.message || 'Failed to load entity detail';
          this.detailLoading = false;
        },
      });
  }

  closeDetail() {
    this.selectedEntity = null;
    this.entityDetail = null;
  }

  riskClass(score: number): string {
    if (score >= 0.8) return 'risk-critical';
    if (score >= 0.6) return 'risk-high';
    if (score >= 0.4) return 'risk-medium';
    return 'risk-low';
  }

  riskLabel(score: number): string {
    if (score >= 0.8) return 'Critical';
    if (score >= 0.6) return 'High';
    if (score >= 0.4) return 'Medium';
    return 'Low';
  }

  riskBarColor(score: number): string {
    if (score >= 0.8) return 'var(--danger)';
    if (score >= 0.6) return '#f97316';
    if (score >= 0.4) return 'var(--warning)';
    return 'var(--success)';
  }

  formatDate(s: string): string {
    if (!s) return '—';
    return new Date(s).toLocaleString();
  }

  formatDateShort(s: string): string {
    if (!s) return '—';
    return new Date(s).toLocaleDateString(undefined, {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  }

  layerClass(layer: string): string {
    return `badge-${(layer || 'unknown').toLowerCase()}`;
  }

  severityClass(sev: string): string {
    return `badge-${(sev || 'low').toLowerCase()}`;
  }
}
