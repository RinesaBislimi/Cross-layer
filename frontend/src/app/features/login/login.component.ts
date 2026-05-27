import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { AuthService } from '../../core/services/auth.service';

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink],
  templateUrl: './login.component.html',
  styleUrls: ['./login.component.css'],
})
export class LoginComponent {
  mode: 'login' | 'register' = 'login';

  email    = '';
  password = '';
  fullName = '';
  error    = '';
  loading  = false;

  constructor(private auth: AuthService, private router: Router) {

    if (this.auth.isLoggedIn()) {
      this.router.navigate(['/dashboard']);
    }
  }

  toggleMode(): void {
    this.mode  = this.mode === 'login' ? 'register' : 'login';
    this.error = '';
  }

  submit(): void {
    this.error   = '';
    this.loading = true;

    const obs = this.mode === 'login'
      ? this.auth.login(this.email.trim(), this.password)
      : this.auth.register(this.email.trim(), this.password, this.fullName.trim());

    obs.subscribe({
      next: () => {
        this.loading = false;
        this.router.navigate(['/dashboard']);
      },
      error: (err) => {
        this.loading = false;
        this.error   = err?.error?.detail || 'Authentication failed. Please try again.';
      },
    });
  }
}
