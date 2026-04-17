import { Component, OnInit, OnDestroy, ViewChild, ElementRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Chart, ChartConfiguration, registerables } from 'chart.js';
import { ApiService, StatsResponse } from '../../core/services/api.service';
import { WebSocketService } from '../../core/services/websocket.service';
import { Incident } from '../../shared/models/incident';
import { LogEvent } from '../../shared/models/log-event';
import { Subject, interval, auditTime, takeUntil, of } from 'rxjs';
import { catchError } from 'rxjs/operators';

Chart.register(...registerables);

@Component({
  selector: 'app-statistics',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './statistics.component.html',
  styleUrls: ['./statistics.component.css'],
})
export class StatisticsComponent implements OnInit, OnDestroy {
  @ViewChild('chartSeverity')    chartSeverityRef!:    ElementRef<HTMLCanvasElement>;
  @ViewChild('chartMode')        chartModeRef!:        ElementRef<HTMLCanvasElement>;
  @ViewChild('chartLayerVolume') chartLayerVolumeRef!: ElementRef<HTMLCanvasElement>;
  @ViewChild('chartSourceVol')   chartSourceVolRef!:   ElementRef<HTMLCanvasElement>;
  @ViewChild('chartAnomalyRate') chartAnomalyRateRef!: ElementRef<HTMLCanvasElement>;
  @ViewChild('chartTimeline')    chartTimelineRef!:    ElementRef<HTMLCanvasElement>;

  stats: StatsResponse | null = null;
  recentIncidents: Incident[] = [];
  recentLogs: LogEvent[] = [];

  loading = true;
  error: string | null = null;
  activeTab: 'incidents' | 'logs' = 'incidents';

  private chartSev:         Chart | null = null;
  private chartMode:        Chart | null = null;
  private chartLayerVolume: Chart | null = null;
  private chartSourceVol:   Chart | null = null;
  private chartAnomalyRate: Chart | null = null;
  private chartTimeline:    Chart | null = null;
  private destroy$ = new Subject<void>();

  constructor(private api: ApiService, public ws: WebSocketService) {}

  ngOnInit(): void {
    this.load();
    interval(30000).pipe(takeUntil(this.destroy$)).subscribe(() => this.refresh());
    this.ws.messages.pipe(takeUntil(this.destroy$), auditTime(2000)).subscribe(() => this.refresh());
  }

  load(): void {
    this.loading = true;
    this.error   = null;
    let pending  = 3;
    const done   = () => { if (--pending === 0) this.loading = false; };

    this.api.getSummary().pipe(catchError(() => of(null))).subscribe(data => {
      if (data) this.stats = data;
      else this.error = 'Cannot reach backend — run: cd backend && uvicorn app.main:app --reload';
      done();
    });

    this.api.getIncidents(50).pipe(catchError(() => of([]))).subscribe(list => {
      this.recentIncidents = list;
      // Build incident charts once data arrives
      setTimeout(() => this.buildCharts(), 50);
      done();
    });

    this.api.getLogs({ limit: 50 }).pipe(catchError(() => of([]))).subscribe(list => {
      this.recentLogs = list;
      done();
    });
  }

  private refresh(): void {
    this.api.getSummary().pipe(takeUntil(this.destroy$), catchError(() => of(null))).subscribe(data => {
      if (data) this.stats = data;
    });
    this.api.getIncidents(50).pipe(takeUntil(this.destroy$), catchError(() => of([]))).subscribe(list => {
      this.recentIncidents = list;
      setTimeout(() => this.buildCharts(), 50);
    });
    this.api.getLogs({ limit: 50 }).pipe(takeUntil(this.destroy$), catchError(() => of([]))).subscribe(list => {
      this.recentLogs = list;
    });
  }

  setTab(tab: typeof this.activeTab): void { this.activeTab = tab; }

  get anomalyRate(): number {
    if (!this.stats?.total_logs) return 0;
    return Math.round((this.stats.total_anomalies / this.stats.total_logs) * 100);
  }

  get criticalHighRate(): number {
    if (!this.stats?.total_incidents) return 0;
    const sev = this.stats.incidents_by_severity;
    const bad = (sev.find(s => s.name === 'critical')?.count ?? 0)
              + (sev.find(s => s.name === 'high')?.count ?? 0);
    return Math.round((bad / this.stats.total_incidents) * 100);
  }

  severityColor(sev: string | null): string {
    switch (sev?.toLowerCase()) {
      case 'critical': return 'sev-critical';
      case 'high':     return 'sev-high';
      case 'medium':   return 'sev-medium';
      case 'low':      return 'sev-low';
      default:         return 'sev-info';
    }
  }

  incidentAttr(inc: Incident, key: string): string {
    const val = inc.attributes?.[key];
    return val != null ? String(val) : '—';
  }

  private buildCharts(): void {
    if (!this.stats) return;
    const textC = '#64748b';
    const gridC = 'rgba(0,0,0,0.06)';

    // ── Severity doughnut ────────────────────────────────────────────────────
    if (this.chartSeverityRef?.nativeElement && this.stats.incidents_by_severity.length) {
      this.chartSev?.destroy();
      this.chartSev = new Chart(this.chartSeverityRef.nativeElement, {
        type: 'doughnut',
        data: {
          labels: this.stats.incidents_by_severity.map(x => x.name),
          datasets: [{
            data: this.stats.incidents_by_severity.map(x => x.count),
            backgroundColor: ['#ef4444', '#f97316', '#eab308', '#22c55e', '#6366f1'],
            borderWidth: 2, borderColor: '#fff',
          }],
        },
        options: {
          responsive: true, maintainAspectRatio: false,
          plugins: { legend: { position: 'bottom', labels: { color: textC, padding: 14 } } },
          cutout: '60%',
        },
      } as ChartConfiguration);
    }

    // ── Detection method horizontal bar ──────────────────────────────────────
    if (this.chartModeRef?.nativeElement && this.stats.incidents_by_mode.length) {
      this.chartMode?.destroy();
      this.chartMode = new Chart(this.chartModeRef.nativeElement, {
        type: 'bar',
        data: {
          labels: this.stats.incidents_by_mode.map(x => x.name),
          datasets: [{
            label: 'Incidents',
            data: this.stats.incidents_by_mode.map(x => x.count),
            backgroundColor: ['#6366f1', '#22c55e', '#f59e0b', '#ef4444', '#3b82f6'],
            borderRadius: 6,
          }],
        },
        options: {
          indexAxis: 'y', responsive: true, maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: {
            x: { grid: { color: gridC }, ticks: { color: textC } },
            y: { grid: { color: gridC }, ticks: { color: textC } },
          },
        },
      } as ChartConfiguration);
    }

    // ── Log volume by layer (stacked bar) ────────────────────────────────────
    if (this.chartLayerVolumeRef?.nativeElement && this.stats.logs_by_layer?.length) {
      const layers = this.stats.logs_by_layer;
      const normal = layers.map(l => l.count - (l.anomalies ?? 0));
      const anom   = layers.map(l => l.anomalies ?? 0);
      this.chartLayerVolume?.destroy();
      this.chartLayerVolume = new Chart(this.chartLayerVolumeRef.nativeElement, {
        type: 'bar',
        data: {
          labels: layers.map(l => l.name),
          datasets: [
            { label: 'Normal', data: normal, backgroundColor: '#6366f1aa', borderRadius: 4 },
            { label: 'Anomaly', data: anom,  backgroundColor: '#ef4444cc', borderRadius: 4 },
          ],
        },
        options: {
          responsive: true, maintainAspectRatio: false,
          plugins: {
            legend: { position: 'top', labels: { color: textC, boxWidth: 12, padding: 12 } },
            tooltip: {
              callbacks: {
                label: (ctx) => {
                  const v = ctx.raw as number;
                  return ` ${ctx.dataset.label}: ${v.toLocaleString()}`;
                },
              },
            },
          },
          scales: {
            x: { stacked: true, grid: { display: false }, ticks: { color: textC } },
            y: { stacked: true, grid: { color: gridC }, ticks: { color: textC,
              callback: (v) => Number(v) >= 1e6 ? (Number(v)/1e6).toFixed(1)+'M' : Number(v) >= 1e3 ? (Number(v)/1e3).toFixed(0)+'K' : v } },
          },
        },
      } as ChartConfiguration);
    }

    // ── Log volume by source (horizontal stacked bar) ────────────────────────
    if (this.chartSourceVolRef?.nativeElement && this.stats.logs_by_source?.length) {
      const sources = this.stats.logs_by_source;
      const normal  = sources.map(s => s.count - (s.anomalies ?? 0));
      const anom    = sources.map(s => s.anomalies ?? 0);
      this.chartSourceVol?.destroy();
      this.chartSourceVol = new Chart(this.chartSourceVolRef.nativeElement, {
        type: 'bar',
        data: {
          labels: sources.map(s => s.name),
          datasets: [
            { label: 'Normal', data: normal, backgroundColor: '#22c55eaa', borderRadius: 4 },
            { label: 'Anomaly', data: anom,  backgroundColor: '#f97316cc', borderRadius: 4 },
          ],
        },
        options: {
          indexAxis: 'y', responsive: true, maintainAspectRatio: false,
          plugins: {
            legend: { position: 'top', labels: { color: textC, boxWidth: 12, padding: 12 } },
            tooltip: {
              callbacks: {
                label: (ctx) => {
                  const v = ctx.raw as number;
                  return ` ${ctx.dataset.label}: ${v.toLocaleString()}`;
                },
              },
            },
          },
          scales: {
            x: { stacked: true, grid: { color: gridC }, ticks: { color: textC,
              callback: (v) => Number(v) >= 1e6 ? (Number(v)/1e6).toFixed(1)+'M' : Number(v) >= 1e3 ? (Number(v)/1e3).toFixed(0)+'K' : v } },
            y: { stacked: true, grid: { display: false }, ticks: { color: textC } },
          },
        },
      } as ChartConfiguration);
    }

    // ── Anomaly rate by layer (horizontal bar) ───────────────────────────────
    if (this.chartAnomalyRateRef?.nativeElement && this.stats.logs_by_layer?.length) {
      const layers = this.stats.logs_by_layer.filter(l => l.count > 0);
      const rates  = layers.map(l => l.count > 0 ? +((( l.anomalies ?? 0) / l.count) * 100).toFixed(2) : 0);
      const colors = rates.map(r => r > 10 ? '#ef4444' : r > 3 ? '#f97316' : '#22c55e');
      this.chartAnomalyRate?.destroy();
      this.chartAnomalyRate = new Chart(this.chartAnomalyRateRef.nativeElement, {
        type: 'bar',
        data: {
          labels: layers.map(l => l.name),
          datasets: [{
            label: 'Anomaly rate (%)',
            data: rates,
            backgroundColor: colors,
            borderRadius: 6,
          }],
        },
        options: {
          indexAxis: 'y', responsive: true, maintainAspectRatio: false,
          plugins: {
            legend: { display: false },
            tooltip: { callbacks: { label: (ctx) => ` ${ctx.raw}% anomaly rate` } },
          },
          scales: {
            x: { grid: { color: gridC }, ticks: { color: textC, callback: (v) => v + '%' },
              min: 0, max: Math.max(20, ...rates) + 2 },
            y: { grid: { display: false }, ticks: { color: textC } },
          },
        },
      } as ChartConfiguration);
    }

    // ── Incident timeline (line chart grouped by day) ────────────────────────
    if (this.chartTimelineRef?.nativeElement && this.recentIncidents.length) {
      const buckets = new Map<string, number>();
      for (const inc of this.recentIncidents) {
        if (!inc.start_time) continue;
        const day = inc.start_time.substring(0, 10);
        buckets.set(day, (buckets.get(day) ?? 0) + 1);
      }
      const sorted  = [...buckets.entries()].sort((a, b) => a[0].localeCompare(b[0]));
      const labels  = sorted.map(([d]) => d);
      const counts  = sorted.map(([, c]) => c);
      this.chartTimeline?.destroy();
      this.chartTimeline = new Chart(this.chartTimelineRef.nativeElement, {
        type: 'line',
        data: {
          labels,
          datasets: [{
            label: 'Incidents/day',
            data: counts,
            borderColor: '#6366f1',
            backgroundColor: 'rgba(99,102,241,0.12)',
            fill: true,
            tension: 0.35,
            pointRadius: 4,
            pointBackgroundColor: '#6366f1',
          }],
        },
        options: {
          responsive: true, maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: {
            x: { grid: { color: gridC }, ticks: { color: textC, maxRotation: 45 } },
            y: { grid: { color: gridC }, ticks: { color: textC, stepSize: 1 }, beginAtZero: true },
          },
        },
      } as ChartConfiguration);
    }
  }

  ngOnDestroy(): void {
    this.destroy$.next(); this.destroy$.complete();
    this.chartSev?.destroy();
    this.chartMode?.destroy();
    this.chartLayerVolume?.destroy();
    this.chartSourceVol?.destroy();
    this.chartAnomalyRate?.destroy();
    this.chartTimeline?.destroy();
  }
}
