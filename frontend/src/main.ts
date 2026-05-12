import { bootstrapApplication } from '@angular/platform-browser';
import { AppComponent } from './app/app.component';
import { appConfig } from './app/app.config';
import { APP_CONFIG, AppConfig } from './app/core/services/config/config.token';

async function loadConfig(): Promise<AppConfig> {
  const response = await fetch('/assets/config.json');
  if (!response.ok) {
    throw new Error(`Failed to load config: ${response.statusText}`);
  }
  const config = (await response.json()) as AppConfig;

  const ALLOWED_API_ORIGINS = ['http://localhost:8000', 'https://api.tracewise.example.com'];
  try {
    const parsed = new URL(config.apiUrl);
    if (!ALLOWED_API_ORIGINS.includes(parsed.origin)) {
      throw new Error(`Untrusted apiUrl origin: ${parsed.origin}`);
    }
  } catch (err) {
    if (err instanceof Error && err.message.includes('Untrusted')) {
      throw err;
    }
    throw new Error(`Invalid apiUrl in config: ${config.apiUrl}`);
  }

  return config;
}

loadConfig()
  .then((config) => {
    return bootstrapApplication(AppComponent, {
      ...appConfig,
      providers: [...appConfig.providers, { provide: APP_CONFIG, useValue: config }],
    });
  })
  .catch((err) => console.error('Application bootstrap failed:', err));
