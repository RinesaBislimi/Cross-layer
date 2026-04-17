import { Routes } from '@angular/router';

export const routes: Routes = [
  { path: '', redirectTo: 'dashboard', pathMatch: 'full' },
  { path: 'dashboard',     loadComponent: () => import('./features/dashboard/dashboard.component').then(m => m.DashboardComponent) },
  { path: 'logs',          loadComponent: () => import('./features/logs/logs.component').then(m => m.LogsComponent) },
  { path: 'incidents',     loadComponent: () => import('./features/incidents/incidents.component').then(m => m.IncidentsComponent) },
  { path: 'statistics',    loadComponent: () => import('./features/statistics/statistics.component').then(m => m.StatisticsComponent) },
  { path: 'analysis',      loadComponent: () => import('./features/analysis/analysis.component').then(m => m.AnalysisComponent) },
  { path: 'heatmap',       loadComponent: () => import('./features/heatmap/heatmap.component').then(m => m.HeatmapComponent) },
  { path: 'entities',      loadComponent: () => import('./features/entities/entities.component').then(m => m.EntitiesComponent) },
  { path: 'attack-chains', loadComponent: () => import('./features/attack-chains/attack-chains.component').then(m => m.AttackChainsComponent) },
  { path: 'reports',       loadComponent: () => import('./features/reports/reports.component').then(m => m.ReportsComponent) },
  { path: 'alert-rules',   loadComponent: () => import('./features/alert-rules/alert-rules.component').then(m => m.AlertRulesComponent) },
  { path: '**', redirectTo: 'dashboard' },
];
