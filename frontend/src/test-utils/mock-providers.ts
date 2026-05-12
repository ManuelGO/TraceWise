import { vi } from 'vitest';
import { AppConfig } from '../app/core/services/config/config.token';

/**
 * Common mock providers and utilities for testing
 * Provides reusable mocks for services and tokens used across the application
 */

/**
 * Creates a mock AppConfig token value for testing
 */
export const mockAppConfig = (overrides?: Partial<AppConfig>): AppConfig => ({
  apiUrl: 'http://localhost:8000',
  environment: 'development',
  appName: 'TraceWise',
  appVersion: '0.0.1',
  logLevel: 'debug',
  cacheDuration: 300000,
  sessionTimeout: 1800000,
  ...overrides,
});

/**
 * Creates a mock ConfigService for testing
 * Derives values from mockAppConfig to eliminate duplication
 */
export const mockConfigService = (overrides?: Partial<AppConfig>) => {
  const cfg = mockAppConfig(overrides);
  return {
    getConfig: vi.fn().mockReturnValue(cfg),
    getApiUrl: vi.fn().mockReturnValue(cfg.apiUrl),
    getEnvironment: vi.fn().mockReturnValue(cfg.environment),
    getAppName: vi.fn().mockReturnValue(cfg.appName),
    getAppVersion: vi.fn().mockReturnValue(cfg.appVersion),
    getLogLevel: vi.fn().mockReturnValue(cfg.logLevel),
    getCacheDuration: vi.fn().mockReturnValue(cfg.cacheDuration),
    getSessionTimeout: vi.fn().mockReturnValue(cfg.sessionTimeout),
    isDevelopment: vi.fn().mockReturnValue(cfg.environment === 'development'),
    isProduction: vi.fn().mockReturnValue(cfg.environment === 'production'),
  };
};

/**
 * Creates a spy object that tracks calls to all methods
 * Useful for verifying component behavior during tests
 */
export const createSpyObj = <T extends Record<string, any>>(
  methodNames: (keyof T)[],
): Partial<T> =>
  Object.fromEntries(methodNames.map((m) => [m, vi.fn()])) as Partial<T>;
