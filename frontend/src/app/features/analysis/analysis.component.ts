import { Component, ElementRef, OnInit, ViewChild } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import Chart, { TooltipItem } from 'chart.js/auto';
import { ApiService, ModelStatus } from '../../core/services/api.service';

export interface CvScores {
  f1_mean: number; f1_std: number;
  auc_mean: number; auc_std: number;
  precision_mean: number; recall_mean: number;
  folds: number;
}

export interface ThresholdRow {
  threshold: number; precision: number;
  recall: number; f1: number; fpr: number;
}

export interface FeatureImportance {
  features: string[];
  importances: number[];
}

export interface TrainingMetrics {
  precision: number; recall: number; f1: number;
  false_positive_rate: number; specificity: number;
  accuracy: number; mcc: number;
  tp: number; tn: number; fp: number; fn: number;
  n_positive: number; n_negative: number; n_total: number;

  train_time_s?: number; n_features?: number;
  n_train?: number; model_type?: string;
  roc_auc?: number; avg_precision?: number;
  roc_curve?: { fpr: number[]; tpr: number[] };
  pr_curve?: { precision: number[]; recall: number[] };
  threshold_analysis?: ThresholdRow[];
  cv_scores?: CvScores;
  feature_importance?: FeatureImportance;
  [key: string]: unknown;
}

export interface HistoryEntry {
  id: number;
  timestamp: Date;
  action: string;
  step: 1 | 2 | 3;
  status: 'success' | 'error' | 'running';
  summary: string;
  metricsBySplit?: Record<string, TrainingMetrics>;
  report?: string;
  dataset?: string;
  modelType?: string;
  featureCols?: string[];
  raw?: unknown;
}

@Component({
  selector: 'app-analysis',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './analysis.component.html',
  styleUrls: ['./analysis.component.css'],
})
export class AnalysisComponent implements OnInit {
  @ViewChild('metricsChart')    metricsChart?:    ElementRef<HTMLCanvasElement>;
  @ViewChild('rocChart')        rocChart?:        ElementRef<HTMLCanvasElement>;
  @ViewChild('prChart')         prChart?:         ElementRef<HTMLCanvasElement>;
  @ViewChild('featureChart')    featureChart?:    ElementRef<HTMLCanvasElement>;
  @ViewChild('thresholdChart')  thresholdChart?:  ElementRef<HTMLCanvasElement>;


  ingestLoading = false;
  trainLoading  = false;
  generateLoading = false;

  get loading(): boolean { return this.ingestLoading || this.trainLoading || this.generateLoading; }

  modelType = 'rf';

  algorithms = [
    {
      value: 'rf', label: 'Random Forest', icon: '🌲', type: 'ensemble',
      desc: 'Robust tree ensemble with built-in feature importance. Best all-round choice for tabular anomaly data.',
      tags: ['Feature importance', 'Handles imbalance', 'Fast'],
    },
    {
      value: 'xgboost', label: 'XGBoost', icon: '⚡', type: 'ensemble',
      desc: 'Gradient-boosted trees with regularisation. High accuracy on structured data with fewer false positives.',
      tags: ['High accuracy', 'Regularisation', 'Scalable'],
    },
    {
      value: 'lgbm', label: 'LightGBM', icon: '🚀', type: 'ensemble',
      desc: 'Leaf-wise boosting — faster and more memory-efficient than XGBoost on large datasets.',
      tags: ['Very fast', 'Low memory', 'Large datasets'],
    },
    {
      value: 'svm', label: 'SVM (Linear)', icon: '📐', type: 'linear',
      desc: 'Maximum-margin classifier. Works well on high-dimensional network flow features.',
      tags: ['High-dimensional', 'Margin-based', 'Interpretable'],
    },
    {
      value: 'mlp', label: 'Neural Network', icon: '🧠', type: 'neural',
      desc: 'Multi-layer perceptron capable of learning complex non-linear patterns across all three layers.',
      tags: ['Non-linear', 'Deep patterns', 'Flexible'],
    },
    {
      value: 'isolation_forest', label: 'Isolation Forest', icon: '🔍', type: 'unsupervised',
      desc: 'Unsupervised anomaly isolation — no labels required. Ideal for discovering novel attack patterns.',
      tags: ['No labels needed', 'Novelty detection', 'Unsupervised'],
    },
  ];

  get selectedAlgo() {
    return this.algorithms.find(a => a.value === this.modelType) ?? null;
  }
  modelStatuses: ModelStatus[] = [];
  modelStatusLoading = false;
  activeTab: 'overview' | 'roc' | 'pr' | 'features' | 'threshold' | 'report' = 'overview';

  history: HistoryEntry[] = [];
  private historyCounter = 0;

  selectedEntry: HistoryEntry | null = null;
  private chart: Chart | null = null;


  step1Done = false;
  step2Done = false;
  step3Done = false;

  private static readonly STORAGE_KEY = 'analysis_history';

  constructor(private api: ApiService) {}

  ngOnInit(): void {
    this._loadHistory();
    this.loadModelStatus();
  }

  clearHistory(): void {
    this.history = [];
    this.historyCounter = 0;
    this.selectedEntry = null;
    this._destroyCharts();
    localStorage.removeItem(AnalysisComponent.STORAGE_KEY);
  }

  private _saveHistory(): void {
    try {
      const payload = JSON.stringify(this.history.slice(0, 50));
      localStorage.setItem(AnalysisComponent.STORAGE_KEY, payload);
    } catch {  }
  }

  private _loadHistory(): void {
    try {
      const raw = localStorage.getItem(AnalysisComponent.STORAGE_KEY);
      if (!raw) return;
      const parsed: HistoryEntry[] = JSON.parse(raw);

      this.history = parsed.map(e => ({ ...e, timestamp: new Date(e.timestamp) }));
      if (this.history.length) {
        this.historyCounter = Math.max(...this.history.map(e => e.id));
        this.step1Done = this.history.some(e => e.step === 1 && e.status === 'success');
        this.step2Done = this.history.some(e => e.step === 2 && e.status === 'success');
        this.step3Done = this.history.some(e => e.step === 3 && e.status === 'success');
      }
    } catch { localStorage.removeItem(AnalysisComponent.STORAGE_KEY); }
  }

  loadModelStatus(): void {
    this.modelStatusLoading = true;
    this.api.getModelStatus().subscribe({
      next: (list) => { this.modelStatuses = list; this.modelStatusLoading = false; },
      error: () => { this.modelStatusLoading = false; },
    });
  }


  ingestBgl(): void    { this._runIngest('Ingest BGL',    () => this.api.ingestBgl()); }
  ingestCicids(): void { this._runIngest('Ingest CICIDS', () => this.api.ingestCicids()); }
  ingestTda(): void    { this._runIngest('Ingest TDA',    () => this.api.ingestTda()); }

  private _runIngest(action: string, call: () => any): void {
    this.ingestLoading = true;
    const entry = this._addRunning(action, 1);
    call().subscribe({
      next: (res: any) => {
        this.ingestLoading = false;
        this.step1Done = true;
        const inserted = res?.inserted ?? res?.count ?? '?';
        this._resolve(entry, 'success', `Inserted ${inserted} records`);
        this._finishEntry(entry, res);
      },
      error: (err: any) => {
        this.ingestLoading = false;
        this._resolve(entry, 'error', err?.error?.detail || err?.message || 'Failed');
      },
    });
  }


  trainBgl(): void        { this._runTrain('Train BGL',         () => this.api.trainBgl(this.modelType)); }
  trainCicids(): void     { this._runTrain('Train CICIDS',      () => this.api.trainCicids(this.modelType)); }
  trainTda(): void        { this._runTrain('Train TDA',         () => this.api.trainTda(this.modelType)); }
  trainCrossLayer(): void { this._runTrain('Train Cross-layer', () => this.api.trainCrossLayer(this.modelType)); }

  private _runTrain(action: string, call: () => any): void {
    this.trainLoading = true;
    const entry = this._addRunning(action, 2);
    call().subscribe({
      next: (res: any) => {
        this.trainLoading = false;
        this.step2Done = true;
        this._finishEntry(entry, res);
        this.loadModelStatus();
        const f1 = res?.test_metrics?.f1 ?? res?.val_metrics?.f1;
        const summary = f1 != null ? `F1 = ${Number(f1).toFixed(3)}` : 'Trained';
        this._resolve(entry, 'success', summary);
        setTimeout(() => this._openEntry(entry), 0);
      },
      error: (err: any) => {
        this.trainLoading = false;
        this._resolve(entry, 'error', err?.error?.detail || err?.message || 'Failed');
      },
    });
  }


  generateCrossLayerIncidents(): void {
    this._runGenerate('Generate Cross-layer incidents', () => this.api.generateCrossLayerIncidents());
  }
  generateMlIncidents(): void {
    this._runGenerate('Generate ML incidents', () => this.api.generateMlIncidents());
  }


  fixLoading = false;
  fixResult  = '';

  fixLabels(): void {
    this.fixLoading = true;
    this.fixResult  = '';
    this.api.fixLabels().subscribe({
      next: (res: any) => {
        this.fixLoading = false;
        const dist: any[] = res.distribution ?? [];
        const attacks = dist.filter((d: any) => d.label === 1).reduce((s: number, d: any) => s + d.count, 0);
        const total   = dist.reduce((s: number, d: any) => s + d.count, 0);
        this.fixResult = `✓ Done — ${attacks.toLocaleString()} anomalies out of ${total.toLocaleString()} total events labelled. Simulation ready.`;
      },
      error: (e: any) => {
        this.fixLoading = false;
        this.fixResult  = `✗ ${e?.error?.detail || 'Fix failed — see server logs.'}`;
      },
    });
  }


  clearSimLoading = false;
  clearSimResult  = '';

  clearSimulatedIncidents(): void {
    this.clearSimLoading = true;
    this.clearSimResult  = '';
    this.api.clearSimulatedIncidents().subscribe({
      next: (res: any) => {
        this.clearSimLoading = false;
        this.clearSimResult  = `✓ Deleted ${(res.deleted ?? 0).toLocaleString()} simulated incident${res.deleted !== 1 ? 's' : ''}. ML incidents are now visible.`;
      },
      error: (e: any) => {
        this.clearSimLoading = false;
        this.clearSimResult  = `✗ ${e?.error?.detail || 'Clear failed — see server logs.'}`;
      },
    });
  }


  enrichLoading = false;
  enrichResult  = '';

  enrichEntities(): void {
    this.enrichLoading = true;
    this.enrichResult  = '';
    this.api.enrichEntities().subscribe({
      next: (res: any) => {
        this.enrichLoading = false;
        this.enrichResult  = `Updated ${res.updated} events (IPs: ${res.ip_extracted}, users: ${res.user_extracted}, hosts: ${res.hostname_extracted})`;
      },
      error: () => {
        this.enrichLoading = false;
        this.enrichResult  = 'Enrichment failed — see server logs.';
      },
    });
  }


  simLayer        = 'bgl';
  simRate         = 10;
  simMax          = 300;
  simAnomaliesOnly = false;
  simRunning      = false;
  simStatus: any  = null;
  simError        = '';
  private _simPoller?: any;

  simLayers = [
    { value: 'bgl',    label: 'BGL (System logs)' },
    { value: 'cicids', label: 'CICIDS (Network)' },
    { value: 'tda',    label: 'TDA (Application)' },
    { value: 'all',    label: 'All layers' },
  ];

  startSim(): void {
    this.simError = '';
    this.api.startSimulation({
      layer:          this.simLayer,
      rate:           this.simRate,
      max_events:     this.simMax,
      only_anomalies: this.simAnomaliesOnly,
    }).subscribe({
      next: () => {
        this.simRunning = true;
        this._pollSimStatus();
      },
      error: (e: any) => {
        this.simError = e?.error?.detail || 'Failed to start simulation.';
      },
    });
  }

  stopSim(): void {
    this.api.stopSimulation().subscribe({
      next: () => { this._pollSimStatus(); },
      error: () => { this.simRunning = false; this._clearPoller(); },
    });
  }

  private _pollSimStatus(): void {
    this._clearPoller();
    this._simPoller = setInterval(() => {
      this.api.getSimulationStatus().subscribe({
        next: (s: any) => {
          this.simStatus  = s;
          this.simRunning = s.running;
          if (!s.running) this._clearPoller();
        },
        error: () => this._clearPoller(),
      });
    }, 800);
  }

  private _clearPoller(): void {
    if (this._simPoller) { clearInterval(this._simPoller); this._simPoller = undefined; }
  }

  simProgressPct(): number {
    if (!this.simStatus || !this.simMax) return 0;
    return Math.min(100, Math.round((this.simStatus.sent / this.simMax) * 100));
  }

  private _runGenerate(action: string, call: () => any): void {
    this.generateLoading = true;
    const entry = this._addRunning(action, 3);
    call().subscribe({
      next: (res: any) => {
        this.generateLoading = false;
        this.step3Done = true;
        this._finishEntry(entry, res);
        const created = res?.created ?? res?.incidents_created ?? res?.count ?? '?';
        this._resolve(entry, 'success', `Created ${created} incidents`);
      },
      error: (err: any) => {
        this.generateLoading = false;
        this._resolve(entry, 'error', err?.error?.detail || err?.message || 'Failed');
      },
    });
  }


  private _addRunning(action: string, step: 1 | 2 | 3): HistoryEntry {
    const entry: HistoryEntry = {
      id: ++this.historyCounter,
      timestamp: new Date(),
      action,
      step,
      status: 'running',
      summary: 'Running…',
    };
    this.history.unshift(entry);
    return entry;
  }

  private _resolve(entry: HistoryEntry, status: 'success' | 'error', summary: string): void {
    entry.status = status;
    entry.summary = summary;
    this._saveHistory();
  }

  private _finishEntry(entry: HistoryEntry, res: any): void {
    entry.raw = res;
    entry.dataset   = res?.dataset;
    entry.modelType = res?.model_type ?? res?.train_metrics?.model_type;
    entry.featureCols = res?.feature_cols;
    const hasMetrics = res?.train_metrics || res?.val_metrics || res?.test_metrics;
    if (hasMetrics) {
      const m: Record<string, TrainingMetrics> = {};
      if (res.train_metrics) m['Train'] = res.train_metrics;
      if (res.val_metrics)   m['Validation'] = res.val_metrics;
      if (res.test_metrics)  m['Test'] = res.test_metrics;
      entry.metricsBySplit = m;
      entry.report = res.report;
    }
  }

  private _openEntry(entry: HistoryEntry): void {
    this.selectedEntry = entry;
    this.activeTab = 'overview';
    setTimeout(() => this._buildActiveCharts(), 0);
  }

  openEntry(entry: HistoryEntry): void {
    this.selectedEntry = this.selectedEntry?.id === entry.id ? null : entry;
    if (this.selectedEntry) {
      this.activeTab = 'overview';
      this._destroyCharts();
      setTimeout(() => this._buildActiveCharts(), 0);
    }
  }

  setTab(tab: typeof this.activeTab): void {
    this.activeTab = tab;
    setTimeout(() => this._buildActiveCharts(), 50);
  }

  bestF1(rows: ThresholdRow[]): number {
    return Math.max(...rows.map(r => r.f1));
  }

  _destroyCharts(): void {
    this.chart?.destroy(); this.chart = null;
    this._rocChart?.destroy(); this._rocChart = null;
    this._prChart?.destroy(); this._prChart = null;
    this._featureChart?.destroy(); this._featureChart = null;
    this._thresholdChart?.destroy(); this._thresholdChart = null;
  }

  private _rocChart: Chart | null = null;
  private _prChart: Chart | null = null;
  private _featureChart: Chart | null = null;
  private _thresholdChart: Chart | null = null;

  private _buildActiveCharts(): void {
    const e = this.selectedEntry;
    if (!e?.metricsBySplit) return;
    if (this.activeTab === 'overview') this._buildChart(e.metricsBySplit);
    if (this.activeTab === 'roc')      this._buildRocChart(e.metricsBySplit);
    if (this.activeTab === 'pr')       this._buildPrChart(e.metricsBySplit);
    if (this.activeTab === 'features') this._buildFeatureChart(e.metricsBySplit);
    if (this.activeTab === 'threshold') this._buildThresholdChart(e.metricsBySplit);
  }

  private _buildChart(metricsBySplit: Record<string, TrainingMetrics>): void {
    const canvas = this.metricsChart?.nativeElement;
    if (!canvas) return;
    this.chart?.destroy();
    const labels = ['Precision', 'Recall', 'F1', 'FPR'];
    const keys   = ['precision', 'recall', 'f1', 'false_positive_rate'];
    const colors = ['#4f46e5', '#059669', '#c026d3'];
    this.chart = new Chart(canvas, {
      type: 'bar',
      data: {
        labels,
        datasets: Object.entries(metricsBySplit).map(([split, m], i) => ({
          label: split,
          data: keys.map(k => Number(m[k] ?? 0)),
          backgroundColor: colors[i % colors.length],
          borderRadius: 6,
          barPercentage: 0.7,
        })),
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { position: 'top' },
          tooltip: {
            callbacks: {
              label: ctx => `${ctx.dataset.label}: ${Number(ctx.parsed.y).toFixed(3)}`,
            },
          },
        },
        scales: {
          y: { beginAtZero: true, max: 1, ticks: { callback: v => Number(v).toFixed(1) } },
        },
      },
    });
  }


  private _buildRocChart(splits: Record<string, TrainingMetrics>): void {
    const canvas = this.rocChart?.nativeElement;
    if (!canvas) return;
    this._rocChart?.destroy();
    const colors = ['#4f46e5', '#059669', '#f59e0b'];
    const datasets: any[] = [];

    datasets.push({ label: 'Random (AUC=0.5)', data: [{x:0,y:0},{x:1,y:1}], borderColor: '#94a3b8', borderDash: [6,4], borderWidth: 1.5, pointRadius: 0, fill: false });
    Object.entries(splits).forEach(([split, m], i) => {
      if (!m.roc_curve) return;
      const pts = m.roc_curve.fpr.map((f, j) => ({ x: f, y: m.roc_curve!.tpr[j] }));
      datasets.push({ label: `${split} (AUC=${(m.roc_auc ?? 0).toFixed(3)})`, data: pts, borderColor: colors[i], borderWidth: 2, pointRadius: 0, fill: false, tension: 0.1 });
    });
    this._rocChart = new Chart(canvas, {
      type: 'scatter', data: { datasets },
      options: { responsive: true, maintainAspectRatio: false,
        plugins: { legend: { position: 'top' }, tooltip: { callbacks: { label: (ctx: TooltipItem<'scatter'>) => `FPR=${(ctx.parsed.x ?? 0).toFixed(3)}, TPR=${(ctx.parsed.y ?? 0).toFixed(3)}` } } },
        scales: {
          x: { type: 'linear', min: 0, max: 1, title: { display: true, text: 'False Positive Rate' } },
          y: { type: 'linear', min: 0, max: 1, title: { display: true, text: 'True Positive Rate (Recall)' } },
        },
        elements: { line: { borderWidth: 2 } },
        showLine: true,
      } as any,
    });
  }


  private _buildPrChart(splits: Record<string, TrainingMetrics>): void {
    const canvas = this.prChart?.nativeElement;
    if (!canvas) return;
    this._prChart?.destroy();
    const colors = ['#4f46e5', '#059669', '#f59e0b'];
    const datasets: any[] = [];
    Object.entries(splits).forEach(([split, m], i) => {
      if (!m.pr_curve) return;
      const pts = m.pr_curve.recall.map((r, j) => ({ x: r, y: m.pr_curve!.precision[j] }));
      datasets.push({ label: `${split} (AP=${(m.avg_precision ?? 0).toFixed(3)})`, data: pts, borderColor: colors[i], borderWidth: 2, pointRadius: 0, fill: false, tension: 0.1 });
    });
    this._prChart = new Chart(canvas, {
      type: 'scatter', data: { datasets },
      options: { responsive: true, maintainAspectRatio: false,
        plugins: { legend: { position: 'top' }, tooltip: { callbacks: { label: (ctx: TooltipItem<'scatter'>) => `Recall=${(ctx.parsed.x ?? 0).toFixed(3)}, Precision=${(ctx.parsed.y ?? 0).toFixed(3)}` } } },
        scales: {
          x: { type: 'linear', min: 0, max: 1, title: { display: true, text: 'Recall' } },
          y: { type: 'linear', min: 0, max: 1, title: { display: true, text: 'Precision' } },
        },
        showLine: true,
      } as any,
    });
  }


  private _buildFeatureChart(splits: Record<string, TrainingMetrics>): void {
    const canvas = this.featureChart?.nativeElement;
    if (!canvas) return;
    this._featureChart?.destroy();
    const fi = splits['Train']?.feature_importance;
    if (!fi) return;
    this._featureChart = new Chart(canvas, {
      type: 'bar',
      data: {
        labels: fi.features,
        datasets: [{ label: 'Importance', data: fi.importances, backgroundColor: '#6366f1', borderRadius: 4 }],
      },
      options: {
        indexAxis: 'y', responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: { callbacks: { label: (ctx: TooltipItem<'bar'>) => `${((ctx.parsed.x ?? 0) * 100).toFixed(2)}%` } } },
        scales: { x: { title: { display: true, text: 'Importance Score' }, ticks: { callback: v => (Number(v) * 100).toFixed(1) + '%' } } },
      },
    });
  }


  private _buildThresholdChart(splits: Record<string, TrainingMetrics>): void {
    const canvas = this.thresholdChart?.nativeElement;
    if (!canvas) return;
    this._thresholdChart?.destroy();
    const rows = splits['Test']?.threshold_analysis ?? splits['Validation']?.threshold_analysis;
    if (!rows?.length) return;
    const labels = rows.map(r => r.threshold.toFixed(2));
    this._thresholdChart = new Chart(canvas, {
      type: 'line',
      data: {
        labels,
        datasets: [
          { label: 'F1',        data: rows.map(r => r.f1),        borderColor: '#4f46e5', tension: 0.3, pointRadius: 4, fill: false },
          { label: 'Precision', data: rows.map(r => r.precision), borderColor: '#059669', tension: 0.3, pointRadius: 4, fill: false },
          { label: 'Recall',    data: rows.map(r => r.recall),    borderColor: '#f59e0b', tension: 0.3, pointRadius: 4, fill: false },
          { label: 'FPR',       data: rows.map(r => r.fpr),       borderColor: '#ef4444', tension: 0.3, pointRadius: 4, fill: false, borderDash: [4,3] },
        ],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { position: 'top' }, tooltip: { mode: 'index', intersect: false } },
        scales: {
          x: { title: { display: true, text: 'Decision Threshold' } },
          y: { min: 0, max: 1, title: { display: true, text: 'Metric Value' } },
        },
      },
    });
  }


  hasRoc(entry: HistoryEntry): boolean {
    return !!Object.values(entry.metricsBySplit ?? {}).find(m => m.roc_curve);
  }
  hasPr(entry: HistoryEntry): boolean {
    return !!Object.values(entry.metricsBySplit ?? {}).find(m => m.pr_curve);
  }
  hasFeatureImportance(entry: HistoryEntry): boolean {
    return !!entry.metricsBySplit?.['Train']?.feature_importance;
  }
  hasThreshold(entry: HistoryEntry): boolean {
    const splits = entry.metricsBySplit ?? {};
    return !!(splits['Test']?.threshold_analysis ?? splits['Validation']?.threshold_analysis);
  }
  trainMeta(entry: HistoryEntry): TrainingMetrics | null {
    return entry.metricsBySplit?.['Train'] ?? null;
  }
  cvScores(entry: HistoryEntry): CvScores | null {
    return entry.metricsBySplit?.['Train']?.cv_scores ?? null;
  }


  cmSplits(entry: HistoryEntry): string[] {
    return entry.metricsBySplit ? Object.keys(entry.metricsBySplit) : [];
  }

  cmTotal(m: TrainingMetrics): number {
    return (m.tp || 0) + (m.tn || 0) + (m.fp || 0) + (m.fn || 0);
  }

  cmAccuracy(m: TrainingMetrics): string {
    const total = this.cmTotal(m);
    if (!total) return '—';
    return (((m.tp + m.tn) / total) * 100).toFixed(1) + '%';
  }


  get trainedCount(): number { return this.modelStatuses.filter(m => m.trained).length; }
  get totalModels(): number  { return this.modelStatuses.length; }

  modelIcon(m: ModelStatus): string {
    return m.trained ? '✅' : '⬜';
  }

  formatKb(kb: number | null): string {
    if (kb == null) return '—';
    return kb >= 1024 ? (kb / 1024).toFixed(1) + ' MB' : kb.toFixed(0) + ' KB';
  }

  stepClass(step: 1 | 2 | 3): string {
    const done = step === 1 ? this.step1Done : step === 2 ? this.step2Done : this.step3Done;
    return done ? 'step-done' : '';
  }

  historyIcon(e: HistoryEntry): string {
    if (e.status === 'running') return '⏳';
    if (e.status === 'success') return '✓';
    return '✕';
  }

  trackById(_: number, e: HistoryEntry): number { return e.id; }
}
