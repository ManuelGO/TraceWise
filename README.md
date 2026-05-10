# TraceWise AI

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

## Architecture

- **Backend**: FastAPI with agentic workflows for EUDR compliance
- **Frontend**: Angular SPA for user-facing compliance management interface
- **Integration**: REST API communication between frontend and backend

## License

[License TBD]
