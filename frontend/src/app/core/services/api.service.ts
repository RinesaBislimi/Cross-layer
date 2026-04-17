import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { LogEvent } from '../../shared/models/log-event';
import { Incident } from '../../shared/models/incident';

@Injectable({ providedIn: 'root' })
export class ApiService {
  private base = environment.apiUrl;

  constructor(private http: HttpClient) {}

  getHealth(): Observable<{ status: string }> {
    return this.http.get<{ status: string }>(`${this.base}/health`);
  }

  ingestBgl(): Observable<{ inserted: number }> {
    return this.http.post<{ inserted: number }>(`${this.base}/admin/ingest/bgl`, null);
  }

  ingestCicids(): Observable<{ inserted: number }> {
    return this.http.post<{ inserted: number }>(`${this.base}/admin/ingest/cicids`, null);
  }

  ingestTda(): Observable<{ inserted: number }> {
    return this.http.post<{ inserted: number }>(`${this.base}/admin/ingest/tda`, null);
  }

  getLogs(params: { layer?: string; source?: string; limit?: number } = {}): Observable<LogEvent[]> {
    let httpParams = new HttpParams();
    if (params.layer) httpParams = httpParams.set('layer', params.layer);
    if (params.source) httpParams = httpParams.set('source', params.source);
    if (params.limit != null) httpParams = httpParams.set('limit', params.limit.toString());
    return this.http.get<LogEvent[]>(`${this.base}/logs`, { params: httpParams });
  }

  getIncidents(limit = 100): Observable<Incident[]> {
    return this.http.get<Incident[]>(`${this.base}/incidents`, {
      params: { limit: limit.toString() },
    });
  }

  getIncidentEvents(id: number): Observable<LogEvent[]> {
    return this.http.get<LogEvent[]>(`${this.base}/incidents/${id}/events`);
  }

  getCommonEntities(minLayers = 2, limit = 50): Observable<{ entity: string; layers: string[]; num_layers: number }[]> {
    return this.http.get<{ entity: string; layers: string[]; num_layers: number }[]>(
      `${this.base}/admin/common-entities`,
      { params: { min_layers: minLayers.toString(), limit: limit.toString() } }
    );
  }

  trainBgl(modelType = 'rf'): Observable<any> {
    return this.http.post<any>(`${this.base}/admin/train/bgl`, null, {
      params: { model_type: modelType },
    });
  }

  trainCicids(modelType = 'rf'): Observable<any> {
    return this.http.post<any>(`${this.base}/admin/train/cicids`, null, {
      params: { model_type: modelType },
    });
  }

  trainTda(modelType = 'rf'): Observable<any> {
    return this.http.post<any>(`${this.base}/admin/train/tda`, null, {
      params: { model_type: modelType },
    });
  }

  trainCrossLayer(modelType = 'rf', windowMinutes = 10, minLayers = 2): Observable<any> {
    return this.http.post<any>(`${this.base}/admin/train/cross-layer`, null, {
      params: {
        model_type: modelType,
        window_minutes: windowMinutes.toString(),
        min_layers: minLayers.toString(),
      },
    });
  }

  generateCrossLayerIncidents(
    windowMinutes = 10,
    minLayers = 2,
    lookbackHours = 24,
    requireAnomaly = false,
    slidingWindow = true,
    maxEventsPerIncident = 2000,
  ): Observable<any> {
    return this.http.post<any>(`${this.base}/admin/incidents/generate`, null, {
      params: {
        window_minutes: windowMinutes.toString(),
        min_layers: minLayers.toString(),
        lookback_hours: lookbackHours.toString(),
        require_anomaly: String(requireAnomaly),
        sliding_window: String(slidingWindow),
        max_events_per_incident: maxEventsPerIncident.toString(),
      },
    });
  }

  generateMlIncidents(
    lookbackHours = 168,
    probabilityThreshold = 0.5,
    batchSize = 4000,
    maxEventsPerSource = 80000,
    mergeWindowMinutes = 15,
    fallbackToLabel = true,
  ): Observable<any> {
    return this.http.post<any>(`${this.base}/admin/incidents/generate-ml`, null, {
      params: {
        lookback_hours: lookbackHours.toString(),
        probability_threshold: probabilityThreshold.toString(),
        batch_size: batchSize.toString(),
        max_events_per_source: maxEventsPerSource.toString(),
        merge_window_minutes: mergeWindowMinutes.toString(),
        fallback_to_label: String(fallbackToLabel),
      },
    });
  }

  correlateEntity(entity: string, minutes = 10): Observable<Incident> {
    return this.http.post<Incident>(`${this.base}/correlate/${encodeURIComponent(entity)}`, null, {
      params: { minutes: minutes.toString() },
    });
  }

  getSummary(): Observable<StatsResponse> {
    return this.http.get<StatsResponse>(`${this.base}/summary`);
  }

  getStats(): Observable<StatsResponse> {
    return this.http.get<StatsResponse>(`${this.base}/stats`);
  }

  getModelStatus(): Observable<ModelStatus[]> {
    return this.http.get<ModelStatus[]>(`${this.base}/admin/model-status`);
  }

  getCommonEntitiesData(minLayers = 2, limit = 20): Observable<EntityData[]> {
    return this.http.get<EntityData[]>(
      `${this.base}/admin/common-entities`,
      { params: { min_layers: minLayers.toString(), limit: limit.toString() } }
    );
  }

  analyzeIncident(incidentId: number): Observable<{ incident_id: number; explanation: string }> {
    return this.http.post<{ incident_id: number; explanation: string }>(
      `${this.base}/admin/analyze/incident/${incidentId}`, null
    );
  }

  analyzeLog(logId: number): Observable<{ log_id: number; explanation: string }> {
    return this.http.post<{ log_id: number; explanation: string }>(
      `${this.base}/admin/analyze/log/${logId}`, null
    );
  }

  computeStats(): Observable<{ status: string; elapsed_seconds: number; layers: number; total_anomalies: number }> {
    return this.http.post<any>(`${this.base}/admin/compute-stats`, null);
  }

  chat(question: string): Observable<{ question: string; answer: string; provider: string }> {
    return this.http.post<{ question: string; answer: string; provider: string }>(
      `${this.base}/admin/chat`, { question }
    );
  }

  chatStream(question: string): Observable<{ token?: string; done?: boolean; provider?: string; error?: string }> {
    type StreamEvent = { token?: string; done?: boolean; provider?: string; error?: string };
    return new Observable<StreamEvent>(observer => {
      const controller = new AbortController();

      fetch(`${this.base}/admin/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question }),
        signal: controller.signal,
      }).then(async resp => {
        if (!resp.ok) {
          const err = await resp.json().catch(() => ({ detail: 'Stream request failed' }));
          observer.error({ error: err });
          return;
        }
        const reader = resp.body!.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() ?? '';
          for (const line of lines) {
            if (!line.startsWith('data:')) continue;
            try {
              const parsed: StreamEvent = JSON.parse(line.slice(5).trim());
              observer.next(parsed);
              if (parsed.done) { observer.complete(); return; }
            } catch { /* ignore malformed lines */ }
          }
        }
        observer.complete();
      }).catch(err => {
        if (err?.name !== 'AbortError') observer.error(err);
      });

      return () => controller.abort();
    });
  }
}

export interface StatsRow { name: string; count: number; anomalies?: number; }

export interface StatsResponse {
  total_logs: number;
  total_anomalies: number;
  total_incidents: number;
  logs_by_layer: StatsRow[];
  logs_by_source: StatsRow[];
  incidents_by_severity: StatsRow[];
  incidents_by_mode: StatsRow[];
  large_dataset?: boolean;
}

export interface ModelStatus {
  name: string;
  layer: string;
  trained: boolean;
  size_kb: number | null;
  path: string;
}

export interface EntityData {
  entity: string;
  layers: string[];
  num_layers: number;
}
