# Contributing to TraceWise Frontend

Thank you for contributing to TraceWise! This document provides guidelines for contributing to the project.

## Code of Conduct

- Be respectful and constructive
- Provide clear feedback
- Help others learn and grow
- Report issues responsibly

## Getting Started

1. Fork the repository
2. Clone your fork: `git clone <your-fork-url>`
3. Create a feature branch: `git checkout -b feature/my-feature`
4. Install dependencies: `npm install`
5. Make your changes
6. Follow the guidelines below
7. Submit a pull request

## Development Workflow

### Before Starting Work

```bash
# Update from main
git checkout main
git pull origin main

# Create feature branch
git checkout -b feature/descriptive-name
```

### While Developing

```bash
# Run dev server
npm start

# Run linting
npm run lint

# Check formatting
npm run format:check

# Run tests
npm run test:unit

# Check build
npm run build
```

### Before Submitting PR

```bash
# Format code
npm run format

# Fix linting issues
npm run lint -- --fix

# Run all tests
npm run test:unit
npm run test:e2e:headless

# Build for production
npm run build:prod
```

## Code Style

### Naming Conventions

#### Components

```typescript
// File: my-component.component.ts
// Class: MyComponentComponent or MyComponent
@Component({
  selector: 'app-my-component',
  ...
})
export class MyComponentComponent {}
```

#### Services

```typescript
// File: my.service.ts
// Class: MyService
@Injectable({ providedIn: 'root' })
export class MyService {}
```

#### Pipes

```typescript
// File: my.pipe.ts
// Class: MyPipe
@Pipe({ name: 'my', standalone: true })
export class MyPipe implements PipeTransform {}
```

#### Directives

```typescript
// File: my.directive.ts
// Class: MyDirective
@Directive({ selector: '[appMy]', standalone: true })
export class MyDirective {}
```

#### Files

Use kebab-case for file names:
- `my-component.component.ts`
- `my.service.ts`
- `my.pipe.ts`
- `my.directive.ts`

### TypeScript Style

#### Strict Mode

All code must pass TypeScript strict mode:

```typescript
// Use explicit types
const count: number = 0;
const name: string = 'John';

// Avoid 'any'
const data: any = {}; // ❌ Don't do this

// Use interfaces
interface User {
  id: string;
  name: string;
}

// Initialize properties
private user: User | null = null;
```

#### Naming

```typescript
// Classes: PascalCase
class UserService {}

// Functions/variables: camelCase
function getUserById(id: string) {}
const maxRetries = 3;

// Constants: UPPER_SNAKE_CASE
const MAX_RETRIES = 3;
const API_URL = 'https://api.example.com';

// Private properties: prefix with underscore
private _count = 0;
```

### Component Structure

```typescript
import { Component, Input, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';

interface MyData {
  id: string;
  name: string;
}

@Component({
  selector: 'app-my-component',
  standalone: true,
  imports: [CommonModule],
  template: `<div>{{ data.name }}</div>`,
  styles: [`div { color: blue; }`],
})
export class MyComponentComponent implements OnInit {
  @Input() data!: MyData;

  private myService = inject(MyService);

  ngOnInit(): void {
    // Initialization logic
  }
}
```

### Service Structure

```typescript
import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

interface ApiResponse {
  data: unknown[];
}

@Injectable({ providedIn: 'root' })
export class MyService {
  private http = inject(HttpClient);

  getData(): Observable<ApiResponse> {
    return this.http.get<ApiResponse>('/api/data');
  }
}
```

## Testing

### Unit Testing

All new code should include unit tests:

```typescript
// my.service.spec.ts
import { TestBed } from '@angular/core/testing';
import { MyService } from './my.service';

describe('MyService', () => {
  let service: MyService;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    service = TestBed.inject(MyService);
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });

  it('should perform expected action', () => {
    // Arrange
    const input = 'test';

    // Act
    const result = service.doSomething(input);

    // Assert
    expect(result).toBe('expected');
  });
});
```

### Component Testing

```typescript
// my-component.component.spec.ts
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { MyComponentComponent } from './my-component.component';

describe('MyComponentComponent', () => {
  let component: MyComponentComponent;
  let fixture: ComponentFixture<MyComponentComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [MyComponentComponent],
    }).compileComponents();

    fixture = TestBed.createComponent(MyComponentComponent);
    component = fixture.componentInstance;
    component.data = { id: '1', name: 'Test' };
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should display data', () => {
    const compiled = fixture.nativeElement;
    expect(compiled.textContent).toContain('Test');
  });
});
```

### E2E Testing

Test critical user workflows:

```typescript
// critical-feature.cy.ts
describe('Critical Feature', () => {
  beforeEach(() => {
    cy.visit('/');
  });

  it('should complete workflow', () => {
    cy.contains('Start').click();
    cy.url().should('include', '/feature');
    cy.get('[data-testid="result"]').should('be.visible');
  });
});
```

## Testing Requirements

- New features must include unit tests
- Critical paths must have E2E tests
- Aim for > 70% code coverage
- All tests must pass before PR merge

## Commit Messages

### Format

```
<type>(<scope>): <subject>

<body>

<footer>
```

### Types

- `feat`: New feature
- `fix`: Bug fix
- `refactor`: Code refactoring without behavior change
- `style`: Code style changes (formatting, missing semicolons)
- `test`: Test additions or changes
- `docs`: Documentation changes
- `chore`: Build, dependencies, tooling

### Examples

```
feat(dashboard): add statistics widget

- Fetch stats from API
- Display in dashboard
- Add unit tests

Closes #123
```

```
fix(auth): handle token expiration correctly

The auth service now properly refreshes expired tokens.

Fixes #456
```

## Pull Request Guidelines

### PR Title

- Start with type: `feat:`, `fix:`, `refactor:`
- Be descriptive but concise
- Use imperative mood: "Add feature" not "Added feature"

### PR Description

```markdown
## Description
Brief description of changes

## Changes
- Change 1
- Change 2

## Testing
How to test this change

## Checklist
- [ ] Code follows style guidelines
- [ ] Self-review completed
- [ ] Tests added/updated
- [ ] Documentation updated
- [ ] No breaking changes
```

### Review Process

1. Create PR with description
2. Automated checks must pass
3. Code review by maintainer
4. Address feedback
5. Merge when approved

## Component Creation Checklist

- [ ] Component is standalone
- [ ] Imports are explicit
- [ ] TypeScript strict mode compliant
- [ ] Component has unit test
- [ ] Styling uses Tailwind/Material
- [ ] Props are documented via Input/Output
- [ ] Accessibility considered (ARIA labels if needed)
- [ ] Performance optimized (OnPush change detection if possible)

## Service Creation Checklist

- [ ] Service has `providedIn: 'root'`
- [ ] Uses dependency injection
- [ ] Has unit tests with 80%+ coverage
- [ ] Error handling implemented
- [ ] Logging added for debugging
- [ ] Observable subscriptions properly managed
- [ ] No circular dependencies

## Documentation Requirements

- Add JSDoc comments to public methods
- Update README.md for new features
- Update ARCHITECTURE.md for structural changes
- Add inline comments for complex logic
- Include example usage in PR description

## Performance Guidelines

- Lazy load features and large components
- Use OnPush change detection
- Unsubscribe from Observables properly
- Avoid memory leaks
- Monitor bundle size

## Security Guidelines

- Never commit secrets or credentials
- Use environment variables for sensitive data
- Validate all user input
- Sanitize dynamic HTML
- Use HTTPS in production
- Follow OWASP guidelines

## Questions?

- Check existing issues and PRs
- Read ARCHITECTURE.md for design patterns
- Ask in PRs or issues
- Contact maintainers

Thank you for contributing! 🎉
