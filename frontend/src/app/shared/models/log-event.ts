export interface LogEvent {
  id: number;
  layer: string;
  source: string;
  timestamp: string;
  entity: string | null;
  raw: string;
  features: Record<string, unknown> | null;
  label: number | null;
}
