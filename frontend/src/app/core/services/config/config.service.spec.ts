import { TestBed } from '@angular/core/testing';
import { ConfigService } from './config.service';
import { APP_CONFIG, AppConfig } from './config.token';

describe('ConfigService', () => {
  let service: ConfigService;
  const mockConfig: AppConfig = {
    apiUrl: 'http://localhost:8000',
    environment: 'development',
    appName: 'TraceWise',
    appVersion: '0.0.1',
    logLevel: 'debug',
    cacheDuration: 300000,
    sessionTimeout: 1800000,
  };

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [ConfigService, { provide: APP_CONFIG, useValue: mockConfig }],
    });
    service = TestBed.inject(ConfigService);
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });

  it('should return API URL', () => {
    expect(service.getApiUrl()).toBe('http://localhost:8000');
  });

  it('should return environment', () => {
    expect(service.getEnvironment()).toBe('development');
  });

  it('should return app name', () => {
    expect(service.getAppName()).toBe('TraceWise');
  });

  it('should identify development environment', () => {
    expect(service.isDevelopment()).toBe(true);
    expect(service.isProduction()).toBe(false);
  });

  it('should return cache duration', () => {
    expect(service.getCacheDuration()).toBe(300000);
  });
});
