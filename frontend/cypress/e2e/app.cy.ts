describe('TraceWise App', () => {
  beforeEach(() => {
    cy.visit('http://localhost:4200');
  });

  it('should load the application', () => {
    cy.title().should('include', 'tracewise-frontend');
  });

  it('should display navigation menu', () => {
    cy.get('mat-toolbar').should('be.visible');
  });

  it('should navigate to dashboard', () => {
    cy.contains('Dashboard').click();
    cy.url().should('include', '/dashboard');
  });

  it('should navigate to traces', () => {
    cy.contains('Traces').click();
    cy.url().should('include', '/traces');
  });

  it('should navigate to settings', () => {
    cy.contains('Settings').click();
    cy.url().should('include', '/settings');
  });

  it('should display 404 for invalid route', () => {
    cy.visit('http://localhost:4200/invalid-route');
    cy.contains('404').should('be.visible');
  });

  it('should redirect to dashboard on root path', () => {
    cy.visit('http://localhost:4200');
    cy.url().should('include', '/dashboard');
  });
});
