export interface Incident {
  id: number;
  entity: string | null;
  type: string;
  severity: string | null;
  start_time: string;
  end_time: string | null;
  events: number[] | null;
  attributes: Record<string, unknown> | null;
}
