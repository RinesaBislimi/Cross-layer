export interface LogEvent {
  id: number;
  layer: string;
  source: string;
  timestamp: string;
  entity: string | null;
  raw: string;
  message: string | null;
  features: Record<string, unknown> | null;
  label: number | null;
  confidence: number | null;
}
