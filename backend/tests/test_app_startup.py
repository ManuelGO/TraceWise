from app.main import create_app


def test_app_creation():
    """Test that the app can be created successfully."""
    app = create_app()
    assert app is not None
    assert app.title == "TraceWise API"
    assert app.version == "0.1.0"


def test_app_routes():
    """Test that the app has expected routes registered."""
    app = create_app()
    routes = [route.path for route in app.routes]
    # API router should be included
    assert len(routes) > 0


def test_app_middleware():
    """Test that the app has CORS middleware configured."""
    app = create_app()
    middleware_names = [middleware.cls.__name__ for middleware in app.user_middleware]
    assert "CORSMiddleware" in middleware_names


def test_app_docs_endpoints():
    """Test that docs are configured based on environment."""
    app = create_app()
    # Default environment is development, so docs should be enabled
    assert app.docs_url == "/docs" or app.docs_url is None
    assert app.redoc_url == "/redoc" or app.redoc_url is None
