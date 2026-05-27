import { Injectable, signal, computed } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Router } from '@angular/router';
import { Observable, tap } from 'rxjs';
import { environment } from '../../../environments/environment';

export interface UserInfo {
  id:         number;
  email:      string;
  full_name:  string;
  role:       string;
  is_active:  boolean;
  created_at: string;
}

export interface AuthResponse {
  access_token: string;
  token_type:   string;
  user:         UserInfo;
}

const TOKEN_KEY = 'cl_token';
const USER_KEY  = 'cl_user';

@Injectable({ providedIn: 'root' })
export class AuthService {
  private base = environment.apiUrl;


  private _user = signal<UserInfo | null>(this._loadUser());
  readonly user        = this._user.asReadonly();
  readonly isLoggedIn  = computed(() => this._user() !== null);
  readonly isAdmin     = computed(() => this._user()?.role === 'admin');

  constructor(private http: HttpClient, private router: Router) {}



  getToken(): string | null {
    return localStorage.getItem(TOKEN_KEY);
  }

  private _loadUser(): UserInfo | null {
    try {
      const raw = localStorage.getItem(USER_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  }

  private _persist(res: AuthResponse): void {
    localStorage.setItem(TOKEN_KEY, res.access_token);
    localStorage.setItem(USER_KEY, JSON.stringify(res.user));
    this._user.set(res.user);
  }



  register(email: string, password: string, fullName = ''): Observable<AuthResponse> {
    return this.http.post<AuthResponse>(`${this.base}/auth/register`, {
      email, password, full_name: fullName,
    }).pipe(tap(res => this._persist(res)));
  }

  login(email: string, password: string): Observable<AuthResponse> {
    return this.http.post<AuthResponse>(`${this.base}/auth/login`, {
      email, password,
    }).pipe(tap(res => this._persist(res)));
  }

  logout(): void {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    this._user.set(null);
    this.router.navigate(['/login']);
  }

  refreshProfile(): Observable<UserInfo> {
    return this.http.get<UserInfo>(`${this.base}/auth/me`).pipe(
      tap(u => {
        localStorage.setItem(USER_KEY, JSON.stringify(u));
        this._user.set(u);
      })
    );
  }
}
