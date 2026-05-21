import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ApiService } from '../../core/services/api.service';

interface ResponseRule {
  id:             number;
  name:           string;
  description:    string;
  condition:      string;
  layer:          string;
  action_type:    string;
  action_target:  string;
  action_payload: string;
  enabled:        boolean;
  created_at:     string;
  trigger_count:  number;
  last_fired_at:  string | null;
}

interface NewRule {
  name:           string;
  description:    string;
  condition:      string;
  layer:          string;
  action_type:    string;
  action_target:  string;
  action_payload: string;
}

@Component({
  selector: 'app-response-rules',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './response-rules.component.html',
  styleUrls: ['./response-rules.component.css'],
})
export class ResponseRulesComponent implements OnInit {
  rules:     ResponseRule[] = [];
  loading    = true;
  loadError  = '';
  showForm   = false;
  formError  = '';
  testFeedback: Record<number, string> = {};

  newRule: NewRule = this._blank();

  conditions = [
    { value: 'any_anomaly',       label: 'Any anomaly detected' },
    { value: 'critical_severity', label: 'Critical severity' },
    { value: 'high_severity',     label: 'High or critical severity' },
    { value: 'cross_layer',       label: 'Cross-layer incident' },
    { value: 'entity_repeat',     label: 'Entity repeat activity' },
  ];

  layers = [
    { value: '',            label: 'All layers' },
    { value: 'system',      label: 'System' },
    { value: 'network',     label: 'Network' },
    { value: 'application', label: 'Application' },
  ];

  actionTypes = [
    { value: 'webhook',      label: 'Webhook POST' },
    { value: 'email_team',   label: 'Email team' },
    { value: 'block_ip',     label: 'Block IP (log action)' },
    { value: 'isolate_host', label: 'Isolate host (log action)' },
    { value: 'create_ticket', label: 'Create ticket (log action)' },
  ];

  constructor(private api: ApiService) {}

  ngOnInit(): void { this.loadRules(); }

  loadRules(): void {
    this.loading   = true;
    this.loadError = '';
    this.api.getResponseRules().subscribe({
      next: (r) => { this.rules = r; this.loading = false; },
      error: () => { this.loadError = 'Failed to load response rules.'; this.loading = false; },
    });
  }

  openForm(): void { this.showForm = true; this.formError = ''; }

  resetForm(): void { this.showForm = false; this.formError = ''; this.newRule = this._blank(); }

  addRule(): void {
    this.formError = '';
    const p = this.newRule;
    if (!p.name.trim()) { this.formError = 'Rule name is required.'; return; }
    this.api.createResponseRule({
      name:           p.name.trim(),
      description:    p.description.trim(),
      condition:      p.condition,
      layer:          p.layer,
      action_type:    p.action_type,
      action_target:  p.action_target.trim(),
      action_payload: p.action_payload.trim() || '{}',
    }).subscribe({
      next: (r) => { this.rules.unshift(r as ResponseRule); this.resetForm(); },
      error: (e) => { this.formError = e?.error?.detail || 'Failed to create rule.'; },
    });
  }

  deleteRule(id: number): void {
    if (!confirm('Delete this response rule?')) return;
    this.api.deleteResponseRule(id).subscribe({
      next: () => { this.rules = this.rules.filter(r => r.id !== id); },
    });
  }

  toggleRule(id: number): void {
    this.api.toggleResponseRule(id).subscribe({
      next: (r: any) => {
        const idx = this.rules.findIndex(x => x.id === id);
        if (idx >= 0) this.rules[idx] = r;
      },
    });
  }

  testRule(rule: ResponseRule): void {
    this.testFeedback[rule.id] = '…';
    this.api.testResponseRule(rule.id).subscribe({
      next: (res: any) => {
        const m = res.matched ?? 0;
        this.testFeedback[rule.id] = m > 0
          ? `✓ Matched ${m} incident(s) — action would fire: ${rule.action_type}`
          : 'ℹ No incidents matched the rule condition';
        setTimeout(() => delete this.testFeedback[rule.id], 6000);
      },
      error: () => {
        this.testFeedback[rule.id] = '✕ Test failed';
        setTimeout(() => delete this.testFeedback[rule.id], 4000);
      },
    });
  }

  needsTarget(action: string): boolean {
    return action === 'webhook' || action === 'email_team';
  }

  actionLabel(a: string): string {
    return this.actionTypes.find(x => x.value === a)?.label ?? a;
  }

  conditionLabel(c: string): string {
    return this.conditions.find(x => x.value === c)?.label ?? c;
  }

  layerLabel(l: string): string {
    return this.layers.find(x => x.value === l)?.label ?? 'All layers';
  }

  formatDate(s: string): string {
    if (!s) return '';
    try { return new Date(s).toLocaleDateString(); } catch { return s; }
  }

  formatLastFired(s: string | null): string {
    if (!s) return 'Never';
    try {
      const d = new Date(s);
      return d.toLocaleString();
    } catch { return s; }
  }

  actionBadgeClass(a: string): string {
    const map: Record<string, string> = {
      webhook: 'action-webhook', email_team: 'action-email',
      block_ip: 'action-block', isolate_host: 'action-isolate',
      create_ticket: 'action-ticket',
    };
    return map[a] || '';
  }

  private _blank(): NewRule {
    return {
      name: '', description: '', condition: 'critical_severity',
      layer: '', action_type: 'webhook', action_target: '', action_payload: '{}',
    };
  }
}
