import { Injectable, inject } from '@angular/core';
import { ConfigService } from '../config/config.service';

type LogLevel = 'debug' | 'info' | 'warn' | 'error';

@Injectable({
  providedIn: 'root',
})
export class LoggingService {
  private configService = inject(ConfigService);

  private isLevelEnabled(level: LogLevel): boolean {
    const levels: Record<LogLevel, number> = {
      debug: 0,
      info: 1,
      warn: 2,
      error: 3,
    };

    const raw = this.configService.getLogLevel();
    const configLevel = (raw in levels ? raw : 'debug') as LogLevel;
    return levels[level] >= levels[configLevel];
  }

  debug(message: string, data?: unknown): void {
    if (this.isLevelEnabled('debug')) {
      console.log(`[DEBUG] ${message}`, data);
    }
  }

  info(message: string, data?: unknown): void {
    if (this.isLevelEnabled('info')) {
      console.log(`[INFO] ${message}`, data);
    }
  }

  warn(message: string, data?: unknown): void {
    if (this.isLevelEnabled('warn')) {
      console.warn(`[WARN] ${message}`, data);
    }
  }

  error(message: string, error?: unknown): void {
    if (this.isLevelEnabled('error')) {
      console.error(`[ERROR] ${message}`, error);
    }
  }
}
