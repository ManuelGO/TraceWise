# TraceWise AI

[![CI Pipeline](https://github.com/marvelo/tracewise/actions/workflows/ci.yml/badge.svg)](https://github.com/marvelo/tracewise/actions/workflows/ci.yml)

An agentic EUDR (European Union Deforestation Regulation) compliance workflow platform.

TraceWise AI provides intelligent compliance tracking and workflow automation for EUDR requirements, enabling organizations to streamline their deforestation risk management and regulatory reporting processes.

## Project Structure

This is a monorepo containing both backend and frontend components:

- **[backend/](./backend/)** — FastAPI-based REST API with agentic EUDR compliance workflows
- **[frontend/](./frontend/)** — Angular-based web application for compliance management

## Quick Start

### Backend
```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

### Frontend
```bash
cd frontend
npm install
ng serve
```

## Development

- Both backend and frontend share this monorepo
- Each component has its own dependencies and build process
- See respective README files in `backend/` and `frontend/` for detailed setup

### Local Code Quality Checks

Before pushing code, run the local checks to match CI validation:

#### Backend
```bash
cd backend
python -m venv venv
source venv/bin/activate

# Install package with dev dependencies
pip install -e ".[dev]"

# Lint and format code (Ruff)
ruff check app/ tests/
ruff format app/ tests/

# Type checking
mypy app/

# Run tests
pytest
```

#### Frontend
```bash
cd frontend

# Format code
npm run format

# Lint code
npm run lint

# Check formatting
npm run format:check

# Build
npm run build:prod
```

### CI/CD Pipeline

This project uses GitHub Actions for automated testing and code quality checks:

- **Backend**: Python linting and formatting (Ruff), type checking (mypy), and unit tests (pytest)
  - Runs on Python 3.11 and 3.12
  - Redis service container available for integration tests
- **Frontend**: TypeScript/HTML linting (ESLint), formatting (Prettier), and production build verification
  - All checks run on every push to main and all pull requests
  - All checks must pass before merging to main

## Architecture

- **Backend**: FastAPI with agentic workflows for EUDR compliance
- **Frontend**: Angular SPA for user-facing compliance management interface
- **Integration**: REST API communication between frontend and backend

## License

[License TBD]
