# Tenant Identity Specification

## Purpose

The multi-tenant identity substrate: `tenants`, `users`, tenant-scoped `roles`, and `memberships` (user ↔ tenant ↔ role), their migration and composite indexes, plus the idempotent first-admin bootstrap. It makes the PRD §5 tenant-isolation invariant testable before any document or retrieval code exists. New domain — first change, no prior spec.

## Requirements

### Requirement: Tenant-scoped identity model

The system MUST persist `tenants` (id, name, created_at), `users` (id, email, password_hash), `roles` (id, tenant_id, name), and `memberships` (id, tenant_id, user_id, role_id) per the ARCHITECTURE ERD, via an up/down migration. User emails MUST be unique system-wide. Every tenant-scoped table MUST have a composite index leading with `tenant_id`.

#### Scenario: Fresh migration creates the identity schema

- GIVEN an empty database and the identity migration
- WHEN the migration runs up, then down
- THEN the four tables and their composite (tenant_id, …) indexes exist
- AND the down migration drops them without affecting other tables

#### Scenario: Email uniqueness enforced

- GIVEN an existing user with email `a@example.com`
- WHEN a second user with the same email is persisted
- THEN persistence fails with the error envelope and no duplicate is created

### Requirement: Tenant-scoped roles

Roles MUST belong to exactly one tenant; a role name MUST be unique within its tenant; a role MUST NOT grant capabilities in any other tenant.

#### Scenario: Same role name in two tenants

- GIVEN tenants A and B
- WHEN tenant A creates role `editor` and tenant B creates role `editor`
- THEN both succeed, because names are unique per tenant

#### Scenario: Cross-tenant role grant denied

- GIVEN a membership in tenant A
- WHEN an actor assigns a tenant B role to that membership
- THEN the assignment fails with the error envelope and no membership row changes

### Requirement: First-admin bootstrap

The system MUST provide an env/CLI bootstrap that creates the first tenant and its admin user when no identity data exists. Re-running the bootstrap MUST be idempotent: it MUST NOT duplicate tenants, users, roles, or memberships, and MUST NOT reset or overwrite pre-existing uncommitted bootstrap state.

#### Scenario: Idempotent seed

- GIVEN a seeded tenant with an admin
- WHEN the bootstrap command runs again
- THEN no duplicate rows are created and existing identity data is unchanged

#### Scenario: Bootstrap with existing data

- GIVEN a tenant and users provisioned through admin APIs
- WHEN the bootstrap command runs
- THEN it exits successfully without modifying existing data

### Requirement: Cross-tenant isolation

Any identity query or operation MUST be scoped to exactly one tenant, resolved from verified context. Attempts to read or mutate another tenant's users, roles, or memberships MUST fail via the error envelope and MUST NOT disclose whether the target exists.

#### Scenario: Cross-tenant read denied (release gate)

- GIVEN an admin of tenant A
- WHEN the admin lists tenant B users or requests a tenant B user
- THEN the request fails with the error envelope and no tenant B data is returned

#### Scenario: Cross-tenant mutation denied

- GIVEN memberships in tenants A and B
- WHEN an admin of tenant A updates a tenant B membership's role
- THEN the mutation fails and tenant B's membership is unchanged
