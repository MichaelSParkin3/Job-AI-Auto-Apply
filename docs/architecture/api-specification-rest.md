# API Specification (REST)

```yaml
openapi: 3.0.0
info:
  title: Job AI Auto Apply Preview API
  version: 0.1.1
  description: Local-only API for UI ↔ preview server control
servers:
  - url: http://localhost:4950
    description: Local development/usage
paths:
  /api/run/preview:
    post:
      summary: Create a preview run
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                searchUrl: { type: string }
                limit: { type: integer, default: 2 }
                profileId: { type: string }
                dryRun: { type: boolean, default: true }
      responses:
        '200':
          description: OK
          content:
            application/json:
              schema:
                type: object
                properties:
                  runId: { type: string }
                  status: { type: string, enum: [pending, review, submitting, submitted, error, aborted, duplicate] }
                  preview:
                    type: object
                    properties:
                      screenshotUrl: { type: string }
                      summary: { type: string }
  /api/run/{id}:
    get:
      summary: Get run preview state
      parameters:
        - in: path
          name: id
          required: true
          schema: { type: string }
      responses:
        '200': { description: OK }
  /api/run/{id}/approve:
    post:
      summary: Approve and submit
      parameters:
        - in: path
          name: id
          required: true
          schema: { type: string }
      responses:
        '200': { description: OK }
  /api/run/{id}/edit:
    post:
      summary: Apply a small textual edit and retry once
      parameters:
        - in: path
          name: id
          required: true
          schema: { type: string }
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                text: { type: string }
      responses:
        '200': { description: OK }
  /api/run/{id}/abort:
    post:
      summary: Abort current run
      parameters:
        - in: path
          name: id
          required: true
          schema: { type: string }
      responses:
        '200': { description: OK }
  /api/run/{id}/updates:
    get:
      summary: Poll recent events
      parameters:
        - in: path
          name: id
          required: true
          schema: { type: string }
        - in: query
          name: since
          required: false
          schema: { type: string }
      responses:
        '200': { description: OK }
components:
  schemas:
    ApiError:
      type: object
      properties:
        error:
          type: object
          properties:
            code: { type: string }
            message: { type: string }
            details: { type: object }
            timestamp: { type: string }
            requestId: { type: string }
```

---
