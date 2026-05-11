import { Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { toSignal } from '@angular/core/rxjs-interop';
import { MatTableModule } from '@angular/material/table';
import { MatButtonModule } from '@angular/material/button';
import { MockDataService } from '../../core/services/mock-data/mock-data.service';

@Component({
  selector: 'app-traces',
  standalone: true,
  imports: [CommonModule, MatTableModule, MatButtonModule],
  templateUrl: './traces.component.html',
})
export class TracesComponent {
  private mockDataService = inject(MockDataService);
  displayedColumns: string[] = ['id', 'name', 'status', 'createdAt'];
  traces = toSignal(this.mockDataService.getTraces(), { initialValue: null });

  getStatusClass(status: string): string {
    const statusClasses: Record<string, string> = {
      pending: 'text-yellow-600',
      processing: 'text-blue-600',
      completed: 'text-green-600',
    };
    return statusClasses[status] || '';
  }
}
