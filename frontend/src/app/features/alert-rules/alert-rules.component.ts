import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ApiService, AlertRuleResponse } from '../../core/services/api.service';

interface AlertRule {
  id: number;
  name: string;
  condition: 'any_anomaly' | 'critical_severity' | 'high_severity' | 'cross_layer' | 'entity_repeat';
  layer: string;
  notifyMethod: 'browser' | 'webhook' | 'email';
  notifyTarget: string;
  enabled: boolean;
  createdAt: string;
  triggerCount: number;
  lastFiredAt: string | null;
}

function fromApi(r: AlertRuleResponse): AlertRule {
  return {
    id:           r.id,
    name:         r.name,
    condition:    r.condition as AlertRule['condition'],
    layer:        r.layer,
    notifyMethod: r.notify_method as AlertRule['notifyMethod'],
    notifyTarget: r.notify_target,
    enabled:      r.enabled,
    createdAt:    r.created_at,
    triggerCount: r.trigger_count,
    lastFiredAt:  r.last_fired_at,
  };
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
  showForm   = false;
  formError: string | null = null;
  loadError: string | null = null;
  loading    = false;
  testFeedback: Record<number, string> = {};
  notifPermission: NotificationPermission = 'default';

  newRule: {
    name: string; condition: AlertRule['condition']; layer: string;
    notifyMethod: AlertRule['notifyMethod']; notifyTarget: string;
  } = this.blankRule();

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

  constructor(private api: ApiService) {}

  ngOnInit(): void {
    this.notifPermission = (window as any).Notification?.permission ?? 'default';
    this.loadRules();
  }

  loadRules(): void {
    this.loading   = true;
    this.loadError = null;
    this.api.getAlertRules().subscribe({
      next: (data) => {
        this.rules   = data.map(fromApi);
        this.loading = false;
      },
      error: (err) => {
        this.loadError = 'Could not load rules — is the backend running?';
        this.loading   = false;
        console.error(err);
      },
    });
  }

  addRule(): void {
    this.formError = null;
    if (!this.newRule.name.trim()) {
      this.formError = 'Rule name is required.'; return;
    }
    if (!this.newRule.condition) {
      this.formError = 'Please select a condition.'; return;
    }
    if (!this.newRule.notifyMethod) {
      this.formError = 'Please select a notification method.'; return;
    }
    if (
      (this.newRule.notifyMethod === 'webhook' || this.newRule.notifyMethod === 'email') &&
      !this.newRule.notifyTarget.trim()
    ) {
      this.formError = `Please enter a ${this.newRule.notifyMethod === 'webhook' ? 'webhook URL' : 'email address'}.`;
      return;
    }

    this.api.createAlertRule({
      name:          this.newRule.name.trim(),
      condition:     this.newRule.condition,
      layer:         this.newRule.layer,
      notify_method: this.newRule.notifyMethod,
      notify_target: this.newRule.notifyTarget.trim(),
    }).subscribe({
      next: (created) => {
        this.rules = [fromApi(created), ...this.rules];
        this.resetForm();
      },
      error: (err) => {
        this.formError = err?.error?.detail ?? 'Failed to save rule.';
      },
    });
  }

  deleteRule(id: number): void {
    this.api.deleteAlertRule(id).subscribe({
      next: () => { this.rules = this.rules.filter(r => r.id !== id); },
      error: () => { alert('Could not delete rule.'); },
    });
  }

  toggleRule(id: number): void {
    this.api.toggleAlertRule(id).subscribe({
      next: (updated) => {
        const idx = this.rules.findIndex(r => r.id === id);
        if (idx !== -1) this.rules[idx] = fromApi(updated);
      },
      error: () => { alert('Could not toggle rule.'); },
    });
  }

  resetForm(): void {
    this.newRule   = this.blankRule();
    this.showForm  = false;
    this.formError = null;
  }

  openForm(): void {
    this.newRule   = this.blankRule();
    this.formError = null;
    this.showForm  = true;
  }

  // ── Test a rule immediately ──────────────────────────────────────────────

  testRule(rule: AlertRule): void {
    if (rule.notifyMethod === 'browser') {
      const fire = () => {
        new (window as any).Notification(`🔔 TEST — ${rule.name}`, {
          body: `Condition: "${this.conditionLabel(rule.condition)}" — this is a test fire.`,
          icon: '/favicon.ico',
        });
      };
      const perm = (window as any).Notification?.permission;
      if (perm === 'granted') {
        fire();
        this._showFeedback(rule.id, '✓ Browser notification fired');
      } else if (perm !== 'denied') {
        (window as any).Notification?.requestPermission?.().then((p: string) => {
          this.notifPermission = p as NotificationPermission;
          if (p === 'granted') { fire(); this._showFeedback(rule.id, '✓ Browser notification fired'); }
          else                 { this._showFeedback(rule.id, '✕ Permission denied by browser'); }
        });
      } else {
        this._showFeedback(rule.id, '✕ Notifications blocked — enable in browser settings');
      }

    } else if (rule.notifyMethod === 'webhook') {
      if (!rule.notifyTarget) {
        this._showFeedback(rule.id, '✕ No webhook URL configured'); return;
      }
      fetch(rule.notifyTarget, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          rule: rule.name, condition: rule.condition,
          test: true, timestamp: new Date().toISOString(),
        }),
      })
        .then(() => this._showFeedback(rule.id, '✓ Webhook POST sent'))
        .catch(() => this._showFeedback(rule.id, '✕ Webhook request failed'));

    } else if (rule.notifyMethod === 'email') {
      if (!rule.notifyTarget?.trim()) {
        this._showFeedback(rule.id, '✕ No email address configured'); return;
      }
      this._showFeedback(rule.id, 'ℹ Sending…');
      this.api.sendAlertEmail(rule.notifyTarget.trim(), rule.name, rule.condition, true)
        .subscribe({
          next: () => this._showFeedback(rule.id, `✓ Test email sent to ${rule.notifyTarget}`),
          error: (err) => {
            const detail: string = err?.error?.detail ?? 'Email delivery failed';
            this._showFeedback(rule.id, `✕ ${detail}`);
          },
        });

    } else {
      this._showFeedback(rule.id, '✕ No target configured');
    }
  }

  private _showFeedback(id: number, msg: string): void {
    this.testFeedback[id] = msg;
    setTimeout(() => { delete this.testFeedback[id]; }, 5000);
  }

  // ── Label helpers ────────────────────────────────────────────────────────

  conditionLabel(c: string): string {
    return this.conditions.find(x => x.value === c)?.label ?? c;
  }

  notifyLabel(m: string): string {
    return this.notifyMethods.find(x => x.value === m)?.label ?? m;
  }

  layerLabel(l: string): string {
    return this.layers.find(x => x.value === l)?.label ?? (l || 'All layers');
  }

  needsTarget(method: string | undefined): boolean {
    return method === 'webhook' || method === 'email';
  }

  targetPlaceholder(method: string | undefined): string {
    if (method === 'webhook') return 'https://hooks.example.com/...';
    if (method === 'email')   return 'alerts@example.com';
    return '';
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

  formatDate(s: string): string {
    if (!s) return '—';
    return new Date(s).toLocaleDateString(undefined, {
      month: 'short', day: 'numeric', year: 'numeric',
    });
  }

  formatLastFired(s: string | null): string {
    if (!s) return 'Never';
    const d = new Date(s);
    return d.toLocaleString(undefined, {
      month: 'short', day: 'numeric',
      hour: '2-digit', minute: '2-digit',
    });
  }

  private blankRule() {
    return {
      name: '', condition: 'any_anomaly' as AlertRule['condition'],
      layer: '', notifyMethod: 'browser' as AlertRule['notifyMethod'], notifyTarget: '',
    };
  }
}
