import { Component, OnDestroy, OnInit } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { CommonModule } from '@angular/common';
import { Subscription } from 'rxjs';
import { WebSocketService } from './core/services/websocket.service';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [RouterLink, RouterLinkActive, RouterOutlet, CommonModule],
  template: `
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
          <a routerLink="/alert-rules"   routerLinkActive="active" class="nav-link">
            <span class="nav-label">Alert Rules</span>
          </a>
        </div>

        <div class="nav-footer">
          <div class="ws-pill" [class.ws-live]="ws.isConnected">
            <span class="ws-dot"></span>
            <span>{{ ws.isConnected ? 'Live' : 'Offline' }}</span>
          </div>
        </div>
      </nav>

      <!-- Main content -->
      <main class="main">
        <router-outlet></router-outlet>
      </main>
    </div>
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
      -webkit-background-clip: initial;
      -webkit-text-fill-color: initial;
      background-clip: initial;
      background: none;
    }

    /* ── Nav links ───────────────────────────────────────────────── */
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

  constructor(public ws: WebSocketService) {
    ws.connect();
  }

  ngOnInit(): void {
    this.sub = this.ws.messages.subscribe(msg => {
      if (msg && ((msg as any).type === 'incident' || (msg as any).severity === 'critical' || (msg as any).label === 1)) {
        this.alertCount++;
      }
    });
  }

  ngOnDestroy(): void {
    this.sub?.unsubscribe();
  }
}
