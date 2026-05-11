# TraceWise Frontend Architecture

## Overview

TraceWise frontend is a modern Angular 19 application built with a modular, scalable architecture. The application uses standalone components, reactive programming with RxJS, and a clear separation of concerns.

## Architectural Principles

1. **Modularity**: Code is organized by feature and responsibility
2. **Scalability**: Structure supports growth without refactoring
3. **Maintainability**: Clear patterns and conventions for consistency
4. **Performance**: Lazy loading, code splitting, and optimization built-in
5. **Type Safety**: TypeScript strict mode enforced throughout

## Directory Structure

```
src/
├── app/
│   ├── core/              # Singleton services & core infrastructure
│   ├── shared/            # Reusable components & utilities
│   ├── features/          # Feature-specific business logic
│   └── ...
├── assets/                # Static assets & config
├── styles.scss            # Global styles
├── main.ts                # Application bootstrap
└── index.html
```

## Core Layer

**Location**: `src/app/core/`

The core layer contains singleton services and application-wide infrastructure:

### Services

- **ConfigService**: Manages application configuration loaded from `config.json`
- **LoggingService**: Provides structured logging with configurable levels
- **AuthService**: Handles authentication state and token management
- **MockDataService**: Provides placeholder data for features

### Components

- **LayoutComponent**: Main application layout with navigation
- **NotFoundComponent**: 404 error page

### Configuration

- **config.token.ts**: Defines `APP_CONFIG` injection token
- **http.interceptor.ts**: HTTP client interceptor for API calls

### Key Characteristics

- Services are provided at root level (`providedIn: 'root'`)
- Singleton instances shared across application
- Dependency injection for loose coupling
- No circular dependencies

## Shared Layer

**Location**: `src/app/shared/`

The shared layer contains reusable components, directives, and pipes:

### Components

- **NavigationComponent**: Application-wide navigation menu

### Utility Components

- **CardComponent**: Reusable card wrapper with styling

### Pipes

- **TruncatePipe**: Truncates strings to specified length
- **DateFormatPipe**: Formats dates in multiple formats

### Exports

- **index.ts**: Barrel export for convenient importing

### Key Characteristics

- No dependencies on features
- Reusable across feature modules
- Standalone components with explicit imports
- Pure functionality with minimal side effects

## Features Layer

**Location**: `src/app/features/`

The features layer contains feature-specific business logic:

### Feature Structure

```
features/
├── dashboard/
│   └── dashboard.component.ts
├── traces/
│   └── traces.component.ts
└── settings/
    └── settings.component.ts
```

### Feature Modules

Each feature is lazy-loaded for better performance:

- **Dashboard**: Application overview with statistics
- **Traces**: Compliance record management
- **Settings**: User preferences and configuration

### Key Characteristics

- Lazy-loaded routes for code splitting
- Feature-specific components and services
- Can depend on core and shared
- Cannot depend on other features (no cross-feature dependencies)

## Data Flow

### Configuration Flow

```
main.ts
  ↓
Load config.json from assets
  ↓
Provide APP_CONFIG token
  ↓
ConfigService injects token
  ↓
Components inject ConfigService
```

### HTTP Data Flow

```
Component
  ↓
HttpClient.get(url)
  ↓
ApiInterceptor
  - Adds base URL
  - Adds auth headers
  - Logs request
  ↓
Backend API
  ↓
Error handling
  ↓
LoggingService
```

### Routing Flow

```
AppComponent (root)
  ↓
Router outlet
  ↓
LayoutComponent
  ↓
Route outlet
  ↓
Lazy-loaded feature
```

## State Management

The application uses RxJS Observables for reactive state:

```typescript
// Service with observable
private traces$ = this.mockData.getTraces();

// Component subscribes
constructor(mockData: MockDataService) {
  this.traces$ = mockData.getTraces();
}

// Template uses async pipe
*ngIf="traces$ | async as traces"
```

### Principles

- Use Observables for async operations
- Prefer `async` pipe over manual subscription
- Use `takeUntil` pattern for unsubscribing
- Services expose data as Observables

## Styling Architecture

### Tailwind CSS

- Utility-first CSS framework
- Responsive design with breakpoints (sm, md, lg, xl)
- Custom colors defined in `tailwind.config.js`
- Global styles in `src/styles.scss`

### Angular Material

- Pre-built components for complex UI
- Material Design icons
- Accessibility built-in
- Theme configuration in `src/styles.scss`

### Precedence

1. Tailwind utilities for layout and spacing
2. Material components for complex interactions
3. Custom CSS for specific styling needs

## HTTP Communication

### Interceptor Pattern

All HTTP requests pass through `ApiInterceptor`:

```typescript
// Adds API base URL
if (!req.url.startsWith('http')) {
  req = req.clone({
    url: `${apiUrl}${req.url}`,
  });
}

// Adds authorization header
if (token) {
  req = req.clone({
    setHeaders: { Authorization: `Bearer ${token}` },
  });
}

// Logs requests
this.loggingService.debug(`HTTP ${req.method} ${req.url}`);

// Handles errors
catchError((error) => {
  this.loggingService.error(`HTTP Error ${error.status}`, error);
  return throwError(() => new Error(errorMessage));
});
```

## Dependency Injection

### Pattern

```typescript
// Inject services into components/services
constructor(private service: MyService) {}

// Or using newer syntax
private service = inject(MyService);
```

### Key Principles

- Inject at lowest level needed (components vs services)
- Use `inject()` function for standalone components
- Keep dependencies minimal and explicit
- Avoid circular dependencies

## Routing

### Route Structure

```typescript
export const routes: Routes = [
  { path: '', redirectTo: '/dashboard', pathMatch: 'full' },
  {
    path: '',
    component: LayoutComponent,
    children: [
      {
        path: 'dashboard',
        loadComponent: () => import(...).then(m => m.DashboardComponent),
      },
      // ...
    ],
  },
  { path: '**', component: NotFoundComponent },
];
```

### Lazy Loading

- Features are lazy-loaded via `loadComponent`
- Reduces initial bundle size
- Each feature loads on demand

## Testing Strategy

### Unit Tests (Vitest)

- Test services, pipes, utilities
- Mock external dependencies
- Aim for > 70% coverage
- Use `@testing-library/angular` for component testing

### E2E Tests (Cypress)

- Test user workflows
- Navigate through application
- Verify integration with backend
- Test edge cases and error states

## Configuration Management

### Design

```
config.json (assets/)
    ↓
fetch at startup
    ↓
APP_CONFIG token
    ↓
ConfigService
    ↓
Components/Services inject ConfigService
```

### Benefits

- Single source of truth
- Runtime configuration (no rebuilds)
- Environment-specific settings
- Easy Docker/K8s integration

## Performance Considerations

### Bundle Size

- Target: < 750KB initial + lazy chunks
- Use lazy loading for features
- Tree shake unused code
- Monitor bundle size with `webpack-bundle-analyzer`

### Runtime Performance

- Use `OnPush` change detection when possible
- Unsubscribe from Observables (async pipe or takeUntil)
- Avoid memory leaks
- Profile with Chrome DevTools

## Security

### Built-in Protections

- Angular sanitizes user input
- CSRF tokens via HTTP interceptor
- No hardcoded secrets
- Authorization headers from ConfigService

### Best Practices

- Validate input on server
- Never store sensitive data in localStorage
- Use HTTPS in production
- Implement rate limiting on backend

## Extensibility

### Adding New Features

1. Create `src/app/features/my-feature/` directory
2. Create `my-feature.component.ts` with standalone component
3. Add lazy-loaded route in `app.routes.ts`
4. Use shared components and core services

### Adding New Services

1. Create in appropriate layer (core or feature)
2. Use `providedIn: 'root'` for singletons
3. Inject via constructor or `inject()`
4. Write unit tests

### Adding New Shared Components

1. Create in `src/app/shared/`
2. Make standalone component
3. Export from `shared/index.ts`
4. Document usage

## Technology Stack

- **Framework**: Angular 19
- **Language**: TypeScript 5.6
- **Styling**: Tailwind CSS 3.x + Angular Material 19
- **HTTP**: Angular HttpClient with custom interceptor
- **Routing**: Angular Router with lazy loading
- **Testing**: Vitest + Cypress
- **Code Quality**: ESLint + Prettier
- **Package Manager**: npm

## Future Enhancements

- State management (NgRx/Akita) for complex state
- GraphQL for API queries
- PWA capabilities (service workers)
- Internationalization (i18n)
- Advanced caching strategies
- Real-time updates (WebSocket/SignalR)
