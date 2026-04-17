import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { HttpClient } from '@angular/common/http';

interface SeverityBucket { name: string; count: number; }
interface LayerBucket    { name: string; count: number; avg_risk: number; }
interface TopEntity       { entity: string; count: number; max_risk: number; }
interface TopIncident     { id: string; type: string; severity: string; layer: string; entity: string; risk: number; time: string; }
interface DailyTrend      { date: string; total: number; high_critical: number; }

interface ReportSummary {
  generated_at: string;
  total_incidents: number;
  by_severity: SeverityBucket[];
  by_layer: LayerBucket[];
  top_entities: TopEntity[];
  top_incidents: TopIncident[];
  daily_trend: DailyTrend[];
}

@Component({
  selector: 'app-reports',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './reports.component.html',
  styleUrls: ['./reports.component.css'],
})
export class ReportsComponent implements OnInit {
  report: ReportSummary | null = null;
  loading = true;
  error: string | null = null;

  constructor(private http: HttpClient) {}

  ngOnInit() {
    this.http
      .get<ReportSummary>('http://127.0.0.1:8000/analytics/report-summary')
      .subscribe({
        next: (res) => {
          this.report = res;
          this.loading = false;
        },
        error: (e) => {
          this.error = e.message || 'Failed to load report';
          this.loading = false;
        },
      });
  }

  printReport() {
    window.print();
  }

  riskClass(score: number): string {
    if (score >= 0.8) return 'risk-critical';
    if (score >= 0.6) return 'risk-high';
    if (score >= 0.4) return 'risk-medium';
    return 'risk-low';
  }

  sevClass(sev: string): string {
    return `badge-${(sev || 'low').toLowerCase()}`;
  }

  layerClass(layer: string): string {
    return `badge-${(layer || 'unknown').toLowerCase()}`;
  }

  totalHighCritical(): number {
    if (!this.report) return 0;
    const crit = this.report.by_severity.find(s => s.name === 'critical')?.count ?? 0;
    const high = this.report.by_severity.find(s => s.name === 'high')?.count ?? 0;
    return crit + high;
  }

  anomalyRate(): number {
    if (!this.report || this.report.total_incidents === 0) return 0;
    return Math.round((this.totalHighCritical() / this.report.total_incidents) * 100);
  }

  topEntity(): string {
    return this.report?.top_entities?.[0]?.entity ?? '—';
  }

  sevBarWidth(count: number): number {
    if (!this.report || this.report.total_incidents === 0) return 0;
    return Math.round((count / this.report.total_incidents) * 100);
  }

  layerBarWidth(avg_risk: number): number {
    return Math.round(avg_risk * 100);
  }

  sevBarColor(name: string): string {
    const map: Record<string, string> = {
      critical: 'var(--danger)',
      high: '#f97316',
      medium: 'var(--warning)',
      low: 'var(--success)',
    };
    return map[name.toLowerCase()] ?? '#9ca3af';
  }

  formatDate(s: string): string {
    if (!s) return '—';
    return new Date(s).toLocaleString();
  }

  formatDateShort(s: string): string {
    if (!s) return '—';
    return new Date(s).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
  }

  maxDailyTotal(): number {
    if (!this.report?.daily_trend?.length) return 1;
    return Math.max(...this.report.daily_trend.map(d => d.total), 1);
  }
}
