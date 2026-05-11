import { Component } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { NavigationComponent } from '../../shared/components/navigation/navigation.component';

@Component({
  selector: 'app-layout',
  standalone: true,
  imports: [RouterOutlet, NavigationComponent],
  templateUrl: './layout.component.html',
})
export class LayoutComponent {}
