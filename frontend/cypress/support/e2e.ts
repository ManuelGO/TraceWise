// Cypress support file for E2E tests
// Add custom commands and global configuration here

// Disable uncaught exception handling for Angular
Cypress.on('uncaught:exception', (err, runnable) => {
  // Angular throws errors for route navigation
  if (err.message.includes('navigation')) {
    return false;
  }
  return true;
});

// Custom commands
Cypress.Commands.add('login', (email: string, password: string) => {
  cy.visit('http://localhost:4200/login');
  cy.get('input[type="email"]').type(email);
  cy.get('input[type="password"]').type(password);
  cy.get('button[type="submit"]').click();
  cy.url().should('include', '/dashboard');
});

declare global {
  namespace Cypress {
    interface Chainable {
      login(email: string, password: string): Chainable<void>;
    }
  }
}
