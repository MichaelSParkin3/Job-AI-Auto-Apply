# Coding Standards

## Critical Fullstack Rules
- Type Sharing: TS types in `packages/shared`; Python pydantic models in backend — keep contracts aligned.
- API Calls: UI must call only Preview BFF endpoints; no direct filesystem access.
- Env Vars: Access via config objects; never use `process.env` directly in components; backend reads `.env.local` once.
- Error Handling: Use standard `ApiError` shape across stack; no throw strings.
- State Updates: Use Zustand immutable updates; no direct mutation.
- Guardrails: Browser automation restricted to `*.simplyhired.com`; one tab; headful only.

## Naming Conventions
| Element | Frontend | Backend | Example |
|---|---|---|---|
| Components | PascalCase | - | `PreviewCard.tsx` |
| Hooks | camelCase with `use` | - | `usePreview.ts` |
| API Routes | - | kebab-case | `/api/run-preview` (or RESTful `/api/run/preview`) |
| Files/Modules | kebab-case | snake_case | `artifact-store.ts`, `file_store.py` |

---

## Commenting Standards

Clear, consistent comments are crucial for maintainability. This project adheres to the following standards, inspired by Google's style guides.

### Python (Google Style Docstrings)

All public modules, functions, classes, and methods must have a docstring using triple-double quotes (`"""`).

- **Summary Line**: Start with a short, imperative summary line ending in a period.
- **Args**: List each argument, its type, and a description.
- **Returns/Yields**: Describe the expected return or yielded value and its type.
- **Raises**: Document any exceptions that can be raised.

**Example Function:**
```python
"""Fetches and processes user data.

Args:
    user_id (int): The primary identifier for the user.
    active_only (bool): If True, fetches only active users.

Returns:
    dict: A dictionary containing the user's profile information,
        or None if the user is not found.

Raises:
    IOError: An error occurred accessing the data source.
"""
```

### TypeScript/JavaScript (JSDoc)

Use JSDoc (`/** ... */`) for all public functions, classes, and complex type definitions.

- **Annotations**: Use tags like `@param`, `@returns`, `@throws`, and `@deprecated`.
- **Types**: Specify parameter and return types using `{Type}` syntax.
- **Description**: Provide a clear description of the function's purpose.

**Example Function:**
```typescript
/**
 * Renders a user profile card with the given user data.
 * @param {object} user - The user object containing profile details.
 * @param {string} user.name - The user's full name.
 * @param {string} user.avatarUrl - URL for the user's profile picture.
 * @returns {JSX.Element} The rendered React component.
 * @throws {Error} If the user object is missing required fields.
 */
```