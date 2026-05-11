import { Injectable, inject } from '@angular/core';
import { APP_CONFIG, AppConfig } from './config.token';

@Injectable({
  providedIn: 'root',
})
export class ConfigService {
  private config = inject(APP_CONFIG);

  getConfig(): AppConfig {
    return this.config;
  }

  getApiUrl(): string {
    return this.config.apiUrl;
  }

  getEnvironment(): string {
    return this.config.environment;
  }

  getAppName(): string {
    return this.config.appName;
  }

  getAppVersion(): string {
    return this.config.appVersion;
  }

  getLogLevel(): string {
    return this.config.logLevel;
  }

  getCacheDuration(): number {
    return this.config.cacheDuration;
  }

  getSessionTimeout(): number {
    return this.config.sessionTimeout;
  }

  isProduction(): boolean {
    return this.config.environment === 'production';
  }

  isDevelopment(): boolean {
    return this.config.environment === 'development';
  }
}
