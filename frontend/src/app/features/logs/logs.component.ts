import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ApiService } from '../../core/services/api.service';
import { LogEvent } from '../../shared/models/log-event';

interface FeatureTip { name: string; value: string; level: 'high' | 'medium' | 'low'; }

@Component({
  selector: 'app-logs',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './logs.component.html',
  styleUrls: ['./logs.component.css'],
})
export class LogsComponent implements OnInit {
  allLogs:       LogEvent[] = [];
  layerFilter    = '';
  sourceFilter   = '';
  anomalyFilter: 'all' | 'normal' | 'anomaly' = 'all';
  searchText     = '';
  limit          = 200;
  pageSize       = 50;
  currentPage    = 0;
  loading        = false;
  error: string | null = null;
  expandedId:    number | null = null;

  layers  = ['system', 'network', 'application', 'security'];
  sources = ['BGL', 'CICIDS2017', 'TDA'];

  constructor(private api: ApiService) {}

  ngOnInit(): void { this.load(); }

  load(): void {
    this.loading = true;
    this.error   = null;
    this.currentPage = 0;
    const params: { layer?: string; source?: string; limit: number } = { limit: this.limit };
    if (this.layerFilter)  params.layer  = this.layerFilter;
    if (this.sourceFilter) params.source = this.sourceFilter;
    this.api.getLogs(params).subscribe({
      next:  (list) => { this.allLogs = list; this.loading = false; },
      error: (err)  => { this.error = err?.message || 'Failed to load logs'; this.loading = false; },
    });
  }

  get filteredLogs(): LogEvent[] {
    let logs = this.allLogs;
    if (this.searchText.trim()) {
      const q = this.searchText.toLowerCase();
      logs = logs.filter(l =>
        (l.raw     || '').toLowerCase().includes(q) ||
        (l.entity  || '').toLowerCase().includes(q) ||
        (l.source  || '').toLowerCase().includes(q)
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

  get totalPages(): number { return Math.ceil(this.filteredLogs.length / this.pageSize); }
  get anomalyCount(): number { return this.allLogs.filter(l => l.label === 1).length; }
  get normalCount():  number { return this.allLogs.filter(l => l.label !== 1).length; }

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




  confidencePct(log: LogEvent): number | null {
    if (log.confidence == null) return null;
    return Math.round(log.confidence * 100);
  }

  confidenceLabel(pct: number): string {
    if (pct >= 90) return 'Very high';
    if (pct >= 70) return 'High';
    if (pct >= 50) return 'Moderate';
    return 'Low';
  }

  confidenceClass(pct: number): string {
    if (pct >= 90) return 'conf-critical';
    if (pct >= 70) return 'conf-high';
    if (pct >= 50) return 'conf-medium';
    return 'conf-low';
  }


  topFeatures(log: LogEvent): FeatureTip[] {
    if (!log.features) return [];
    const entries = Object.entries(log.features)
      .filter(([, v]) => typeof v === 'number' && isFinite(v as number))
      .map(([k, v]) => ({ k, v: v as number, abs: Math.abs(v as number) }))
      .sort((a, b) => b.abs - a.abs)
      .slice(0, 5);

    if (!entries.length) return [];

    const maxAbs = entries[0].abs || 1;
    return entries.map(e => ({
      name:  e.k.replace(/_/g, ' '),
      value: Number.isInteger(e.v) ? e.v.toLocaleString() : e.v.toFixed(4),
      level: (e.abs / maxAbs > 0.7 ? 'high' : e.abs / maxAbs > 0.3 ? 'medium' : 'low') as 'high' | 'medium' | 'low',
    }));
  }


  anomalySignals(log: LogEvent): string[] {
    const signals: string[] = [];
    const raw   = (log.raw     || '').toUpperCase();
    const msg   = (log.message || '').toUpperCase();
    const text  = raw + ' ' + msg;
    const feats = log.features || {};

    const src = (log.source || '').toUpperCase();

    if (src.includes('BGL')) {

      if (/FATAL|FAILURE|FAIL|HARDWARE|FAULT/.test(text))   signals.push('Hardware fault detected');
      if (/UNCORRECTABLE|ECC|PARITY/.test(text))             signals.push('Memory error (ECC / parity)');
      if (/KERNEL PANIC|OOPS|BUG:/.test(text))              signals.push('Kernel panic / oops');
      if (/TIMEOUT|HUNG|DEADLOCK/.test(text))               signals.push('Timeout or hang condition');
      if (/TEMPERATURE|THERMAL|OVERHEAT/.test(text))        signals.push('Thermal anomaly');
    }

    if (src.includes('CICIDS')) {

      const bps   = (feats['Flow Bytes/s']     ?? feats['flow_bytes_s']     ?? 0) as number;
      const pps   = (feats['Flow Packets/s']   ?? feats['flow_packets_s']   ?? 0) as number;
      const dur   = (feats['Flow Duration']    ?? feats['flow_duration']    ?? -1) as number;
      const synF  = (feats['SYN Flag Count']   ?? feats['syn_flag_count']   ?? 0) as number;
      const rstF  = (feats['RST Flag Count']   ?? feats['rst_flag_count']   ?? 0) as number;
      const fwdP  = (feats['Total Fwd Packets']?? feats['total_fwd_packets']?? 0) as number;

      if (bps  > 1_000_000) signals.push(`High flow rate: ${(bps/1e6).toFixed(1)} MB/s`);
      if (pps  > 10_000)    signals.push(`High packet rate: ${pps.toFixed(0)} pkt/s`);
      if (dur  >= 0 && dur < 100 && fwdP > 500) signals.push('Short burst with many packets (DoS pattern)');
      if (synF > 50)        signals.push(`SYN flood indicator: ${synF} SYN flags`);
      if (rstF > 30)        signals.push(`Port scan / reset storm: ${rstF} RST flags`);
      if (/PORTSCAN|SCAN|BRUTE|DDOS|DOS|BOT/.test(text)) signals.push('Attack keyword in label/metadata');
    }

    if (src.includes('TDA')) {

      if (/DROP|TRUNCATE|DELETE\s+FROM\s+\w+\s*;/.test(text)) signals.push('Destructive SQL command');
      if (/UNION\s+SELECT|1=1|OR\s+1|--\s/.test(text))        signals.push('SQL injection pattern');
      if (/EXEC|EXECUTE|XP_|SP_/.test(text))                  signals.push('Stored procedure / exec call');
      if (/SELECT\s+\*\s+FROM/.test(text))                    signals.push('Bulk data dump (SELECT *)');
      const q = (feats['query_count'] ?? feats['num_queries'] ?? 0) as number;
      if (q > 1000) signals.push(`High query volume: ${q.toLocaleString()} queries`);
    }


    if (/PRIVILEGE|ROOT|SUDO|ADMIN|ESCALAT/.test(text)) signals.push('Privilege escalation keyword');
    if (/BRUTE|PASSWORD|AUTH\s+FAIL|INVALID\s+USER/.test(text)) signals.push('Authentication failure pattern');
    if (/MALWARE|RANSOMWARE|EXPLOIT|SHELLCODE/.test(text)) signals.push('Malware keyword detected');

    return signals;
  }

}
