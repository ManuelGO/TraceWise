import { Injectable, inject } from '@angular/core';
import {
  HttpInterceptor,
  HttpRequest,
  HttpHandler,
  HttpEvent,
  HttpErrorResponse,
} from '@angular/common/http';
import { Observable, throwError } from 'rxjs';
import { catchError } from 'rxjs/operators';
import { ConfigService } from '../../services/config/config.service';
import { LoggingService } from '../../services/logging/logging.service';
import { AuthService } from '../../services/auth/auth.service';

@Injectable()
export class ApiInterceptor implements HttpInterceptor {
  private configService = inject(ConfigService);
  private loggingService = inject(LoggingService);
  private authService = inject(AuthService);

  intercept(req: HttpRequest<unknown>, next: HttpHandler): Observable<HttpEvent<unknown>> {
    const apiUrl = this.configService.getApiUrl();

    if (!req.url.startsWith('http://') && !req.url.startsWith('https://')) {
      const separator = req.url.startsWith('/') ? '' : '/';
      req = req.clone({
        url: `${apiUrl}${separator}${req.url}`,
      });
    }

    const token = this.authService.getAuthToken();
    const targetUrl = new URL(req.url.startsWith('http') ? req.url : `${apiUrl}${req.url}`);
    const apiOrigin = new URL(apiUrl).origin;
    if (token && targetUrl.origin === apiOrigin) {
      req = req.clone({
        setHeaders: {
          Authorization: `Bearer ${token}`,
        },
      });
    }

    this.loggingService.debug(`HTTP ${req.method} ${req.url}`);

    return next.handle(req).pipe(
      catchError((error: HttpErrorResponse) => {
        this.loggingService.error(`HTTP Error ${error.status} on ${req.method} request`, {
          status: error.status,
          url: req.url,
        });

        return throwError(() => new Error(`Request failed with status ${error.status}`));
      })
    );
  }
}
