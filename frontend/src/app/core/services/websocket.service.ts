import { Injectable } from '@angular/core';
import { Observable, Subject } from 'rxjs';
import { environment } from '../../../environments/environment';

@Injectable({ providedIn: 'root' })
export class WebSocketService {
  private ws: WebSocket | null = null;
  private messages$ = new Subject<unknown>();
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;

  get messages(): Observable<unknown> {
    return this.messages$.asObservable();
  }

  connect(): void {
    if (this.ws?.readyState === WebSocket.OPEN) return;
    this.ws = new WebSocket(environment.wsUrl);

    this.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        this.messages$.next(data);
      } catch {
        this.messages$.next(event.data);
      }
    };

    this.ws.onclose = () => {
      this.ws = null;
      if (this.reconnectAttempts < this.maxReconnectAttempts) {
        this.reconnectAttempts++;
        setTimeout(() => this.connect(), 2000);
      }
    };

    this.ws.onerror = () => {
      this.ws?.close();
    };
  }

  disconnect(): void {
    this.reconnectAttempts = this.maxReconnectAttempts;
    this.ws?.close();
    this.ws = null;
  }

  send(data: string | object): void {
    if (this.ws?.readyState !== WebSocket.OPEN) return;
    this.ws.send(typeof data === 'string' ? data : JSON.stringify(data));
  }

  get isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }
}
