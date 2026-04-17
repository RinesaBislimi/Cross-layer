import { Routes } from '@angular/router';

export const routes: Routes = [
  { path: '', redirectTo: 'dashboard', pathMatch: 'full' },
  { path: 'dashboard', loadComponent: () => import('./features/dashboard/dashboard.component').then(m => m.DashboardComponent) },
  { path: 'logs', loadComponent: () => import('./features/logs/logs.component').then(m => m.LogsComponent) },
  { path: 'incidents', loadComponent: () => import('./features/incidents/incidents.component').then(m => m.IncidentsComponent) },
  { path: 'statistics', loadComponent: () => import('./features/statistics/statistics.component').then(m => m.StatisticsComponent) },
  { path: 'analysis', loadComponent: () => import('./features/analysis/analysis.component').then(m => m.AnalysisComponent) },
  { path: 'ai-assistant', loadComponent: () => import('./features/ai-assistant/ai-assistant.component').then(m => m.AiAssistantComponent) },
  { path: '**', redirectTo: 'dashboard' },
];
