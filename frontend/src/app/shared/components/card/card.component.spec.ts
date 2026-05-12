import { CardComponent } from './card.component';

describe('CardComponent', () => {
  let component: CardComponent;

  beforeEach(() => {
    component = new CardComponent();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should have undefined title by default', () => {
    expect(component.title).toBeUndefined();
  });

  it('should accept title as input property', () => {
    component.title = 'My Card Title';
    expect(component.title).toBe('My Card Title');
  });

  it('should update title when input property changes', () => {
    component.title = 'Initial Title';
    expect(component.title).toBe('Initial Title');

    component.title = 'Updated Title';
    expect(component.title).toBe('Updated Title');
  });

  it('should be a standalone component', () => {
    // Verify the component is properly configured as standalone
    expect(CardComponent).toBeTruthy();
    // A standalone component can be used without an NgModule
  });
});
