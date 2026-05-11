import { Injectable } from '@angular/core';
import { BehaviorSubject, Observable, throwError } from 'rxjs';

export interface User {
  id: string;
  email: string;
  name: string;
}

@Injectable({
  providedIn: 'root',
})
export class AuthService {
  private currentUser = new BehaviorSubject<User | null>(null);
  public currentUser$ = this.currentUser.asObservable();

  private isAuthenticated = new BehaviorSubject<boolean>(false);
  public isAuthenticated$ = this.isAuthenticated.asObservable();

  login(_email: string, _password: string): Observable<User> {
    return throwError(() => new Error('Authentication not yet implemented'));
  }

  logout(): void {
    // TODO: Implement logout logic
    this.currentUser.next(null);
    this.isAuthenticated.next(false);
    localStorage.removeItem('auth_token');
  }

  getCurrentUser(): Observable<User | null> {
    return this.currentUser$;
  }

  isAuthenticatedUser(): Observable<boolean> {
    return this.isAuthenticated$;
  }

  setAuthToken(token: string): void {
    localStorage.setItem('auth_token', token);
  }

  getAuthToken(): string | null {
    return localStorage.getItem('auth_token');
  }

  clearAuthToken(): void {
    localStorage.removeItem('auth_token');
  }
}
