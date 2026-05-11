import { InjectionToken } from '@angular/core';

export interface AppConfig {
  apiUrl: string;
  environment: 'development' | 'staging' | 'production';
  appName: string;
  appVersion: string;
  logLevel: 'debug' | 'info' | 'warn' | 'error';
  cacheDuration: number;
  sessionTimeout: number;
}

export const APP_CONFIG = new InjectionToken<AppConfig>('app.config');
