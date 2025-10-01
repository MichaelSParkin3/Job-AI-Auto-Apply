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
                mode: { type: string, enum: [review, auto_review, auto_submit], default: review }
      responses:
        '200':
          description: OK
          content:
            application/json:
              schema:
                type: object
                properties:
                  runId: { type: string }
                  status: { type: string, enum: [pending, review, auto_pending, submitting, submitted, error, aborted, duplicate] }
                  mode: { type: string, enum: [review, auto_review, auto_submit] }
                  preview:
                    type: object
                    properties:
                      screenshotUrl: { type: string }
                      summary: { type: string }
                      suggestedDecision: { $ref: '#/components/schemas/SubmissionDecision' }
                  queue:
                    $ref: '#/components/schemas/ReviewQueueSnapshot'
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
  /api/queue/{id}:
    get:
      summary: Fetch review queue snapshot
      parameters:
        - in: path
          name: id
          required: true
          schema: { type: string }
      responses:
        '200':
          description: OK
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ReviewQueueSnapshot'
  /api/queue/{id}/decision:
    post:
      summary: Submit a human decision or override
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
              $ref: '#/components/schemas/SubmissionDecision'
      responses:
        '200': { description: OK }
  /api/queue/{id}/candidate/{candidateId}/answers/{fieldKey}/decision:
    post:
      summary: Record reviewer action on a drafted answer
      parameters:
        - in: path
          name: id
          required: true
          schema: { type: string }
        - in: path
          name: candidateId
          required: true
          schema: { type: string }
        - in: path
          name: fieldKey
          required: true
          schema: { type: string }
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/DraftAnswerDecisionRequest'
      responses:
        '200':
          description: Updated draft answer review payload
          content:
            application/json:
              schema:
                type: object
                properties:
                  draftAnswer: { $ref: '#/components/schemas/DraftAnswerSummary' }
                  queue: { $ref: '#/components/schemas/ReviewQueueSnapshot' }
        '409':
          description: Draft outdated; client must refetch before retrying
  /api/queue/{id}/{candidateId}/mode:
    put:
      summary: Override candidate lane assignment
      parameters:
        - in: path
          name: id
          required: true
          schema: { type: string }
        - in: path
          name: candidateId
          required: true
          schema: { type: string }
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [mode]
              properties:
                mode:
                  type: string
                  enum: [human, ai]
                reason:
                  type: string
      responses:
        '200':
          description: Queue snapshot reflecting override
          content:
            application/json:
              schema:
                type: object
                properties:
                  mode: { type: string, enum: [human, ai] }
                  queue:
                    $ref: '#/components/schemas/ReviewQueueSnapshot'
  /api/queue/{id}/heartbeat:
    post:
      summary: Scheduler heartbeat for unattended runs
      parameters:
        - in: path
          name: id
          required: true
          schema: { type: string }
      requestBody:
        required: false
      responses:
        '204': { description: No Content }
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
    SubmissionDecision:
      type: object
      required: [decisionId, candidateId, outcome, mode, confidence, timestamp]
      properties:
        decisionId: { type: string }
        candidateId: { type: string }
        outcome: { type: string, enum: [approve, abort, edit_request, needs_review] }
        mode: { type: string, enum: [human, ai] }
        confidence: { type: number, minimum: 0, maximum: 1 }
        rationale: { type: string }
        requestedChanges:
          type: array
          items:
            type: object
            properties:
              field: { type: string }
              value: { type: string }
              reason: { type: string }
        timestamp: { type: string, format: date-time }
    ReviewQueueSnapshot:
      type: object
      required: [pending, decided, escalated, lastUpdated, mode]
      properties:
        mode: { type: string, enum: [review, auto_review, auto_submit] }
        pending:
          type: array
          items: { $ref: '#/components/schemas/ApplicationCandidateSummary' }
        decided:
          type: array
          items: { $ref: '#/components/schemas/SubmissionDecision' }
        escalated:
          type: array
          items: { $ref: '#/components/schemas/ApplicationCandidateSummary' }
        lastUpdated: { type: string, format: date-time }
        answersTelemetry:
          type: object
          properties:
            drafted: { type: integer }
            approved: { type: integer }
            savedToProfile: { type: integer }
            averageConfidence: { type: number }
            histogram:
              type: array
              items:
                type: object
                properties:
                  bucket: { type: string }
                  count: { type: integer }
    ApplicationCandidateSummary:
      type: object
      required: [id, posting, state, discoveredAt, assignedMode]
      properties:
        id: { type: string }
        posting:
          type: object
          properties:
            postingUrl: { type: string }
            title: { type: string }
            company: { type: string }
            location: { type: string }
        formPlanPath: { type: string }
        discoveredAt: { type: string, format: date-time }
        state: { type: string, enum: [discovered, planned, awaiting_decision, decided, submitted, shelved] }
        lastDecisionId: { type: string }
        assignedMode: { type: string, enum: [human, ai] }
        updatedAt: { type: string, format: date-time }
        draftAnswers:
          type: array
          items: { $ref: '#/components/schemas/DraftAnswerSummary' }
    DraftAnswerSummary:
      type: object
      required: [fieldKey, question, confidence, source, lastUpdatedAt]
      properties:
        fieldKey: { type: string }
        question: { type: string }
        draftedValuePreview: { type: string }
        confidence: { type: number, minimum: 0, maximum: 1 }
        rationalePreview: { type: string }
        source: { type: string, enum: [profile, override, resume, llm_draft] }
        lastUpdatedAt: { type: string, format: date-time }
        minConfidenceMet: { type: boolean }
        reviewerStatus: { type: string, enum: [pending, approved, edited, rejected] }
    DraftAnswerDecisionRequest:
      type: object
      required: [action, lastUpdatedAt]
      properties:
        action: { type: string, enum: [approve, approve_save, edit, edit_save] }
        value: { type: string }
        reviewerNotes: { type: string }
        lastUpdatedAt: { type: string, format: date-time }
```

---
  /api/run/{id}/handoff/{candidateId}/launch:
    post:
      summary: Relaunch Browser-Use with saved handoff snapshot
      parameters:
        - in: path
          name: id
          required: true
          schema: { type: string }
        - in: path
          name: candidateId
          required: true
          schema: { type: string }
      responses:
        '202':
          description: Launch accepted
          content:
            application/json:
              schema:
                type: object
                properties:
                  launchedAt: { type: string, format: date-time }
                  snapshotPath: { type: string }
  /api/queue/{id}/handoff-confirmation:
    post:
      summary: Record outcome of assisted submit
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
              required: [candidateId, outcome]
              properties:
                candidateId: { type: string }
                outcome: { type: string, enum: [success, still_blocked] }
                blockedReason: { type: string, enum: [captcha, mfa, unknown_form_change], nullable: true }
      responses:
        '200':
          description: Queue snapshot reflecting outcome
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ReviewQueueSnapshot'
