import 'zone.js';
import 'zone.js/testing';
import { getTestBed } from '@angular/core/testing';
import {
  BrowserDynamicTestingModule,
  platformBrowserDynamicTesting,
} from '@angular/platform-browser-dynamic/testing';
import { BrowserAnimationsModule } from '@angular/platform-browser/animations';
import { vi } from 'vitest';

// Initialize the Angular testing environment with guard for worker threads
try {
  getTestBed().initTestEnvironment(
    [BrowserDynamicTestingModule, BrowserAnimationsModule],
    platformBrowserDynamicTesting(),
  );
} catch {
  // Already initialized in this worker
}

// Suppress Angular deprecation warnings in tests using vi.spyOn for safe teardown
beforeEach(() => {
  vi.spyOn(console, 'warn').mockImplementation((...args: any[]) => {
    const message = args[0];
    if (typeof message === 'string' && message.includes('NgZone')) {
      return;
    }
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});
