import { Injectable, OnDestroy } from '@angular/core';
import { Subject, takeUntil } from 'rxjs';
import { WebSocketService } from './websocket.service';

export interface VoiceConfig {
  rate: number;
  pitch: number;
  volume: number;
}

const SEVERITY_CONFIG: Record<string, VoiceConfig> = {
  critical: { rate: 1.1, pitch: 0.8, volume: 1.0 },
  high:     { rate: 1.0, pitch: 1.0, volume: 1.0 },
  medium:   { rate: 0.95, pitch: 1.1, volume: 0.9 },
  low:      { rate: 0.9,  pitch: 1.2, volume: 0.8 },
  default:  { rate: 1.0,  pitch: 1.0, volume: 1.0 },
};

@Injectable({ providedIn: 'root' })
export class VoiceNotificationService implements OnDestroy {
  private muted = false;
  private supported = typeof window !== 'undefined' && 'speechSynthesis' in window;
  private destroy$ = new Subject<void>();
  private queue: string[] = [];
  private speaking = false;

  constructor(private ws: WebSocketService) {
    this.ws.messages.pipe(takeUntil(this.destroy$)).subscribe((msg: any) => {
      this.handleMessage(msg);
    });
  }



  get isMuted(): boolean { return this.muted; }
  get isSupported(): boolean { return this.supported; }

  toggleMute(): void {
    this.muted = !this.muted;
    if (this.muted && this.supported) {
      window.speechSynthesis.cancel();
      this.queue = [];
      this.speaking = false;
    }
  }


  speakRaw(text: string, config: Partial<VoiceConfig> = {}): void {
    if (!this.supported) return;
    const merged: VoiceConfig = { ...SEVERITY_CONFIG['default'], ...config };
    this.enqueue(text, merged);
  }



  private handleMessage(msg: any): void {
    if (!this.supported || this.muted || !msg) return;

    if (msg.type === 'incident') {
      this.announceIncident(msg);
    } else if (msg.type === 'incident_batch') {


      const incidents: any[] = msg.incidents ?? msg.data ?? [];

      if (incidents.length > 0) {

        if (incidents.length === 1) {
          this.announceIncident(incidents[0]);
        } else {
          const critical = incidents.filter((i: any) => i.severity === 'critical').length;
          const high     = incidents.filter((i: any) => i.severity === 'high').length;
          let text = `${incidents.length} new incidents detected.`;
          if (critical > 0) text += ` ${critical} critical.`;
          if (high > 0)     text += ` ${high} high severity.`;
          const cfg = critical > 0
            ? SEVERITY_CONFIG['critical']
            : high > 0 ? SEVERITY_CONFIG['high'] : SEVERITY_CONFIG['default'];
          this.enqueue(text, cfg);
        }
      } else {

        const count    = msg.count ?? 1;
        const severity = (msg.severity ?? 'medium').toLowerCase();
        const layer    = msg.layer ?? '';
        const cfg      = SEVERITY_CONFIG[severity] ?? SEVERITY_CONFIG['default'];
        const layerLabel = layer ? ` in ${layer} layer` : '';
        const text = count === 1
          ? `New ${severity} incident detected${layerLabel}.`
          : `${count} new incidents detected${layerLabel}. Severity: ${severity}.`;
        this.enqueue(text, cfg);
      }
    }
  }

  private announceIncident(inc: any): void {
    const severity = (inc.severity ?? inc.data?.severity ?? 'unknown').toLowerCase();
    const entity   = inc.entity   ?? inc.data?.entity   ?? '';
    const type     = inc.type     ?? inc.data?.type     ?? 'anomaly';
    const cfg      = SEVERITY_CONFIG[severity] ?? SEVERITY_CONFIG['default'];


    const severityWord = severity.charAt(0).toUpperCase() + severity.slice(1);
    let text = `${severityWord} incident detected`;
    if (entity) text += ` on ${entity}`;


    if (type.startsWith('Cross-layer')) {
      text += '. Cross-layer correlation triggered.';
    } else if (type.startsWith('ML:')) {
      const src = type.replace('ML:', '').trim();
      text += `. Machine learning anomaly in ${src}.`;
    } else if (type) {
      text += `. Type: ${type}.`;
    } else {
      text += '.';
    }

    this.enqueue(text, cfg);
  }

  private enqueue(text: string, cfg: VoiceConfig): void {
    this.queue.push(JSON.stringify({ text, cfg }));
    if (!this.speaking) this.drainQueue();
  }

  private drainQueue(): void {
    if (this.queue.length === 0) {
      this.speaking = false;
      return;
    }
    this.speaking = true;
    const raw = this.queue.shift()!;
    const { text, cfg } = JSON.parse(raw) as { text: string; cfg: VoiceConfig };

    const utt = new SpeechSynthesisUtterance(text);
    utt.rate   = cfg.rate;
    utt.pitch  = cfg.pitch;
    utt.volume = cfg.volume;
    utt.lang   = 'en-US';

    utt.onend = () => this.drainQueue();
    utt.onerror = () => this.drainQueue();

    window.speechSynthesis.speak(utt);
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
    if (this.supported) window.speechSynthesis.cancel();
  }
}
