import { ComponentFixture } from '@angular/core/testing';
import { BrowserAnimationsModule } from '@angular/platform-browser/animations';

/**
 * Angular Testing Library configuration and utilities
 * Provides common setup for component testing with Angular Testing Library
 */

export const defaultTestComponentOptions = {
  imports: [BrowserAnimationsModule],
};

/**
 * Standard fixture cleanup - called after each test
 */
export function cleanupFixture(fixture: ComponentFixture<any>): void {
  fixture.destroy();
}

/**
 * Wait for Angular to process pending async operations
 * Useful when testing components with async pipes, HTTP calls, etc.
 */
export async function detectChanges(fixture: ComponentFixture<any>) {
  fixture.detectChanges();
  await fixture.whenStable();
}
