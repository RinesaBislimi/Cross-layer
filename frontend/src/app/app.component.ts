import { Component, OnDestroy, OnInit } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet, Router } from '@angular/router';
import { CommonModule } from '@angular/common';
import { Subscription } from 'rxjs';
import { WebSocketService } from './core/services/websocket.service';
import { ApiService } from './core/services/api.service';
import { AuthService } from './core/services/auth.service';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [RouterLink, RouterLinkActive, RouterOutlet, CommonModule],
  template: `
    <!-- Login page — no sidebar -->
    <ng-container *ngIf="!auth.isLoggedIn(); else appLayout">
      <router-outlet></router-outlet>
    </ng-container>

    <!-- Main app layout -->
    <ng-template #appLayout>
      <div class="layout">
        <!-- Sidebar nav -->
        <nav class="sidenav">
          <div class="nav-brand">
            <span class="brand-name">CrossLayer</span>
          </div>

          <div class="nav-links">
            <a routerLink="/dashboard"   routerLinkActive="active" [routerLinkActiveOptions]="{ exact: true }" class="nav-link">
              <span class="nav-label">Dashboard</span>
            </a>
            <a routerLink="/logs"        routerLinkActive="active" class="nav-link">
              <span class="nav-label">Logs</span>
            </a>
            <a routerLink="/incidents"   routerLinkActive="active" class="nav-link">
              <span class="nav-label">Incidents</span>
              <span class="nav-badge" *ngIf="alertCount > 0">{{ alertCount > 99 ? '99+' : alertCount }}</span>
            </a>
            <a routerLink="/statistics"  routerLinkActive="active" class="nav-link">
              <span class="nav-label">Statistics</span>
            </a>
            <a routerLink="/analysis"    routerLinkActive="active" class="nav-link">
              <span class="nav-label">ML Analysis</span>
            </a>

            <div class="nav-section-label">Analytics</div>

            <a routerLink="/heatmap"       routerLinkActive="active" class="nav-link">
              <span class="nav-label">Heatmap</span>
            </a>
            <a routerLink="/entities"      routerLinkActive="active" class="nav-link">
              <span class="nav-label">Entity Risk</span>
            </a>
            <a routerLink="/attack-chains" routerLinkActive="active" class="nav-link">
              <span class="nav-label">Attack Chains</span>
            </a>
            <a routerLink="/reports"       routerLinkActive="active" class="nav-link">
              <span class="nav-label">Reports</span>
            </a>

            <div class="nav-section-label">Security Ops</div>

            <a routerLink="/alert-rules"    routerLinkActive="active" class="nav-link">
              <span class="nav-label">Alert Rules</span>
            </a>
            <a routerLink="/response-rules" routerLinkActive="active" class="nav-link">
              <span class="nav-label">Auto Response</span>
            </a>
          </div>

          <div class="nav-footer">
            <div class="ws-pill" [class.ws-live]="ws.isConnected">
              <span class="ws-dot"></span>
              <span>{{ ws.isConnected ? 'Live' : 'Offline' }}</span>
            </div>

            <!-- User info + logout -->
            <div *ngIf="auth.user()" class="user-pill">
              <span class="user-avatar">{{ userInitial }}</span>
              <span class="user-name">{{ auth.user()?.full_name || auth.user()?.email }}</span>
              <button class="btn-logout" (click)="logout()" title="Sign out">⏻</button>
            </div>
          </div>
        </nav>

        <!-- Main content -->
        <main class="main">
          <router-outlet></router-outlet>
        </main>
      </div>
    </ng-template>
  `,
  styles: [`
    /* ── Layout ─────────────────────────────────────────────────── */
    .layout { display: flex; min-height: 100vh; background: #f5f6fa; }

    /* ── Sidebar ─────────────────────────────────────────────────── */
    .sidenav {
      width: 220px;
      min-height: 100vh;
      background: #ffffff;
      border-right: 1px solid #e8eaf0;
      display: flex;
      flex-direction: column;
      position: sticky;
      top: 0;
      height: 100vh;
      overflow-y: auto;
      flex-shrink: 0;
      box-shadow: 4px 0 20px -4px rgba(13,17,23,.06);
    }

    /* ── Brand ───────────────────────────────────────────────────── */
    .nav-brand {
      display: flex;
      align-items: center;
      gap: 0.7rem;
      padding: 1.2rem 1.25rem 1.1rem;
      border-bottom: 1px solid #f2f3f8;
    }
    .brand-name {
      font-size: 0.93rem;
      font-weight: 800;
      letter-spacing: -0.03em;
      color: #0d1117;
    }

    /* ── Nav links ───────────────────────────────────���───────────── */
    .nav-section-label {
      font-size: 0.62rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: #9ca3af;
      padding: 0.6rem 0.85rem 0.15rem;
    }
    .nav-links { display: flex; flex-direction: column; gap: 0.1rem; padding: 0.9rem 0.7rem; flex: 1; }
    .nav-link {
      display: flex;
      align-items: center;
      gap: 0.65rem;
      padding: 0.55rem 0.85rem;
      border-radius: 9px;
      color: #5a6a85;
      font-size: 0.845rem;
      font-weight: 500;
      text-decoration: none;
      transition: background 0.12s, color 0.12s;
      position: relative;
      letter-spacing: 0.003em;
    }
    .nav-link:hover { background: #f5f6fa; color: #0d1117; text-decoration: none; }
    .nav-link.active {
      background: #eef2ff;
      color: #4f46e5;
      font-weight: 600;
    }
    .nav-link.active::after {
      content: '';
      position: absolute;
      left: 0;
      top: 20%;
      bottom: 20%;
      width: 3px;
      background: #4f46e5;
      border-radius: 0 2px 2px 0;
    }
    .nav-label { flex: 1; }

    /* ── Alert badge ─────────────────────────────────────────────── */
    .nav-badge {
      background: #dc2626; color: #fff;
      font-size: 0.63rem; font-weight: 800;
      padding: 0.1rem 0.4rem; border-radius: 999px;
      min-width: 18px; text-align: center;
      box-shadow: 0 0 0 2px #fff;
      animation: badge-pulse 2s ease-in-out infinite;
    }
    @keyframes badge-pulse { 0%,100%{opacity:1;transform:scale(1)} 50%{opacity:.78;transform:scale(.93)} }

    /* ── Footer ──────────────────────────────────────────────────── */
    .nav-footer {
      padding: 0.9rem 1rem;
      border-top: 1px solid #f2f3f8;
      display: flex;
      flex-direction: column;
      gap: 0.6rem;
    }
    .ws-pill {
      display: flex; align-items: center; gap: 0.45rem;
      font-size: 0.71rem; color: #9ca3af;
      padding: 0.32rem 0.7rem; border-radius: 999px;
      background: #f8f9fc; border: 1px solid #e8eaf0;
      width: fit-content; font-weight: 500;
    }
    .ws-pill.ws-live { color: #059669; background: #f0fdf4; border-color: #86efac; }
    .ws-dot { width: 6px; height: 6px; border-radius: 50%; background: #d1d5db; flex-shrink: 0; }
    .ws-pill.ws-live .ws-dot {
      background: #059669;
      box-shadow: 0 0 0 3px rgba(5,150,105,.15);
      animation: dot-pulse 1.5s ease-in-out infinite;
    }
    @keyframes dot-pulse { 0%,100%{opacity:1} 50%{opacity:.3} }

    /* ── User pill ───────────────────────────────────────────────── */
    .user-pill {
      display: flex;
      align-items: center;
      gap: 0.45rem;
      padding: 0.35rem 0.5rem;
      border-radius: 8px;
      background: #f8f9fc;
      border: 1px solid #e8eaf0;
    }
    .user-avatar {
      width: 22px;
      height: 22px;
      border-radius: 50%;
      background: #4f46e5;
      color: #fff;
      font-size: 0.65rem;
      font-weight: 700;
      display: flex;
      align-items: center;
      justify-content: center;
      flex-shrink: 0;
    }
    .user-name {
      font-size: 0.72rem;
      color: #374151;
      font-weight: 500;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      flex: 1;
      min-width: 0;
    }
    .btn-logout {
      background: transparent;
      border: none;
      padding: 0.15rem;
      cursor: pointer;
      color: #9ca3af;
      font-size: 0.75rem;
      line-height: 1;
      flex-shrink: 0;
      transition: color 0.12s;
    }
    .btn-logout:hover { color: #dc2626; }

    /* ── Main ────────────────────────────────────────────────────── */
    .main { flex: 1; padding: 1.75rem 2rem; overflow: hidden; min-width: 0; }

    /* ── Responsive ──────────────────────────────────────────────── */
    @media (max-width: 768px) {
      .sidenav { width: 164px; }
      .brand-name { font-size: 0.83rem; }
      .main { padding: 1.25rem; }
    }
  `],
})
export class AppComponent implements OnInit, OnDestroy {
  alertCount = 0;
  private sub?: Subscription;

  constructor(
    public ws: WebSocketService,
    private api: ApiService,
    public auth: AuthService,
    private router: Router,
  ) {
    ws.connect();
  }

  get userInitial(): string {
    const u = this.auth.user();
    if (!u) return '?';
    return (u.full_name || u.email || '?')[0].toUpperCase();
  }

  logout(): void {
    this.auth.logout();
  }

  ngOnInit(): void {
    this.sub = this.ws.messages.subscribe(msg => {
      if (!msg) return;
      const m = msg as any;
      if (m.type === 'incident' || m.type === 'incident_batch' ||
          m.severity === 'critical' || m.label === 1) {
        this.alertCount += m.count || 1;
      }
      this._evaluateAlertRules(m);
    });
  }

  ngOnDestroy(): void {
    this.sub?.unsubscribe();
  }



  private _evaluateAlertRules(msg: any): void {
    try {
      const rules: any[] = JSON.parse(localStorage.getItem('cl_alert_rules') || '[]');
      let changed = false;
      for (const rule of rules) {
        if (!rule.enabled) continue;
        if (this._ruleMatches(rule, msg)) {
          this._fireAlert(rule, msg);
          rule.triggerCount = (rule.triggerCount || 0) + 1;
          changed = true;
        }
      }
      if (changed) localStorage.setItem('cl_alert_rules', JSON.stringify(rules));
    } catch {  }
  }

  private _ruleMatches(rule: any, msg: any): boolean {
    const sev    = (msg?.severity || '').toLowerCase();
    const label  = msg?.label;
    const layers = msg?.attributes?.layers || [];
    const type   = (msg?.type || '').toLowerCase();
    const entity = msg?.entity;

    switch (rule.condition) {
      case 'any_anomaly':       return label === 1 || type === 'anomaly';
      case 'critical_severity': return sev === 'critical';
      case 'high_severity':     return sev === 'high' || sev === 'critical';
      case 'cross_layer':       return layers.length > 1 || type.includes('cross-layer') || type === 'incident_batch';
      case 'entity_repeat':     return !!entity;
      default:                  return false;
    }
  }

  private _fireAlert(rule: any, msg: any): void {
    const title = `CrossLayer: ${rule.name}`;
    const body  = `${rule.condition.replace(/_/g, ' ')} — ${msg?.type || msg?.severity || 'event detected'}`;

    if (rule.notifyMethod === 'browser') {
      if ((window as any).Notification?.permission === 'granted') {
        new (window as any).Notification(title, { body, icon: '/favicon.ico' });
      } else if ((window as any).Notification?.permission !== 'denied') {
        (window as any).Notification?.requestPermission?.().then((p: string) => {
          if (p === 'granted') new (window as any).Notification(title, { body, icon: '/favicon.ico' });
        });
      }
    }

    if (rule.notifyMethod === 'webhook' && rule.notifyTarget) {
      fetch(rule.notifyTarget, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rule: rule.name, condition: rule.condition, event: msg, timestamp: new Date().toISOString() }),
      }).catch(() => {  });
    }

    if (rule.notifyMethod === 'email' && rule.notifyTarget) {
      this.api.sendAlertEmail(rule.notifyTarget, rule.name, rule.condition, false)
        .subscribe({ error: () => {  } });
    }
  }
}
