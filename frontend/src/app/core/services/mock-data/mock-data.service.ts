import { Injectable } from '@angular/core';
import { Observable, of } from 'rxjs';

export interface Trace {
  id: string;
  name: string;
  status: 'pending' | 'processing' | 'completed';
  createdAt: string;
}

export interface DashboardStats {
  totalTraces: number;
  complianceRate: number;
  activeWorkflows: number;
}

@Injectable({
  providedIn: 'root',
})
export class MockDataService {
  getTraces(): Observable<Trace[]> {
    return of([
      {
        id: '1',
        name: 'EUDR Compliance Check',
        status: 'completed',
        createdAt: new Date().toISOString(),
      },
      {
        id: '2',
        name: 'Supplier Verification',
        status: 'processing',
        createdAt: new Date().toISOString(),
      },
      {
        id: '3',
        name: 'Documentation Review',
        status: 'pending',
        createdAt: new Date().toISOString(),
      },
    ]);
  }

  getDashboardStats(): Observable<DashboardStats> {
    return of({
      totalTraces: 3,
      complianceRate: 65,
      activeWorkflows: 1,
    });
  }
}
