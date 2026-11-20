# Requirements and traceability

Baseline: the supplied *Animal Shelter and Adoption Management System* proposal by Vivek Babariya, Jindagi Patel and Advait Sarang. IDs below preserve the proposal’s requirements and stories. UC IDs make the actor goals explicit for this increment.

“Implemented” means the supplied prototype contains the behavior and has automated SQLite evidence; it does not mean the team has accepted the story, reviewed authorship, tested all browsers or validated MySQL.

| Requirement | Behavior | Story | Use case | Tests |
|---|---|---|---|---|
| FR-01 | Register/login with adopter and staff access | US-01 | UC-01 Manage account access | T01–03, T07, T24–25 |
| FR-02 | Staff add, view and update animal profiles | US-02 | UC-02 Maintain animal profiles | T05, T20 |
| FR-03 | Search/filter available animal profiles | US-03, US-04 | UC-03 Find and inspect animals | T04, T20 |
| FR-04 | Registered adopter submits an eligible application, initially Pending | US-05 | UC-04 Submit adoption application | T06, T07, T13, T24–25 |
| FR-05 | Staff review and approve/reject applications | US-06 | UC-05 Review adoption application | T08–10, T18 |
| FR-06 | Track Available, Pending and Adopted animal states | US-07 | UC-05 Review adoption application; UC-08 Complete adoption | T08–13, T18 |
| FR-07 | Staff create/update medical records | US-08 | UC-06 Maintain medical records | T14 |
| FR-08 | Adopters/staff create, reschedule and cancel appointments with access rules | US-09 | UC-07 Manage meet-and-greet appointments | T07, T15–19 |
| FR-09 | Store completed adoption history with animal, adopter and date | US-10 | UC-08 Complete adoption | T11–12 |
| FR-10 | Adopters view their own application status | US-05, US-06 | UC-09 Track application status | T06–11, T20 |

| NFR | Baseline target | Current evidence |
|---|---|---|
| NFR-01 Usability | Find an animal detail page within four navigation actions | Direct list-to-profile route exists. Team must count actions in a browser. |
| NFR-02 Performance | Search/profile around two seconds under normal demo conditions | Not benchmarked. Measure browser navigation against a specified dataset and machine. |
| NFR-03 Security/privacy | Password hashes, sessions, roles, private adopter data | Hashing, CSRF, owner/staff guards and escaped output tested. No production security assessment. |
| NFR-04 Integrity | Validate fields, enforce relationships, provide clear errors | Invalid/stale requests, uniqueness, foreign keys and rollback tested on SQLite. |
| NFR-05 Compatibility | Responsive interface on current Chrome, Edge, Firefox and Safari | Responsive CSS implemented; real browser/device checks pending. |

## Clarifications for team and instructor review

- A submitted application does not reserve the animal. Approval reserves it and rejects other pending applications. Completion records the actual placement.
- Public registration always creates an adopter. Staff are provisioned from the local command line.
- SQLite is the quick-start and automated-test backend; MySQL remains the proposal’s target integration.
- A user may apply only once per animal. Reopening, reversal and return workflows require separate future requirements.
- Medical notes are visible only to staff. The public animal profile contains general care information.
- Appointment times use America/Chicago. Application/adoption/event timestamps use UTC.
- The proposal mentioned JavaScript; this increment uses normal HTML forms and server rendering without custom JavaScript. Bootstrap CSS is served locally by Bootstrap-Flask.
