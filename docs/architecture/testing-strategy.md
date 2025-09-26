# Testing Strategy

## Testing Pyramid
```
E2E Tests
/        \
Integration Tests
/            \
Frontend Unit  Backend Unit
```

## Test Organization
```text
apps/ui/src/__tests__/...
apps/preview/tests/...
core/tests/...
```

## Test Examples
```ts
// Frontend Component Test (Vitest + RTL)
import { render, screen } from '@testing-library/react'
import { PreviewCard } from '@/components/PreviewCard'

test('renders screenshot', () => {
  render(<PreviewCard screenshotUrl="/shot.png" summary="ok" />)
  expect(screen.getByAltText('Final review screenshot')).toBeInTheDocument()
})
```

```py
# Backend API Test (pytest)
from fastapi.testclient import TestClient
from apps.preview.main import app

client = TestClient(app)

def test_preview_route():
    r = client.post('/api/run/preview', json={"searchUrl": "https://...", "limit": 1, "profileId": "default", "dryRun": True})
    assert r.status_code == 200
```

```ts
// E2E Test (Playwright) — optional local
import { test, expect } from '@playwright/test'

test('ui loads', async ({ page }) => {
  await page.goto('http://localhost:4950/ui')
  await expect(page.getByRole('button', { name: 'Approve' })).toBeVisible()
})
```

---
