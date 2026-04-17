import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { HttpClient } from '@angular/common/http';

interface ChainEvent {
  id: string;
  incident_type: string;
  severity: string;
  layer: string;
  entity: string;
  risk_score: number;
  start_time: string;
}

interface AttackChain {
  id: string;
  events: ChainEvent[];
  layer_count: number;
  layers: string[];
  max_risk: number;
  start_time: string;
  end_time: string;
  cross_layer: boolean;
  entity: string;
}

@Component({
  selector: 'app-attack-chains',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './attack-chains.component.html',
  styleUrls: ['./attack-chains.component.css'],
})
export class AttackChainsComponent implements OnInit {
  chains: AttackChain[] = [];
  loading = true;
  error: string | null = null;
  expandedId: string | null = null;

  constructor(private http: HttpClient) {}

  ngOnInit() {
    this.http
      .get<{ chains: AttackChain[]; total: number }>('http://127.0.0.1:8000/analytics/attack-chains')
      .subscribe({
        next: (res) => {
          this.chains = res.chains;
          this.loading = false;
        },
        error: (e) => {
          this.error = e.message || 'Failed to load attack chains';
          this.loading = false;
        },
      });
  }

  toggleExpand(id: string) {
    this.expandedId = this.expandedId === id ? null : id;
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

  severityClass(sev: string): string {
    return `badge-${(sev || 'low').toLowerCase()}`;
  }

  layerClass(layer: string): string {
    return `badge-${(layer || 'unknown').toLowerCase()}`;
  }

  formatDate(s: string): string {
    if (!s) return '—';
    return new Date(s).toLocaleString();
  }

  formatTime(s: string): string {
    if (!s) return '—';
    return new Date(s).toLocaleTimeString(undefined, {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  }

  formatDateShort(s: string): string {
    if (!s) return '—';
    const d = new Date(s);
    return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) +
      ' ' + d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
  }

  get crossLayerCount(): number {
    return this.chains.filter((c) => c.cross_layer).length;
  }

  get totalEvents(): number {
    return this.chains.reduce((s, c) => s + (c.events?.length || 0), 0);
  }
}
