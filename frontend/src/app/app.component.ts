import { Component } from '@angular/core';
import { RouterOutlet } from '@angular/router';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [RouterOutlet],
  template: `
    <div class="container">
      <h1>TraceWise - EUDR Compliance Platform</h1>
      <p>Welcome to TraceWise AI</p>
      <p>An intelligent compliance tracking and workflow automation platform for EUDR requirements.</p>
      <router-outlet></router-outlet>
    </div>
  `,
  styles: [`
    .container {
      padding: 2rem;
      text-align: center;
      max-width: 800px;
      margin: 2rem auto;
    }
    h1 {
      color: #1976d2;
      margin-bottom: 1rem;
    }
    p {
      margin: 0.5rem 0;
      font-size: 1.1rem;
    }
  `],
})
export class AppComponent {
  title = 'tracewise-frontend';
}
