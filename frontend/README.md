# TraceWise Frontend

An intelligent compliance tracking and workflow automation platform for EUDR requirements, built with Angular 19.

## Prerequisites

- **Node.js**: 18.19.x or 20.x LTS
- **npm**: 9.x or 10.x
- **Git**

## Installation

```bash
# Clone the repository
git clone <repository-url>
cd tracewise-frontend

# Install dependencies
npm install
```

## Development

### Starting the Development Server

```bash
npm start
```

The application will be available at `http://localhost:4200`

### Building for Production

```bash
npm run build:prod
```

The production build will be generated in the `dist/tracewise-frontend/` directory.

## Testing

### Unit Tests (Vitest)

```bash
# Run tests once
npm run test:unit

# Run tests in watch mode
npm run test:unit:watch

# Generate coverage report
npm run test:unit:coverage

# Open Vitest UI dashboard
npm run test:ui
```

### E2E Tests (Cypress)

```bash
# Open Cypress test runner
npm run test:e2e

# Run tests in headless mode
npm run test:e2e:headless
```

## Code Quality

### Linting

```bash
npm run lint
```

### Code Formatting

```bash
# Format code
npm run format

# Check formatting
npm run format:check
```

## Project Structure

```
src/
├── app/
│   ├── core/                 # Singleton services, layout, config
│   │   ├── auth.service.ts
│   │   ├── config.service.ts
│   │   ├── config.token.ts
│   │   ├── logging.service.ts
│   │   ├── http.interceptor.ts
│   │   ├── mock-data.service.ts
│   │   ├── layout.component.ts
│   │   └── not-found.component.ts
│   ├── shared/               # Reusable components, pipes, directives
│   │   ├── navigation.component.ts
│   │   ├── card.component.ts
│   │   ├── truncate.pipe.ts
│   │   ├── date-format.pipe.ts
│   │   └── index.ts
│   ├── features/             # Feature-specific components
│   │   ├── dashboard/
│   │   │   └── dashboard.component.ts
│   │   ├── traces/
│   │   │   └── traces.component.ts
│   │   └── settings/
│   │       └── settings.component.ts
│   ├── app.component.ts      # Root component
│   ├── app.routes.ts         # Route configuration
│   └── app.config.ts         # Application configuration
├── assets/
│   └── config.json           # Runtime configuration
├── styles.scss               # Global styles
├── main.ts                   # Application bootstrap
└── index.html

cypress/
├── e2e/                      # E2E tests
├── support/                  # Test helpers
└── cypress.config.ts         # Cypress configuration
```

## Configuration

### Runtime Configuration

The application loads configuration from `src/assets/config.json` at runtime. This file contains:

- `apiUrl`: Backend API base URL
- `environment`: Current environment (development, staging, production)
- `appName`: Application name
- `appVersion`: Application version
- `logLevel`: Logging level (debug, info, warn, error)
- `cacheDuration`: Cache duration in milliseconds
- `sessionTimeout`: Session timeout in milliseconds

### Environment Setup

To configure for different environments, modify the `config.json` file in your deployment:

**Development:**
```json
{
  "apiUrl": "http://localhost:8000",
  "environment": "development",
  "logLevel": "debug"
}
```

**Production:**
```json
{
  "apiUrl": "https://api.tracewise.com",
  "environment": "production",
  "logLevel": "error"
}
```

## Architecture

### Module Structure

- **Core**: Singleton services, configuration, layout components
- **Shared**: Reusable components, pipes, directives
- **Features**: Feature-specific components with lazy loading

### Styling

- **Tailwind CSS**: Utility-first CSS framework
- **Angular Material**: Pre-built components for complex UI elements

### HTTP Communication

All HTTP requests go through an interceptor that:
- Adds the API base URL to relative requests
- Includes authorization headers
- Handles errors with logging

### State Management

Uses RxJS Observables for reactive data flow. Complex state management (Redux/NgRx) can be added as the application grows.

## Docker

### Building Docker Image

```bash
docker build -t tracewise-frontend .
```

### Running Docker Container

```bash
docker run -p 4200:4200 tracewise-frontend
```

The application will be available at `http://localhost:4200`

## Performance

### Bundle Size

- Initial bundle: ~150KB (gzipped)
- Lazy-loaded features: ~10-30KB each
- Target: < 750KB (gzipped)

### Optimization

- Lazy loading for feature routes
- AOT compilation enabled
- Tree shaking for unused code
- Minification and compression

## Contributing

### Code Style

This project follows Angular style guide and uses:
- **ESLint** for code linting
- **Prettier** for code formatting
- **TypeScript** strict mode

### Before Committing

```bash
npm run lint
npm run format:check
npm run test:unit
npm run build:prod
```

### Adding New Components

```bash
# Generate a new component
ng generate component features/my-feature

# Generate a new service
ng generate service core/my-service

# Generate a new pipe
ng generate pipe shared/my-pipe
```

## Troubleshooting

### Build Fails

1. Clear Angular cache: `rm -rf .angular`
2. Reinstall dependencies: `rm -rf node_modules && npm install`
3. Try building again: `npm run build`

### Tests Fail

1. Ensure port 4200 is available for dev server
2. Clear test cache: `rm -rf coverage`
3. Run tests in isolation: `npm run test:unit -- --run`

### Port Already in Use

Change the port in `package.json`:
```json
"start": "ng serve --host 0.0.0.0 --port 5200"
```

## Resources

- [Angular Documentation](https://angular.io)
- [Tailwind CSS](https://tailwindcss.com)
- [Angular Material](https://material.angular.io)
- [Vitest](https://vitest.dev)
- [Cypress](https://cypress.io)

## License

MIT License - see LICENSE file for details
