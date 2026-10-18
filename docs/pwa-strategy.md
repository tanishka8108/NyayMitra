# NyayMitra PWA Strategy

## Objective

NyayMitra will be developed as a Progressive Web App (PWA) so that
users can access the platform reliably on supported devices and
continue to use selected functionality during limited connectivity.

## Current Foundation

The frontend includes a Web App Manifest with:

- Application name: NyayMitra
- Short name: NyayMitra
- Standalone display mode
- Start URL: /
- Theme color
- Background color

## Offline Strategy

The application will progressively introduce offline support.

### Planned offline capabilities

- Cache the application shell.
- Cache static frontend assets.
- Preserve selected previously loaded case information where appropriate.
- Provide a clear offline indicator.
- Allow users to continue viewing previously cached information.

### Network-dependent features

The following features will require network connectivity:

- Authentication
- New case searches
- Backend/API requests
- ML predictions
- Lawyer recommendations
- Court-order processing
- Voice processing

## Future Implementation

Service-worker based caching and offline synchronization will be
implemented after the core frontend and backend API integration is stable.

The PWA layer should not interfere with normal API communication or
authentication.

## Security Considerations

Sensitive legal information should not be stored in persistent browser
storage unless the team explicitly approves the storage mechanism and
security requirements.

Offline caching should prioritize application assets and non-sensitive
data.