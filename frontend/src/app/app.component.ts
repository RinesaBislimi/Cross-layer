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
          <span class="brand-icon">🛡</span>
          <span class="brand-name">CrossLayer</span>
        </div>

        <div class="nav-links">
          <a routerLink="/dashboard"   routerLinkActive="active" [routerLinkActiveOptions]="{ exact: true }" class="nav-link">
            <span class="nav-icon">🏠</span><span class="nav-label">Dashboard</span>
          </a>
          <a routerLink="/logs"        routerLinkActive="active" class="nav-link">
            <span class="nav-icon">📋</span><span class="nav-label">Logs</span>
          </a>
          <a routerLink="/incidents"   routerLinkActive="active" class="nav-link">
            <span class="nav-icon">🚨</span>
            <span class="nav-label">Incidents</span>
            <span class="nav-badge" *ngIf="alertCount > 0">{{ alertCount > 99 ? '99+' : alertCount }}</span>
          </a>
          <a routerLink="/statistics"  routerLinkActive="active" class="nav-link">
            <span class="nav-icon">📊</span><span class="nav-label">Statistics</span>
          </a>
          <a routerLink="/analysis"    routerLinkActive="active" class="nav-link">
            <span class="nav-icon">🤖</span><span class="nav-label">ML Analysis</span>
          </a>
          <a routerLink="/ai-assistant" routerLinkActive="active" class="nav-link">
            <span class="nav-icon">💬</span><span class="nav-label">AI Assistant</span>
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
    /* Layout */
    .layout { display: flex; min-height: 100vh; background: #f8fafc; }

    /* Sidebar */
    .sidenav {
      width: 218px;
      min-height: 100vh;
      background: #ffffff;
      border-right: 1px solid #e2e8f0;
      display: flex;
      flex-direction: column;
      position: sticky;
      top: 0;
      height: 100vh;
      overflow-y: auto;
      flex-shrink: 0;
      box-shadow: 2px 0 8px rgba(15,23,42,.04);
    }

    /* Brand */
    .nav-brand {
      display: flex;
      align-items: center;
      gap: 0.65rem;
      padding: 1.15rem 1.25rem 1rem;
      border-bottom: 1px solid #f1f5f9;
    }
    .brand-icon {
      font-size: 1.35rem;
      background: linear-gradient(135deg,#4f46e5,#7c3aed);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
    }
    .brand-name {
      font-size: 1rem; font-weight: 800; letter-spacing: -0.03em;
      background: linear-gradient(135deg,#0f172a 0%,#4f46e5 100%);
      -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;
    }

    /* Nav links */
    .nav-links { display: flex; flex-direction: column; gap: 0.2rem; padding: 0.85rem 0.65rem; flex: 1; }
    .nav-link {
      display: flex;
      align-items: center;
      gap: 0.7rem;
      padding: 0.6rem 0.8rem;
      border-radius: 10px;
      color: #64748b;
      font-size: 0.875rem;
      font-weight: 500;
      text-decoration: none;
      transition: background 0.13s, color 0.13s;
      position: relative;
    }
    .nav-link:hover { background: #f1f5f9; color: #0f172a; text-decoration: none; }
    .nav-link.active {
      background: linear-gradient(135deg,#eef2ff 0%,#e0e7ff 100%);
      color: #4f46e5; font-weight: 700;
      box-shadow: inset 0 0 0 1px #c7d2fe;
    }
    .nav-icon { font-size: 1.05rem; flex-shrink: 0; }
    .nav-label { flex: 1; }

    /* Alert badge */
    .nav-badge {
      background: #dc2626; color: #fff;
      font-size: 0.65rem; font-weight: 800;
      padding: 0.1rem 0.4rem; border-radius: 999px;
      min-width: 18px; text-align: center;
      box-shadow: 0 0 0 2px #fff;
      animation: badge-pulse 2s ease-in-out infinite;
    }
    @keyframes badge-pulse { 0%,100%{opacity:1;transform:scale(1)} 50%{opacity:.75;transform:scale(.92)} }

    /* Footer */
    .nav-footer {
      padding: 0.85rem 1rem;
      border-top: 1px solid #f1f5f9;
      background: #fafafa;
    }
    .ws-pill {
      display: flex; align-items: center; gap: 0.45rem;
      font-size: 0.72rem; color: #94a3b8;
      padding: 0.35rem 0.7rem; border-radius: 999px;
      background: #f1f5f9; border: 1px solid #e2e8f0;
      width: fit-content; font-weight: 500;
    }
    .ws-pill.ws-live { color: #059669; background: #f0fdf4; border-color: #86efac; }
    .ws-dot { width: 7px; height: 7px; border-radius: 50%; background: #cbd5e1; }
    .ws-pill.ws-live .ws-dot {
      background: #059669;
      box-shadow: 0 0 0 3px rgba(5,150,105,.2);
      animation: dot-pulse 1.5s ease-in-out infinite;
    }
    @keyframes dot-pulse { 0%,100%{opacity:1} 50%{opacity:.35} }

    /* Main */
    .main { flex: 1; padding: 1.75rem 2rem; overflow: hidden; min-width: 0; }

    /* Responsive */
    @media (max-width: 768px) {
      .sidenav { width: 60px; }
      .brand-name, .nav-label, .ws-pill span:last-child { display: none; }
      .nav-brand { justify-content: center; padding: 1rem 0.5rem; }
      .brand-icon { font-size: 1.4rem; }
      .nav-link { justify-content: center; padding: 0.65rem; gap: 0; }
      .nav-icon { font-size: 1.2rem; }
      .nav-badge { position: absolute; top: 3px; right: 3px; }
      .nav-footer { padding: 0.5rem; display: flex; justify-content: center; background: none; }
      .ws-pill { padding: 0.35rem; border-radius: 50%; }
      .ws-dot { width: 9px; height: 9px; }
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
