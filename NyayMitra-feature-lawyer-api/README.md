# Lawyer API — Frontend Integration Guide

## 1. Overview

This module provides the backend API for managing lawyer information.

The backend is built using:

* **FastAPI** — REST API framework
* **PostgreSQL** — Database
* **SQLAlchemy** — Database interaction / ORM
* **Pydantic** — Request and response validation
* **Uvicorn** — Development server

The purpose of this API is to allow the frontend application to:

* Fetch lawyer information
* View individual lawyer profiles
* Add lawyer information
* Update lawyer information
* Delete lawyer information
* Use lawyer data in search, listing, and profile screens

The frontend does **not** communicate directly with PostgreSQL.

The communication flow is:

```text
┌──────────────────────┐
│       Frontend       │
│   React / Frontend   │
└──────────┬───────────┘
           │
           │ HTTP Request
           │ JSON
           ↓
┌──────────────────────┐
│      FastAPI         │
│     Lawyer API       │
└──────────┬───────────┘
           │
           │ SQLAlchemy
           ↓
┌──────────────────────┐
│     PostgreSQL       │
│     Lawyer Data      │
└──────────────────────┘
```

---

# 2. Base API URL

During local development, the API runs on:

```text
http://127.0.0.1:8000
```

Therefore, the frontend should use:

```text
http://127.0.0.1:8000
```

as the development API base URL.

For example:

```text
GET http://127.0.0.1:8000/lawyers
```

> The final production URL will be different after the backend is deployed.

---

# 3. Start the Backend

Before testing the frontend integration, the backend must be running.

From the backend project directory:

```bash
uvicorn app.main:app --reload
```

The server should start at:

```text
http://127.0.0.1:8000
```

---

# 4. API Documentation

FastAPI automatically provides interactive API documentation.

Open:

```text
http://127.0.0.1:8000/docs
```

This page allows the frontend developer to:

* See available endpoints
* See HTTP methods
* See required parameters
* See request body structure
* Send test requests
* View API responses
* Check HTTP status codes

The `/docs` page should be used as the primary reference if an endpoint's exact schema changes during development.

---

# 5. Lawyer API Endpoints

The frontend will communicate with the following types of endpoints.

| Method    | Endpoint        | Purpose         |
| --------- | --------------- | --------------- |
| GET       | `/lawyers`      | Get lawyer list |
| GET       | `/lawyers/{id}` | Get one lawyer  |
| POST      | `/lawyers`      | Create lawyer   |
| PUT/PATCH | `/lawyers/{id}` | Update lawyer   |
| DELETE    | `/lawyers/{id}` | Delete lawyer   |

> **Important:** Use the exact endpoint paths shown in Swagger at `/docs` if they differ from the examples above.

---

# 6. GET — Fetch All Lawyers

## Endpoint

```http
GET /lawyers
```

Full local URL:

```text
http://127.0.0.1:8000/lawyers
```

### Purpose

This endpoint is used when the frontend needs to display a list of lawyers.

For example, it can be used on:

* Lawyer listing page
* Search results
* Lawyer directory
* Dashboard
* Practice-area results

### Request

No request body is required.

```http
GET /lawyers
```

### Example Response

```json
[
  {
    "id": 1,
    "name": "Example Lawyer",
    "gender": "Female",
    "date_of_birth": "1990-01-15",
    "phone": "9876543210",
    "email": "lawyer@example.com",
    "office_address": "Pune, Maharashtra",
    "pincode": "411001",
    "website": "https://example.com",
    "bio": "Experienced legal professional.",
    "practice_area": "Civil Law"
  }
]
```

The frontend can use this response to create lawyer cards or list items.

Example:

```text
┌─────────────────────────────┐
│ Example Lawyer              │
│ Civil Law                   │
│ Pune, Maharashtra           │
│                             │
│       View Profile →        │
└─────────────────────────────┘
```

---

# 7. GET — Fetch One Lawyer

## Endpoint

```http
GET /lawyers/{id}
```

Example:

```text
GET /lawyers/1
```

### Purpose

This endpoint should be used when the user opens an individual lawyer's profile.

For example:

```text
Lawyer Listing
      │
      │ Click "View Profile"
      ↓
GET /lawyers/1
      │
      ↓
Lawyer Profile Page
```

### Example Response

```json
{
  "id": 1,
  "name": "Example Lawyer",
  "gender": "Female",
  "date_of_birth": "1990-01-15",
  "phone": "9876543210",
  "email": "lawyer@example.com",
  "office_address": "Pune, Maharashtra",
  "pincode": "411001",
  "website": "https://example.com",
  "bio": "Experienced legal professional.",
  "practice_area": "Civil Law"
}
```

The frontend can then display these fields in the lawyer profile page.

---

# 8. POST — Create Lawyer

## Endpoint

```http
POST /lawyers
```

### Purpose

This endpoint is used when the frontend needs to create a new lawyer record.

The frontend sends lawyer information as JSON.

### Example Request

```json
{
  "name": "Example Lawyer",
  "gender": "Female",
  "date_of_birth": "1990-01-15",
  "phone": "9876543210",
  "email": "lawyer@example.com",
  "office_address": "Pune, Maharashtra",
  "pincode": "411001",
  "website": "https://example.com",
  "bio": "Experienced legal professional.",
  "practice_area": "Civil Law"
}
```

### Frontend Flow

```text
User fills form
      ↓
Frontend validates input
      ↓
POST /lawyers
      ↓
FastAPI
      ↓
Pydantic validation
      ↓
SQLAlchemy
      ↓
PostgreSQL
      ↓
Response
      ↓
Frontend displays success/error
```

---

# 9. PUT/PATCH — Update Lawyer

## Endpoint

```http
PUT /lawyers/{id}
```

or, if the API implements partial updates:

```http
PATCH /lawyers/{id}
```

Example:

```text
PUT /lawyers/1
```

### Purpose

This endpoint is used when an existing lawyer's information needs to be changed.

For example:

* Phone number changed
* Office address changed
* Website updated
* Bio updated
* Practice area changed

### Example Request

```json
{
  "name": "Example Lawyer",
  "phone": "9999999999",
  "office_address": "New Office Address",
  "practice_area": "Corporate Law"
}
```

The exact fields accepted should be checked in Swagger.

---

# 10. DELETE — Delete Lawyer

## Endpoint

```http
DELETE /lawyers/{id}
```

Example:

```text
DELETE /lawyers/1
```

### Purpose

Deletes the lawyer record associated with the specified ID.

### Frontend Flow

```text
User clicks Delete
      ↓
Frontend confirmation
      ↓
DELETE /lawyers/1
      ↓
FastAPI
      ↓
PostgreSQL
      ↓
Success response
      ↓
Frontend refreshes lawyer list
```

The frontend should ideally ask for confirmation before sending a DELETE request.

---

# 11. JSON Format

The API communicates using JSON.

The frontend should send JSON for requests that require a request body.

Example:

```json
{
  "name": "Example Lawyer",
  "email": "lawyer@example.com",
  "practice_area": "Civil Law"
}
```

The response from the API is also returned as JSON.

---

# 12. Frontend Integration Example

The frontend can call the API using `fetch()`.

### Get all lawyers

```javascript
const response = await fetch(
  "http://127.0.0.1:8000/lawyers"
);

const lawyers = await response.json();

console.log(lawyers);
```

---

## Get a specific lawyer

```javascript
const lawyerId = 1;

const response = await fetch(
  `http://127.0.0.1:8000/lawyers/${lawyerId}`
);

const lawyer = await response.json();

console.log(lawyer);
```

---

## Create a lawyer

```javascript
const response = await fetch(
  "http://127.0.0.1:8000/lawyers",
  {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      name: "Example Lawyer",
      gender: "Female",
      phone: "9876543210",
      email: "lawyer@example.com",
      practice_area: "Civil Law"
    })
  }
);

const result = await response.json();

console.log(result);
```

---

# 13. Important — CORS

If the frontend and backend are running on different ports, the browser may block requests because of CORS.

For example:

```text
Frontend:
http://localhost:3000

Backend:
http://127.0.0.1:8000
```

These are different origins.

The FastAPI backend therefore needs to allow requests from the frontend origin.

If the frontend developer gets an error such as:

```text
Access to fetch at ... has been blocked by CORS policy
```

the backend CORS configuration needs to be checked.

---

# 14. Error Handling

The frontend should handle both successful and unsuccessful API requests.

Typical HTTP status codes include:

| Status Code | Meaning                   |
| ----------- | ------------------------- |
| 200         | Request successful        |
| 201         | Resource created          |
| 400         | Bad request               |
| 404         | Lawyer/resource not found |
| 422         | Validation error          |
| 500         | Server error              |

For example, if a lawyer ID does not exist:

```text
GET /lawyers/9999
```

the frontend should display an appropriate message instead of assuming that a lawyer was returned.

Example:

```text
Lawyer not found.
```

---

# 15. Validation

The API validates incoming data before storing it in PostgreSQL.

For example, if a required field is missing or has an incorrect format, the API may return:

```text
422 Unprocessable Entity
```

The frontend should therefore:

1. Validate basic form input.
2. Send the request.
3. Check the HTTP response.
4. Display validation errors returned by the API.

---

# 16. Lawyer Profile Integration

A possible frontend lawyer profile flow is:

```text
┌─────────────────────────┐
│      Lawyer List        │
└────────────┬────────────┘
             │
             │ User clicks lawyer
             ↓
┌─────────────────────────┐
│ GET /lawyers/{id}       │
└────────────┬────────────┘
             │
             ↓
┌─────────────────────────┐
│    Lawyer Profile       │
│                         │
│ Name                    │
│ Practice Area           │
│ Bio                     │
│ Contact                 │
│ Office Address          │
│ Website                 │
└─────────────────────────┘
```

The frontend does not need to know how the database works.

It only needs to call the API and display the returned data.

---

# 17. Search / Filtering

If search and filtering endpoints are implemented in the backend, the frontend can use them to provide features such as:

* Search by lawyer name
* Filter by practice area
* Filter by location
* Filter by other supported fields

For example, a future endpoint could follow a pattern such as:

```text
GET /lawyers?practice_area=Civil%20Law
```

The exact query parameters should only be used after they are implemented in the backend.

---

# 18. Database Flow

The frontend should **never directly connect to PostgreSQL**.

Correct architecture:

```text
Frontend
   │
   │ HTTP
   ↓
FastAPI
   │
   │ SQLAlchemy
   ↓
PostgreSQL
```

Incorrect architecture:

```text
Frontend
   │
   │
   └──────────────→ PostgreSQL
```

The API acts as the layer between the frontend and database.

---

# 19. Local Development Setup

For local integration, both applications need to be running.

### Backend

```text
http://127.0.0.1:8000
```

### Frontend

The frontend will normally run on its own development port, depending on the framework.

For example:

```text
http://localhost:3000
```

or:

```text
http://localhost:5173
```

The frontend should use the backend URL as its API base URL.

---

# 20. Recommended Frontend API Configuration

Instead of writing the backend URL throughout the frontend code, define a single API base URL.

Example:

```javascript
const API_BASE_URL = "http://127.0.0.1:8000";
```

Then:

```javascript
fetch(`${API_BASE_URL}/lawyers`);
```

and:

```javascript
fetch(`${API_BASE_URL}/lawyers/${id}`);
```

This makes it easier to change the backend URL when the application is deployed.

---

# 21. Integration Checklist

The frontend developer can use the following checklist.

### Backend

* [ ] Start PostgreSQL
* [ ] Start FastAPI
* [ ] Verify `http://127.0.0.1:8000`
* [ ] Open `/docs`
* [ ] Confirm lawyer endpoints are available

### Frontend

* [ ] Set API base URL
* [ ] Implement GET lawyers
* [ ] Display lawyer list
* [ ] Implement GET lawyer by ID
* [ ] Connect lawyer profile page
* [ ] Implement POST if required
* [ ] Implement UPDATE if required
* [ ] Implement DELETE if required
* [ ] Handle loading states
* [ ] Handle API errors
* [ ] Test with actual database data

### Integration

* [ ] Test frontend → API
* [ ] Test API → PostgreSQL
* [ ] Test PostgreSQL → API
* [ ] Test API → frontend
* [ ] Test complete user flow

---

# 22. Testing the Integration

Before considering the integration complete, test the following:

### Test 1 — Fetch Lawyers

```text
Frontend
   ↓
GET /lawyers
   ↓
API
   ↓
PostgreSQL
   ↓
Lawyer records
   ↓
Frontend
```

Expected result:

The frontend displays the lawyers stored in the database.

---

### Test 2 — Open Lawyer Profile

```text
Click lawyer
      ↓
GET /lawyers/{id}
      ↓
API
      ↓
Database
      ↓
Lawyer data
      ↓
Profile page
```

Expected result:

The selected lawyer's information is displayed.

---

### Test 3 — Create Lawyer

```text
Fill form
    ↓
POST /lawyers
    ↓
API validation
    ↓
PostgreSQL
    ↓
Success response
```

Expected result:

A new lawyer record is stored in the database.

---

### Test 4 — Update Lawyer

```text
Edit profile
    ↓
PUT/PATCH /lawyers/{id}
    ↓
Database updated
    ↓
Updated data returned
```

Expected resu
