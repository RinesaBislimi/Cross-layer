import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ApiService } from '../../core/services/api.service';
import { LogEvent } from '../../shared/models/log-event';

@Component({
  selector: 'app-logs',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './logs.component.html',
  styleUrls: ['./logs.component.css'],
})
export class LogsComponent implements OnInit {
  allLogs: LogEvent[] = [];
  layerFilter = '';
  sourceFilter = '';
  anomalyFilter: 'all' | 'normal' | 'anomaly' = 'all';
  searchText = '';
  limit = 200;
  pageSize = 50;
  currentPage = 0;
  loading = false;
  error: string | null = null;
  expandedId: number | null = null;

  layers = ['system', 'network', 'application', 'security'];
  sources = ['BGL', 'CICIDS2017', 'TDA'];

  constructor(private api: ApiService) {}

  ngOnInit(): void { this.load(); }

  load(): void {
    this.loading = true;
    this.error = null;
    this.currentPage = 0;
    const params: { layer?: string; source?: string; limit: number } = { limit: this.limit };
    if (this.layerFilter) params.layer = this.layerFilter;
    if (this.sourceFilter) params.source = this.sourceFilter;
    this.api.getLogs(params).subscribe({
      next: (list) => { this.allLogs = list; this.loading = false; },
      error: (err) => { this.error = err?.message || 'Failed to load logs'; this.loading = false; },
    });
  }

  get filteredLogs(): LogEvent[] {
    let logs = this.allLogs;
    if (this.searchText.trim()) {
      const q = this.searchText.toLowerCase();
      logs = logs.filter(l =>
        (l.raw || '').toLowerCase().includes(q) ||
        (l.entity || '').toLowerCase().includes(q) ||
        (l.source || '').toLowerCase().includes(q)
      );
    }
    if (this.anomalyFilter === 'anomaly') logs = logs.filter(l => l.label === 1);
    if (this.anomalyFilter === 'normal')  logs = logs.filter(l => l.label !== 1);
    return logs;
  }

  get pagedLogs(): LogEvent[] {
    const start = this.currentPage * this.pageSize;
    return this.filteredLogs.slice(start, start + this.pageSize);
  }

  get totalPages(): number {
    return Math.ceil(this.filteredLogs.length / this.pageSize);
  }

  get anomalyCount(): number { return this.allLogs.filter(l => l.label === 1).length; }
  get normalCount(): number  { return this.allLogs.filter(l => l.label !== 1).length; }

  prevPage(): void { if (this.currentPage > 0) this.currentPage--; }
  nextPage(): void { if (this.currentPage < this.totalPages - 1) this.currentPage++; }

  toggleExpand(id: number): void {
    this.expandedId = this.expandedId === id ? null : id;
  }

  onFilterChange(): void { this.currentPage = 0; }

  formatDate(s: string): string { return new Date(s).toLocaleString(); }

  featuresJson(f: Record<string, unknown> | null): string {
    if (!f) return 'null';
    try { return JSON.stringify(f, null, 2); } catch { return String(f); }
  }
}
