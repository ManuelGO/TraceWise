# Frontend Testing Guide

This document provides comprehensive guidance on testing Angular components and services in TraceWise using Vitest and Angular Testing Library.

## Quick Start

### Running Tests

```bash
# Run all tests once
npm run test:unit

# Run tests in watch mode (re-run on file changes)
npm run test:unit:watch

# Generate coverage report
npm run test:unit:coverage

# Open interactive test dashboard
npm run test:ui
```

### File Naming Convention

- Test files must end with `.spec.ts`
- Place them in the same directory as the component/service they test
- Example: `config.service.spec.ts` tests `config.service.ts`

### Test File Structure

```
src/
├── app/
│   ├── core/services/config/
│   │   ├── config.service.ts
│   │   └── config.service.spec.ts  ← Test file
│   └── shared/components/card/
│       ├── card.component.ts
│       └── card.component.spec.ts  ← Test file
└── test-utils/                       ← Shared test utilities
    ├── mock-providers.ts
    └── testing-library-setup.ts
```

## Writing Tests

### Test Structure (Arrange-Act-Assert)

Every test should follow the AAA pattern:

```typescript
it('should do something specific', () => {
  // Arrange: Set up test data and dependencies
  const input = 'test value';
  
  // Act: Perform the action being tested
  const result = functionUnderTest(input);
  
  // Assert: Verify the result
  expect(result).toBe('expected value');
});
```

## Service Tests

### Basic Service Test Pattern

```typescript
import { TestBed } from '@angular/core/testing';
import { MyService } from './my.service';

describe('MyService', () => {
  let service: MyService;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [MyService],
    });
    service = TestBed.inject(MyService);
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });

  it('should return expected value', () => {
    const result = service.myMethod();
    expect(result).toEqual(expectedValue);
  });
});
```

### Testing with Dependencies

When a service depends on other services, provide mocks:

```typescript
import { TestBed } from '@angular/core/testing';
import { MyService } from './my.service';
import { DependencyService } from './dependency.service';

describe('MyService with Dependencies', () => {
  let service: MyService;
  let dependencyService: jasmine.SpyObj<DependencyService>;

  beforeEach(() => {
    const spy = jasmine.createSpyObj('DependencyService', ['method']);
    
    TestBed.configureTestingModule({
      providers: [
        MyService,
        { provide: DependencyService, useValue: spy },
      ],
    });
    
    service = TestBed.inject(MyService);
    dependencyService = TestBed.inject(DependencyService) as jasmine.SpyObj<DependencyService>;
  });

  it('should call dependency method', () => {
    service.doSomething();
    expect(dependencyService.method).toHaveBeenCalled();
  });
});
```

### Testing with Tokens

When using injection tokens (like APP_CONFIG):

```typescript
import { TestBed } from '@angular/core/testing';
import { ConfigService } from './config.service';
import { APP_CONFIG, AppConfig } from './config.token';
import { mockAppConfig } from '../test-utils/mock-providers';

describe('ConfigService with Token', () => {
  let service: ConfigService;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        ConfigService,
        { provide: APP_CONFIG, useValue: mockAppConfig() },
      ],
    });
    service = TestBed.inject(ConfigService);
  });

  it('should use injected config', () => {
    expect(service.getApiUrl()).toBe('http://localhost:8000');
  });

  it('should allow config override', () => {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      providers: [
        ConfigService,
        { 
          provide: APP_CONFIG, 
          useValue: mockAppConfig({ apiUrl: 'http://custom:9000' }) 
        },
      ],
    });
    service = TestBed.inject(ConfigService);
    
    expect(service.getApiUrl()).toBe('http://custom:9000');
  });
});
```

## Component Tests

### Basic Component Test Pattern

```typescript
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { MyComponent } from './my.component';

describe('MyComponent', () => {
  let component: MyComponent;
  let fixture: ComponentFixture<MyComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [MyComponent], // For standalone components
    });

    fixture = TestBed.createComponent(MyComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should render content', () => {
    const compiled = fixture.nativeElement;
    expect(compiled.querySelector('h1')).toBeTruthy();
  });
});
```

### Testing Inputs and Outputs

```typescript
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { MyComponent } from './my.component';

describe('MyComponent with Input/Output', () => {
  let component: MyComponent;
  let fixture: ComponentFixture<MyComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [MyComponent],
    });

    fixture = TestBed.createComponent(MyComponent);
    component = fixture.componentInstance;
  });

  it('should update when input changes', () => {
    component.title = 'New Title';
    fixture.detectChanges();
    
    expect(component.title).toBe('New Title');
  });

  it('should emit output event', () => {
    spyOn(component.myEvent, 'emit');
    component.triggerEvent();
    
    expect(component.myEvent.emit).toHaveBeenCalledWith(expectedValue);
  });
});
```

## Testing Async Operations

### Testing Promises and Async Code

```typescript
it('should handle async operations', async () => {
  const result = await component.asyncMethod();
  expect(result).toEqual(expectedValue);
});
```

### Testing with `fakeAsync` and `tick`

```typescript
import { fakeAsync, tick } from '@angular/core/testing';

it('should handle delayed operations', fakeAsync(() => {
  component.startTimer();
  
  tick(1000); // Fast-forward time by 1000ms
  fixture.detectChanges();
  
  expect(component.timerFinished).toBe(true);
}));
```

## Common Testing Patterns

### Testing with `spy`

```typescript
it('should call method on user interaction', () => {
  spyOn(service, 'save');
  component.onSave();
  expect(service.save).toHaveBeenCalledWith(expectedData);
});
```

### Testing Error Handling

```typescript
it('should handle errors gracefully', () => {
  spyOn(service, 'fetch').and.returnValue(
    throwError(() => new Error('Network error'))
  );
  
  component.loadData();
  
  expect(component.error).toBe('Network error');
});
```

### Testing DOM Elements

```typescript
import { DebugElement } from '@angular/core';
import { By } from '@angular/platform-browser';

it('should find element by CSS selector', () => {
  const element: DebugElement = fixture.debugElement.query(
    By.css('.my-class')
  );
  expect(element).toBeTruthy();
});

it('should find element by directive', () => {
  const elements = fixture.debugElement.queryAll(
    By.directive(MyDirective)
  );
  expect(elements.length).toBeGreaterThan(0);
});
```

## Using Test Utilities

### Mock Providers

The `src/test-utils/` directory provides reusable mocks:

```typescript
import { mockAppConfig, mockConfigService } from '../test-utils/mock-providers';

// Use in tests
const config = mockAppConfig({ environment: 'production' });
const serviceMock = mockConfigService();
```

## Best Practices

### 1. Test Behavior, Not Implementation

❌ **Bad:**
```typescript
it('should call getApiUrl method', () => {
  spyOn(service, 'getApiUrl');
  service.getApiUrl();
  expect(service.getApiUrl).toHaveBeenCalled();
});
```

✅ **Good:**
```typescript
it('should return correct API URL', () => {
  const url = service.getApiUrl();
  expect(url).toBe('http://localhost:8000');
});
```

### 2. Keep Tests Independent

Each test should be isolated and not depend on others:

```typescript
beforeEach(() => {
  // Reset state before each test
  TestBed.resetTestingModule();
  // Reinitialize services
});
```

### 3. Use Descriptive Test Names

```typescript
// Good - describes what the test verifies
it('should display error message when API request fails', () => {
  // ...
});

// Bad - vague
it('should work correctly', () => {
  // ...
});
```

### 4. Avoid Testing Implementation Details

Don't test private methods or internal logic that users don't care about. Focus on public API:

```typescript
// Bad - testing private implementation
it('should initialize _cache', () => {
  expect(service._cache).toBeDefined();
});

// Good - testing public behavior
it('should return cached value on second call', () => {
  const result1 = service.getData();
  const result2 = service.getData();
  expect(result2).toBe(result1);
});
```

### 5. Use Data-TestId for Reliable Element Selection

In templates, use `data-testid` for more reliable element selection:

```typescript
// In template
<button data-testid="submit-btn">Submit</button>

// In test
const button = fixture.nativeElement.querySelector('[data-testid="submit-btn"]');
expect(button.textContent).toContain('Submit');
```

## Coverage Expectations

### MVP Coverage Targets

- **Statements:** 50%+ (focus on critical paths)
- **Branches:** 40%+ (main decision points)
- **Functions:** 50%+ (exported APIs)
- **Lines:** 50%+ (code executed)

These are realistic targets for initial setup. Increase as the test suite matures.

### Viewing Coverage Reports

```bash
npm run test:unit:coverage
open coverage/index.html
```

The HTML report shows:
- Overall coverage percentage
- File-by-file breakdown
- Uncovered lines highlighted
- Branch coverage details

## Debugging Tests

### Run Single Test File

```bash
npm run test:unit -- src/app/services/config/config.service.spec.ts
```

### Run Tests Matching Pattern

```bash
npm run test:unit -- --grep "ConfigService"
```

### Use Vitest UI for Visual Debugging

```bash
npm run test:ui
```

This opens an interactive dashboard where you can:
- View test results in real-time
- See code coverage visualization
- Debug failing tests
- Inspect component output

### Console Logging in Tests

```typescript
it('should debug values', () => {
  const result = service.calculate(5);
  console.log('Result:', result); // Visible in test output
  expect(result).toBe(10);
});
```

## Troubleshooting

### Issue: "Cannot read properties of undefined"

**Cause:** Service dependency not injected

**Solution:**
```typescript
TestBed.configureTestingModule({
  providers: [ServiceClass, DependencyService], // Add missing provider
});
```

### Issue: "Timeout waiting for async operation"

**Cause:** Async operation not completed or properly awaited

**Solution:**
```typescript
it('should complete async operation', async () => {
  await expectAsync(promise).toBeResolved(); // Use explicit async/await
});
```

### Issue: "Module not found" in template

**Cause:** Template references component not imported

**Solution:**
```typescript
TestBed.configureTestingModule({
  imports: [MyComponent, SharedModule], // Import all used components/modules
});
```

## CI/CD Integration

Tests run automatically on:
- Pull requests to `main`
- Pushes to `main`

Test failures block merges. View CI logs in GitHub Actions to debug failures.

## Resources

- [Angular Testing Documentation](https://angular.io/guide/testing)
- [Vitest Documentation](https://vitest.dev/)
- [Angular Testing Library](https://github.com/testing-library/angular)
- [ConfigService Example](src/app/core/services/config/config.service.spec.ts)
- [CardComponent Example](src/app/shared/components/card/card.component.spec.ts)

## Contributing

When adding new features, include tests that cover:
1. Happy path (normal operation)
2. Edge cases (boundary conditions)
3. Error scenarios (what happens when things go wrong)

Follow the patterns demonstrated in existing test files.
