import { Routes } from '@angular/router';
import { authGuard } from './core/guards/auth.guard';

export const routes: Routes = [
  { path: '', redirectTo: 'dashboard', pathMatch: 'full' },


  {
    path: 'login',
    loadComponent: () => import('./features/login/login.component').then(m => m.LoginComponent),
  },


  { path: 'dashboard',     canActivate: [authGuard], loadComponent: () => import('./features/dashboard/dashboard.component').then(m => m.DashboardComponent) },
  { path: 'logs',          canActivate: [authGuard], loadComponent: () => import('./features/logs/logs.component').then(m => m.LogsComponent) },
  { path: 'incidents',     canActivate: [authGuard], loadComponent: () => import('./features/incidents/incidents.component').then(m => m.IncidentsComponent) },
  { path: 'statistics',    canActivate: [authGuard], loadComponent: () => import('./features/statistics/statistics.component').then(m => m.StatisticsComponent) },
  { path: 'analysis',      canActivate: [authGuard], loadComponent: () => import('./features/analysis/analysis.component').then(m => m.AnalysisComponent) },
  { path: 'heatmap',       canActivate: [authGuard], loadComponent: () => import('./features/heatmap/heatmap.component').then(m => m.HeatmapComponent) },
  { path: 'entities',      canActivate: [authGuard], loadComponent: () => import('./features/entities/entities.component').then(m => m.EntitiesComponent) },
  { path: 'attack-chains', canActivate: [authGuard], loadComponent: () => import('./features/attack-chains/attack-chains.component').then(m => m.AttackChainsComponent) },
  { path: 'reports',       canActivate: [authGuard], loadComponent: () => import('./features/reports/reports.component').then(m => m.ReportsComponent) },
  { path: 'alert-rules',   canActivate: [authGuard], loadComponent: () => import('./features/alert-rules/alert-rules.component').then(m => m.AlertRulesComponent) },
{ path: 'response-rules', canActivate: [authGuard], loadComponent: () => import('./features/response-rules/response-rules.component').then(m => m.ResponseRulesComponent) },

  { path: '**', redirectTo: 'dashboard' },
];
