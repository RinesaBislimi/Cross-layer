import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { HttpClient } from '@angular/common/http';

interface HeatCell { hour: number; dow: number; total: number; anomalies: number; }

@Component({
  selector: 'app-heatmap',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './heatmap.component.html',
  styleUrls: ['./heatmap.component.css'],
})
export class HeatmapComponent implements OnInit {
  cells: HeatCell[] = [];
  loading = true;
  error: string | null = null;
  sampleSize = 0;

  hours = Array.from({ length: 24 }, (_, i) => i);
  days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

  dowOrder = [2, 3, 4, 5, 6, 7, 1];

  maxAnomalies = 0;
  totalAnomalies = 0;
  peakHour = 0;
  peakDay = '';

  hoveredCell: HeatCell | null = null;
  hoveredLabel = '';

  constructor(private http: HttpClient) {}

  ngOnInit() {
    this.http
      .get<{ data: HeatCell[]; sample_size: number }>('http://127.0.0.1:8000/analytics/heatmap')
      .subscribe({
        next: (res) => {
          this.cells = res.data;
          this.sampleSize = res.sample_size;
          this.compute();
          this.loading = false;
        },
        error: (e) => {
          this.error = e.message || 'Failed to load heatmap data';
          this.loading = false;
        },
      });
  }

  compute() {
    this.maxAnomalies = Math.max(...this.cells.map((c) => c.anomalies), 1);
    this.totalAnomalies = this.cells.reduce((s, c) => s + c.anomalies, 0);


    const hourTotals = Array(24).fill(0);
    this.cells.forEach((c) => (hourTotals[c.hour] += c.anomalies));
    this.peakHour = hourTotals.indexOf(Math.max(...hourTotals));


    const dayTotals: Record<number, number> = {};
    this.dowOrder.forEach((d) => (dayTotals[d] = 0));
    this.cells.forEach((c) => (dayTotals[c.dow] = (dayTotals[c.dow] || 0) + c.anomalies));
    const peakDow = Object.entries(dayTotals).sort((a, b) => b[1] - a[1])[0]?.[0];
    const dowToDay: Record<number, string> = {
      2: 'Monday',
      3: 'Tuesday',
      4: 'Wednesday',
      5: 'Thursday',
      6: 'Friday',
      7: 'Saturday',
      1: 'Sunday',
    };
    this.peakDay = dowToDay[Number(peakDow)] || '';
  }

  getCell(dow: number, hour: number): HeatCell | null {
    return this.cells.find((c) => c.dow === dow && c.hour === hour) || null;
  }

  getCellColor(cell: HeatCell | null): string {
    if (!cell || cell.anomalies === 0) return '#f0f1f5';
    const ratio = cell.anomalies / this.maxAnomalies;
    if (ratio > 0.75) return '#ef4444';
    if (ratio > 0.5) return '#f97316';
    if (ratio > 0.25) return '#fbbf24';
    if (ratio > 0.1) return '#fde68a';
    return '#fef9c3';
  }

  getCellTextColor(cell: HeatCell | null): string {
    if (!cell || cell.anomalies === 0) return 'transparent';
    const ratio = cell.anomalies / this.maxAnomalies;
    return ratio > 0.5 ? '#fff' : '#1a1a1a';
  }

  onCellEnter(cell: HeatCell | null, dow: number, hour: number) {
    this.hoveredCell = cell;
    const dowToDay: Record<number, string> = {
      2: 'Mon',
      3: 'Tue',
      4: 'Wed',
      5: 'Thu',
      6: 'Fri',
      7: 'Sat',
      1: 'Sun',
    };
    const dayName = dowToDay[dow] || '';
    const count = cell?.anomalies ?? 0;
    const total = cell?.total ?? 0;
    this.hoveredLabel = `${dayName} ${hour}:00 — ${count} anomalies / ${total} total`;
  }

  onCellLeave() {
    this.hoveredCell = null;
    this.hoveredLabel = '';
  }

  formatHour(h: number): string {
    if (h === 0) return '12a';
    if (h < 12) return `${h}a`;
    if (h === 12) return '12p';
    return `${h - 12}p`;
  }

  get legendStops(): { color: string; label: string }[] {
    return [
      { color: '#f0f1f5', label: '0' },
      { color: '#fef9c3', label: 'low' },
      { color: '#fde68a', label: '' },
      { color: '#fbbf24', label: 'med' },
      { color: '#f97316', label: '' },
      { color: '#ef4444', label: 'high' },
    ];
  }
}
