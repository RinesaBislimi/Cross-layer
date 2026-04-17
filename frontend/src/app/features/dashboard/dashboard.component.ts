import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { ApiService, StatsResponse } from '../../core/services/api.service';
import { WebSocketService } from '../../core/services/websocket.service';
import { LogEvent } from '../../shared/models/log-event';
import { Incident } from '../../shared/models/incident';
import { Subject, takeUntil, interval, filter, take } from 'rxjs';

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [CommonModule, RouterLink],
  templateUrl: './dashboard.component.html',
  styleUrls: ['./dashboard.component.css'],
})
export class DashboardComponent implements OnInit, OnDestroy {
  healthOk: boolean | null = null;   // null = checking, true = ok, false = offline
  recentLogs: LogEvent[] = [];
  recentIncidents: Incident[] = [];
  stats: StatsResponse | null = null;
  wsMessages: unknown[] = [];
  liveAlertCount = 0;
  countdown = 30;
  loading = true;
  statsComputing = false;
  statsComputeMsg = '';
  private destroy$ = new Subject<void>();

  constructor(
    private api: ApiService,
    public ws: WebSocketService,
  ) {}

  ngOnInit(): void {
    this.refresh();

    // Countdown timer + auto-refresh every 30 s
    interval(1000).pipe(takeUntil(this.destroy$)).subscribe(() => {
      this.countdown--;
      if (this.countdown <= 0) {
        this.countdown = 30;
        this.refresh();
      }
    });

    // When WS connects for the first time, refresh to pick up live data
    this.ws.messages.pipe(
      takeUntil(this.destroy$),
      filter(() => this.stats === null),
      take(1),
    ).subscribe(() => this.refresh());

    // Live message feed
    this.ws.messages.pipe(takeUntil(this.destroy$)).subscribe((msg) => {
      this.wsMessages = [msg, ...this.wsMessages].slice(0, 20);
      this.liveAlertCount++;
    });
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }

  refresh(): void {
    this.loading = true;

    this.api.getHealth().pipe(takeUntil(this.destroy$)).subscribe({
      next: (r) => (this.healthOk = r.status === 'ok'),
      error: () => (this.healthOk = false),
    });

    this.api.getSummary().pipe(takeUntil(this.destroy$)).subscribe({
      next: (s) => {
        console.log('[Dashboard] /summary:', s);
        this.stats = s;
        this.loading = false;
      },
      error: (err) => {
        console.error('[Dashboard] /summary error:', err);
        this.loading = false;
      },
    });

    this.api.getLogs({ limit: 12 }).pipe(takeUntil(this.destroy$)).subscribe({
      next: (logs) => (this.recentLogs = logs),
      error: () => {},
    });

    this.api.getIncidents(8).pipe(takeUntil(this.destroy$)).subscribe({
      next: (incidents) => (this.recentIncidents = incidents),
      error: () => {},
    });
  }

  // ── Derived metrics ──────────────────────────────────────────────────────────
  get criticalCount(): number {
    return this.stats?.incidents_by_severity?.find(s => s.name === 'critical')?.count ?? 0;
  }

  get anomalyRate(): number {
    if (!this.stats || this.stats.total_incidents === 0) return 0;
    const sev = this.stats.incidents_by_severity;
    const critHigh = (sev.find(s => s.name === 'critical')?.count ?? 0)
                   + (sev.find(s => s.name === 'high')?.count ?? 0);
    return Math.round((critHigh / this.stats.total_incidents) * 100);
  }

  get anomalyLogRate(): number {
    if (!this.stats?.total_logs) return 0;
    return Math.round((this.stats.total_anomalies / this.stats.total_logs) * 100);
  }

  get threatScore(): number {
    // 0–100: weighted from anomaly log rate (60%) + high/critical incident rate (40%)
    const logScore = Math.min(this.anomalyLogRate * 0.6, 60);
    const incScore = Math.min(this.anomalyRate * 0.4, 40);
    return Math.round(logScore + incScore);
  }

  get threatLevel(): string {
    const s = this.threatScore;
    if (s >= 70) return 'critical';
    if (s >= 40) return 'high';
    if (s >= 20) return 'medium';
    return 'low';
  }

  get layerCards() {
    const defs = [
      { key: 'system',      label: 'System',      icon: '🖥', dataset: 'BGL' },
      { key: 'network',     label: 'Network',     icon: '🌐', dataset: 'CICIDS-2017' },
      { key: 'application', label: 'Application', icon: '🗄', dataset: 'TDA' },
    ];
    const total = this.stats?.total_logs || 1;
    return defs.map(d => {
      const row = this.stats?.logs_by_layer?.find(r => r.name === d.key);
      const count    = row?.count    ?? 0;
      const anomalies = (row as any)?.anomalies ?? 0;
      const rate     = count > 0 ? Math.round((anomalies / count) * 100) : 0;
      const share    = count > 0 ? Math.round((count / total) * 100) : 0;
      const status   = rate > 20 ? 'critical' : rate > 5 ? 'warning' : count > 0 ? 'healthy' : 'inactive';
      return { ...d, count, anomalies, rate, share, status };
    });
  }

  get severityRows() {
    if (!this.stats?.incidents_by_severity?.length) return [];
    const total = this.stats.total_incidents || 1;
    return ['critical', 'high', 'medium', 'low']
      .map(name => {
        const found = this.stats!.incidents_by_severity.find(s => s.name === name);
        return { name, count: found?.count ?? 0, pct: found ? Math.round((found.count / total) * 100) : 0 };
      })
      .filter(s => s.count > 0);
  }

  get ringDashOffset(): number {
    // SVG circle r=32 → circumference = 2πr ≈ 201
    return Math.round(201 - (this.threatScore / 100) * 201);
  }

  formatDate(s: string): string {
    return new Date(s).toLocaleString();
  }

  relativeTime(s: string): string {
    const diff = Date.now() - new Date(s).getTime();
    const m = Math.floor(diff / 60000);
    if (m < 1) return 'just now';
    if (m < 60) return `${m}m ago`;
    const h = Math.floor(m / 60);
    if (h < 24) return `${h}h ago`;
    return `${Math.floor(h / 24)}d ago`;
  }

  severityClass(sev: string | null): string {
    if (!sev) return 'badge-medium';
    return `badge-${sev.toLowerCase()}`;
  }

  clearAlertCount(): void {
    this.liveAlertCount = 0;
  }

  computeLayerStats(): void {
    if (this.statsComputing) return;
    this.statsComputing = true;
    this.statsComputeMsg = 'Computing layer stats — this may take several minutes on large datasets…';
    this.api.computeStats().pipe(takeUntil(this.destroy$)).subscribe({
      next: (r) => {
        this.statsComputing = false;
        this.statsComputeMsg = `Done in ${r.elapsed_seconds}s — ${r.layers} layers computed. Refreshing…`;
        setTimeout(() => { this.statsComputeMsg = ''; this.refresh(); }, 1500);
      },
      error: (err) => {
        this.statsComputing = false;
        this.statsComputeMsg = 'Compute failed: ' + (err?.error?.detail || err?.message || 'unknown error');
      },
    });
  }
}
