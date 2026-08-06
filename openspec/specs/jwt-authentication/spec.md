# JWT Authentication Specification

## Purpose

Org-scoped authentication: login with email + password, issuance of a thin signed expiring JWT, per-request verification, and the invariant that tenant identity comes only from the verified token (ADR-0002, ARCHITECTURE). Requirements are enforced by unit and integration tests (`uv run pytest -m 'not e2e'`). New domain — first change, no prior spec.

## Requirements

### Requirement: Password verification with vetted hashing

Login MUST verify the presented password against the stored `password_hash` using a vetted password-hashing library (argon2 or bcrypt family, chosen at design). The system MUST NOT implement or invoke homegrown cryptographic primitives for password handling.

#### Scenario: Valid credentials authenticate

- GIVEN a user with a stored password hash
- WHEN the correct email and password are submitted to login
- THEN authentication succeeds

#### Scenario: Wrong password rejected

- GIVEN a user with a stored password hash
- WHEN the correct email and an incorrect password are submitted
- THEN login fails with the error envelope and no token is issued

### Requirement: Password storage and secrecy

The system MUST store passwords only as salted hashes with a vetted algorithm and MUST NOT store, log, or return plaintext passwords or hashes in responses, logs, or errors. Login failures MUST NOT distinguish a wrong email from a wrong password.

#### Scenario: No credential disclosure

- GIVEN a failed login attempt
- WHEN the error envelope is returned
- THEN it contains no password, hash, or account-existence hint

### Requirement: Token issuance at login

A successful login MUST issue a thin custom JWT, signed with a secret from the environment/secret manager, carrying the user id and the tenant id of the membership used, with an `exp` claim. The token MUST NOT embed client-supplied tenant, role, or capability claims.

#### Scenario: Login returns an expiring token

- GIVEN valid credentials for a tenant membership
- WHEN login succeeds
- THEN the response contains a signed token with user id, tenant id, and a future expiry
- AND the token verifies with the configured secret

### Requirement: Per-request verification

Every protected request MUST verify the token's signature, expiry, and required claims before processing. Expired, forged, tampered, or malformed tokens MUST be rejected with the error envelope (401) and the request MUST NOT be processed.

#### Scenario: Expired token rejected

- GIVEN a token whose `exp` is in the past
- WHEN it is presented to a protected route
- THEN the request is rejected with the error envelope and no data is returned

#### Scenario: Forged token rejected

- GIVEN a token signed with a different secret
- WHEN it is presented to a protected route
- THEN the request is rejected with the error envelope

#### Scenario: Tampered claims rejected

- GIVEN a valid token whose tenant id claim was modified after signing
- WHEN it is presented to a protected route
- THEN verification fails and the request is rejected

### Requirement: Tenant only from verified token

The tenant for a request MUST be resolved exclusively from the verified token. The system MUST NOT accept tenant identity from body, query, path, or headers supplied by the client.

#### Scenario: Client-supplied tenant ignored

- GIVEN a token for tenant A
- WHEN a request to a tenant-scoped route also sends `tenant: B` in body or headers
- THEN the route operates on tenant A only
- AND tenant B data is never touched or returned
