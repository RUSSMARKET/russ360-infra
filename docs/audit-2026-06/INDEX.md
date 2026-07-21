# Аудит Russ360 — реестр находок

> **Как читать `status`.** `open` означает «не проверялось на предмет закрытия», а не «точно не сделано» —
> реестр вёлся без сверки с кодом. Пометка `closed` ставится ТОЛЬКО после проверки фактического кода
> на `origin/main` (прод); в карточке при этом появляется раздел «Статус закрытия» с коммитом и тем,
> что именно проверено. Сообщениям коммитов без сверки с кодом не доверять.
>
> Ревизия статусов начата 2026-07-21.


| id | flow | dimension | severity | confidence | status | файл |
|----|------|-----------|----------|------------|--------|------|
| F-0001 | inventory-transfer | correctness | P1 | likely | open | findings/F-0001-transfer-cancel-accept-race-no-row-lock.md |
| F-0002 | hiring-onboarding | correctness | P1 | confirmed | closed | findings/F-0002-groupleader-hire-missing-membership-precondition.md |
| F-0003 | hiring-onboarding | data-integrity | P2 | confirmed | open | findings/F-0003-history-duplicate-who-key-actor-lost.md |
| F-0004 | hiring-onboarding | data-integrity | P2 | likely | open | findings/F-0004-multipoint-hire-partial-no-compensation.md |
| F-0005 | hiring-onboarding | correctness | P3 | needs-verification | open | findings/F-0005-pointsid-fragile-string-parse.md |
| F-0006 | hiring-onboarding | data-integrity | P3 | needs-verification | open | findings/F-0006-core-employee-link-by-email-wrong-match.md |
| F-0007 | point-agent-binding | correctness | P1 | confirmed | closed | findings/F-0007-point-leader-read-not-switched-to-core.md |
| F-0008 | point-agent-binding | data-integrity | P2 | confirmed | open | findings/F-0008-visibility-merges-frozen-pivot-ghost-agents.md |
| F-0009 | point-agent-binding | data-integrity | P2 | likely | open | findings/F-0009-detach-noop-on-role-mismatch.md |
| F-0010 | point-agent-binding | data-integrity | P2 | confirmed | open | findings/F-0010-bulk-productpointagents-nonatomic-fake-counts.md |
| F-0011 | point-agent-binding | correctness | P3 | confirmed | open | findings/F-0011-addpointagent-partial-batch-on-error.md |
| F-0012 | point-agent-binding | data-integrity | P3 | likely | open | findings/F-0012-point-delete-distributed-op-no-transaction.md |
| F-0013 | project-support-membership | data-integrity | P1 | confirmed | closed | findings/F-0013-membership-role-swap-overwrites-and-sticky.md |
| F-0014 | project-support-membership | correctness | P1 | confirmed | closed | findings/F-0014-addsupport-missing-core-employee-link-500.md |
| F-0015 | project-support-membership | data-integrity | P1 | confirmed | open | findings/F-0015-project-team-multiwrite-no-compensation.md |
| F-0016 | project-support-membership | correctness | P2 | confirmed | open | findings/F-0016-setprojectmanager-swallowed-false-no-role-validation.md |
| F-0017 | project-support-membership | correctness | P2 | needs-verification | open | findings/F-0017-deactivateproject-user-property-crash.md |
| F-0018 | project-support-membership | correctness | P3 | confirmed | open | findings/F-0018-deleteproject-history-after-delete-core-archive-first.md |
| F-0019 | project-support-membership | architecture-drift | P2 | likely | open | findings/F-0019-pm-relation-reads-frozen-project-manager-id.md |
| F-0020 | registration-auth | data-integrity | P1 | confirmed | open | findings/F-0020-phone-normalization-mismatch-services.md |
| F-0021 | registration-auth | data-integrity | P1 | confirmed | open | findings/F-0021-setpassword-identity-before-s2s-no-compensation.md |
| F-0022 | registration-auth | correctness | P2 | confirmed | open | findings/F-0022-init-http-inside-db-transaction.md |
| F-0023 | registration-auth | data-integrity | P2 | confirmed | open | findings/F-0023-identity-external-id-never-set-orphan-pairs.md |
| F-0024 | registration-auth | correctness | P3 | likely | open | findings/F-0024-otp-resend-throttle-by-ip-invalidates-prior.md |
| F-0025 | registration-auth | correctness | P3 | likely | open | findings/F-0025-init-overwrites-shell-record-no-ownership-gate.md |
| F-0026 | login-otp | correctness | P2 | likely | open | findings/F-0026-sklad-disabled-user-retains-inventory-access.md |
| F-0027 | login-otp | correctness | P2 | confirmed | open | findings/F-0027-identity-suspend-not-propagated-live-session.md |
| F-0028 | login-otp | correctness | P2 | likely | open | findings/F-0028-otp-verify-race-double-consume.md |
| F-0029 | login-otp | data-integrity | P2 | confirmed | open | findings/F-0029-legacy-users-null-identity-password-hash.md |
| F-0030 | password-recovery-sync | data-integrity | P2 | confirmed | open | findings/F-0030-legacy-passwordrecovery-no-identity-sync.md |
| F-0031 | password-recovery-sync | data-integrity | P1 | confirmed | open | findings/F-0031-sklad-cabinet-changepassword-no-identity-sync.md |
| F-0032 | password-recovery-sync | data-integrity | P2 | confirmed | open | findings/F-0032-canonical-recovery-besteffort-sync-asymmetry.md |
| F-0033 | password-recovery-sync | correctness | P2 | likely | open | findings/F-0033-recovery-sync-fragile-phone-key.md |
| F-0034 | inventory-check | data-integrity | P1 | likely | open | findings/F-0034-apply-corrections-double-apply-no-lock.md |
| F-0035 | inventory-check | data-integrity | P1 | likely | open | findings/F-0035-apply-corrections-negative-available-toctou.md |
| F-0036 | inventory-check | data-integrity | P1 | confirmed | open | findings/F-0036-recalc-expected-nonidempotent-double-count-on-resubmit.md |
| F-0037 | inventory-check | correctness | P2 | likely | open | findings/F-0037-check-approve-reject-stale-status-no-lock.md |
| F-0038 | inventory-check | data-integrity | P2 | confirmed | open | findings/F-0038-apply-corrections-skips-missing-balance-silently.md |
| F-0039 | inventory-check | data-integrity | P3 | likely | open | findings/F-0039-corrections-leave-qty-reserved-stale.md |
| F-0040 | inventory-issue-writeoff | data-integrity | P3 | confirmed | open | findings/F-0040-balances-no-db-nonnegative-constraint.md |
| F-0041 | inventory-issue-writeoff | data-integrity | P3 | likely | open | findings/F-0041-writeoff-request-reserve-leak-orphaned-holder.md |
| F-0042 | inventory-receipt-warehouse | data-integrity | P1 | confirmed | open | findings/F-0042-receipt-double-click-double-credit.md |
| F-0043 | inventory-receipt-warehouse | correctness | P2 | likely | open | findings/F-0043-firstorcreate-then-lock-unique-violation-race.md |
| F-0044 | inventory-receipt-warehouse | correctness | P3 | likely | open | findings/F-0044-allocate-recipient-role-not-rechecked-on-accept.md |
| F-0045 | inventory-requests-approvals | correctness | P2 | confirmed | open | findings/F-0045-approve-correction-stale-transfer-status-no-lock.md |
| F-0046 | inventory-requests-approvals | correctness | P3 | likely | open | findings/F-0046-correction-request-singular-latestofmany-hides-history.md |
| F-0047 | inventory-requests-approvals | architecture-drift | P3 | confirmed | open | findings/F-0047-generic-request-write-actions-skip-review-gate.md |
| F-0048 | sklad-assignments | data-integrity | P2 | confirmed | open | findings/F-0048-update-promoters-silent-skip-partial-success.md |
| F-0049 | sklad-assignments | correctness | P2 | likely | open | findings/F-0049-reassign-promoter-during-active-check-desync.md |
| F-0050 | transfer-documents | data-integrity | P2 | confirmed | open | findings/F-0050-orphan-files-on-upload-transaction-rollback.md |
| F-0051 | transfer-documents | architecture-drift | P3 | confirmed | open | findings/F-0051-sender-upload-ignores-alternate-file-keys.md |
| F-0052 | staff-visibility | correctness | P1 | confirmed | open | findings/F-0052-project-staff-rg-pm-zero-agents.md |
| F-0053 | staff-visibility | correctness | P2 | confirmed | open | findings/F-0053-has-access-to-user-null-deref-500.md |
| F-0054 | staff-visibility | correctness | P2 | confirmed | open | findings/F-0054-rd-pm-product-matrix-first-project-only.md |
| F-0055 | staff-visibility | data-integrity | P2 | needs-verification | open | findings/F-0055-shared-employee-external-id-collapses-visibility.md |
| F-0056 | staff-management | data-integrity | P2 | confirmed | open | findings/F-0056-block-staff-no-core-employee-status-sync.md |
| F-0057 | staff-management | data-integrity | P2 | confirmed | open | findings/F-0057-block-staff-no-identity-suspend-fresh-login.md |
| F-0058 | staff-management | data-integrity | P2 | confirmed | open | findings/F-0058-agent-test-grant-core-writes-inside-db-transaction.md |
| F-0059 | staff-management | data-integrity | P2 | likely | open | findings/F-0059-update-staff-role-change-detaches-core-no-reattach.md |
| F-0060 | staff-management | data-integrity | P2 | likely | open | findings/F-0060-create-staff-non-project-roles-orphan-no-transaction.md |
| F-0061 | sklad-pages-roles | correctness | P1 | confirmed | open | findings/F-0061-core-role-not-mapped-to-sklad-pages.md |
| F-0062 | sklad-pages-roles | correctness | P2 | confirmed | open | findings/F-0062-sklad-effective-role-no-fallback-dead-getrolecode.md |
| F-0063 | sklad-pages-roles | correctness | P2 | confirmed | open | findings/F-0063-sklad-global-vs-membership-role-admin-shortcut.md |
| F-0064 | sklad-pages-roles | data-integrity | P3 | confirmed | open | findings/F-0064-sklad-roles-endpoint-static-4-codes.md |
| F-0065 | role-pages-permissions | data-integrity | P2 | confirmed | open | findings/F-0065-rusaifin-role-pages-unseeded-baseline.md |
| F-0066 | role-pages-permissions | correctness | P3 | confirmed | open | findings/F-0066-rusaifin-missing-role-id-not-guarded.md |
| F-0067 | role-pages-permissions | correctness | P3 | confirmed | open | findings/F-0067-rusaifin-admin-pages-data-driven-not-bypassed.md |
| F-0068 | project-switch | data-integrity | P2 | confirmed | open | findings/F-0068-sklad-accessible-projects-stale-cache-dead-invalidation.md |
| F-0069 | project-switch | data-integrity | P3 | confirmed | open | findings/F-0069-current-project-no-cross-service-sync.md |
| F-0070 | user-profile-me | correctness | P2 | confirmed | open | findings/F-0070-sklad-me-role-resolver-diverges-from-authz.md |
| F-0071 | user-profile-me | architecture-drift | P2 | confirmed | open | findings/F-0071-sklad-getrolecode-reads-legacy-local-memberships.md |
| F-0072 | user-profile-me | correctness | P3 | confirmed | open | findings/F-0072-rusaifin-me-global-role-vs-core-membership-roles.md |
| F-0073 | user-profile-me | correctness | P3 | confirmed | open | findings/F-0073-sklad-me-route-missing-not-disabled.md |
| F-0074 | product-consent | correctness | P1 | confirmed | closed | findings/F-0074-consent-sms-limit-reset-unbounded-bombing.md |
| F-0075 | product-consent | correctness | P2 | confirmed | open | findings/F-0075-consent-prefill-pii-oracle-no-state-guard.md |
| F-0076 | product-consent | data-integrity | P2 | confirmed | open | findings/F-0076-consent-complete-duplicate-no-transaction.md |
| F-0077 | products-catalog | correctness | P1 | confirmed | open | findings/F-0077-system-add-all-products-detaches-instead-of-attaches.md |
| F-0078 | products-catalog | correctness | P2 | confirmed | open | findings/F-0078-bulk-product-point-agents-fake-counts-nonatomic-core-loop.md |
| F-0079 | products-catalog | data-integrity | P3 | confirmed | open | findings/F-0079-delete-product-noop-returns-success-false-history.md |
| F-0080 | products-catalog | data-integrity | P2 | likely | open | findings/F-0080-product-category-delete-no-cascade-orphan-pivots.md |
| F-0081 | products-catalog | correctness | P3 | confirmed | open | findings/F-0081-system-product-to-point-attach-detach-nontransactional.md |
| F-0082 | shift-planning | correctness | P2 | confirmed | open | findings/F-0082-planned-shift-write-missing-object-level-authz.md |
| F-0083 | shift-planning | data-integrity | P2 | likely | open | findings/F-0083-shift-start-no-lock-duplicate-open-shifts.md |
| F-0084 | shift-planning | architecture-drift | P3 | likely | open | findings/F-0084-user-point-relation-residual-frozen-pivot-reader.md |
| F-0085 | sklad-projects-admin | data-integrity | P2 | confirmed | open | findings/F-0085-sklad-admin-user-create-orphan-no-core-mirror.md |
| F-0086 | sklad-projects-admin | data-integrity | P2 | confirmed | open | findings/F-0086-sklad-admin-user-delete-reverse-orphan-sync-resurrection.md |
| F-0087 | sklad-projects-admin | data-integrity | P3 | likely | open | findings/F-0087-sklad-external-user-id-editable-no-validation-mislink.md |
| F-0088 | core-crud | architecture-drift | P1 | confirmed | closed | findings/F-0088-core-write-routes-no-scope-authorization.md |
| F-0089 | core-crud | data-integrity | P2 | confirmed | open | findings/F-0089-core-idempotency-read-then-write-race-duplicate-employee.md |
| F-0090 | core-crud | data-integrity | P3 | confirmed | open | findings/F-0090-core-idempotency-key-global-not-client-scoped.md |
| F-0091 | sklad-sku-catalog | data-integrity | P1 | confirmed | open | findings/F-0091-sku-delete-from-project-orphans-inventory-balances.md |
| F-0092 | icontact-sync | data-integrity | P1 | likely | open | findings/F-0092-icontact-movement-snapshot-not-atomic-retry-double-post.md |
| F-0093 | icontact-sync | correctness | P2 | needs-verification | open | findings/F-0093-icontact-snapshot-vs-group-granularity-double-apply.md |
| F-0094 | icontact-sync | correctness | P2 | confirmed | open | findings/F-0094-icontact-process-catchall-kills-retry-stuck-run.md |
| F-0095 | chats | correctness | P0 | confirmed | closed | findings/F-0095-chat-idor-nonfunctional-constructor-guard.md |
| F-0096 | chats | data-integrity | P3 | likely | open | findings/F-0096-chat-add-users-no-validation-no-dedup.md |
| F-0097 | notifications-redirect | correctness | P2 | confirmed | open | findings/F-0097-redirect-history-no-auth-telemetry-leak.md |
| F-0098 | notifications-redirect | correctness | P3 | confirmed | open | findings/F-0098-redirect-to-limited-open-redirect.md |
| F-0099 | webhooks | data-integrity | P1 | confirmed | closed | findings/F-0099-webhook-clear-no-auth-destroys-shift-reports.md |
| F-0100 | webhooks | architecture-drift | P2 | confirmed | open | findings/F-0100-webhooks-secret-in-url-no-idempotency.md |
| F-0101 | results-reporting | correctness | P2 | confirmed | open | findings/F-0101-get-agent-result-missing-reporting-scope.md |
| F-0102 | results-reporting | correctness | P2 | confirmed | open | findings/F-0102-get-staff-shift-by-id-no-permission-gate.md |
| F-0103 | results-reporting | correctness | P3 | confirmed | open | findings/F-0103-get-agent-result-undefined-date-key-500.md |
| F-0104 | rusaifin-inventory-agent | data-integrity | P2 | confirmed | open | findings/F-0104-rusaifin-inventory-status-no-lock-no-transition-guard.md |
| F-0105 | rusaifin-inventory-agent | data-integrity | P3 | needs-verification | open | findings/F-0105-rusaifin-inventory-orphan-on-point-delete.md |
| F-0106 | requests-cards-magnit | correctness | P1 | confirmed | closed | findings/F-0106-delete-ruchnik-no-authz-idor.md |
| F-0107 | requests-cards-magnit | correctness | P2 | confirmed | open | findings/F-0107-create-ruchnik-arbitrary-user-id.md |
| F-0108 | requests-cards-magnit | data-integrity | P2 | confirmed | open | findings/F-0108-magnit-app-files-attached-to-wrong-request.md |
| F-0109 | requests-cards-magnit | data-integrity | P3 | likely | open | findings/F-0109-request-setfield-race-duplicate.md |
| F-0110 | motivation | data-integrity | P1 | confirmed | open | findings/F-0110-compensation-cyrillic-table-homoglyph-mismatch.md |
| F-0111 | motivation | correctness | P2 | likely | open | findings/F-0111-motivation-comment-not-null-vs-optional-validation.md |
| F-0112 | motivation | data-integrity | P3 | confirmed | open | findings/F-0112-compensation-bringfriend-missing-from-user-audit.md |
| F-0113 | tasks | correctness | P1 | confirmed | closed | findings/F-0113-task-update-delete-comment-no-ownership-authz.md |
| F-0114 | tasks | correctness | P3 | confirmed | open | findings/F-0114-task-listing-or-precedence-soft-delete-bypass.md |
| F-0115 | education | correctness | P2 | likely | open | findings/F-0115-education-section-docs-no-product-scope-idor.md |
| F-0116 | requests-cards-magnit | correctness | P1 | confirmed | open | findings/F-0116-delete-request-no-authz-idor.md |
| F-0117 | motivation | correctness | P2 | confirmed | open | findings/F-0117-motivation-list-no-zone-scope-leak.md |
| F-0118 | staff-visibility | correctness | P2 | confirmed | open | findings/F-0118-export-staff-registry-no-viewer-scope.md |
| F-0119 | requests-cards-magnit | correctness | P2 | confirmed | open | findings/F-0119-export-ruchnik-no-membership-scope.md |
| F-0120 | requests-cards-magnit | correctness | P3 | confirmed | open | findings/F-0120-search-card-get-product-global-idor-read.md |
| F-0121 | point-agent-binding | correctness | P3 | likely | open | findings/F-0121-product-point-agents-no-project-scope-authz.md |

## Сводка по severity
- P0: 1 (F-0095 — chat IDOR, конструктор-guard не работает; ФЛАГ ВЛАДЕЛЬЦУ 2026-06-09)
- P1: 25 (F-0001, F-0002, F-0007, F-0013, F-0014, F-0015, F-0020, F-0021, F-0031, F-0034, F-0035, F-0036, F-0042, F-0052, F-0061, F-0074, F-0077, F-0088, F-0091, F-0092, F-0099, F-0106, F-0110, F-0113, F-0116)
- P2: 61 (F-0003, F-0004, F-0008, F-0009, F-0010, F-0016, F-0017, F-0019, F-0022, F-0023, F-0026, F-0027, F-0028, F-0029, F-0030, F-0032, F-0033, F-0037, F-0038, F-0043, F-0045, F-0048, F-0049, F-0050, F-0053, F-0054, F-0055, F-0056, F-0057, F-0058, F-0059, F-0060, F-0062, F-0063, F-0065, F-0068, F-0070, F-0071, F-0075, F-0076, F-0078, F-0080, F-0082, F-0083, F-0085, F-0086, F-0089, F-0093, F-0094, F-0097, F-0100, F-0101, F-0102, F-0104, F-0107, F-0108, F-0111, F-0115, F-0117, F-0118, F-0119)
- P3: 34 (F-0005, F-0006, F-0011, F-0012, F-0018, F-0024, F-0025, F-0039, F-0040, F-0041, F-0044, F-0046, F-0047, F-0051, F-0064, F-0066, F-0067, F-0069, F-0072, F-0073, F-0079, F-0081, F-0084, F-0087, F-0090, F-0096, F-0098, F-0103, F-0105, F-0109, F-0112, F-0114, F-0120, F-0121)
- **ИТОГО: 121 находка (1 P0 + 25 P1 + 61 P2 + 34 P3) по 36 потокам (TIER 1-4 закрыты; +6 из аудита свитчера 2026-06-22)**

## Опровергнуто при верификации (не залогировано)
- «disabled-юзер аутентифицируется в rusaifin» — ОПРОВЕРГНУТО: все 237 `auth:oauth`-роутов несут `UserIsNotDisabled` (дефект валиден только для sklad → F-0026).
