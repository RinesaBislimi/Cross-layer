import { Component, ElementRef, AfterViewChecked, OnInit, ViewChild } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ApiService } from '../../core/services/api.service';

export interface ChatMessage {
  role: 'user' | 'ai';
  text: string;
  html?: string;
  timestamp?: string;
}

interface ChatSession {
  id: string;
  provider: string;
  title: string;
  startedAt: string;
  messages: ChatMessage[];
}

const CHAT_STORAGE_KEY = 'cl_chat_sessions';
const MAX_SESSIONS = 30;

@Component({
  selector: 'app-ai-assistant',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './ai-assistant.component.html',
  styleUrls: ['./ai-assistant.component.css'],
})
export class AiAssistantComponent implements AfterViewChecked, OnInit {
  @ViewChild('chatHistory') chatHistoryRef?: ElementRef<HTMLDivElement>;

  chatMessages: ChatMessage[] = [];
  chatQuestion = '';
  chatLoading = false;
  chatProvider = '';
  currentSessionId = '';
  sessions: ChatSession[] = [];
  private shouldScroll = false;

  constructor(private api: ApiService) {}

  ngOnInit(): void {
    this._loadSessions();
    if (this.sessions.length) {
      this._restoreSession(this.sessions[0]);
    }
  }

  ngAfterViewChecked(): void {
    if (this.shouldScroll) {
      this.shouldScroll = false;
      const el = this.chatHistoryRef?.nativeElement;
      if (el) el.scrollTop = el.scrollHeight;
    }
  }

  // ── Chat actions ────────────────────────────────────────────────

  newChat(): void {
    this.chatMessages = [];
    this.chatProvider = '';
    this.currentSessionId = '';
  }

  sendChat(): void {
    const q = this.chatQuestion.trim();
    if (!q || this.chatLoading) return;

    if (!this.chatMessages.length) {
      this.currentSessionId = Date.now().toString();
    }

    this.chatMessages.push({ role: 'user', text: q, timestamp: new Date().toISOString() });

    // Push an empty AI message immediately — tokens will stream into it
    const aiMsg: ChatMessage = { role: 'ai', text: '', timestamp: new Date().toISOString() };
    this.chatMessages.push(aiMsg);

    this.chatQuestion = '';
    this.chatLoading = true;
    this.shouldScroll = true;

    this.api.chatStream(q).subscribe({
      next: (event) => {
        if (event.token) {
          aiMsg.text += event.token;
          aiMsg.html = this._mdToHtml(aiMsg.text);
          this.shouldScroll = true;
        }
        if (event.provider) this.chatProvider = event.provider;
        if (event.error) {
          aiMsg.text = this._friendlyError(event.error);
          aiMsg.html = undefined;
          this.chatLoading = false;
          this._saveCurrentSession();
        }
        if (event.done) {
          this.chatLoading = false;
          this._saveCurrentSession();
        }
      },
      error: (err) => {
        this.chatLoading = false;
        aiMsg.text = this._friendlyError(err?.error?.detail || err?.message || '');
        aiMsg.html = undefined;
        this.shouldScroll = true;
        this._saveCurrentSession();
      },
      complete: () => {
        if (this.chatLoading) {
          this.chatLoading = false;
          this._saveCurrentSession();
        }
      },
    });
  }

  private _friendlyError(detail: string): string {
    if (detail.includes('OPENAI_API_KEY') || detail.includes('sk-'))
      return 'OpenAI API key not set. Add OPENAI_API_KEY=sk-... to backend/.env and restart.';
    if (detail.includes('GROQ_API_KEY') || detail.includes('gsk_'))
      return 'Groq API key not set. Add GROQ_API_KEY=gsk_... to backend/.env and restart.';
    if (detail.includes('credit') || detail.includes('billing') || detail.includes('quota'))
      return 'API quota exceeded. Check your usage limits.';
    if (detail.includes('ANTHROPIC') || detail.includes('anthropic'))
      return 'Anthropic key issue. Set LLM_PROVIDER=groq in backend/.env.';
    return detail || 'Request failed. Check LLM_PROVIDER and API key in backend/.env.';
  }

  loadSession(s: ChatSession): void {
    this._restoreSession(s);
  }

  deleteSession(id: string, event: Event): void {
    event.stopPropagation();
    this.sessions = this.sessions.filter(s => s.id !== id);
    localStorage.setItem(CHAT_STORAGE_KEY, JSON.stringify(this.sessions));
    if (this.currentSessionId === id) {
      this.newChat();
    }
  }

  clearAllSessions(): void {
    this.sessions = [];
    this.newChat();
    localStorage.removeItem(CHAT_STORAGE_KEY);
  }

  // ── Session grouping ────────────────────────────────────────────

  get todaySessions():     ChatSession[] { return this._group('today'); }
  get yesterdaySessions(): ChatSession[] { return this._group('yesterday'); }
  get olderSessions():     ChatSession[] { return this._group('older'); }

  sessionTitle(s: ChatSession): string {
    return s.title || 'New conversation';
  }

  get activeTitle(): string {
    const s = this.sessions.find(x => x.id === this.currentSessionId);
    return s ? this.sessionTitle(s) : 'Conversation';
  }

  sessionDate(s: ChatSession): string {
    const d = new Date(s.startedAt);
    const now = new Date();
    const diffMs = now.getTime() - d.getTime();
    const diffMin = Math.floor(diffMs / 60000);
    if (diffMin < 1)  return 'just now';
    if (diffMin < 60) return `${diffMin}m ago`;
    const diffH = Math.floor(diffMin / 60);
    if (diffH < 24)   return `${diffH}h ago`;
    if (diffH < 48)   return 'Yesterday';
    return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
  }

  // ── Provider label ──────────────────────────────────────────────

  get providerLabel(): string {
    switch (this.chatProvider.toLowerCase()) {
      case 'openai':    return 'ChatGPT';
      case 'anthropic': return 'Claude';
      case 'gemini':    return 'Gemini';
      case 'groq':      return 'Groq';
      case 'ollama':    return 'Ollama';
      case 'local':     return 'Built-in';
      default:          return this.chatProvider || 'Assistant';
    }
  }

  // ── Private helpers ─────────────────────────────────────────────

  private _restoreSession(s: ChatSession): void {
    this.chatMessages = s.messages.map(m => ({
      ...m,
      html: m.role === 'ai' ? this._mdToHtml(m.text) : undefined,
    }));
    this.chatProvider = s.provider;
    this.currentSessionId = s.id;
    this.shouldScroll = true;
  }

  private _generateTitle(messages: ChatMessage[]): string {
    const first = messages.find(m => m.role === 'user');
    if (!first) return 'New conversation';
    const t = first.text.trim();
    return t.length > 48 ? t.slice(0, 45) + '…' : t;
  }

  private _saveCurrentSession(): void {
    if (!this.chatMessages.length) return;
    const session: ChatSession = {
      id: this.currentSessionId,
      provider: this.chatProvider,
      title: this._generateTitle(this.chatMessages),
      startedAt: this.chatMessages[0].timestamp ?? new Date().toISOString(),
      messages: this.chatMessages.map(({ html: _, ...m }) => m),
    };
    const idx = this.sessions.findIndex(s => s.id === this.currentSessionId);
    if (idx >= 0) {
      this.sessions[idx] = session;
    } else {
      this.sessions.unshift(session);
    }
    if (this.sessions.length > MAX_SESSIONS) this.sessions = this.sessions.slice(0, MAX_SESSIONS);
    localStorage.setItem(CHAT_STORAGE_KEY, JSON.stringify(this.sessions));
  }

  private _loadSessions(): void {
    try {
      const raw = localStorage.getItem(CHAT_STORAGE_KEY);
      this.sessions = raw ? JSON.parse(raw) : [];
    } catch { this.sessions = []; }
  }

  private _group(which: 'today' | 'yesterday' | 'older'): ChatSession[] {
    const now = new Date();
    const startOfToday     = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
    const startOfYesterday = startOfToday - 86400000;

    return this.sessions.filter(s => {
      const t = new Date(s.startedAt).getTime();
      if (which === 'today')     return t >= startOfToday;
      if (which === 'yesterday') return t >= startOfYesterday && t < startOfToday;
      return t < startOfYesterday;
    });
  }

  private _mdToHtml(raw: string): string {
    let t = raw
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');

    t = t.replace(/^[─\-]{3,}\s*$/gm, '<hr>');

    t = t.replace(
      /((?:^\|.+\|\n?)+)/gm,
      (block) => {
        const rows = block.trim().split('\n').filter(r => r.trim());
        let html = '<table class="md-table">';
        rows.forEach((row, i) => {
          if (/^\|[\s\-|:]+\|$/.test(row)) return;
          const cells = row.split('|').slice(1, -1).map(c => c.trim());
          const tag = i === 0 ? 'th' : 'td';
          html += '<tr>' + cells.map(c => `<${tag}>${c}</${tag}>`).join('') + '</tr>';
        });
        html += '</table>';
        return html;
      }
    );

    t = t.replace(/`([^`]+)`/g, '<code>$1</code>');
    t = t.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    t = t.replace(/\*([^*\n]+)\*/g, '<em>$1</em>');

    t = t.replace(
      /((?:^\d+\.\s+.+\n?)+)/gm,
      (block) => {
        const items = block.trim().split('\n')
          .filter(l => /^\d+\./.test(l.trim()))
          .map(l => `<li>${l.replace(/^\d+\.\s+/, '')}</li>`)
          .join('');
        return `<ol>${items}</ol>`;
      }
    );

    t = t.replace(
      /((?:^[•\-]\s+.+\n?)+)/gm,
      (block) => {
        const items = block.trim().split('\n')
          .filter(l => /^[•\-]\s+/.test(l.trim()))
          .map(l => `<li>${l.replace(/^[•\-]\s+/, '')}</li>`)
          .join('');
        return `<ul>${items}</ul>`;
      }
    );

    t = t.replace(/^(<strong>[^<]+<\/strong>)\s*$/gm, '<h4>$1</h4>');
    t = t.replace(/\n/g, '<br>');
    t = t
      .replace(/<br>\s*(<\/?(?:ul|ol|li|table|tr|th|td|hr|h4)[^>]*>)/g, '$1')
      .replace(/(<\/?(?:ul|ol|li|table|tr|th|td|hr|h4)[^>]*>)\s*<br>/g, '$1');

    return t;
  }
}
