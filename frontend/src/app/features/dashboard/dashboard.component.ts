import { Component, inject } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { MatCardModule } from '@angular/material/card';
import { MockDataService } from '../../core/services/mock-data/mock-data.service';

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [MatCardModule],
  templateUrl: './dashboard.component.html',
})
export class DashboardComponent {
  private mockDataService = inject(MockDataService);
  stats = toSignal(this.mockDataService.getDashboardStats(), { initialValue: null });
}
