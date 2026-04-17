import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';

interface AlertRule {
  id: string;
  name: string;
  condition: 'any_anomaly' | 'critical_severity' | 'high_severity' | 'cross_layer' | 'entity_repeat';
  layer: string; // '' = all layers
  notifyMethod: 'browser' | 'webhook' | 'email';
  notifyTarget: string; // webhook URL or email
  enabled: boolean;
  createdAt: string;
  triggerCount: number;
}

@Component({
  selector: 'app-alert-rules',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './alert-rules.component.html',
  styleUrls: ['./alert-rules.component.css'],
})
export class AlertRulesComponent implements OnInit {
  rules: AlertRule[] = [];
  showForm = false;
  formError: string | null = null;

  newRule: Partial<AlertRule> = this.blankRule();

  conditions: { value: AlertRule['condition']; label: string }[] = [
    { value: 'any_anomaly',       label: 'Any anomaly detected' },
    { value: 'critical_severity', label: 'Critical severity incident' },
    { value: 'high_severity',     label: 'High severity incident' },
    { value: 'cross_layer',       label: 'Cross-layer attack chain' },
    { value: 'entity_repeat',     label: 'Entity flagged 2+ times' },
  ];

  layers: { value: string; label: string }[] = [
    { value: '',            label: 'All layers' },
    { value: 'system',      label: 'System' },
    { value: 'network',     label: 'Network' },
    { value: 'application', label: 'Application' },
    { value: 'security',    label: 'Security' },
  ];

  notifyMethods: { value: AlertRule['notifyMethod']; label: string }[] = [
    { value: 'browser', label: 'Browser notification' },
    { value: 'webhook', label: 'Webhook' },
    { value: 'email',   label: 'Email' },
  ];

  ngOnInit() {
    this.load();
  }

  load() {
    try {
      const raw = localStorage.getItem('cl_alert_rules');
      this.rules = raw ? JSON.parse(raw) : [];
    } catch {
      this.rules = [];
    }
  }

  save() {
    localStorage.setItem('cl_alert_rules', JSON.stringify(this.rules));
  }

  addRule() {
    this.formError = null;
    if (!this.newRule.name?.trim()) {
      this.formError = 'Rule name is required.';
      return;
    }
    if (!this.newRule.condition) {
      this.formError = 'Please select a condition.';
      return;
    }
    if (!this.newRule.notifyMethod) {
      this.formError = 'Please select a notification method.';
      return;
    }
    if (
      (this.newRule.notifyMethod === 'webhook' || this.newRule.notifyMethod === 'email') &&
      !this.newRule.notifyTarget?.trim()
    ) {
      this.formError = `Please enter a ${this.newRule.notifyMethod === 'webhook' ? 'webhook URL' : 'email address'}.`;
      return;
    }

    const rule: AlertRule = {
      id: `rule_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`,
      name: this.newRule.name!.trim(),
      condition: this.newRule.condition!,
      layer: this.newRule.layer ?? '',
      notifyMethod: this.newRule.notifyMethod!,
      notifyTarget: this.newRule.notifyTarget?.trim() ?? '',
      enabled: true,
      createdAt: new Date().toISOString(),
      triggerCount: 0,
    };

    this.rules = [rule, ...this.rules];
    this.save();
    this.resetForm();
  }

  deleteRule(id: string) {
    this.rules = this.rules.filter((r) => r.id !== id);
    this.save();
  }

  toggleRule(id: string) {
    const rule = this.rules.find((r) => r.id === id);
    if (rule) {
      rule.enabled = !rule.enabled;
      this.save();
    }
  }

  resetForm() {
    this.newRule = this.blankRule();
    this.showForm = false;
    this.formError = null;
  }

  openForm() {
    this.newRule = this.blankRule();
    this.formError = null;
    this.showForm = true;
  }

  conditionLabel(c: string): string {
    return this.conditions.find((x) => x.value === c)?.label ?? c;
  }

  notifyLabel(m: string): string {
    return this.notifyMethods.find((x) => x.value === m)?.label ?? m;
  }

  layerLabel(l: string): string {
    return this.layers.find((x) => x.value === l)?.label ?? (l || 'All layers');
  }

  needsTarget(method: string | undefined): boolean {
    return method === 'webhook' || method === 'email';
  }

  targetPlaceholder(method: string | undefined): string {
    if (method === 'webhook') return 'https://hooks.example.com/...';
    if (method === 'email') return 'alerts@example.com';
    return '';
  }

  private blankRule(): Partial<AlertRule> {
    return {
      name: '',
      condition: 'any_anomaly',
      layer: '',
      notifyMethod: 'browser',
      notifyTarget: '',
    };
  }

  formatDate(s: string): string {
    if (!s) return '—';
    return new Date(s).toLocaleDateString(undefined, {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  }

  conditionBadgeClass(c: string): string {
    const map: Record<string, string> = {
      any_anomaly:       'cond-any',
      critical_severity: 'cond-critical',
      high_severity:     'cond-high',
      cross_layer:       'cond-cross',
      entity_repeat:     'cond-entity',
    };
    return map[c] ?? 'cond-any';
  }
}
