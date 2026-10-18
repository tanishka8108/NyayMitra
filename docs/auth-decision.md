# NyayMitra Authentication & Authorization Decision

## 1. Authentication

NyayMitra will use token-based authentication for authenticated users.

The frontend will communicate with the backend authentication API for:

- User registration
- User login
- Logout
- Authentication state

The exact authentication implementation and token handling will be finalized during backend integration.

---

## 2. JWT

JWT-based authentication is planned for communication between the frontend and backend.

The frontend should not make assumptions about the final JWT payload until the backend authentication contract is finalized.

Expected flow:

Login
  ↓
Backend validates credentials
  ↓
Backend issues authentication token
  ↓
Frontend maintains authenticated session
  ↓
Frontend sends authenticated requests to protected APIs

---

## 3. Role-Based Access Control (RBAC)

NyayMitra will use role-based access control.

The application defines four roles:

- USER
- LAWYER
- ADMIN
- STAFF

Role definitions:

| Role | Responsibility |
|------|----------------|
| USER | Access personal cases, case status, guidance, court orders and related services |
| LAWYER | Access lawyer-related functionality and assigned/relevant case information |
| ADMIN | Manage administrative functions and platform-level data |
| STAFF | Perform authorized staff/case-management operations |

---

## 4. Frontend Role Handling

The frontend will use a centralized role definition located at:

`src/auth/roles.ts`

This prevents different parts of the application from using inconsistent role names.

Frontend route/page access will eventually be controlled according to the authenticated user's role.

---

## 5. Backend Authority

The backend remains the final authority for authentication and authorization.

Frontend route protection is only a user-interface/access-control layer and must not be treated as a security boundary.

Every protected API endpoint must independently validate authentication and authorization on the backend.

---

## 6. Current Scope

At this stage (after Phases 1 and 2):

- Role constants are defined (`USER` / `LAWYER` / `ADMIN`).
- The authentication architecture is documented.
- Sessions use opaque bearer tokens stored server-side in the
  `sessions` table (passwords PBKDF2-hashed) rather than JWT — a
  deliberate no-new-packages choice; the contract described here is
  unchanged.
- Backend authentication endpoints are integrated on the lawyer
  service: `POST /api/auth/register`, `POST /api/auth/register/lawyer`,
  `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/me`,
  `GET /api/auth/lawyer/profile`, plus the ADMIN-only lawyer
  verification API (`GET`/`PATCH /api/admin/lawyers[/{lawyer_id}]`).
  Every request above is runnable from
  `docs/postman/NyayMitra.postman_collection.json`.
- Protected routes validate role and verification state server-side
  (`require_role(...)` and `require_verified_lawyer` in
  `auth/security.py`). Lawyer registration always lands `PENDING`;
  only an ADMIN can move it to `APPROVED`/`REJECTED`, and a lawyer
  calling the admin routes — including on their own row — receives
  403.

The frontend- and backend-side development contract above still applies: route protection in the UI remains an access-control layer, never a security boundary.