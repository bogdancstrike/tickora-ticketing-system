Feature: Comments and review under self-assignment policy

  As of 2026-05-09 only the active assignee (and admins / beneficiary side)
  may write comments or change status. Bystander chiefs and sector members
  must self-assign first.

  Scenario: Active assignee posts a public update
    Given an in-progress ticket assigned to a sector member
    When the assignee posts a public comment "Working on it"
    Then the comment is stored with public visibility and a comment_created audit entry

  Scenario: Bystander chief is rejected from posting until they self-assign
    Given an in-progress ticket assigned to another sector member
    When the chief tries to post a public comment
    Then the comment is rejected with a permission_denied error
    And an access_denied audit entry exists

  Scenario: Distributor reviews a pending ticket and routes it to a sector
    Given a pending ticket awaiting distribution
    When a distributor reviews the ticket and routes it to sector s10
    Then the ticket is assigned to sector s10 with assigned_to_sector status
    And a sector-history entry exists for the routing

  Scenario: Beneficiary reads only public comments
    Given an in-progress ticket with one public and one private comment
    When the beneficiary lists the comments
    Then only the public comment is returned
